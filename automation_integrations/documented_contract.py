"""Reviewed fixed-endpoint contracts for providers that publish prose API docs.

No network or credential access occurs here. JSON fixtures carry provenance,
request schemas and explicit exclusions; arbitrary HTTP/RPC dispatch is absent.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import datetime as dt
from functools import lru_cache
import json
from pathlib import Path
import re

try:
    from .openapi_contract import validate_schema
except ImportError:
    from openapi_contract import validate_schema


YANDEX_IDEMPOTENT_WRITES = frozenset({
    'promocodes_create', 'vehicles_bulk_create', 'vehicles_bulk_update', 'vehicles_bulk_archive'})


@lru_cache(maxsize=2)
def _contract(service):
    if service not in ('yandex_go', 'saby'):
        raise ValueError('unknown_service')
    root = Path(__file__).resolve().parent
    for path in (root / 'contracts' / f'{service}.json', root.parent / 'registry' / 'contracts' / f'{service}.json'):
        if path.is_file():
            doc = json.loads(path.read_text(encoding='utf-8'))
            if doc.get('service') != service or doc.get('schema_version') != 1:
                raise ValueError('invalid_contract')
            return doc
    raise ValueError('contract_unavailable')


def operations(service):
    """Return isolated metadata so callers cannot mutate the trusted registry."""
    result = deepcopy(_contract(service)['operations'])
    for operation, row in result.items():
        row['params_schema'] = deepcopy(row['parameters'])
        if row['effect'] == 'write':
            row['effect'] = 'business_write'
        if service == 'yandex_go' and operation in YANDEX_IDEMPOTENT_WRITES:
            row['requires_idempotency_key'] = True
    return result


def _operation(service, operation):
    if not isinstance(operation, str):
        raise ValueError('unsupported_operation')
    found = _contract(service)['operations'].get(operation)
    if found is None:
        raise ValueError('unsupported_operation')
    return found


def _extra_checks(value, schema):
    if schema.get('x-coordinates'):
        if not -180 <= value[0] <= 180 or not -90 <= value[1] <= 90:
            raise ValueError('invalid_coordinate')
    if isinstance(value, str):
        if schema.get('x-russian-date'):
            formats = ('%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H.%M.%S') if schema['x-russian-date'] == 'datetime' else ('%d.%m.%Y',)
            if not any(_date_matches(value, fmt) for fmt in formats):
                raise ValueError('invalid_date')
        if 'x-integer-string-minimum' in schema and int(value) < schema['x-integer-string-minimum']:
            raise ValueError('invalid_pagination')
        if 'x-integer-string-maximum' in schema and int(value) > schema['x-integer-string-maximum']:
            raise ValueError('invalid_pagination')
        if schema.get('contentEncoding') == 'base64':
            try:
                base64.b64decode(value, validate=True)
            except (ValueError, UnicodeError):
                raise ValueError('invalid_base64') from None
    if isinstance(value, dict):
        for key, child in value.items():
            _extra_checks(child, schema.get('properties', {}).get(key, {}))
        if 'Ссылка' in value and 'ДвоичныеДанные' in value:
            raise ValueError('mutually_exclusive_file_sources')
    if isinstance(value, list):
        for child in value:
            _extra_checks(child, schema.get('items', {}))
    # Extra semantic constraints in the valid union branch still apply.
    for keyword in ('anyOf', 'oneOf'):
        for branch in schema.get(keyword, []):
            try:
                validate_schema(value, branch)
            except ValueError:
                continue
            _extra_checks(value, branch)
            break


def _date_matches(value, fmt):
    try:
        return dt.datetime.strptime(value, fmt).strftime(fmt) == value
    except ValueError:
        return False


def validate(service, operation, params):
    spec = _operation(service, operation)
    # Validate before copying/defaulting; hostile types and unknown method/URL
    # fields must not reach a credential reader or transport.
    validate_schema(params, spec['parameters'])
    if len(json.dumps(params, ensure_ascii=False).encode()) > 1024 * 1024:
        raise ValueError('parameters_too_large')
    result = deepcopy(params)
    result.setdefault('path', {})
    result.setdefault('query', {})
    if service == 'saby' and operation == 'service_stages_list':
        result['body']['Фильтр']['Блокировать'] = 'Нет'
    _extra_checks(result, spec['parameters'])
    if service == 'yandex_go':
        body = result.get('body', {})
        if operation == 'promocodes_create':
            if body.get('service', 'taxi') in ('taxi', 'fuel', 'cargo') and body['value'] > 5000:
                raise ValueError('invalid_promocode_value')
            end = dt.date.fromisoformat(body['active_until'])
            today = dt.datetime.now(dt.timezone.utc).date()
            start = dt.date.fromisoformat(body.get('active_from', today.isoformat()))
            if not today <= start <= end <= today + dt.timedelta(days=90):
                raise ValueError('invalid_promocode_dates')
        for bucket in (body, result['query']):
            for low, high in (('date_from', 'date_to'), ('since_datetime', 'till_datetime'), ('updated_at_from', 'updated_at_to')):
                if low in bucket and high in bucket:
                    try:
                        lower = dt.datetime.fromisoformat(bucket[low])
                        upper = dt.datetime.fromisoformat(bucket[high])
                        if lower > upper:
                            raise ValueError('invalid_date_range')
                    except (TypeError, ValueError):
                        raise ValueError('invalid_date_range') from None
    return result


def build(service, operation, params):
    params = validate(service, operation, params)
    spec = _operation(service, operation)
    body = params.get('body')
    if service == 'saby':
        body = {'jsonrpc': '2.0', 'id': 1, 'method': spec['rpc_method'], 'params': body}
    query = {key: str(value).lower() if isinstance(value, bool) else value
             for key, value in params['query'].items()}
    return {'method': spec['method'], 'path': spec['path'], 'query': query, 'body': body}
