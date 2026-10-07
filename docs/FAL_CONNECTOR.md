# fal connector

Access was checked before documentation research on 2026-10-04: the existing Vaultwarden `FAL_KEY` returned HTTP 200 from the model catalog. `/v1/account/billing` returned HTTP 403 because it requires an ADMIN key. This does not block model discovery or ordinary model inference. No paid generation or remote administration was performed during connector development.

`automation_integrations/fal_media.py` implements an injectable, standard-library provider adapter. It delegates durable jobs, owner authorization, budgets and result delivery to the common media runner. `registry/contracts/fal.json` is required at runtime; installed layouts may place it at `automation_integrations/contracts/fal.json`.

## Capability coverage

The live Platform OpenAPI contains 87 operations; the static documentation contains 82. Their union contains **88 distinct operation IDs**. The live version wins when parameter names differ (`asset_id` versus the older `vector_id`); compute-instance creation is documented only in the static specification. Both original snapshots and URL/date/SHA-256 provenance are retained under `docs/media-api-snapshots/fal/`.

All 88 are represented in the connector contract, including model discovery, pricing and estimates; request history, usage, analytics and billing events; workflows; assets, collections, characters, entities and tags; storage ACLs, signed URLs and retention settings; serverless apps, revisions, events, queues, logs, files, metrics and usage; compute instances; API-key administration; account and organization reports. Available methods are permission-dependent. Creating an API key is described but deliberately has no executable adapter until a secure sink can capture the one-time credential without returning it to the model.

The connector additionally provides generic `submit`, `run`, `stream`, `status`, `result`, `cancel`, `status_stream`, `upload`, `model_schema`, `model_documentation`, `capabilities` and `operation_schema`. `models`, `pricing`, `estimate`, `usage`, `billing`, `billing_events`, `requests` and `analytics` are friendly aliases for their Platform methods.

The model catalog is **dynamic**. Search by task/category, follow `next_cursor`, inspect the selected endpoint using `model_schema`, and send its input object unchanged. This covers image, video, audio, speech, 3D, training/fine-tuning, utilities, custom endpoints and workflows whenever the account and model expose them. New model IDs do not require a code release. Provider validation remains authoritative for individual model inputs.

## Calling contract

```python
execute(operation, params, credentials, transport=transport)
validate(operation, params)
```

`OPERATIONS`, `OPERATION_SCHEMAS`, `WRITE_OPERATIONS`, `GENERATION_OPERATIONS`, `PLATFORM_OPERATIONS`, `UNSUPPORTED` and `DOCUMENTED` are available for catalog/runner integration. The transport implements:

```python
request(method, absolute_url, headers=None, query=None, body=None,
        timeout=30, response_kind="json")
```

Text/CSV/metrics are returned in a JSON `text` field; binary files use `data_base64`; SSE is a bounded collection of `events`. No operation performs automatic retries. A failed or interrupted submit may have succeeded remotely; the common runner must retain an uncertain outcome and never submit it again automatically.

```json
{"operation":"models","params":{"q":"image to video","limit":20}}
{"operation":"model_schema","params":{"endpoint_id":"owner/model/version"}}
{"operation":"estimate","params":{"body":{"estimate_type":"unit_price","endpoints":{"owner/model/version":{"unit_quantity":1}}}}}
{"operation":"submit","params":{"endpoint_id":"owner/model/version","input":{"prompt":"..."},"options":{"store_io":false,"no_retry":true,"lifecycle":{"expiration_duration_seconds":3600}}}}
{"operation":"status","params":{"endpoint_id":"owner/model/version","request_id":"saved-request-id","logs":true}}
{"operation":"result","params":{"endpoint_id":"owner/model/version","request_id":"saved-request-id"}}
```

Platform operations use named path/query/header parameters and a nested `body` for JSON request bodies. `operation_schema` returns the precise schema. Arbitrary request hosts, paths, methods and authentication headers are not accepted. Documented idempotency headers remain available where the provider exposes them.

Submit accepts lifecycle/access controls, start deadline, priority, runner hint, request tags, queue limit, callback URL, IO retention, retry controls and fallback control. These are separate from model inputs. The documented SDK tags format is packed `X-Fal-Tags: key=value,key=value`. Queue controls are rejected for direct `run`/`stream` operations.

Queue polling reconstructs the documented SDK application root: `fal-ai/flux/dev` becomes `fal-ai/flux/requests/{id}`; `workflows/owner/name` keeps the namespace. This follows the current official Python SDK, which differs from some illustrative prose URLs. Completion can contain an error; `COMPLETED` alone is not proof of success. Cancellation is best effort once processing starts.

## Credentials and permissions

Model calls always use `FAL_KEY`, even when `FAL_ADMIN_KEY` exists. Only methods marked `admin_required` prefer the separate admin key. Without it, an API key can attempt the endpoint and receive the provider's permission response; no scope elevation is fabricated. ADMIN is needed for balance, detailed usage/billing and parts of compute/key administration. Account balance and actual spending therefore remain unverified with the current credential.

Upload initialization uses `https://rest.fal.ai/storage/upload/initiate?storage_type=gcs`, followed by an unauthenticated PUT to a validated `storage.googleapis.com` signed URL. The provider key never reaches Google storage or public model documentation. Upload accepts base64 content up to 8 MiB. Serverless multipart uploads use the documented `file_upload` field. Files larger than the local limit can be supplied to models using existing public or presigned URLs; automatic large multipart CDN upload is not implemented.

## Explicit boundaries

The manifest records every reviewed limitation rather than claiming universal execution:

- Bidirectional realtime/msgpack and HTTP-over-WebSocket need a persistent WebSocket transport. The synchronous tool runner does not open these sessions.
- SSE is collected through a bounded request, not forwarded interactively to Telegram.
- Callback registration works for an existing HTTPS endpoint. A public callback receiver with Ed25519 signature verification is outside this adapter; polling works without it.
- Python serverless deployment, SDK/CLI-only runner/scaling/environment/secret actions need that deployment runtime and provider-approved serverless access. Platform REST management and reads are exposed independently.
- Large multipart CDN uploads and one-time API-key credential storage have the limitations above.
- Unit-price and historical estimates are estimates, not guaranteed exact charges. Resolution, duration and model-specific units matter. Read actual billing events when ADMIN access is available.

## Validation

`python3 -m unittest tests.test_fal_media -v` verifies complete operation-ID coverage against both official specifications, snapshot integrity, arbitrary model IDs, model input preservation, queue root routing, auth scope separation, path/header injection rejection, multipart encoding, pricing schema alternatives, no paid-request retries, secret redaction, signed-upload host and credential separation, bounded SSE parsing and truthful unsupported operations.

Regenerate offline artifacts after reviewing new snapshots:

```sh
python3 docs/media-api-snapshots/fal/compile_contract.py
python3 docs/media-api-snapshots/fal/write_capabilities.py
```
