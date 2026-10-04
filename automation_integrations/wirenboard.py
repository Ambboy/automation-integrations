"""Bounded Wiren Board Cloud reads and durable, serialized JWT rotation.

The cache is the source of truth once a refresh token has been used. A pending
refresh may have succeeded remotely, so it must never be retried blindly.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid


OPERATIONS = {
    'me': (),
    'organizations': (),
    'controllers': ('organization_id', 'search', 'serial_number', 'page', 'page_size'),
    'counters': (),
    'controller': ('serial_number',),
    'diagnostic': ('serial_number',),
    'metrics': ('serial_number', 'name', 'start', 'stop'),
    'groups': ('organization_id',),
    'group': ('id',),
    'last_metrics_time': ('serial_number',),
}
METRICS = ('disk_free_data', 'disk_free_root', 'load15', 'mem_available')
_REQUIRED = {
    'controller': ('serial_number',), 'diagnostic': ('serial_number',),
    'metrics': ('serial_number', 'name', 'start', 'stop'),
    'groups': ('organization_id',), 'group': ('id',),
    'last_metrics_time': ('serial_number',),
}
_ISO_DATE = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})')


def validate(operation, params):
    """Reject URLs, arbitrary methods and unsupported filters before secrets."""
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise ValueError('unknown_operation')
    if not isinstance(params, dict) or set(params) - set(OPERATIONS[operation]):
        raise ValueError('invalid_parameters')
    if not set(_REQUIRED.get(operation, ())) <= set(params):
        raise ValueError('missing_parameter')
    normalized = dict(params)
    for key, value in params.items():
        if key in ('page', 'page_size'):
            if type(value) is not int or not 1 <= value <= (10000 if key == 'page' else 100):
                raise ValueError('invalid_pagination')
            continue
        if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('invalid_parameter_value')
        if key in ('organization_id', 'id'):
            try:
                parsed = uuid.UUID(value)
                if str(parsed) != value.lower():
                    raise ValueError()
                normalized[key] = str(parsed)
            except ValueError:
                raise ValueError('invalid_identifier') from None
        elif key == 'serial_number':
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,36}', value):
                raise ValueError('invalid_serial_number')
            normalized[key] = value.upper()
        elif key == 'search' and len(value) > 256:
            raise ValueError('invalid_parameter_value')
        elif key == 'name' and value not in METRICS:
            raise ValueError('unsupported_metric')
    if operation == 'metrics':
        try:
            dates = []
            for key in ('start', 'stop'):
                if not _ISO_DATE.fullmatch(params[key]):
                    raise ValueError()
                value = dt.datetime.fromisoformat(params[key].replace('Z', '+00:00'))
                if value.utcoffset() is None:
                    raise ValueError()
                dates.append(value)
            if not dt.timedelta(0) < dates[1] - dates[0] <= dt.timedelta(hours=24):
                raise ValueError()
        except ValueError:
            raise ValueError('invalid_date_range_max_24_hours') from None
    return normalized


def _failure(code, status=None):
    # api_read imports this module both as a package and as a deployed script.
    try:
        from .api_read import Failure
    except ImportError:
        main = sys.modules.get('__main__')
        if Path(getattr(main, '__file__', '')).name == 'api_read.py' and hasattr(main, 'Failure'):
            Failure = main.Failure
        else:
            from api_read import Failure
    return Failure(code, status)


def _token(value):
    return isinstance(value, str) and 1 <= len(value) <= 16384 and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)


def _remember(vault, *values):
    for value in values:
        if _token(value) and value not in vault.sensitive:
            vault.sensitive.append(value)


def _write_cache(path, data):
    """Atomic replace plus directory fsync; both tokens always move together."""
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(data, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        raise _failure('session_cache_write_failed') from None
    finally:
        if temporary is not None:
            with contextlib.suppress(OSError):
                os.unlink(temporary)


def _load_cache(path, fingerprint, access, refresh):
    try:
        with path.open(encoding='utf-8') as source:
            row = json.load(source)
    except FileNotFoundError:
        row = None
    except (OSError, ValueError):
        raise _failure('session_cache_invalid_reauthentication_required') from None
    if row is not None:
        if not isinstance(row, dict) or row.get('version') != 1 or not isinstance(row.get('fingerprint'), str):
            raise _failure('session_cache_invalid_reauthentication_required')
        if row['fingerprint'] == fingerprint:
            if row.get('status') != 'ready':
                raise _failure('reauthentication_required')
            if any(row.get(k) is not None and not _token(row[k]) for k in ('access', 'refresh')):
                raise _failure('session_cache_invalid_reauthentication_required')
            if not row.get('access') and not row.get('refresh'):
                raise _failure('reauthentication_required')
            try:
                path.chmod(0o600)
            except OSError:
                raise _failure('session_cache_write_failed') from None
            return row
    # A changed Vault credential is an explicit new authentication seed.
    row = {'version': 1, 'fingerprint': fingerprint, 'status': 'ready',
           'access': access, 'refresh': refresh}
    _write_cache(path, row)
    return row


def _refresh(http, vault, path, row):
    if not row.get('refresh'):
        _write_cache(path, {**row, 'status': 'reauthentication_required', 'access': None})
        raise _failure('reauthentication_required')
    # Crash, timeout, invalid JSON or failed persistence after this point must
    # not send the old refresh token a second time on the next invocation.
    _write_cache(path, {**row, 'status': 'refresh_pending', 'access': None})
    try:
        response = http.call('POST', '/auth/token/refresh/', body={'refresh': row['refresh']})
    except Exception as exc:
        status = getattr(exc, 'status', None)
        code = 'reauthentication_required' if status in (401, 403) else 'refresh_outcome_unknown'
        raise _failure(code, status) from None
    if not isinstance(response, dict):
        raise _failure('reauthentication_required')
    access = response.get('access')
    refresh = response.get('refresh', row['refresh'])
    _remember(vault, access, refresh)
    valid = _token(access) and _token(refresh)
    updated = {**row, 'status': 'ready' if valid else 'reauthentication_required',
               'access': access if _token(access) else None,
               'refresh': refresh if _token(refresh) else None}
    # Preserve a rotated refresh even when the other response fields are bad.
    _write_cache(path, updated)
    if not valid:
        raise _failure('reauthentication_required')
    return updated


def _read(http, operation, params, access):
    headers = {'Authorization': 'Bearer ' + access}
    paths = {'me': '/users/me/', 'organizations': '/organizations/',
             'controllers': '/controllers/', 'counters': '/controllers-count/', 'groups': '/groups/'}
    if operation in paths:
        query = dict(params)
        if operation == 'controllers':
            query = {'page': 1, 'page_size': 20, **query}
        return http.call('GET', paths[operation], headers=headers, query=query)
    if operation == 'group':
        return http.call('GET', '/groups/' + params['id'] + '/', headers=headers)
    path = '/controllers/' + params['serial_number'] + '/'
    suffixes = {'controller': '', 'diagnostic': 'diagnostic/',
                'last_metrics_time': 'last-metrics-time/', 'metrics': 'system-metrics/'}
    path += suffixes[operation]
    if operation == 'metrics':
        return http.call('POST', path, headers=headers,
                         body={key: params[key] for key in ('name', 'start', 'stop')})
    return http.call('GET', path, headers=headers)


def _validate_response(operation, result):
    invalid = False
    if operation in ('organizations', 'groups', 'metrics'):
        invalid = not isinstance(result, list) or any(not isinstance(row, dict) for row in result)
    else:
        invalid = not isinstance(result, dict)
    if not invalid and operation == 'controllers':
        invalid = (type(result.get('count')) is not int or result['count'] < 0
                   or not isinstance(result.get('results'), list)
                   or any(not isinstance(row, dict) for row in result['results'])
                   or any(key not in result or result[key] is not None and not isinstance(result[key], str)
                          for key in ('next', 'previous')))
    if not invalid and operation == 'counters':
        invalid = any(type(result.get(key)) is not int or result[key] < 0 for key in ('count', 'countAgentNotOk'))
    if invalid:
        raise _failure('invalid_provider_response')
    return result


def pagination(result, params):
    """Expose usable page numbers without following or returning remote URLs."""
    page, size = params.get('page', 1), params.get('page_size', 20)
    more = result.get('next') is not None
    return {'page': page, 'page_size': size, 'count': result['count'],
            'returned': len(result['results']), 'has_more': more,
            'next_page': page + 1 if more and page < 10000 else None}


def result_state(operation, result):
    if operation == 'controllers':
        return 'empty' if not result['results'] else 'data'
    return 'empty' if isinstance(result, list) and not result else 'data'


@contextlib.contextmanager
def _locked_session(config, vault, http):
    state = Path(config['state_dir'])
    try:
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(state / 'wirenboard.lock', os.O_CREAT | os.O_WRONLY, 0o600)
    except OSError:
        raise _failure('session_cache_write_failed') from None
    with os.fdopen(fd, 'w') as lock:
        try:
            os.fchmod(lock.fileno(), 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
        except OSError:
            raise _failure('session_cache_write_failed') from None
        secret = vault.get('wirenboard')
        access, refresh = (secret.get('WBCLOUD_' + key + '_TOKEN') for key in ('ACCESS', 'REFRESH'))
        access = access or None
        refresh = refresh or None
        if any(value is not None and not _token(value) for value in (access, refresh)) or not (access or refresh):
            raise _failure('credential_field_missing')
        _remember(vault, access, refresh)
        fingerprint = hashlib.sha256(json.dumps([access, refresh], separators=(',', ':')).encode()).hexdigest()
        path = state / 'wirenboard-session.json'
        row = _load_cache(path, fingerprint, access, refresh)
        _remember(vault, row.get('access'), row.get('refresh'))
        yield path, row


@contextlib.contextmanager
def authorized_session(config, vault, http):
    """Validate access with a read, then expose one-shot authenticated calls.

    The caller owns mutation durability and verification. No mutation is retried,
    including after 401. This shares the read adapter's rotated-token cache.
    """
    with _locked_session(config, vault, http) as (path, row):
        refreshed = False
        if not row.get('access'):
            row = _refresh(http, vault, path, row)
            refreshed = True
        try:
            me = http.call('GET', '/users/me/', headers={'Authorization': 'Bearer ' + row['access']})
        except Exception as exc:
            if getattr(exc, 'status', None) != 401:
                raise
            if refreshed:
                _write_cache(path, {**row, 'status': 'reauthentication_required', 'access': None})
                raise _failure('reauthentication_required', 401) from None
            row = _refresh(http, vault, path, row)
            try:
                me = http.call('GET', '/users/me/', headers={'Authorization': 'Bearer ' + row['access']})
            except Exception as retry:
                if getattr(retry, 'status', None) == 401:
                    _write_cache(path, {**row, 'status': 'reauthentication_required', 'access': None})
                    raise _failure('reauthentication_required', 401) from None
                raise
        if not isinstance(me, dict) or not isinstance(me.get('id'), (str, int)):
            raise _failure('invalid_provider_response')

        def call(method, route, *, query=None, body=None):
            return http.call(method, route, headers={'Authorization': 'Bearer ' + row['access']},
                             query=query, body=body)
        call.user_id = str(me['id'])
        yield call


def execute(operation, params, config, vault, http):
    """Return one read response. No login/password or implicit write fallback."""
    try:
        params = validate(operation, params)
    except ValueError as exc:
        raise _failure(str(exc)) from None
    with _locked_session(config, vault, http) as (path, row):
        refreshed = False
        if not row.get('access'):
            row = _refresh(http, vault, path, row)
            refreshed = True
        try:
            result = _read(http, operation, params, row['access'])
        except Exception as exc:
            if getattr(exc, 'status', None) != 401:
                raise
            if refreshed:
                _write_cache(path, {**row, 'status': 'reauthentication_required', 'access': None})
                raise _failure('reauthentication_required', 401) from None
            row = _refresh(http, vault, path, row)
            try:
                result = _read(http, operation, params, row['access'])
            except Exception as retry:
                if getattr(retry, 'status', None) == 401:
                    _write_cache(path, {**row, 'status': 'reauthentication_required', 'access': None})
                    raise _failure('reauthentication_required', 401) from None
                raise
        return _validate_response(operation, result)
