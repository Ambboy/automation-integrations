"""ABCP family HTTP adapter. Fixed reviewed operations, independent of Hermes.

The stdio boundary never returns credentials, authenticated URLs or tracebacks.
No transport request is retried, including POST reads and partially accepted writes.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

MAX_REQUEST = 2 * 1024 * 1024
MAX_RESPONSE = 32 * 1024 * 1024
SECRET_KEYS = {'userlogin', 'userpsw', 'sitehash', 'accesshash', 'sitelogin', 'sitepsw',
               'authorization', 'cookie', 'password', 'passwordnew', 'password_md5', 'api_key'}
RESERVED_KEYS = SECRET_KEYS - {'password', 'passwordnew'}


class AbcpError(Exception):
    def __init__(self, code, http_status=None, provider_code=None):
        self.code, self.http_status, self.provider_code = code, http_status, provider_code
        super().__init__(code)


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(obj, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def load_config(path):
    p = Path(path)
    if p.is_symlink() or p.stat().st_mode & 0o077:
        raise AbcpError('private_config_permissions_required')
    config = json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(config, dict) or not Path(config['state_dir']).is_absolute():
        raise AbcpError('invalid_config')
    return config


def _contract():
    path = Path(__file__).resolve().parent.parent / 'registry/contracts/abcp.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or not isinstance(data.get('operations'), dict):
        raise AbcpError('invalid_contract')
    return data


def operation(ident):
    if not isinstance(ident, str):
        raise AbcpError('unknown_operation')
    row = _contract()['operations'].get(ident)
    if row is None:
        raise AbcpError('unknown_operation')
    return row


def _schema(value, schema):
    """Validate the documented subset of JSON Schema, without guessed types."""
    if not schema:
        return
    for union in ('anyOf', 'oneOf'):
        if union in schema:
            valid = 0
            for variant in schema[union]:
                try:
                    _schema(value, variant)
                    valid += 1
                except AbcpError:
                    pass
            if valid == 0 or (union == 'oneOf' and valid != 1):
                raise AbcpError('invalid_parameter_type')
    kind = schema.get('type')
    matches = {'object': isinstance(value, dict), 'array': isinstance(value, list),
               'string': isinstance(value, str), 'integer': type(value) is int,
               'number': type(value) in (int, float), 'boolean': type(value) is bool,
               'null': value is None}
    if kind and not any(matches.get(k, False) for k in (kind if isinstance(kind, list) else [kind])):
        raise AbcpError('invalid_parameter_type')
    if 'enum' in schema and value not in schema['enum']:
        raise AbcpError('invalid_parameter_enum')
    if isinstance(value, dict):
        if any(key not in value for key in schema.get('required', [])):
            raise AbcpError('missing_required_parameter')
        props = schema.get('properties', {})
        if schema.get('additionalProperties') is False and set(value) - set(props):
            raise AbcpError('unknown_parameter')
        for key, item in value.items():
            _schema(item, props.get(key, schema.get('additionalProperties') if isinstance(schema.get('additionalProperties'), dict) else {}))
    elif isinstance(value, list):
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', 10000):
            raise AbcpError('invalid_array_length')
        for item in value:
            _schema(item, schema.get('items', {}))
    elif isinstance(value, str):
        if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', MAX_REQUEST):
            raise AbcpError('invalid_string_length')
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            raise AbcpError('invalid_parameter_format')
    elif type(value) in (int, float):
        if not math.isfinite(value) or value < schema.get('minimum', -math.inf) or value > schema.get('maximum', math.inf):
            raise AbcpError('invalid_parameter_range')


def _safe_params(value, depth=0):
    if depth > 18:
        raise AbcpError('parameters_too_deep')
    if isinstance(value, dict):
        for key, child in value.items():
            # Bracket notation is generated here, never accepted from a caller.
            if not isinstance(key, str) or not re.fullmatch(r'[\w.-]{1,120}', key, re.UNICODE):
                raise AbcpError('invalid_parameter_name')
            if key.casefold() in RESERVED_KEYS or key.casefold() in ('base_url', 'endpoint', 'host'):
                raise AbcpError('reserved_parameter')
            _safe_params(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _safe_params(child, depth + 1)
    elif isinstance(value, str):
        if '\x00' in value:
            raise AbcpError('invalid_parameter_value')
    elif value is not None and type(value) not in (int, float, bool):
        raise AbcpError('invalid_parameter_value')
    elif type(value) is float and not math.isfinite(value):
        raise AbcpError('invalid_parameter_value')


def validate(ident, params, *, write=False):
    row = operation(ident)
    if row.get('unsupported_reason'):
        raise AbcpError(row['unsupported_reason'])
    effect = row.get('effect')
    if write and effect not in ('business_write', 'write', 'report_generation'):
        raise AbcpError('read_tool_required')
    if not write and effect != 'read':
        raise AbcpError('write_tool_required')
    if not isinstance(params, dict):
        raise AbcpError('invalid_parameters')
    _safe_params(params)
    if len(json.dumps(params, ensure_ascii=False, allow_nan=False).encode()) > MAX_REQUEST:
        raise AbcpError('parameters_too_large')
    _schema(params, row.get('parameters', {}))
    path = row['path'].strip('/')
    for key in row.get('path_parameters', []):
        if key not in params or not re.fullmatch(r'[A-Za-z0-9_-]+', str(params[key])):
            raise AbcpError('invalid_path_parameter')
        path = path.replace('{' + key + '}', str(params[key]))
    if (not re.fullmatch(r'[A-Za-z0-9_/-]+', path) or '..' in path
            or row['method'] not in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH')):
        raise AbcpError('invalid_fixed_contract')
    return json.loads(json.dumps(params, ensure_ascii=False, allow_nan=False))


def credentials(config):
    p = Path(config['credentials_file'])
    if p.is_symlink() or p.stat().st_mode & 0o077:
        raise AbcpError('credential_permissions_required')
    values = {}
    for line in p.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, sep, val = line.partition('=')
        if not sep:
            raise AbcpError('invalid_credentials_file')
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def fingerprint(config):
    return hashlib.sha256(json.dumps(credentials(config), sort_keys=True).encode()).hexdigest()


def _auth(row, values):
    kind = row.get('auth', 'abcp')
    if kind == 'abcp':
        host = values.get('ABCP_API_HOST', '').removeprefix('https://').rstrip('/')
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.public\.api\.abcp\.ru', host, re.I):
            raise AbcpError('invalid_abcp_host')
        base = 'https://' + host
        auth = {'userlogin': values.get('ABCP_API_LOGIN'), 'userpsw': values.get('ABCP_API_PASSWORD_MD5')}
    elif kind == 'vinqu':
        base = 'https://publicapi.vinqu.com'
        auth = {'hash' if row['path'].strip('/') == 'brands/get' else 'siteHash': values.get('VINQU_SITE_HASH'),
                'accessHash': values.get('VINQU_ACCESS_HASH')}
    elif kind == 'carcare':
        base = 'https://car-care.abcp.ru'
        auth = {'sitelogin': values.get('CARCARE_SITE_LOGIN'), 'sitepsw': values.get('CARCARE_SITE_PASSWORD_MD5')}
    else:
        raise AbcpError('unknown_auth_family')
    if not all(isinstance(x, str) and x for x in auth.values()):
        raise AbcpError('credentials_not_configured_' + kind)
    return base, auth


def form_pairs(params, prefix=''):
    pairs = []
    iterable = params.items() if isinstance(params, dict) else enumerate(params)
    for key, value in iterable:
        name = f'{prefix}[{key}]' if prefix else str(key)
        if isinstance(value, (dict, list)):
            pairs.extend(form_pairs(value, name))
        elif value is not None:
            pairs.append((name, '1' if value is True else '0' if value is False else str(value)))
    return pairs


def _multipart(params, file_fields):
    boundary = 'abcp-' + uuid.uuid4().hex
    chunks = []
    for key, value in params.items():
        if key in file_fields:
            if not isinstance(value, dict) or set(value) - {'filename', 'content_base64', 'content_type'}:
                raise AbcpError('invalid_upload')
            filename = value.get('filename', '')
            media = value.get('content_type', 'application/octet-stream')
            if not re.fullmatch(r'[\w .-]{1,160}', filename) or not re.fullmatch(r'[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+', media):
                raise AbcpError('invalid_upload_metadata')
            try:
                content = base64.b64decode(value['content_base64'], validate=True)
            except (KeyError, ValueError):
                raise AbcpError('invalid_upload_base64') from None
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; filename="{filename}"\r\nContent-Type: {media}\r\n\r\n'.encode() + content + b'\r\n')
        else:
            for name, text in form_pairs({key: value}):
                chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{text}\r\n'.encode())
    chunks.append(f'--{boundary}--\r\n'.encode())
    return b''.join(chunks), 'multipart/form-data; boundary=' + boundary


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def sanitize(value, secrets=()):
    if isinstance(value, dict):
        return {key: '[redacted]' if str(key).casefold() in SECRET_KEYS else sanitize(child, secrets)
                for key, child in value.items()}
    if isinstance(value, list):
        return [sanitize(child, secrets) for child in value]
    if isinstance(value, str):
        for secret in secrets:
            if not secret:
                continue
            for representation in {secret, urllib.parse.quote(secret, safe=''), urllib.parse.quote_plus(secret)}:
                value = value.replace(representation, '[redacted]')
        value = re.sub(r'(?i)((?:userpsw|userlogin|accesshash|sitehash|sitelogin|sitepsw)=)[^&\s"<>]+', r'\1[redacted]', value)
    return value


def _business(data, write):
    if isinstance(data, list) and write:
        states = [_business(item, True) for item in data]
        if 'partial' in states or ('provider_rejected' in states and 'accepted_unverified' in states):
            return 'partial'
        if states and all(state == 'provider_rejected' for state in states):
            return 'provider_rejected'
        return 'accepted_unverified'
    if not isinstance(data, dict):
        return 'accepted_unverified' if write else 'read'
    error = data.get('errorCode') not in (None, 0, '0', '')
    error = error or data.get('success') in (False, 'false')
    if write:
        error = error or data.get('status') in (0, '0', False, 'error', 'Error')
    error = error or bool(data.get('errorMessage')) or bool(data.get('error')) or bool(data.get('Error'))
    if error:
        if any(data.get(key) for key in ('orders', 'orderIds', 'successOrders', 'created')):
            return 'partial'
        return 'provider_rejected'
    return 'accepted_unverified' if write else 'read'


def _result_dir(config):
    root = Path(config['state_dir']) / 'results'
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def bound_result(config, result):
    """Keep complete JSON locally and provide explicit pagination for large data."""
    if len(json.dumps(result, ensure_ascii=False).encode()) <= 48000:
        return result
    ident = str(uuid.uuid4())
    atomic_json(_result_dir(config) / (ident + '.json'), result)
    data = result.get('data')
    return {**{k: v for k, v in result.items() if k != 'data'}, 'data': None,
            'result_id': ident, 'stored_complete': True,
            'data_type': type(data).__name__, 'data_count': len(data) if isinstance(data, (list, dict)) else None,
            'instruction': 'Use result_page with result_id, json_pointer=/data, offset=0, limit=20. Follow next_offset; nested objects can be addressed using JSON Pointer.'}


def result_page(config, params):
    if set(params) - {'result_id', 'json_pointer', 'offset', 'limit'}:
        raise AbcpError('unknown_parameter')
    ident = params.get('result_id')
    try:
        if str(uuid.UUID(ident)) != ident:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise AbcpError('invalid_result_id') from None
    pointer = params.get('json_pointer', '/data')
    offset, limit = params.get('offset', 0), params.get('limit', 20)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise AbcpError('invalid_pagination')
    if not isinstance(pointer, str) or (pointer and not pointer.startswith('/')):
        raise AbcpError('invalid_json_pointer')
    p = _result_dir(config) / (ident + '.json')
    if not p.is_file() or p.is_symlink():
        raise AbcpError('result_not_found')
    value = json.loads(p.read_text())
    try:
        for token in pointer.split('/')[1:] if pointer else []:
            key = token.replace('~1', '/').replace('~0', '~')
            value = value[int(key)] if isinstance(value, list) else value[key]
    except (KeyError, TypeError, IndexError, ValueError):
        raise AbcpError('invalid_json_pointer') from None
    if isinstance(value, (list, dict)):
        selected = value[offset:offset + limit] if isinstance(value, list) else dict(list(value.items())[offset:offset + limit])
        while len(json.dumps(selected, ensure_ascii=False).encode()) > 40000 and limit > 1:
            limit = max(1, limit // 2)
            selected = value[offset:offset + limit] if isinstance(value, list) else dict(list(value.items())[offset:offset + limit])
        if len(json.dumps(selected, ensure_ascii=False).encode()) > 40000:
            return {'ok': True, 'result_id': ident, 'json_pointer': pointer, 'item_too_large': True,
                    'keys': list(selected) if isinstance(selected, dict) else [offset],
                    'instruction': 'Address the selected child using json_pointer to inspect its nested fields.'}
        return {'ok': True, 'data': selected, 'total': len(value), 'offset': offset,
                'next_offset': offset + limit if offset + limit < len(value) else None,
                'result_id': ident, 'json_pointer': pointer}
    if isinstance(value, str) and len(value) > 40000:
        start = offset
        return {'ok': True, 'data': value[start:start+40000], 'offset': start, 'unit': 'characters',
                'next_offset': start + 40000 if start + 40000 < len(value) else None}
    return {'ok': True, 'data': value, 'next_offset': None}


def execute(config, ident, params, *, write=False, opener=None):
    params = validate(ident, params, write=write)
    row = operation(ident)
    values = credentials(config)
    request_secrets = [str(params[key]) for key in row.get('sensitive_fields', []) if key in params]
    def gather_secrets(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key.casefold() in SECRET_KEYS and isinstance(value, str):
                    request_secrets.append(value)
                else:
                    gather_secrets(value)
        elif isinstance(obj, list):
            for value in obj:
                gather_secrets(value)
    gather_secrets(params)
    base, auth = _auth(row, values)
    path = '/' + row['path'].lstrip('/')
    for key in row.get('path_parameters', []):
        path = path.replace('{' + key + '}', urllib.parse.quote(str(params.pop(key)), safe=''))
    for key, style in row.get('parameter_serialization', {}).items():
        if style == 'csv' and isinstance(params.get(key), list):
            if any(isinstance(value, (list, dict)) or ',' in str(value) for value in params[key]):
                raise AbcpError('invalid_csv_parameter')
            params[key] = ','.join(str(value) for value in params[key])
    url = base + path
    auth_location = row.get('auth_location', 'query' if row['method'] == 'GET' else 'body')
    if auth_location == 'none':
        auth = {}
    fields = {**params, **auth} if auth_location != 'query' or row['method'] == 'GET' else params
    if auth_location == 'query' and row['method'] != 'GET':
        url += '?' + urllib.parse.urlencode(form_pairs(auth))
    headers = {'Accept': 'application/json', 'User-Agent': 'Automation-ABCP/1.0'}
    body = None
    method = row['method']
    encoding = row.get('encoding', 'form')
    if method == 'GET':
        url += '?' + urllib.parse.urlencode(form_pairs(fields))
    elif encoding == 'json':
        # ABCP JSON methods still use the ordinary request authentication fields.
        body = json.dumps(fields, ensure_ascii=False, allow_nan=False).encode('utf-8')
        headers['Content-Type'] = 'application/json; charset=utf-8'
    elif encoding == 'multipart':
        body, headers['Content-Type'] = _multipart(fields, row.get('file_fields', []))
    else:
        body = urllib.parse.urlencode(form_pairs(fields)).encode('utf-8')
        headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=utf-8'
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    timeout = config.get('timeout_seconds', 45)
    if type(timeout) not in (float, int) or not 1 <= timeout <= 90:
        raise AbcpError('invalid_timeout')
    try:
        try:
            response = opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            status = response.status
            raw = response.read(MAX_RESPONSE + 1)
            content_type = response.headers.get('Content-Type', '')
        if 300 <= status < 400:
            raise AbcpError('redirect_refused', status)
        if (row.get('auth') == 'vinqu' and row['path'].strip('/') == 'vinquery/chatList' and status == 404
                and b'messages not found' in raw.lower()):
            return {'ok': True, 'data': [], 'business_status': 'read', 'http_status': 404,
                    'provider_called': True, 'note': 'Documented empty VINQU chat window; at most last 15 minutes.'}
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError, OSError):
        raise AbcpError('transport_outcome_unknown' if write else 'transport_unavailable') from None
    if len(raw) > MAX_RESPONSE:
        raise AbcpError('response_too_large_outcome_unknown' if write else 'response_too_large')
    try:
        data = None if not raw.strip() and row.get('response_kind') == 'empty_or_json' and status < 400 else json.loads(raw)
    except (ValueError, UnicodeError):
        if status >= 400:
            raise AbcpError('provider_http_error', status) from None
        if row.get('response_kind') in ('binary', 'file', 'binary_or_json', 'pdf_or_json'):
            if not raw or 'text/html' in content_type.lower():
                raise AbcpError('invalid_provider_response') from None
            root = _result_dir(config)
            ident_file = str(uuid.uuid4())
            filename = root / (ident_file + ('.pdf' if raw.startswith(b'%PDF-') else '.bin'))
            fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
            data = {'artifact_path': str(filename), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                    'content_type': content_type}
        else:
            raise AbcpError('invalid_provider_json_outcome_unknown' if write else 'invalid_provider_json') from None
    data = sanitize(data, [*values.values(), *request_secrets])
    business = _business(data, write)
    if write and row['path'].strip('/') == 'cp/orders/online' and isinstance(data, list):
        sent = [position.get('confirmSend') for order in data if isinstance(order, dict)
                for position in order.get('positions', []) if isinstance(position, dict)]
        if any(value is False or value == 0 for value in sent):
            business = 'partial' if any(value is True or value == 1 for value in sent) else 'outcome_unknown'
    if status >= 500 and business != 'partial':
        raise AbcpError('provider_http_outcome_unknown' if write else 'provider_http_error', status)
    if status >= 400 and business != 'partial':
        business = 'provider_rejected'
    result = {'ok': business != 'provider_rejected', 'operation': ident, 'data': data,
              'http_status': status, 'business_status': business, 'provider_called': True,
              'source': row.get('source'), 'mutation_verified': False if write else None}
    if business == 'provider_rejected':
        result['error'] = 'provider_business_error'
    if business == 'partial':
        result['warning'] = 'Some objects may have been created. Inspect returned IDs; never repeat the request.'
    receipt = {k: result.get(k) for k in ('ok', 'error', 'http_status', 'business_status')}
    receipt['checked_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    atomic_json(Path(config['state_dir']) / ('abcp.' + ident + '.json'), receipt)
    return result


def process(config, request):
    if not isinstance(request, dict) or set(request) - {'service', 'operation', 'params'} or request.get('service') != 'abcp':
        raise AbcpError('invalid_request')
    ident, params = request.get('operation'), request.get('params', {})
    if not isinstance(params, dict):
        raise AbcpError('invalid_parameters')
    if ident == 'result_page':
        return result_page(config, params)
    if ident == 'connection_status':
        if params:
            raise AbcpError('unknown_parameter')
        values = credentials(config)
        return {'ok': True, 'configured': {family: all(values.get(k) for k in keys) for family, keys in {
            'abcp': ('ABCP_API_HOST', 'ABCP_API_LOGIN', 'ABCP_API_PASSWORD_MD5'),
            'vinqu': ('VINQU_SITE_HASH', 'VINQU_ACCESS_HASH'),
            'carcare': ('CARCARE_SITE_LOGIN', 'CARCARE_SITE_PASSWORD_MD5')}.items()},
                'documented_operations': len(_contract()['operations']), 'provider_called': False}
    return bound_result(config, execute(config, ident, params))


def main():
    os.umask(0o077)
    try:
        config = load_config(sys.argv[1])
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise AbcpError('request_too_large')
        result = process(config, json.loads(raw))
    except AbcpError as exc:
        result = {'ok': False, 'error': exc.code, 'http_status': exc.http_status,
                  'provider_code': exc.provider_code, 'retry': 'No automatic retry; inspect operation and access.'}
    except Exception:
        result = {'ok': False, 'error': 'invalid_request_or_configuration'}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
