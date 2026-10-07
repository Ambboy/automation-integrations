"""Install ETM document lifecycle recovery and its instructions, with guarded rollback.

The native plugin starts a fresh runner subprocess for each call and reads its
catalog on demand, so these files take effect without restarting the gateway.
Only the ETM catalog entry changes; unrelated services, configuration, credentials,
plugin files and existing checkout records are preserved.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from ops import wirenboard_release as guarded


OLD_UNCERTAIN = (
    '- On uncertain write outcomes inspect the same draft with `status`, never blindly repeat checkout. '
    'Read back every resulting document before claiming placement. Use `invoice` for lines and '
    '`invoice_list` filtered by the exact `usr-inv-num` for document metadata; the line-item body\'s '
    '`store` is not necessarily the issuing destination. Compare list `st_dest` with the requested '
    'office, check contract binding and payment-title evidence, and reconcile the actual sum. A '
    'correct destination or contract written in `Remarks`/`ps` does not establish the structured '
    'binding: the provider can create a specification using account defaults despite that text. '
    'If preflight reports a destination or contract mismatch, report the existing specification and '
    'its exact business number without sending reservation or another create request.'
)
NEW_UNCERTAIN = (
    '- On uncertain write outcomes inspect the same draft with `status`; do not blindly repeat '
    'checkout. Read back every resulting document before claiming placement. Use `invoice` for '
    'lines and `invoice_list` filtered by the exact `usr-inv-num` for document metadata; the '
    'line-item body\'s `store` is not necessarily the issuing destination. Compare list `st_dest` '
    'with the requested office, check contract binding and payment-title evidence, and reconcile '
    'the actual sum. Text in `Remarks`/`ps` does not prove structured destination or contract '
    'binding. A mismatching specification is an existing document to inspect and correct or '
    'cancel under the owner\'s instruction. Use the lifecycle recovery operations for that exact '
    'document, preserve its business number, and verify the result before ordering a replacement.'
)
OLD_REFERENCE = (
    '- For the public API route, preserve an explicit `customer_order_number` supplied by the owner. '
    'Otherwise use the adapter-generated durable customer reference from the prepared checkout; '
    'this is our order reference, not the supplier\'s native document number. Keep the same reference '
    'and draft when checking an uncertain outcome. Stop when the destination or contract cannot be '
    'verified, and do not claim order placement until the resulting supplier document is read back '
    'and verified. An unverified or uncertain submission must be inspected with `status`, never '
    'replaced by another order or retried blindly.'
)
NEW_REFERENCE = (
    '- For the public API route, preserve an explicit `customer_order_number` supplied by the owner. '
    'Otherwise use the adapter-generated durable customer reference; it is our reference, not the '
    'supplier\'s native document number. Keep that reference and draft when inspecting an uncertain '
    'outcome. Verify the actual destination, contract, quantities and total before claiming '
    'placement. An unresolved draft does not prohibit status, cancellation, documented edits or '
    'continuation for its known documents. A replacement requires the earlier document to be '
    'verified cancelled or otherwise reconciled so it cannot become a duplicate order.'
)
OLD_CORRESPONDENCE = (
    '- If checkout is blocked and a supplier message is the fallback, use the exact discovered '
    'message schema and preserve the previous completed supply. Follow that operation\'s own '
    'confirmation policy: authorization for checkout with `confirmation_required=false` does not '
    'waive `confirmation_required=true` on document correspondence. Posting a request is not a '
    'placed order or a confirmed delivery date.'
)
NEW_CORRESPONDENCE = (
    '- When the owner explicitly asks to send a supplier message, use the exact discovered message '
    'schema and preserve completed supplies. An ordering request alone does not authorize a '
    'supplier message. Follow the operation\'s returned confirmation policy and do not demand a '
    'second approval when `confirmation_required=false`. Posting a message is not a placed order '
    'or a confirmed delivery date.'
)
LIFECYCLE_HEADING = '## Document lifecycle and recovery'
LIFECYCLE_SECTION = LIFECYCLE_HEADING + """

- Discover the current ETM service, all capability pages, and the exact operation schema before use. The catalog exposes supported document reads and writes beyond checkout: use their documented parameters and results instead of treating a missing recipe here as a restriction.
- For an explicit owner instruction to cancel, correct, continue or replace an existing document, prepare the matching operation with the exact provider document ID. Reuse established quantities, destination, contract and other task terms. When `confirmation_required=false`, execute immediately; the owner does not need to repeat consent or send a UUID. Ask only for missing business terms.
- An earlier unresolved checkout must remain visible with its known supplier IDs and receipts, but must not prevent inspection, cancellation, supported edits or continuation of those documents. Use the existing-document recovery path; do not clear state files, discard evidence or bypass the adapter.
- For cancellation, inspect current supplier state, cancel the exact intended document, and read back the result. A local draft cancellation alone does not cancel an ETM specification. After the adapter verifies the supplier cancellation and reconciles the earlier draft, a replacement may proceed under the owner's existing instruction.
- For edits or continuation, preserve the same supplier document and confirm that the requested operation is supported in its present state. Reconcile split documents individually. An unknown network result calls for a status/readback check of the same operation, never automatic replay or a fresh create request.
- Read-only questions and connector checks must not create specifications, reserve stock, arrange transfers, request shipment or send messages. Use read or preparation operations for validation; business writes require the owner's matching task instruction.

"""
SKILL_REPLACEMENTS = ((OLD_UNCERTAIN, NEW_UNCERTAIN),
                      (OLD_REFERENCE, NEW_REFERENCE),
                      (OLD_CORRESPONDENCE, NEW_CORRESPONDENCE))

# Publish the new dependency before adapters and the read entrypoint.
RUNNER_FILES = ('etm_lifecycle_actions.py', 'etm_lifecycle.py', 'etm_authorization.py', 'confirmed_write.py',
                'etm_workflow.py')
REGISTRY_FILES = ('capabilities/etm.json', 'contracts/etm.json')
CATALOG_SUFFIX = 'etm-lifecycle.1'


@dataclass(frozen=True)
class Layout(guarded.Layout):
    backup: Path = guarded.ROOT / 'update-20261007-etm-lifecycle'

    @property
    def skill(self) -> Path:
        return self.home / 'skills/productivity/supplier-order-audits/references/etm.md'

    def targets(self):
        release = self.root / 'release'
        return [(self.source / 'automation_integrations' / name, release / name)
                for name in RUNNER_FILES] + [
            (self.source / 'registry' / name, release / name) for name in REGISTRY_FILES
        ] + [
            (self.backup / 'candidate-catalog.json', release / 'catalog.json'),
            (self.backup / 'candidate-etm-skill.md', self.skill),
        ]


def candidate_catalog(layout: Layout) -> dict:
    source_bytes = guarded.checked_bytes(layout.source / 'registry/catalog.json')
    installed_bytes = guarded.checked_bytes(layout.root / 'release/catalog.json')
    if source_bytes is None or installed_bytes is None:
        raise guarded.ReleaseError('Both source and installed catalogs are required')
    source, installed = json.loads(source_bytes), json.loads(installed_bytes)
    for catalog in (source, installed):
        if (not isinstance(catalog, dict) or catalog.get('schema_version') != 1
                or not isinstance(catalog.get('version'), str) or not catalog['version']
                or not isinstance(catalog.get('services'), list)):
            raise guarded.ReleaseError('Unexpected ETM lifecycle release catalog format')
        identifiers = []
        for service in catalog['services']:
            if not isinstance(service, dict) or not isinstance(service.get('id'), str) or not service['id']:
                raise guarded.ReleaseError('Unexpected catalog service format')
            identifiers.append(service['id'])
        if len(set(identifiers)) != len(identifiers) or identifiers.count('etm') != 1:
            raise guarded.ReleaseError('Catalog must contain unique services and exactly one ETM entry')
    # Non-ETM source entries are irrelevant: only the ETM entry is copied.
    # In particular, an older source must never replace newer installed services.
    etm = next(item for item in source['services'] if item['id'] == 'etm')
    # Build from the installed catalog so unrelated metadata and version suffixes
    # survive even if the source catalog's version string is older.
    candidate = dict(installed)
    candidate['services'] = [etm if item['id'] == 'etm' else item for item in installed['services']]
    if CATALOG_SUFFIX not in installed['version'].split('+'):
        candidate['version'] = installed['version'] + '+' + CATALOG_SUFFIX
    return candidate


def prepare(layout: Layout = Layout()) -> dict:
    if layout.backup.exists() or layout.backup.is_symlink():
        raise guarded.ReleaseError('Release staging already exists; inspect before retrying')
    raw_skill = guarded.checked_bytes(layout.skill)
    if raw_skill is None:
        raise guarded.ReleaseError('ETM skill is missing')
    skill = raw_skill.decode('utf-8')
    if (LIFECYCLE_HEADING in skill or skill.count('## Status interpretation') != 1
            or any(skill.count(old) != 1 or new in skill for old, new in SKILL_REPLACEMENTS)):
        raise guarded.ReleaseError('ETM lifecycle instructions changed; review the current skill first')
    # Fail before creating staging when the new module or another source is absent.
    for source, _ in layout.targets()[:-2]:
        if guarded.checked_bytes(source) is None:
            raise guarded.ReleaseError('A required ETM release source is missing')
    for name in REGISTRY_FILES:
        registry = json.loads(guarded.checked_bytes(layout.source / 'registry' / name))
        if not isinstance(registry, dict) or registry.get('service') != 'etm':
            raise guarded.ReleaseError('An ETM registry source belongs to another service')
    catalog_path = layout.root / 'release/catalog.json'
    catalog_before = guarded.fingerprint(catalog_path)
    catalog = candidate_catalog(layout)
    if guarded.fingerprint(layout.config) is None:
        raise guarded.ReleaseError('Hermes config is missing')
    guarded.gateway_state(layout)
    candidate = skill
    for old, new in SKILL_REPLACEMENTS:
        candidate = candidate.replace(old, new)
    candidate = candidate.replace('## Status interpretation', LIFECYCLE_SECTION + '## Status interpretation')
    layout.backup.mkdir(mode=0o700, parents=True)
    guarded.atomic(layout.backup / 'candidate-catalog.json', guarded.json_bytes(catalog))
    guarded.atomic(layout.backup / 'candidate-etm-skill.md', candidate.encode('utf-8'))
    result = guarded.prepare(layout)
    manifest = guarded.load_manifest(layout)
    before = {entry['target']: entry['before'] for entry in manifest['entries']}
    if (before[str(catalog_path)] != catalog_before
            or before[str(layout.skill)] != guarded.sha(raw_skill)):
        # The candidate was built from an older live snapshot. Withdraw its
        # manifest so even a direct guarded.apply cannot publish stale content.
        (layout.backup / 'manifest.json').unlink()
        raise guarded.ReleaseError('Catalog or skill changed while preparing; staging is not applicable')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'apply', 'rollback'))
    args = parser.parse_args()
    actions = {'prepare': prepare, 'apply': guarded.apply, 'rollback': guarded.rollback}
    try:
        result = actions[args.action](Layout())
    except (guarded.ReleaseError, OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, guarded.ReleaseError):
            raise SystemExit(str(exc)) from None
        raise SystemExit('ETM lifecycle release failed; inspect hashes and gateway state without printing credentials.') from None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
