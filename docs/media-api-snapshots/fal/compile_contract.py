"""Offline compiler: combine official docs and live OpenAPI, preferring live IDs."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
rows = {}
for file, url in [('platform-doc-openapi.json', 'https://fal.ai/docs/api-reference/platform-apis/openapi/v1.json'),
                  ('platform-openapi.json', 'https://api.fal.ai/v1/openapi.json')]:
    spec = json.loads((HERE / file).read_text())
    for path, methods in spec['paths'].items():
        for method, op in methods.items():
            if method not in ('get', 'post', 'put', 'patch', 'delete'):
                continue
            name = re.sub(r'(?<!^)(?=[A-Z])', '_', op['operationId']).lower()
            params = op.get('parameters', [])
            schema = {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
            for param in params:
                schema['properties'][param['name']] = param['schema']
                if param.get('required'):
                    schema['required'].append(param['name'])
            body = op.get('requestBody', {})
            content = body.get('content', {})
            body_type = next(iter(content), None)
            if body_type:
                schema['properties']['body'] = content[body_type]['schema']
                if body.get('required') or name == 'estimate_pricing':
                    schema['required'].append('body')
            if name == 'serverless_upload_local_file':
                schema['properties']['body'] = {'type': 'object', 'additionalProperties': False,
                    'properties': {'file_name': {'type': 'string', 'minLength': 1, 'maxLength': 255},
                    'content_type': {'type': 'string', 'minLength': 1},
                    'data_base64': {'type': 'string', 'minLength': 1, 'maxLength': 12000000}},
                    'required': ['file_name', 'content_type', 'data_base64']}
            response_types = [t for code, r in op.get('responses', {}).items() if code.startswith('2') for t in r.get('content', {})]
            response_kind = 'json'
            if response_types and 'application/json' not in response_types:
                response_kind = 'binary' if 'application/octet-stream' in response_types else 'sse' if 'text/event-stream' in response_types else 'text'
            read_post = name in ('estimate_pricing', 'serverless_logs_history', 'serverless_logs_stream')
            effect = 'read' if method == 'get' or read_post else 'business_write'
            rows[name] = {'id': name, 'provider_operation_id': op['operationId'], 'method': method.upper(),
                'path': '/v1' + path, 'summary': op.get('summary', ''), 'description': op.get('description', '').strip(),
                'category': op.get('tags', []), 'effect': effect, 'schema': schema, 'parameters': params,
                'body_type': body_type, 'response_kind': response_kind,
                'admin_required': any('adminApiKey' in s for s in op.get('security', [])),
                'source': url, 'documentation_url': 'https://fal.ai/docs' + op.get('x-mint', {}).get('href', '/api-reference/platform-apis/index'),
                'source_file': file, 'source_sha256': hashlib.sha256((HERE / file).read_bytes()).hexdigest()}
            if name == 'create_api_key':
                rows[name]['unsupported_reason'] = 'secure_generated_credential_sink_required'
contract = {'schema_version': 1, 'service': 'fal', 'retrieved_at': '2026-10-04', 'operations': rows,
    'source_resolution': 'Union by operationId. Live schema takes precedence; createComputeInstance appears only in static documentation.'}
(ROOT / 'registry/contracts/fal.json').write_text(json.dumps(contract, ensure_ascii=False, indent=2) + '\n')
print('Compiled', len(rows), 'documented platform operations')
