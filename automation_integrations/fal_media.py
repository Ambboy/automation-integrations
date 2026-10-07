"""fal model and Platform API adapter, based on pinned official contracts.

All model IDs/input parameters remain dynamic. Credential lookup, confirmed
administration, generation budgets and durable jobs belong to the caller.
This module never retries mutations or accepts a caller-selected HTTP host.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit
import uuid

try:
    from .openapi_contract import validate_schema
except ImportError:
    from openapi_contract import validate_schema


class Error(Exception):
    def __init__(self, code, status=None, *, provider_code=None, retry_after=None):
        self.code, self.status = code, status
        self.provider_code, self.retry_after = provider_code, retry_after
        super().__init__(code)


def _load_contract():
    root = Path(__file__).resolve().parent
    for path in (root / 'contracts/fal.json', root.parent / 'registry/contracts/fal.json'):
        if path.exists():
            return json.loads(path.read_text())
    raise RuntimeError('fal_contract_missing')


DOCUMENTED = _load_contract()
PLATFORM_OPERATIONS = DOCUMENTED['operations']
ALIASES = {'models': 'get_models', 'pricing': 'get_pricing', 'estimate': 'estimate_pricing',
           'usage': 'get_usage', 'billing': 'get_account_billing', 'billing_events': 'get_billing_events',
           'requests': 'list_requests_by_endpoint', 'analytics': 'get_analytics'}
ENDPOINT = {'type': 'string', 'minLength': 3, 'maxLength': 512,
            'pattern': r'^[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)+$'}
IDENTIFIER = {'type': 'string', 'minLength': 1, 'maxLength': 200, 'pattern': r'^[A-Za-z0-9_-]+$'}
LIFECYCLE = {'type': 'object', 'properties': {
    'expiration_duration_seconds': {'type': 'number', 'exclusiveMinimum': 0},
    'initial_acl': {'type': 'object', 'properties': {
        'default': {'enum': ['allow', 'forbid', 'hide']},
        'rules': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'user': {'type': 'string', 'minLength': 1}, 'decision': {'enum': ['allow', 'forbid', 'hide']}},
            'required': ['user', 'decision'], 'additionalProperties': False}}}, 'additionalProperties': False}},
    'additionalProperties': False}
OPTIONS = {'type': 'object', 'additionalProperties': False, 'properties': {
    'webhook_url': {'type': 'string', 'format': 'uri', 'maxLength': 2048},
    'start_timeout': {'type': 'number', 'exclusiveMinimum': 0.1},
    'priority': {'enum': ['normal', 'low']},
    'hint': {'type': 'string', 'maxLength': 512},
    'lifecycle': LIFECYCLE, 'store_io': {'type': 'boolean'}, 'no_retry': {'type': 'boolean'},
    'disable_fallback': {'type': 'boolean'},
    'max_queue_length': {'type': 'integer', 'minimum': 0},
    'retry_config': {'type': 'object', 'additionalProperties': False, 'properties': {
        name: {'type': 'object', 'properties': {'retries': {'type': 'integer', 'minimum': 0}},
               'required': ['retries'], 'additionalProperties': False}
        for name in ('server_error', 'timeout', 'connection_error')}},
    'tags': {'type': 'object', 'maxProperties': 10, 'additionalProperties': {'type': 'string', 'maxLength': 256}},
}}


def _schema(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


OPERATION_SCHEMAS = {name: row['schema'] for name, row in PLATFORM_OPERATIONS.items()}
OPERATION_SCHEMAS.update({alias: OPERATION_SCHEMAS[name] for alias, name in ALIASES.items()})
OPERATION_SCHEMAS.update({
    'capabilities': _schema({}),
    'operation_schema': _schema({'operation': {'type': 'string'}}, ['operation']),
    'model_schema': _schema({'endpoint_id': ENDPOINT}, ['endpoint_id']),
    'model_documentation': _schema({'endpoint_id': ENDPOINT}, ['endpoint_id']),
    'upload': _schema({'data_base64': {'type': 'string', 'minLength': 1, 'maxLength': 12000000},
        'content_type': {'type': 'string', 'minLength': 1, 'maxLength': 255},
        'file_name': {'type': 'string', 'minLength': 1, 'maxLength': 255}, 'lifecycle': LIFECYCLE},
        ['data_base64', 'content_type', 'file_name']),
    'realtime': _schema({'endpoint_id': ENDPOINT}, ['endpoint_id']),
    'http_websocket': _schema({'endpoint_id': ENDPOINT}, ['endpoint_id']),
})
for _name in ('submit', 'run', 'stream'):
    OPERATION_SCHEMAS[_name] = _schema({'endpoint_id': ENDPOINT, 'input': {'type': 'object'},
        'options': OPTIONS}, ['endpoint_id', 'input'])
for _name in ('status', 'result', 'cancel', 'status_stream'):
    OPERATION_SCHEMAS[_name] = _schema({'endpoint_id': ENDPOINT, 'request_id': IDENTIFIER,
        'logs': {'type': 'boolean'}}, ['endpoint_id', 'request_id'])
OPERATIONS = {name: tuple(schema['properties']) for name, schema in OPERATION_SCHEMAS.items()}
GENERATION_OPERATIONS = frozenset({'submit', 'run', 'stream'})
WRITE_OPERATIONS = frozenset({name for name, row in PLATFORM_OPERATIONS.items() if row['effect'] != 'read'} |
                            set(GENERATION_OPERATIONS) | {'cancel', 'upload'})
UNSUPPORTED = {'realtime': 'persistent_websocket_transport_required',
               'http_websocket': 'persistent_websocket_transport_required',
               **{name: row['unsupported_reason'] for name, row in PLATFORM_OPERATIONS.items() if row.get('unsupported_reason')}}


def validate(operation, params):
    """Validate caller input before credentials are fetched. No arbitrary headers."""
    if operation not in OPERATION_SCHEMAS:
        raise ValueError('unknown_operation')
    if operation in UNSUPPORTED:
        raise ValueError(UNSUPPORTED[operation])
    validate_schema(params, OPERATION_SCHEMAS[operation])
    try:
        size = len(json.dumps(params, ensure_ascii=False, allow_nan=False).encode('utf-8'))
    except (ValueError, TypeError, UnicodeError):
        raise ValueError('invalid_parameters') from None
    if size > 16000000:
        raise ValueError('request_too_large')
    if 'endpoint_id' in params:
        value = params['endpoint_id']
        for endpoint in value if isinstance(value, list) else [value]:
            # Platform search allows comma-separated endpoint IDs as documented.
            if isinstance(endpoint, str) and any(c in endpoint for c in ('?', '#', '\\', '\r', '\n')):
                raise ValueError('invalid_endpoint_id')
    options = params.get('options', {})
    webhook = options.get('webhook_url')
    if webhook:
        parts = urlsplit(webhook)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.fragment:
            raise ValueError('invalid_webhook_url')
    for value in (options.get('hint', ''), *options.get('tags', {}).values()):
        _header_value(value)
    _tags_header(options.get('tags', {}))
    if operation in ('run', 'stream') and set(options) & {'webhook_url', 'priority', 'max_queue_length'}:
        raise ValueError('queue_options_require_submit')
    canonical = ALIASES.get(operation, operation)
    row = PLATFORM_OPERATIONS.get(canonical)
    if row:
        for param in row['parameters']:
            if param['in'] == 'path' and param['name'] in params:
                _path_value(params[param['name']], nested=param['name'] in ('dir', 'file', 'target_path'))
            elif param['in'] == 'header' and param['name'] in params:
                _header_value(params[param['name']])
    if operation == 'upload':
        _upload_data(params)
    if canonical == 'serverless_upload_local_file':
        _upload_data(params['body'])
    return deepcopy(params)


def _header_value(value):
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('invalid_header_value')
    return value


def _tags_header(tags):
    packed, size = {}, 0
    for raw_key, raw_value in tags.items():
        key, value = raw_key.strip().lower(), raw_value.strip()
        if (not re.fullmatch(r'[a-z0-9._-]{1,64}', key) or key.startswith('fal.') or
                any(ord(c) < 32 or ord(c) > 126 or c == ',' for c in value)):
            raise ValueError('invalid_request_tags')
        size += len(key) + len(value)
        if size > 1024:
            raise ValueError('invalid_request_tags')
        packed[key] = value
    return ','.join(key + '=' + value for key, value in packed.items())


def _path_value(value, *, nested=False):
    if (not isinstance(value, str) or not value or len(value) > 2048 or
            any(ord(c) < 32 for c in value) or any(c in value for c in '\\?#%') or
            any(part in ('.', '..', '') for part in value.split('/')) or
            (not nested and '/' in value)):
        raise ValueError('invalid_path_parameter')
    return quote(value, safe='/' if nested else '')


def _upload_data(params):
    name, content_type = params['file_name'], params['content_type']
    if any(c in name for c in '/\\"\r\n') or name in ('.', '..'):
        raise ValueError('invalid_file_name')
    _header_value(content_type)
    if not re.fullmatch(r'[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+', content_type):
        raise ValueError('invalid_content_type')
    try:
        data = base64.b64decode(params['data_base64'], validate=True)
    except (ValueError, TypeError):
        raise ValueError('invalid_base64') from None
    if not 0 < len(data) <= 8 * 1024 * 1024:
        raise ValueError('upload_size_limit_8_mib')
    return data


def queue_base(endpoint_id, request_id):
    """Match fal_client.AppId: owner/alias, or namespace/owner/alias."""
    validate_schema(endpoint_id, ENDPOINT)
    validate_schema(request_id, IDENTIFIER)
    parts = endpoint_id.split('/')
    count = 3 if parts[0] in ('workflows', 'comfy') else 2
    if len(parts) < count:
        raise ValueError('invalid_endpoint_id')
    return 'https://queue.fal.run/' + '/'.join(parts[:count]) + '/requests/' + request_id


def _options(params):
    options = params.get('options', {})
    headers, query = {}, {}
    for key, target in (('start_timeout', 'X-Fal-Request-Start-Timeout'), ('priority', 'X-Fal-Queue-Priority'),
                        ('hint', 'X-Fal-Runner-Hint')):
        if key in options:
            headers[target] = str(options[key])
    for key, target in (('lifecycle', 'X-Fal-Object-Lifecycle-Preference'), ('retry_config', 'X-Fal-Retry-Config')):
        if key in options:
            headers[target] = json.dumps(options[key], separators=(',', ':'))
    for key, target in (('store_io', 'X-Fal-Store-IO'), ('no_retry', 'X-Fal-No-Retry'),
                        ('disable_fallback', 'x-app-fal-disable-fallback')):
        if key in options:
            headers[target] = '1' if options[key] else '0'
    if 'tags' in options:
        headers['X-Fal-Tags'] = _tags_header(options['tags'])
    if 'webhook_url' in options:
        query['fal_webhook'] = options['webhook_url']
    if 'max_queue_length' in options:
        query['fal_max_queue_length'] = options['max_queue_length']
    return headers, query


def _capabilities():
    return {'provider': 'fal', 'platform_operations': len(PLATFORM_OPERATIONS),
        'model_scope': 'All discoverable model endpoints and own apps/workflows; inspect model_schema before inference.',
        'operations': {name: {'effect': 'generation' if name in GENERATION_OPERATIONS else
            'business_write' if name in WRITE_OPERATIONS else 'read',
            'unsupported_reason': UNSUPPORTED.get(name),
            'admin_required': PLATFORM_OPERATIONS.get(ALIASES.get(name, name), {}).get('admin_required', False)}
            for name in OPERATIONS},
        'limits': {'upload_bytes': 8 * 1024 * 1024, 'streaming': 'Bounded SSE collection, not a live duplex session',
            'webhooks': 'External HTTPS callback registration supported; no local receiving endpoint in this adapter',
            'deployment': 'Custom Python deployment, scale/revisions, secrets and runners beyond REST require fal SDK/CLI',
            'credentials': 'API-key creation needs a secure generated-credential sink and is not executed'}}


def _response(result, kind):
    if kind == 'binary':
        if not isinstance(result, bytes):
            raise Error('invalid_provider_binary')
        return {'content_type': 'application/octet-stream', 'data_base64': base64.b64encode(result).decode(), 'size_bytes': len(result)}
    if kind == 'text':
        if isinstance(result, bytes):
            result = result.decode('utf-8', errors='replace')
        return {'text': result}
    if kind == 'sse':
        if isinstance(result, bytes):
            result = result.decode('utf-8', errors='replace')
        if isinstance(result, str):
            events = []
            for block in result.replace('\r\n', '\n').split('\n\n'):
                data = '\n'.join(line[5:].lstrip(' ') for line in block.split('\n') if line.startswith('data:'))
                if not data or data == '[DONE]':
                    continue
                try:
                    events.append(json.loads(data))
                except ValueError:
                    events.append({'text': data})
            return {'events': events}
        return result
    return result


def _public_result(result):
    """Never expose newly returned key material, including nested key listings."""
    if isinstance(result, dict):
        return {key: '[REDACTED]' if key.lower() in ('key_secret', 'secret', 'token', 'api_key', 'authorization')
                else _public_result(value) for key, value in result.items()}
    if isinstance(result, list):
        return [_public_result(item) for item in result]
    return result


def execute(operation, params, credentials, *, transport=None):
    params = validate(operation, params)
    if operation == 'capabilities':
        return _capabilities()
    if operation == 'operation_schema':
        name = params['operation']
        if name not in OPERATION_SCHEMAS:
            raise ValueError('unknown_operation')
        return {'operation': name, 'schema': deepcopy(OPERATION_SCHEMAS[name]), 'unsupported_reason': UNSUPPORTED.get(name)}
    if transport is None:
        try:
            from .media_runtime import MediaHTTP
        except ImportError:
            from media_runtime import MediaHTTP
        transport = MediaHTTP()
    canonical = ALIASES.get(operation, operation)
    row = PLATFORM_OPERATIONS.get(canonical)
    key = credentials.get('FAL_ADMIN_KEY') if row and row['admin_required'] else None
    key = key or credentials.get('FAL_KEY')
    if not isinstance(key, str) or not key or any(c.isspace() for c in key):
        raise Error('credential_field_missing')
    headers = {'Authorization': 'Key ' + key}

    def request(method, url, *, query=None, body=None, extra_headers=None, kind='json', auth=True):
        # No provider response or caller option may select a host that receives secrets.
        allowed = {'api.fal.ai', 'queue.fal.run', 'fal.run', 'rest.fal.ai', 'rest.alpha.fal.ai'}
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.hostname not in allowed or parts.port not in (None, 443) or parts.username or parts.password:
            raise Error('untrusted_provider_url')
        result = transport.request(method, url, headers={**(headers if auth else {}), **(extra_headers or {})},
            query=query, body=body, timeout=30, response_kind=kind)
        parsed = _response(result, kind)
        # In OpenAPI, names such as "token" identify input/property schemas,
        # not a returned credential. Preserve the complete public contract.
        return parsed if operation == 'model_schema' or canonical == 'get_models' else _public_result(parsed)

    if row:
        path = row['path']
        query, extra_headers = {}, {}
        for param in row['parameters']:
            name = param['name']
            if name not in params:
                continue
            value = params[name]
            if param['in'] == 'path':
                path = path.replace('{' + name + '}', _path_value(value, nested=name in ('dir', 'file', 'target_path')))
            elif param['in'] == 'query':
                query[name] = value
            elif param['in'] == 'header':
                extra_headers[name] = _header_value(value)
        body = params.get('body')
        if row['body_type'] == 'multipart/form-data':
            boundary = 'fal-upload-' + uuid.uuid4().hex
            file = body
            data = _upload_data(file)
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file_upload"; filename="{file["file_name"]}"\r\n'
                    f'Content-Type: {file["content_type"]}\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
            extra_headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
        return request(row['method'], 'https://api.fal.ai' + path, query=query, body=body,
                       extra_headers=extra_headers, kind=row['response_kind'])
    if operation == 'model_schema':
        return request('GET', 'https://api.fal.ai/v1/models', query={'endpoint_id': params['endpoint_id'], 'expand': 'openapi-3.0'})
    if operation == 'model_documentation':
        # Public model documentation never receives an API key.
        result = transport.request('GET', 'https://fal.ai/models/' + params['endpoint_id'] + '/llms.txt',
                                   headers={}, response_kind='text', timeout=30)
        return _response(result, 'text')
    if operation in GENERATION_OPERATIONS:
        extra_headers, query = _options(params)
        url = ('https://queue.fal.run/' if operation == 'submit' else 'https://fal.run/') + params['endpoint_id']
        if operation == 'stream':
            url += '/stream'
        result = request('POST', url, query=query, body=params['input'], extra_headers=extra_headers,
                         kind='sse' if operation == 'stream' else 'json')
        if operation == 'submit':
            if not isinstance(result, dict) or not isinstance(result.get('request_id'), str):
                raise Error('missing_provider_request_id')
            validate_schema(result['request_id'], IDENTIFIER)
            result['endpoint_id'] = params['endpoint_id']
        return result
    if operation in ('status', 'result', 'cancel', 'status_stream'):
        base = queue_base(params['endpoint_id'], params['request_id'])
        suffix = {'status': '/status', 'result': '', 'cancel': '/cancel', 'status_stream': '/status/stream'}[operation]
        query = {'logs': '1' if params.get('logs') else '0'} if operation in ('status', 'status_stream') else None
        return request('PUT' if operation == 'cancel' else 'GET', base + suffix, query=query,
                       kind='sse' if operation == 'status_stream' else 'json')
    if operation == 'upload':
        data = _upload_data(params)
        extra_headers = {}
        if 'lifecycle' in params:
            extra_headers['X-Fal-Object-Lifecycle-Preference'] = json.dumps(params['lifecycle'], separators=(',', ':'))
        init = request('POST', 'https://rest.fal.ai/storage/upload/initiate', query={'storage_type': 'gcs'},
            body={'file_name': params['file_name'], 'content_type': params['content_type']}, extra_headers=extra_headers)
        if not isinstance(init, dict):
            raise Error('invalid_upload_response')
        upload_url, file_url = init.get('upload_url'), init.get('file_url')
        upload = urlsplit(upload_url if isinstance(upload_url, str) else '')
        file = urlsplit(file_url if isinstance(file_url, str) else '')
        if (upload.scheme != 'https' or upload.hostname != 'storage.googleapis.com' or upload.port not in (None, 443)
                or upload.username or upload.password or upload.fragment or file.scheme != 'https' or not file.hostname
                or not (file.hostname == 'fal.media' or file.hostname.endswith('.fal.media'))):
            raise Error('untrusted_upload_url')
        # Google signed upload requests must never inherit FAL_KEY.
        transport.request('PUT', upload_url, headers={'Content-Type': params['content_type']}, body=data,
                          timeout=30, response_kind='text')
        return {'url': file_url, 'content_type': params['content_type'], 'file_name': params['file_name'], 'size_bytes': len(data)}
    raise ValueError('unknown_operation')


def upload_file(data: bytes, filename, content_type, credentials, *, transport=None):
    """Upload trusted local bytes without sending base64 through a tool request.

    The caller selects and reads a permitted local file. This helper does not
    accept paths and shares the ordinary upload's validation and auth boundary.
    """
    if not isinstance(data, bytes):
        raise ValueError('invalid_file_bytes')
    if not 0 < len(data) <= 8 * 1024 * 1024:
        raise ValueError('upload_size_limit_8_mib')
    return execute('upload', {'data_base64': base64.b64encode(data).decode('ascii'),
                             'file_name': filename, 'content_type': content_type},
                   credentials, transport=transport)
