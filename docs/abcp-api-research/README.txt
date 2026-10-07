ABCP: official prose contract research, 2026-10-05

Canonical runtime contract: ../../registry/contracts/abcp.json
Executable discovery catalogue: ../../registry/capabilities/abcp.json
Coverage: 287 endpoints, matching the existing baseline exactly.
ABCP client 45; ABCP1 admin 76; TS client 30; TS admin 122; VINQU 8; CarCare 6.
Reviewed classification: 135 reads and 152 business writes. POST does not imply
write and GET does not imply safe read. Payment-link GETs conservatively use the
write boundary. No authenticated requests or remote changes were performed in
this research task.

Sources and reproducibility
- sources.json pins URL, SHA256, byte count and local snapshot location for the
  8 fetched official pages. No credentials were read or used.
- snapshots/*.html are the authoritative fetched bytes; *.txt are convenient
  readable article extracts. Public documentation contains example credentials;
  these are provider examples, not tenant secrets.
- baseline-endpoints.csv preserves the existing 287-operation inventory.
- sections.json is the intermediate structural extraction (285 headings); two
  archive operations embedded under another heading are split during compilation.
- contract-details.json preserves all parameter/response tables and code blocks.
- extraction-notes.json must remain empty after a clean build.
- findings.json records the safety/compatibility facts relevant to execution.

Rebuild after reviewing official documentation changes:
  python3 -m venv /tmp/abcp-docs-venv
  /tmp/abcp-docs-venv/bin/pip install requests beautifulsoup4
  /tmp/abcp-docs-venv/bin/python docs/abcp-api-research/fetch_sources.py
  /tmp/abcp-docs-venv/bin/python docs/abcp-api-research/extract_sections.py
  /tmp/abcp-docs-venv/bin/python docs/abcp-api-research/build_contract.py
  python3 docs/abcp-api-research/verify_catalog.py
Runtime does not depend on requests, BeautifulSoup or these build scripts.

JSON contract
operations is keyed by a stable family + method + snake_case path identifier.
parameters is a flat tool-input JSON Schema whose values may be nested objects
and arrays. Dispatcher-owned authentication parameters are excluded. Path
placeholders are listed in path_parameters and removed from query/body by the
transport. Default lists/maps are PHP brackets. parameter_serialization marks
explicitly comma-separated fields. Multipart file values use filename,
content_base64 and optional content_type. No arbitrary URL or method exists in
agent inputs. auth_field_map records VINQU's hash/siteHash spelling exception.

Only explicit types and unconditional required fields become strict constraints.
Unknown types remain unknown. Conditional requirements and provider-specific
nested shapes stay in documentation and raw parameter tables; additional nested
keys are permitted where the prose does not establish a closed schema. Fields
seen only in request examples have x-source=request_example. Every operation is
live_verified=false; runtime/account permissions and successful business writes
require separate verification. The contract is a documentation inventory, not an
assertion that all modules and roles are enabled on the target account.

Validation: verify_catalog.py has 17 offline regression checks covering exact
baseline parity, source hashes, safe IDs/paths, authentication separation, scalar
request fields vs response objects, POST reads, guarded GET payment links, JSON
and multipart exceptions, upload auth placement, VINQU alias, partial commits,
empty success responses, nested filters and XLSX export. No business writes are
used for validation.
