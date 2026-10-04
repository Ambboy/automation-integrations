"""Bounded Wiren Board Cloud HTTP, directly or through the owner's SSH host.

The same fixed worker runs in either location. Request values travel on stdin
only; they are never interpolated into a shell command or an error message.
"""
from __future__ import annotations

import json
import shlex
import subprocess


class TransportFailure(Exception):
    def __init__(self, code, status=None, retry_after=None):
        self.code, self.status, self.retry_after = code, status, retry_after
        super().__init__(code)


# This is trusted, static Python, shared by the local and SSH implementations.
# Keeping one worker avoids divergent validation or redirect handling remotely.
_REMOTE_SCRIPT = r'''
import datetime
import email.utils
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

ORIGIN = 'https://wirenboard.cloud/api/v1'
MAXIMUM = 2 * 1024 * 1024
MAX_INPUT = 65536
UUID = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
SERIAL = r'[A-Za-z0-9_-]{1,36}'

class WorkerFailure(Exception):
    def __init__(self, code, status=None, retry_after=None):
        self.code, self.status, self.retry_after = code, status, retry_after
        super().__init__(code)

def service_path(path):
    match = re.fullmatch('/controllers/' + SERIAL + r'/services/([1-9][0-9]{0,4})/', path)
    return bool(match and int(match.group(1)) <= 65535)

def controller_path(path):
    return bool(re.fullmatch('/controllers/' + SERIAL + '/', path))

def group_path(path):
    return bool(re.fullmatch('/groups/' + UUID + '/', path))

def documented_empty_response(method, path, status):
    if status == 204:
        return True
    # Only these POSTs document HTTP 200 with no response body.
    return status == 200 and method == 'POST' and (
        path == '/groups-detach-from-controllers/'
        or bool(re.fullmatch('/controllers/' + SERIAL + '/request-diagnostic/', path)))

def validate(request):
    if not isinstance(request, dict) or set(request) != {'method', 'path', 'headers', 'query', 'body'}:
        raise WorkerFailure('invalid_request')
    method, path = request['method'], request['path']
    allowed_query = set()
    if not isinstance(path, str):
        raise WorkerFailure('unsupported_endpoint')
    if method == 'GET':
        if path == '/controllers/':
            allowed_query = {'organization_id', 'search', 'serial_number', 'page', 'page_size'}
        elif path == '/groups/':
            allowed_query = {'organization_id'}
        elif path not in ('/users/me/', '/organizations/', '/controllers-count/') and not (
                re.fullmatch('/controllers/' + SERIAL + r'/(?:diagnostic/|last-metrics-time/|services/)?', path)
                or re.fullmatch('/groups/' + UUID + '/', path)):
            raise WorkerFailure('unsupported_endpoint')
        if request['body'] is not None:
            raise WorkerFailure('invalid_parameters')
    elif method == 'POST':
        body = request['body']
        if path == '/auth/token/refresh/':
            if not isinstance(body, dict) or set(body) != {'refresh'} or not isinstance(body['refresh'], str) or not 1 <= len(body['refresh']) <= 32768:
                raise WorkerFailure('invalid_parameters')
        elif re.fullmatch('/controllers/' + SERIAL + '/system-metrics/', path):
            if not isinstance(body, dict) or set(body) != {'name', 'start', 'stop'}:
                raise WorkerFailure('invalid_parameters')
            if body['name'] not in ('disk_free_data', 'disk_free_root', 'load15', 'mem_available'):
                raise WorkerFailure('invalid_parameters')
            if any(not isinstance(body[k], str) or not 1 <= len(body[k]) <= 64 or any(ord(c) < 32 for c in body[k]) for k in ('start', 'stop')):
                raise WorkerFailure('invalid_parameters')
        elif (path in ('/groups/', '/groups-detach-from-controllers/')
              or re.fullmatch('/groups/' + UUID + '/attach-controllers/', path)
              or re.fullmatch('/controllers/' + SERIAL + '/services/', path)):
            if not isinstance(body, dict):
                raise WorkerFailure('invalid_parameters')
        elif re.fullmatch('/controllers/' + SERIAL + r'/(?:request-diagnostic|tcp-tunnels/(?:ssh|http))/', path):
            if body is not None:
                raise WorkerFailure('invalid_parameters')
        else:
            raise WorkerFailure('unsupported_endpoint')
    elif method in ('PATCH', 'DELETE'):
        if not (controller_path(path) or group_path(path) or service_path(path)):
            raise WorkerFailure('unsupported_endpoint')
        if method == 'PATCH' and not isinstance(request['body'], dict):
            raise WorkerFailure('invalid_parameters')
        if method == 'DELETE' and request['body'] is not None:
            raise WorkerFailure('invalid_parameters')
    else:
        raise WorkerFailure('unsupported_endpoint')
    query = request['query']
    if not isinstance(query, dict) or set(query) - allowed_query:
        raise WorkerFailure('invalid_parameters')
    for key, value in query.items():
        if key in ('page', 'page_size'):
            if type(value) is not int or not 1 <= value <= (10000 if key == 'page' else 100):
                raise WorkerFailure('invalid_parameters')
        elif not isinstance(value, str) or not 1 <= len(value) <= 256 or any(ord(c) < 32 for c in value):
            raise WorkerFailure('invalid_parameters')
        elif key == 'organization_id' and not re.fullmatch(UUID, value):
            raise WorkerFailure('invalid_parameters')
        elif key == 'serial_number' and not re.fullmatch(SERIAL, value):
            raise WorkerFailure('invalid_parameters')
    headers = request['headers']
    if not isinstance(headers, dict):
        raise WorkerFailure('invalid_parameters')
    for key, value in headers.items():
        if not isinstance(key, str) or key.lower() not in ('authorization', 'accept', 'content-type'):
            raise WorkerFailure('invalid_parameters')
        if not isinstance(value, str) or not 1 <= len(value) <= 32768 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise WorkerFailure('invalid_parameters')
    if len({k.lower() for k in headers}) != len(headers):
        raise WorkerFailure('invalid_parameters')

def retry_after(value):
    if not isinstance(value, str) or len(value) > 128:
        return None
    try:
        if value.strip().isdigit():
            seconds = int(value.strip())
        else:
            when = email.utils.parsedate_to_datetime(value)
            if when.tzinfo is None:
                return None
            seconds = int((when - datetime.datetime.now(datetime.timezone.utc)).total_seconds())
        return max(0, min(seconds, 86400))
    except (TypeError, ValueError, OverflowError):
        return None

def http_failure(status, headers=None):
    code = {401: 'authentication_failed', 403: 'access_denied',
            404: 'resource_not_found', 429: 'rate_limited'}.get(status)
    if code is None:
        code = 'redirect_refused' if 300 <= status < 400 else 'provider_unavailable' if status >= 500 else 'provider_http_error'
    delay = retry_after(headers.get('Retry-After')) if status == 429 and headers else None
    return WorkerFailure(code, status, delay)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WorkerFailure('redirect_refused', code)

def reject_constant(value):
    raise ValueError()

def perform(request):
    validate(request)
    url = ORIGIN + request['path']
    if request['query']:
        url += '?' + urllib.parse.urlencode(request['query'])
    headers = {k.lower(): v for k, v in request['headers'].items()}
    headers['accept'] = 'application/json'
    data = None
    if request['body'] is not None:
        data = json.dumps(request['body'], ensure_ascii=False, allow_nan=False).encode('utf-8')
        headers['content-type'] = 'application/json; charset=utf-8'
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        req = urllib.request.Request(url, data=data, headers=headers, method=request['method'])
        with opener.open(req, timeout=25) as response:
            status = response.status
            if not 200 <= status < 300:
                raise http_failure(status, response.headers)
            raw = response.read(MAXIMUM + 1)
            if len(raw) > MAXIMUM:
                raise WorkerFailure('response_too_large')
            if not raw and documented_empty_response(request['method'], request['path'], status):
                return status, None
            try:
                result = json.loads(raw.decode('utf-8'), parse_constant=reject_constant)
            except (UnicodeError, ValueError, RecursionError):
                raise WorkerFailure('invalid_json') from None
            return status, result
    except WorkerFailure:
        raise
    except urllib.error.HTTPError as exc:
        error = http_failure(exc.code, exc.headers)
        exc.close()
        raise error from None
    except Exception:
        raise WorkerFailure('network_error') from None

def main():
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise WorkerFailure('invalid_request')
        request = json.loads(raw.decode('utf-8'), parse_constant=reject_constant)
        status, data = perform(request)
        output = json.dumps({'ok': True, 'status': status, 'data': data},
            ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(output) > MAXIMUM + 4096:
            raise WorkerFailure('response_too_large')
    except WorkerFailure as exc:
        output = json.dumps({'ok': False, 'code': exc.code, 'status': exc.status,
            'retry_after': exc.retry_after}, separators=(',', ':')).encode('utf-8')
    except Exception:
        output = b'{"ok":false,"code":"network_error","status":null,"retry_after":null}'
    sys.stdout.buffer.write(output)

if __name__ == '__main__':
    main()
'''

_worker = {'__name__': __name__ + '._worker'}
exec(compile(_REMOTE_SCRIPT, '<wirenboard-http-worker>', 'exec'), _worker)
_MAX_OUTPUT = 2 * 1024 * 1024 + 4096
_ERROR_CODES = frozenset({
    'invalid_request', 'unsupported_endpoint', 'invalid_parameters',
    'authentication_failed', 'access_denied', 'resource_not_found', 'rate_limited',
    'provider_unavailable', 'provider_http_error', 'redirect_refused', 'network_error',
    'response_too_large', 'invalid_json',
})


def call(method, path, *, headers=None, query=None, body=None, config=None):
    config = config or {}
    transport = config.get('wirenboard_transport')
    if transport not in ('direct', 'ssh:example-hermes'):
        raise TransportFailure('wirenboard_transport_unconfigured')
    # Origin overrides are deliberately unsupported, even for the direct route.
    if any(config.get(key) not in (None, _worker['ORIGIN']) for key in
           ('wirenboard_base_url', 'wirenboard_api_url', 'wirenboard_origin')):
        raise TransportFailure('unsupported_origin')
    request = {'method': method, 'path': path, 'headers': headers if headers is not None else {},
               'query': query if query is not None else {}, 'body': body}
    try:
        _worker['validate'](request)
        payload = json.dumps(request, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(payload) > _worker['MAX_INPUT']:
            raise TransportFailure('invalid_request')
        if transport == 'direct':
            return _worker['perform'](request)[1]
    except _worker['WorkerFailure'] as exc:
        raise TransportFailure(exc.code, exc.status, exc.retry_after) from None
    except TransportFailure:
        raise
    except Exception:
        raise TransportFailure('invalid_request') from None

    # SSH joins the remote arguments into a shell command. Quote the constant
    # Python source; neither credentials nor request values occur in argv.
    argv = ['/usr/bin/ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
            'example-hermes', 'python3', '-c', shlex.quote(_REMOTE_SCRIPT)]
    try:
        response = subprocess.run(argv, input=payload, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, timeout=40, check=False)
        if response.returncode:
            raise TransportFailure('wirenboard_ssh_request_failed')
        raw = response.stdout
        if not isinstance(raw, bytes) or len(raw) > _MAX_OUTPUT:
            raise TransportFailure('response_too_large')
        result = json.loads(raw.decode('utf-8'), parse_constant=_worker['reject_constant'])
        if not isinstance(result, dict):
            raise ValueError()
        status, delay = result.get('status'), result.get('retry_after')
        if status is not None and (type(status) is not int or not 100 <= status <= 599):
            raise ValueError()
        if delay is not None and (type(delay) is not int or not 0 <= delay <= 86400):
            raise ValueError()
        if result.get('ok') is True and set(result) == {'ok', 'status', 'data'} and status is not None and 200 <= status < 300:
            return result['data']
        if result.get('ok') is False and set(result) == {'ok', 'status', 'code', 'retry_after'} and result.get('code') in _ERROR_CODES:
            raise TransportFailure(result['code'], status, delay)
        raise ValueError()
    except TransportFailure:
        raise
    except Exception:
        raise TransportFailure('wirenboard_ssh_request_failed') from None
