"""Vetted, offline ETM/Tochka OpenAPI request contracts.

No HTTP, credentials, remote references or provider URLs are accepted here. The
transport supplies authentication and gates all effects before using ``build``.
The checked-in JSON snapshots include provenance and explicit unsupported reasons.
Regenerate from previously downloaded official documents with::

    python -m automation_integrations.openapi_contract RESEARCH_DIR OUTPUT_DIR

Only regeneration needs PyYAML; runtime validation uses the standard library.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import quote, urlsplit
import uuid

SERVICES = ('etm', 'tochka')
_CREDENTIAL_KEYS = frozenset({'authorization', 'proxy-authorization', 'cookie',
    'session-id', 'session_id', 'log', 'pwd', 'password', 'jwt', 'access_token',
    'refresh_token', 'client_secret', 'api_key', 'apikey', 'x-api-key'})


def _invalid(code='invalid_parameters'):
    # Never include caller values, field names or schema examples in errors.
    raise ValueError(code)


def _json_value(value, depth=0):
    if depth > 64:
        _invalid()
    if value is None or type(value) in (bool, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _invalid()
    elif isinstance(value, str):
        if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            _invalid()
    elif isinstance(value, list):
        for item in value:
            _json_value(item, depth + 1)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _invalid()
            if key.lower() in _CREDENTIAL_KEYS:
                _invalid('credentials_not_allowed')
            _json_value(item, depth + 1)
    else:
        _invalid()


def _equal(a, b):
    if type(a) is bool or type(b) is bool:
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    return a == b


def validate_schema(value, schema, path='params', *, _depth=0):
    """Validate the supported JSON Schema/OpenAPI vocabulary without coercion.

    ``path`` is retained for callers' compatibility, never printed with input.
    Unresolved references fail closed. OpenAPI 3.0 nullable and boolean exclusive
    bounds and OpenAPI 3.1 numeric exclusive bounds are both supported.
    """
    if _depth == 0:
        _json_value(value)
    if _depth > 64 or schema is False:
        _invalid()
    if schema is True:
        return
    if not isinstance(schema, dict) or '$ref' in schema:
        _invalid('unsupported_schema')
    if value is None and schema.get('nullable'):
        return
    for key in ('allOf', 'anyOf', 'oneOf'):
        if key not in schema:
            continue
        hits = 0
        for branch in schema[key]:
            try:
                validate_schema(value, branch, path, _depth=_depth + 1)
                hits += 1
            except ValueError:
                pass
        if ((key == 'allOf' and hits != len(schema[key])) or
                (key == 'anyOf' and not hits) or (key == 'oneOf' and hits != 1)):
            _invalid()
    if 'not' in schema:
        try:
            validate_schema(value, schema['not'], path, _depth=_depth + 1)
        except ValueError:
            pass
        else:
            _invalid()
    if 'const' in schema and not _equal(value, schema['const']):
        _invalid()
    if 'enum' in schema and not any(_equal(value, x) for x in schema['enum']):
        _invalid()
    kinds = schema.get('type', [])
    if isinstance(kinds, str):
        kinds = [kinds]
    matches = {'null': value is None, 'boolean': type(value) is bool,
        'integer': type(value) is int, 'number': type(value) in (int, float),
        'string': isinstance(value, str), 'array': isinstance(value, list),
        'object': isinstance(value, dict)}
    if kinds and not any(matches.get(kind, False) for kind in kinds):
        _invalid()
    if isinstance(value, dict):
        props = schema.get('properties', {})
        if set(schema.get('required', [])) - value.keys():
            _invalid('missing_parameter')
        if not schema.get('minProperties', 0) <= len(value) <= schema.get('maxProperties', math.inf):
            _invalid()
        additional = schema.get('additionalProperties', True)
        patterns = schema.get('patternProperties', {})
        for key, item in value.items():
            matched = False
            if key in props:
                validate_schema(item, props[key], path, _depth=_depth + 1)
                matched = True
            for pattern, subschema in patterns.items():
                if re.search(pattern, key):
                    validate_schema(item, subschema, path, _depth=_depth + 1)
                    matched = True
            if not matched:
                validate_schema(item, additional, path, _depth=_depth + 1)
        for key, required in schema.get('dependentRequired', {}).items():
            if key in value and set(required) - value.keys():
                _invalid()
    elif isinstance(value, list):
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', math.inf):
            _invalid()
        if schema.get('uniqueItems'):
            if any(_equal(item, prev) for i, item in enumerate(value) for prev in value[:i]):
                _invalid()
        prefix = schema.get('prefixItems', [])
        for index, item in enumerate(value):
            subschema = prefix[index] if index < len(prefix) else schema.get('items', True)
            validate_schema(item, subschema, path, _depth=_depth + 1)
    elif isinstance(value, str):
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', math.inf):
            _invalid()
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            _invalid()
        fmt = schema.get('format')
        try:
            if fmt == 'date':
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                    _invalid()
                date.fromisoformat(value)
            elif fmt == 'date-time':
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})', value):
                    _invalid()
                datetime.fromisoformat(value.upper().replace('Z', '+00:00'))
            elif fmt == 'email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
                _invalid()
            elif fmt in ('uri', 'url'):
                parsed = urlsplit(value)
                if not parsed.scheme or any(c.isspace() for c in value):
                    _invalid()
                if parsed.scheme in ('http', 'https') and not parsed.hostname:
                    _invalid()
            elif fmt == 'uuid':
                uuid.UUID(value)
        except (ValueError, OverflowError):
            _invalid()
    elif type(value) in (int, float):
        for bound, sign in (('minimum', -1), ('maximum', 1)):
            if bound in schema and (value < schema[bound] if sign < 0 else value > schema[bound]):
                _invalid()
            exclusive = schema.get('exclusive' + bound.capitalize())
            if type(exclusive) is bool:
                if exclusive and bound in schema and value == schema[bound]:
                    _invalid()
            elif isinstance(exclusive, (int, float)):
                outside = value <= exclusive if sign < 0 else value >= exclusive
                if outside:
                    _invalid()
        if 'multipleOf' in schema:
            step = Decimal(str(schema['multipleOf']))
            if step <= 0 or Decimal(str(value)) % step:
                _invalid()
        fmt = schema.get('format')
        if fmt in ('int32', 'int64'):
            bits = 32 if fmt == 'int32' else 64
            if not -(2 ** (bits - 1)) <= value < 2 ** (bits - 1):
                _invalid()


@lru_cache(maxsize=2)
def _contract(service):
    if service not in SERVICES:
        _invalid('unknown_service')
    here = Path(__file__).resolve().parent
    for filename in (here / 'contracts' / (service + '.json'),
                     here.parent / 'registry' / 'contracts' / (service + '.json')):
        if filename.is_file():
            doc = json.loads(filename.read_text())
            if doc.get('service') != service or doc.get('schema_version') != 1:
                _invalid('invalid_contract')
            return doc
    _invalid('contract_unavailable')


def operations(service):
    """Return independent metadata copies so callers cannot mutate the allowlist."""
    if not isinstance(service, str):
        _invalid('unknown_service')
    return deepcopy(_contract(service)['operations'])


def _operation(service, operation):
    if not isinstance(service, str):
        _invalid('unknown_service')
    if not isinstance(operation, str):
        _invalid('unknown_operation')
    op = _contract(service)['operations'].get(operation)
    if op is None:
        _invalid('unknown_operation')
    if op.get('unsupported_reason'):
        _invalid(op['unsupported_reason'])
    return op


def validate(service, operation, params):
    """Return normalized parameters. Must run before accessing secrets/network."""
    op = _operation(service, operation)
    _json_value(params)
    if not isinstance(params, dict):
        _invalid()
    if len(json.dumps(params, ensure_ascii=False).encode()) > 1024 * 1024:
        _invalid('parameters_too_large')
    validate_schema(params, op['params_schema'])
    if service == 'etm' and operation == 'invoice_create':
        try:
            from .etm_document import validate_body
        except ImportError:
            from etm_document import validate_body
        validate_body(params['body'])
    normalized = deepcopy(params)
    for section in ('path', 'query', 'headers'):
        normalized.setdefault(section, {})
    for value in normalized['path'].values():
        # Slash is part of official Tochka account IDs. Encode it but reject dot
        # segments, percent escapes and controls even before percent encoding.
        text = str(value)
        if (not text or len(text) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in text)
                or any(c in text for c in ('%', '\\', '?', '#'))
                or any(segment in ('.', '..') for segment in text.split('/'))):
            _invalid('invalid_path_parameter')
    for value in normalized['headers'].values():
        if not isinstance(value, str) or any(ord(c) < 32 or ord(c) > 126 for c in value):
            _invalid('invalid_header_parameter')
    for name, value in normalized['query'].items():
        if name in ('page', 'rows', 'perPage', 'limit') and (type(value) is not int or value < 1):
            _invalid('invalid_pagination')
    return normalized


def _scalar(value):
    if type(value) is bool:
        return 'true' if value else 'false'
    return str(value)


def build(service, operation, params):
    """Build a fixed relative route, leaving authentication to the dispatcher."""
    op = _operation(service, operation)
    params = validate(service, operation, params)
    route = op['path']
    for name, value in params['path'].items():
        route = route.replace('{' + name + '}', quote(_scalar(value), safe=''))
    if '{' in route or not route.startswith('/') or route.startswith('//'):
        _invalid('invalid_contract')
    query = {}
    for name, value in params['query'].items():
        # Current official snapshots use only scalar query parameters.
        if isinstance(value, (dict, list)):
            _invalid('unsupported_parameter_serialization')
        query[name] = _scalar(value)
    return {'method': op['method'], 'path': route, 'query': query,
            'body': params.get('body'), 'headers': params['headers'],
            'response_kind': op['response_kind']}


# Stable named aliases, one per published ETM operation, independent of legacy
# flat parameter aliases handled by api_read. The login remains dispatcher-owned.
_ETM_NAMES = {
    'POST /user/login': 'login_check', 'GET /catalog': 'catalog_search',
    'GET /goods/{id}/price': 'goods_price', 'GET /goods/{id}/remains': 'goods_remains',
    'GET /goods/{id}': 'goods_get', 'GET /goods/remains': 'stock_remains',
    'POST /job/create/{procedure}': 'catalog_job_create', 'GET /job/{uuid}': 'catalog_job_get',
    'GET /info/search/{type}/': 'reference_search', 'GET /invoice': 'invoice_list',
    'GET /invoice/{id}/body': 'invoice_get', 'POST /invoice/create': 'invoice_create',
    'POST /invoice/{id}/print/{proc}': 'invoice_print',
    'POST /invoice/{id}/order': 'invoice_order', 'POST /invoice/{id}/delivery': 'invoice_delivery',
    'GET /invoice/{id}/ps': 'invoice_approvals', 'POST /invoice/{id}/ps': 'invoice_approval_update',
    'POST /delivery/point/create': 'delivery_point_create',
    'GET /delivery/point/{id}/date': 'delivery_point_dates',
}


def generate_contracts(research, output):
    """Generate only from fixed local official source files; never fetch refs."""
    import yaml  # Build-time dependency only.
    research, output = Path(research), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source_files = {'etm.yaml': 'https://ipro.etm.ru/ns2000/yaml/cli.yaml',
        'components.yaml': 'https://ipro.etm.ru/ns2000/yaml/components.yaml',
        'goods.yaml': 'https://ipro.etm.ru/ns2000/yaml/goods.yaml',
        'invoice.yaml': 'https://ipro.etm.ru/ns2000/yaml/invoice.yaml',
        'tochka-openapi.json': 'https://enter.tochka.com/doc/openapi/swagger.json'}
    docs = {name: yaml.safe_load((research / name).read_text()) for name in source_files}

    def resolve(value, filename, seen=()):
        if isinstance(value, list):
            return [resolve(item, filename, seen) for item in value]
        if not isinstance(value, dict):
            return value
        if '$ref' in value:
            ref = value['$ref']
            document, pointer = ref.split('#', 1)
            document = document or filename
            if document not in docs or not pointer.startswith('/') or (document, pointer) in seen:
                raise ValueError('unsupported_source_reference')
            target = docs[document]
            for key in pointer.lstrip('/').split('/'):
                target = target[key.replace('~1', '/').replace('~0', '~')]
            resolved = resolve(target, document, seen + ((document, pointer),))
            # In 3.1 siblings constrain referenced schemas too, especially titles,
            # description, examples and bounds in Tochka's generated contracts.
            siblings = {key: resolve(item, filename, seen) for key, item in value.items() if key != '$ref'}
            if siblings:
                return {'allOf': [resolved, siblings]}
            return resolved
        return {key: resolve(item, filename, seen) for key, item in value.items()}

    def empty_object():
        return {'type': 'object', 'properties': {}, 'additionalProperties': False}

    for service, filename in (('etm', 'etm.yaml'), ('tochka', 'tochka-openapi.json')):
        spec, rows = docs[filename], {}
        for route, methods in spec['paths'].items():
            for method, definition in methods.items():
                if method not in ('get', 'post', 'put', 'patch', 'delete'):
                    continue
                ident = method.upper() + ' ' + route
                if service == 'etm':
                    name = _ETM_NAMES[ident]
                else:
                    group = route.split('/')[1].replace('-', '_')
                    name = group + '_' + definition['operationId'].split('_' + group + '_v1_0_', 1)[0]
                if name in rows or not re.fullmatch('[a-z][a-z0-9_]{0,79}', name):
                    raise ValueError('duplicate_or_invalid_alias')
                parameters = resolve(methods.get('parameters', []) + definition.get('parameters', []), filename)
                effect = 'read' if method == 'get' else 'business_write'
                if service == 'etm' and route == '/user/login':
                    effect = 'authentication'
                    parameters = []  # Credentials cannot be model supplied.
                if '/print/' in route or '/job/create/' in route or (service == 'tochka' and route == '/open-banking/v1.0/statements' and method == 'post'):
                    effect = 'report_generation'
                if service == 'etm' and '/print/' in route:
                    # Prose explicitly extends ch3 through ch40.
                    parameters.extend({'name': 'ch' + str(index), 'in': 'query',
                        'schema': {'type': 'string'}, 'description': 'Additional document for group print (documented ch2..ch40)'}
                        for index in range(4, 41))
                schema = empty_object()
                for section in ('path', 'query', 'headers'):
                    schema['properties'][section] = empty_object()
                for param in parameters:
                    section = {'path': 'path', 'query': 'query', 'header': 'headers'}.get(param['in'])
                    if section is None:
                        raise ValueError('unsupported_parameter_location')
                    section_schema = schema['properties'][section]
                    section_schema['properties'][param['name']] = param.get('schema', {})
                    if param.get('required'):
                        section_schema.setdefault('required', []).append(param['name'])
                        if section not in schema.setdefault('required', []):
                            schema['required'].append(section)
                request_body = resolve(definition.get('requestBody', {}), filename)
                body_schema = request_body.get('content', {}).get('application/json', {}).get('schema')
                unsupported = None
                if request_body:
                    if body_schema is None:
                        unsupported = 'official_request_schema_missing'
                    else:
                        schema['properties']['body'] = body_schema
                        if request_body.get('required'):
                            schema.setdefault('required', []).append('body')
                responses = resolve(definition.get('responses', {}), filename)
                media = sorted({content_type for status, response in responses.items()
                    if str(status).startswith('2') for content_type in response.get('content', {})})
                binary = 'application/pdf' in media
                json_response = any('json' in content_type for content_type in media)
                row = {'id': ident, 'method': method.upper(), 'path': route,
                    'summary': definition.get('summary', definition.get('operationId', ident)),
                    'effect': effect, 'source': source_files[filename],
                    'provider_version': spec['info']['version'], 'parameters': parameters,
                    'params_schema': schema, 'request_body': request_body,
                    'response_kind': 'pdf_or_json' if binary and json_response else 'binary' if binary else 'json',
                    'response_media_types': media, 'responses': responses,
                    'security': definition.get('security', spec.get('security', [])),
                    'live_verified': False, 'validation': 'offline_schema_only',
                    'unsupported_reason': unsupported}
                if service == 'etm' and route == '/user/login':
                    row['authentication'] = 'dispatcher_injects_log_pwd'
                if service == 'etm' and '/job/' in route:
                    row['limitations'] = ['Result URLs are returned as data; arbitrary download URLs are not executed.']
                if unsupported:
                    row['limitations'] = ['Official OpenAPI publishes null request schemas for JSON/XML; inventing financial document fields is unsafe.']
                if service == 'etm' and route == '/invoice/create':
                    try:
                        from .etm_document import supplement
                    except ImportError:
                        from etm_document import supplement
                    row = supplement(row)
                rows[name] = row
        files = ['etm.yaml', 'components.yaml', 'goods.yaml', 'invoice.yaml'] if service == 'etm' else [filename]
        result = {'schema_version': 1, 'service': service,
            'scope': 'All operations in the downloaded official OpenAPI snapshot. Schema support does not establish account permissions or live write verification.',
            'sources': [{'url': source_files[file], 'sha256': hashlib.sha256((research / file).read_bytes()).hexdigest()} for file in files],
            'runtime_limits': {'request_bytes': 1048576, 'json_depth': 64, 'path_parameter_length': 2048,
                'pagination': 'Positive integers; no invented provider maximum. One request per invocation; caller follows pagination.'},
            'operations': rows}
        (output / (service + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(service, len(rows), 'supported', sum(not row['unsupported_reason'] for row in rows.values()))
    _contract.cache_clear()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('research', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    generate_contracts(args.research, args.output)
