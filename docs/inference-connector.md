# inference.sh connector

Reviewed on 2026-10-04 after the account access check. The complete current
[official OpenAPI route catalog](https://api.inference.sh/openapi.json) contains
714 methods across 491 paths. All methods are inventoried in
`registry/capabilities/inference.json`; 232 have reviewed executable contracts.
`file_upload` adds a two-request upload workflow, for 233 connector operations.
The OpenAPI contains path parameters but no request-body or query schemas, so
request contracts come from the pinned prose documentation, not guessed generic
HTTP passthrough. Individual app schemas are discovered live.

## Connected surface

- All discoverable apps, with current/versioned metadata and schemas, list/search,
  store pricing, cost estimates, app lifecycle management, versions and promotion.
- Native async app execution for any `namespace/name@version`: input, setup,
  multi-function apps, sessions, workers, cloud/private/private-first routing,
  webhook callback, complete task status/result/log/timing/telemetry/cost and cancel.
- File metadata, list/delete, and two-stage upload. Local file access belongs to the
  root service; `upload_file` accepts bytes and performs POST `/files` then PUT of
  those bytes to the provider-issued signed URL without an Authorization header.
- Session list/get/keepalive/end; flow definitions, graph actions, deployment,
  execution, results, per-node output and cancellation.
- Agent templates/versions, agent runs and chats, messages, execution traces,
  interrupts, tool results and approvals, A2A discovery cards, and non-streaming
  OpenAI-compatible model and agent chat completions.
- Skills and knowledge CRUD/versioning/import/search; MCP catalog, server
  registration and connected tool discovery/calls; trigger definitions/fire/history;
  agent publications; artifact metadata/content/sharing/comments/page-store data.
- Identity/workspace/member metadata, entitlement and balance/usage/payment-history
  reads, API-key metadata, private-engine/remote/exec metadata, CMS reads.

The connector accepts provider inputs without hardcoding models or modalities.
Read `app_get_by_ref`, `app_get` or `app_version` before supplying model-specific
`input` and `setup`. The provider remains the authority for the evolving model
schema. See [Apps](https://inference.sh/docs/api/rest/apps),
[Tasks](https://inference.sh/docs/api/rest/tasks),
[Store](https://inference.sh/docs/api/rest/store), and
[Authentication](https://inference.sh/docs/api/authentication).

## Boundary and semantics

`validate(operation, params)` has no credential or network access. Released
contracts fix methods, hosts, paths and accepted top-level parameters. Path
substitutions reject traversal, slash, query, fragment and percent-encoded
separators. Nested app and tool inputs remain JSON objects. `execute` accepts
`INFSH_API_KEY` (or `INFERENCE_API_KEY`) via an injected credentials dictionary,
adds bearer auth only on `api.inference.sh`, and returns unwrapped provider data.
All responses redact known credentials; token/provisioning endpoints are not
executable. Transport exceptions contain safe codes, never response bodies.

All submissions make one attempt. Native `/run` always sends `wait=false`; the
caller must persist the returned task ID and poll it. A timeout must be recorded
as an unknown outcome and reconciled before another paid submission. The shared
service owns jobs, spend reservations, output downloads and Telegram delivery.
`WRITE_OPERATIONS` includes stateful GET `/skills/resolve` because the provider
imports or refreshes GitHub content. POST list/search/estimate routes remain reads.
Tool approvals and interrupt resolutions may resume paid work and are classified
as generation. Scheduling a provider trigger can start future executions outside
local job controls and must remain a management write with an explicit preview.

Money values from balance, pricing and task costs are integer **microcents**:
**1 USD = 100,000,000 microcents**. Estimates preserve `exact`, `range` and
`unknown`; unknown cost is not zero. The dedicated
[Billing](https://inference.sh/docs/api/rest/billing) and
[Usage](https://inference.sh/docs/api/rest/usage) pages establish the conversion.
One sentence in Tasks inconsistently labels the unit; its conversion formula and
examples agree with Billing. `microcents_to_usd` uses exact Decimal arithmetic.

Task terminal states are 10 completed, 11 failed, 12 cancelled. Flow runs use a
separate enum (3 completed, 4 failed, 5 cancelled). Do not use task numeric states
for flow runs. New API JSON responses use `{data, messages}` envelopes; OpenAI
model lists/completions and A2A cards retain their native formats.

## Explicit remaining coverage

Every unimplemented OpenAPI method has an `unsupported_reason`; inventory presence
is not a promise that a route is executable or that the account grants its scopes.
Reasons include platform admin/internal routes, unknown request schemas, identity
and secret provisioning/reveal, payments/subscription mutations, remote machine
command/control, browser/anonymous embed flows, inbound webhooks, SSE/NDJSON and
WebSocket transports, A2A execution, and multipart artifact publishing or asset
upload/download redirects. Polling supports long-running tasks, chats and flows.

The upload helper caps files at 32 MiB. The small JSON `file_upload` operation
accepts base64 up to 128 KiB; use the root service's local-file wrapper for media.
Signed upload URLs must pass the shared provider artifact-domain allowlist; an
unrecognized storage domain fails closed instead of forwarding credentials.
Text content and render endpoints use the text transport. Supporting skill-file
CDN redirects are inventoried as unavailable.

Lists are bounded to 100 items per call and preserve cursors. The provider's
`limit=-1` full-dump shortcut is intentionally not exposed by the connector.
No provider calls or paid generations occur during the unit suite.

## Reproduction and checks

`docs/media-api-snapshots/inference/sources.json` records source URLs, UTC retrieval
instants, SHA-256 of article text snapshots and the original HTML, plus the complete
OpenAPI hash. The 35 REST pages and authentication/session/file guides were read
as a complete integration reference. `ops/build_inference_contract.py` reproduces
the local request contract and inventory using those snapshots and reviewed field
definitions. It performs no network or credential operations.

```sh
python3 ops/build_inference_contract.py
python3 -m unittest tests.test_inference_media -v
```

The suite verifies inventory completeness and all snapshot hashes, traversal and
host restrictions, dynamic app inputs, forced asynchronous submits/no retry,
query encoding, read/write classification, units and unknown estimates, native
response formats, secret redaction, error handling, text responses, trigger
validation, and two-stage uploads without credential forwarding.
