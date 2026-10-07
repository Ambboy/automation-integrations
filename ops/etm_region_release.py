"""Install only the ETM region/order adapter and its instructions, with guarded rollback.

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


OLD_DESTINATION = (
    '- Check authenticated `/user/session/get` when `checkout_options` ignores the requested destination: '
    'stored city/region and `rights.skladop` can restrict checkout to one office even when the requested '
    'branch is real. Verify branch identity with first-party GET `/info/city/{cityId}`. A public directory '
    'entry does not overcome an authenticated checkout restriction; never substitute another city, '
    'change account rights, or bypass the write adapter.'
)
NEW_DESTINATION = (
    '- Verify the effective city/region through authenticated `/user/session/get`; a requested city in '
    'login parameters or cookies does not prove that the server switched region. The adapter verifies '
    'region changes and the exact requested branch. A branch missing from the portal checkout list '
    'does not establish an account-wide ban or a recent rights change. Consult the returned route and '
    'diagnostics: a supported public API order route is distinct from portal basket checkout and must '
    'verify its own destination and contract. Never substitute another city, change account rights, '
    'or bypass the write adapter.'
)
PUBLIC_ORDER_REFERENCE = (
    '- For the public API route, preserve an explicit `customer_order_number` supplied by the owner. '
    'Otherwise use the adapter-generated durable customer reference from the prepared checkout; '
    'this is our order reference, not the supplier\'s native document number. Keep the same reference '
    'and draft when checking an uncertain outcome. Stop when the destination or contract cannot be '
    'verified, and do not claim order placement until the resulting supplier document is read back '
    'and verified. An unverified or uncertain submission must be inspected with `status`, never '
    'replaced by another order or retried blindly.'
)

# Publish the new dependency before adapters and the read entrypoint.
RUNNER_FILES = ('etm_public_order.py', 'etm_order.py', 'etm_document.py',
                'etm_workflow.py', 'api_read.py')
REGISTRY_FILES = ('capabilities/etm.json', 'contracts/etm.json')
CATALOG_SUFFIX = 'etm-region.1'


@dataclass(frozen=True)
class Layout(guarded.Layout):
    backup: Path = guarded.ROOT / 'update-20261007-etm-region'

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
            raise guarded.ReleaseError('Unexpected ETM release catalog format')
        identifiers = []
        for service in catalog['services']:
            if not isinstance(service, dict) or not isinstance(service.get('id'), str) or not service['id']:
                raise guarded.ReleaseError('Unexpected catalog service format')
            identifiers.append(service['id'])
        if len(set(identifiers)) != len(identifiers) or identifiers.count('etm') != 1:
            raise guarded.ReleaseError('Catalog must contain unique services and exactly one ETM entry')
    if ([item for item in source['services'] if item['id'] != 'etm']
            != [item for item in installed['services'] if item['id'] != 'etm']):
        raise guarded.ReleaseError('Non-ETM catalog entries differ; review newer installed service changes')
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
    if skill.count(OLD_DESTINATION) != 1 or NEW_DESTINATION in skill or PUBLIC_ORDER_REFERENCE in skill:
        raise guarded.ReleaseError('ETM destination instructions changed; review the current skill first')
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
    candidate = skill.replace(OLD_DESTINATION, NEW_DESTINATION + '\n' + PUBLIC_ORDER_REFERENCE)
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
        raise SystemExit('ETM region release failed; inspect hashes and gateway state without printing credentials.') from None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
