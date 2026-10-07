"""Rebuild the fal capability manifest from the reviewed offline contract."""
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from automation_integrations import fal_media as fal

base = 'https://fal.ai/docs/documentation/model-apis/'
extra = {
    'capabilities': ('Describe connector capabilities and limitations', 'local'),
    'operation_schema': ('Inspect exact parameters of any connector operation', 'local'),
    'model_schema': ('Get full current input/output OpenAPI schema for any model', 'https://fal.ai/docs/platform-apis/v1/models'),
    'model_documentation': ('Read current per-model schemas, prices and examples', 'https://fal.ai/docs/documentation/setting-up/agent-surfaces'),
    'submit': ('Submit any model, training or workflow endpoint to persistent queue', base + 'inference/queue'),
    'run': ('Call any endpoint synchronously', base + 'inference/synchronous'),
    'stream': ('Collect bounded SSE output from model /stream endpoint', base + 'inference/streaming'),
    'status': ('Read queue position, status, logs and completion errors', base + 'inference/queue'),
    'result': ('Read model-specific final output without rerunning generation', base + 'inference/queue'),
    'cancel': ('Request queue cancellation; in-progress cancellation is best effort', base + 'inference/queue'),
    'status_stream': ('Collect bounded SSE queue status events', base + 'inference/queue'),
    'upload': ('Upload base64 media through signed GCS URL, up to 8 MiB', base + 'fal-cdn'),
    'realtime': ('Bidirectional msgpack WebSocket inference', base + 'inference/real-time'),
    'http_websocket': ('HTTP model protocol over persistent WebSocket', base + 'inference/websockets'),
}
capabilities = []
for name, schema in fal.OPERATION_SCHEMAS.items():
    if name in fal.ALIASES:
        continue
    if name in fal.PLATFORM_OPERATIONS:
        row = dict(fal.PLATFORM_OPERATIONS[name])
    else:
        summary, source = extra[name]
        row = {'id': name, 'summary': summary, 'description': summary, 'source': source,
               'category': ['Model inference'], 'schema': schema,
               'effect': 'generation' if name in fal.GENERATION_OPERATIONS else 'business_write' if name in fal.WRITE_OPERATIONS else 'read'}
    row['adapter'] = name
    row['implemented'] = name not in fal.UNSUPPORTED
    row['unsupported_reason'] = fal.UNSUPPORTED.get(name)
    row['aliases'] = [alias for alias, target in fal.ALIASES.items() if target == name]
    row['live_verification'] = 'not_tested; access probe only verified model discovery with API key; admin billing returned 403'
    capabilities.append(row)
capabilities.extend([
    {'id': 'webhook_receiver', 'summary': 'Receive and verify fal callbacks', 'effect': 'read',
     'implemented': False, 'adapter': None, 'unsupported_reason': 'public_receiver_and_ed25519_verifier_required',
     'source': base + 'inference/webhooks'},
    {'id': 'serverless_sdk_deployment', 'summary': 'Deploy Python code, environments, secrets, runner and revision management outside Platform REST',
     'effect': 'business_write', 'implemented': False, 'adapter': None, 'unsupported_reason': 'fal_sdk_cli_and_serverless_account_approval_required',
     'source': 'https://fal.ai/docs/documentation/serverless/index'},
    {'id': 'large_multipart_cdn_upload', 'summary': 'CDN multipart uploads larger than local 8 MiB adapter limit',
     'effect': 'business_write', 'implemented': False, 'adapter': None, 'unsupported_reason': 'large_file_streaming_upload_required',
     'source': base + 'fal-cdn'},
])
p = {'schema_version': 1, 'service': 'fal', 'retrieved_at': fal.DOCUMENTED['retrieved_at'],
     'scope': 'Entire documented Platform REST surface (union of live and static OpenAPI by operationId), plus dynamic model execution and lifecycle. All model categories are discovered live; no short hardcoded model list.',
     'authentication_note': 'Authorization: Key FAL_KEY. Admin operations prefer optional FAL_ADMIN_KEY; API scope does not become admin.',
     'sources': json.loads((ROOT / fal.DOCUMENTED['source_snapshot_dir'] / 'provenance.json').read_text()),
     'total': len(capabilities), 'platform_total': len(fal.PLATFORM_OPERATIONS),
     'capabilities': capabilities, 'limits': fal.execute('capabilities', {}, {})['limits']}
(ROOT / 'registry/capabilities/fal.json').write_text(json.dumps(p, ensure_ascii=False, indent=2) + '\n')
print('Wrote',len(capabilities),'capabilities')
