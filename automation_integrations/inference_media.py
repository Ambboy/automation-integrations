"""Reviewed inference.sh API contracts and an injectable, credential-safe client.

Discovery is live: apps and their schemas are never constrained to a static model
list. Only released method/path/request contracts can be executed. This module
makes one submission attempt; durable jobs, spend guards and reconciliation live
in media_service. No credentials are read from environment or disk here.
"""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit

try:
    from .openapi_contract import validate_schema
    from .media_runtime import MediaError, MediaHTTP, sanitize, _url
except ImportError:
    from openapi_contract import validate_schema
    from media_runtime import MediaError, MediaHTTP, sanitize, _url

BASE_URL = 'https://api.inference.sh'
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
MAX_REQUEST_BYTES = 2 * 1024 * 1024
TASK_STATUS = {1: 'received', 2: 'queued', 3: 'dispatched', 4: 'preparing',
               5: 'serving', 6: 'setting_up', 7: 'running', 8: 'cancelling',
               9: 'uploading', 10: 'completed', 11: 'failed', 12: 'cancelled'}
TERMINAL_TASK_STATUSES = frozenset({10, 11, 12})
FLOW_RUN_STATUS = {0: 'unknown', 1: 'pending', 2: 'running', 3: 'completed',
                   4: 'failed', 5: 'cancelled'}


def _load_contract():
    root = Path(__file__).resolve().parent
    for path in (root / 'contracts/inference.json',
                 root.parent / 'registry/contracts/inference.json'):
        if path.is_file():
            value = json.loads(path.read_text(encoding='utf-8'))
            if (value.get('schema_version') != 1 or value.get('service') != 'inference'
                    or value.get('base_url') != BASE_URL):
                raise ValueError('invalid_inference_contract')
            return value
    raise ValueError('inference_contract_unavailable')


_CONTRACT = _load_contract()
_SPECIAL_SCHEMAS = {
    'file_upload': {'type': 'object', 'properties': {
        'content_base64': {'type': 'string', 'minLength': 1, 'maxLength': 131072},
        'filename': {'type': 'string', 'minLength': 1, 'maxLength': 255},
        'content_type': {'type': 'string', 'minLength': 1, 'maxLength': 127}},
        'required': ['content_base64', 'filename', 'content_type'],
        'additionalProperties': False}}
OPERATION_SCHEMAS = {name: deepcopy(row['parameters']) for name, row in _CONTRACT['operations'].items()}
OPERATION_SCHEMAS.update(deepcopy(_SPECIAL_SCHEMAS))
OPERATIONS = {name: tuple(schema.get('properties', {})) for name, schema in OPERATION_SCHEMAS.items()}
WRITE_OPERATIONS = frozenset(name for name, row in _CONTRACT['operations'].items()
                             if row['effect'] != 'read') | {'file_upload'}
GENERATION_OPERATIONS = frozenset(name for name, row in _CONTRACT['operations'].items()
                                  if row['effect'] == 'generation')


def operation_contract(operation):
    """Return an isolated copy for catalog inspection, never a mutable authority."""
    if operation not in _CONTRACT['operations']:
        if operation == 'file_upload':
            return {'effect': 'write', 'category': 'files', 'parameters': deepcopy(_SPECIAL_SCHEMAS[operation]),
                    'required_scopes': ['files:write'], 'method': 'POST', 'path': '/files',
                    'source': 'https://inference.sh/docs/api/rest/files',
                    'description': 'Create file then upload bytes to the provider-issued signed URL.'}
        raise ValueError('unknown_operation')
    return deepcopy(_CONTRACT['operations'][operation])


def _upload_metadata(filename, content_type):
    if (not isinstance(filename, str) or not 1 <= len(filename) <= 255
            or any(ord(c) < 32 for c in filename) or '/' in filename or '\\' in filename
            or filename in ('.', '..')):
        raise ValueError('invalid_filename')
    if (not isinstance(content_type, str)
            or not re.fullmatch(r'[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+', content_type)
            or len(content_type) > 127):
        raise ValueError('invalid_content_type')


def validate(operation, params):
    """Validate before credentials or network are touched; errors contain no inputs."""
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise ValueError('unknown_operation')
    schema = (_SPECIAL_SCHEMAS[operation] if operation in _SPECIAL_SCHEMAS
              else _CONTRACT['operations'][operation]['parameters'])
    validate_schema(params, schema)
    try:
        size = len(json.dumps(params, ensure_ascii=False, allow_nan=False).encode())
    except (ValueError, TypeError, UnicodeError):
        raise ValueError('invalid_parameters') from None
    if size > MAX_REQUEST_BYTES:
        raise ValueError('request_too_large')
    values = deepcopy(params)
    if operation in ('app_run', 'app_run_alias'):
        # Native task execution must return the durable provider ID immediately.
        values['wait'] = False
        if 'session_timeout' in values and values.get('session') != 'new':
            raise ValueError('session_timeout_requires_new_session')
        if values.get('webhook'):
            parsed = urlsplit(values['webhook'])
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('invalid_webhook_url')
    if operation in ('agent_run', 'agent_message'):
        choices = ('chat_id', 'agent', 'agent_config') if operation == 'agent_run' else ('chat_id', 'agent_id', 'agent_config')
        if not any(values.get(k) for k in choices):
            raise ValueError('agent_or_chat_required')
        values['stream'] = False
    if operation in ('chat_completion', 'app_chat_completion', 'agent_chat_completion'):
        if 'tools' in values and 'functions' in values:
            raise ValueError('mutually_exclusive_tools_functions')
        values['stream'] = False
    if operation == 'trigger_create':
        target = {'run_agent': 'agent_id', 'run_app': 'app_id', 'run_flow': 'flow_id',
                  'resolve_interrupt': 'interrupt_id'}[values['action']]
        if not values.get(target):
            raise ValueError('trigger_target_required')
        if values['type'] == 'cron' and not values.get('config', {}).get('expression'):
            raise ValueError('cron_expression_required')
        if values['type'] == 'scheduled' and not values.get('scheduled_at'):
            raise ValueError('scheduled_at_required')
    if operation == 'file_upload':
        _upload_metadata(values['filename'], values['content_type'])
        try:
            raw = base64.b64decode(values['content_base64'], validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('invalid_base64') from None
        if not raw or len(raw) > MAX_UPLOAD_BYTES:
            raise ValueError('file_size_out_of_range')
    # Safe substitutions: a path value can never insert a new path segment.
    row = _CONTRACT['operations'].get(operation, {})
    for name in row.get('path_parameters', []):
        value = values[name]
        if value in ('.', '..') or any(c in value for c in '/\\%?#'):
            raise ValueError('invalid_path_parameter')
    return values


def _credentials(credentials):
    if not isinstance(credentials, dict):
        raise MediaError('credential_field_missing')
    token = credentials.get('INFSH_API_KEY') or credentials.get('INFERENCE_API_KEY')
    if (not isinstance(token, str) or not token or len(token) > 4096
            or any(ord(c) < 33 or ord(c) > 126 for c in token)):
        raise MediaError('credential_field_missing')
    return token


def _query_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if type(value) is bool:
        return 'true' if value else 'false'
    return value


def build_request(operation, params):
    """Build a fixed-host request without credentials, useful for review/tests."""
    values = validate(operation, params)
    if operation == 'file_upload':
        raise ValueError('multi_step_upload_operation')
    row = _CONTRACT['operations'][operation]
    path = row['path']
    for name in row['path_parameters']:
        path = path.replace('{' + name + '}', quote(values.pop(name), safe=''))
    if not path.startswith('/') or path.startswith('//') or '{' in path:
        raise ValueError('invalid_contract_path')
    query = {key: _query_value(values.pop(key)) for key in row['query_parameters'] if key in values}
    body = None if row['method'] == 'GET' or not values else values
    if row.get('body_parameter'):
        body = values.get(row['body_parameter'], {})
    if row['method'] in ('POST', 'PUT', 'PATCH') and body is None:
        body = {}
    return {'method': row['method'], 'url': BASE_URL + path, 'query': query or None,
            'body': body, 'response_kind': row.get('response_kind', 'json')}


def _unwrap(response, *, raw=False):
    if not isinstance(response, (dict, list)):
        raise MediaError('invalid_provider_response')
    if isinstance(response, dict):
        # Also fail safely with test transports that return problem details.
        if isinstance(response.get('status'), int) and response['status'] >= 400 and 'type' in response:
            raise MediaError('provider_http_error', response['status'])
        if response.get('error') and isinstance(response['error'], (dict, bool)):
            raise MediaError('provider_operation_failed')
        if not raw and 'data' in response and set(response) <= {'data', 'messages', 'success'}:
            return response['data']
    return response


def _response_sanitize(value, token):
    """Preserve JSON Schema field names; redact credential values everywhere.

    Model input schemas can legitimately define properties named `api_key` or
    `password`. Those property definitions are data needed for tool discovery,
    not live credentials. Detect schema nodes before recursive key redaction.
    """
    secret_names = {'authorization', 'proxy-authorization', 'password', 'secret',
                    'client_secret', 'api_key', 'apikey', 'access_token',
                    'refresh_token', 'fal_key', 'inference_api_key', 'infsh_api_key'}
    def walk(item, schema=False):
        if isinstance(item, dict):
            schema = schema or ('properties' in item and item.get('type') in ('object', None)
                                and isinstance(item['properties'], dict)) or '$schema' in item
            return {key: '[redacted]' if not schema and str(key).casefold() in secret_names
                    else walk(child, schema) for key, child in item.items()}
        if isinstance(item, list):
            return [walk(child, schema) for child in item]
        if isinstance(item, str):
            return item.replace(token, '[redacted]')
        return item
    return walk(value)


def execute(operation, params, credentials, *, transport=None):
    """Execute once. Timeouts propagate; callers must reconcile before resubmission."""
    params = validate(operation, params)
    token = _credentials(credentials)
    if operation == 'file_upload':
        return upload_file(base64.b64decode(params['content_base64'], validate=True),
                           params['filename'], params['content_type'], credentials, transport=transport)
    request = build_request(operation, params)
    row = _CONTRACT['operations'][operation]
    http = transport or MediaHTTP(allowed_hosts={'api.inference.sh'})
    headers = {'Accept': 'text/markdown, text/plain' if request['response_kind'] == 'text' else 'application/json'}
    if not row.get('public'):
        headers['Authorization'] = 'Bearer ' + token
    response = http.request(request['method'], request['url'], headers=headers,
                            query=request['query'], body=request['body'], timeout=30,
                            response_kind=request['response_kind'])
    if request['response_kind'] == 'text':
        if not isinstance(response, str):
            raise MediaError('invalid_provider_response')
        result = {'content': response, 'content_type': 'text/markdown' if operation != 'artifact_render' else 'text/plain'}
    else:
        result = _unwrap(response, raw=row.get('raw_response', False))
        if operation == 'mcp_tool_call' and isinstance(result, dict) and (result.get('error') or result.get('isError')):
            raise MediaError('provider_tool_failed')
    return _response_sanitize(result, token)


def upload_file(data, filename, content_type, credentials, *, transport=None):
    """Upload trusted caller-provided bytes; no local file paths are accepted here.

    The only upload destination comes from POST /files, is restricted to known
    provider storage domains, and receives no API key. A failed PUT is never
    retried automatically or reported as successful.
    """
    _upload_metadata(filename, content_type)
    if not isinstance(data, bytes) or not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError('file_size_out_of_range')
    token = _credentials(credentials)
    http = transport or MediaHTTP(allowed_hosts={'api.inference.sh'})
    result = http.request('POST', BASE_URL + '/files',
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'},
        body={'files': [{'uri': '', 'filename': filename, 'content_type': content_type,
                         'size': len(data)}]}, timeout=30, response_kind='json')
    rows = _unwrap(result)
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise MediaError('invalid_upload_response')
    row = rows[0]
    if not isinstance(row.get('uri'), str) or not row['uri'] or not row.get('upload_url'):
        raise MediaError('invalid_upload_response')
    _, host = _url(row['upload_url'], artifact=True)
    # With the default client the upload has a separate, exact host boundary.
    uploader = transport or MediaHTTP(allowed_hosts={host})
    uploader.request('PUT', row['upload_url'], headers={'Content-Type': content_type},
                     body=data, timeout=60, response_kind='text')
    return sanitize({key: value for key, value in row.items() if key != 'upload_url'}, [token])


def microcents_to_usd(value):
    if type(value) is not int:
        raise ValueError('invalid_microcents')
    return format(Decimal(value) / Decimal(100000000), '.8f')


def task_state(task):
    if not isinstance(task, dict) or type(task.get('status')) is not int:
        raise ValueError('invalid_task_state')
    return TASK_STATUS.get(task['status'], 'unknown')
