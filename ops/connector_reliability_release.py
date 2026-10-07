"""CAS-guarded update of the reviewed connector modules and media contracts.

No credentials, configuration, provider state or third-party core are targets.
Run prepare, review the manifest, then apply with an idle gateway; activation of
the plugin's catalog helper requires an ordinary idle gateway reload/restart.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from ops import wirenboard_release as guarded


MODULES = ('extended_api.py', 'documented_contract.py', 'confirmed_write.py',
           'wirenboard.py', 'wirenboard_http.py', 'fal_media.py', 'inference_media.py',
           'media_runtime.py', 'media_api.py', 'api_read.py')


@dataclass(frozen=True)
class Layout(guarded.Layout):
    backup: Path = guarded.ROOT / 'update-20261007-connector-reliability'

    def targets(self):
        release = self.root / 'release'
        return [(self.source / 'automation_integrations' / name, release / name) for name in MODULES] + [
            (self.source / 'registry' / kind / (service + '.json'), release / kind / (service + '.json'))
            for kind in ('contracts', 'capabilities') for service in ('fal', 'inference')
        ] + [(self.source / 'registry/catalog.json', release / 'catalog.json'),
             (self.source / 'automation_integrations/catalog.py', self.home / 'plugins/automation-api-catalog/catalog.py')]


@dataclass(frozen=True)
class ReadRecoveryLayout(Layout):
    backup: Path = guarded.ROOT / 'update-20261007-connector-read-recovery'

    def targets(self):
        return [(self.source / 'automation_integrations' / name, self.root / 'release' / name)
                for name in ('api_read.py', 'extended_api.py')]


def protected(layout):
    targets = {target for _, target in layout.targets()}
    result = {}
    for base in (layout.root / 'release', layout.home / 'plugins'):
        for path in base.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path not in targets:
                result[str(path)] = guarded.fingerprint(path)
    for path in (layout.config, layout.root / 'private.json'):
        result[str(path)] = guarded.fingerprint(path)
    return result


def check_protected(layout):
    pins = json.loads((layout.backup / 'protected.json').read_text())
    for path, expected in pins.items():
        if guarded.fingerprint(Path(path)) != expected:
            raise guarded.ReleaseError('An unrelated installed file changed; update refused')


def prepare(layout=Layout()):
    pins = protected(layout)
    result = guarded.prepare(layout)
    guarded.atomic(layout.backup / 'protected.json', guarded.json_bytes(pins))
    check_protected(layout)
    return {**result, 'protected_files': len(pins)}


def apply(layout=Layout()):
    check_protected(layout)
    if (layout.backup / 'applied.json').exists():
        raise guarded.ReleaseError('This release already has an apply receipt')
    if (layout.backup / 'failed-apply.json').exists():
        raise guarded.ReleaseError('Previous failed update requires inspection')
    manifest = guarded.load_manifest(layout)
    entries = manifest['entries']
    backups, staged = [], []
    for entry in entries:
        data = guarded.checked_bytes(layout.backup / entry['backup']) if entry['backup'] else None
        if (guarded.sha(data) if data is not None else None) != entry['before']:
            raise guarded.ReleaseError('Backup hash mismatch')
        backups.append(data)
        candidate = guarded.checked_bytes(layout.backup / entry['staged'])
        if candidate is None or guarded.sha(candidate) != entry['after']:
            raise guarded.ReleaseError('Staged content hash mismatch')
        staged.append(candidate)
    # Preflight failures must never enter recovery: this invocation has not
    # written anything and must preserve concurrent/preexisting installations.
    guarded.ensure_targets(entries, 'before')
    guarded.ensure_config(layout, manifest)
    guarded.gateway_state(layout, idle=True)
    attempted = []
    try:
        for entry, data, backup in zip(entries, staged, backups):
            target = Path(entry['target'])
            if guarded.fingerprint(target) != entry['before']:
                raise guarded.ReleaseError('Concurrent target change before write')
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            attempted.append((entry, backup))
            guarded.atomic(target, data, entry['after_mode'])
        guarded.ensure_targets(entries, 'after')
        guarded.ensure_config(layout, manifest)
        check_protected(layout)
        guarded.receipt(layout, 'applied.json', entries)
        return {'applied': True, 'targets': len(entries), 'config_preserved': True,
                'gateway_restarted': False}
    except Exception:
        if not attempted:
            raise
        if any(guarded.fingerprint(Path(entry['target'])) not in (entry['before'], entry['after'])
               for entry, _ in attempted):
            raise guarded.ReleaseError('Concurrent target change; recovery cannot overwrite it') from None
        for entry, data in reversed(attempted):
            target = Path(entry['target'])
            if guarded.fingerprint(target) == entry['before']:
                continue
            if guarded.fingerprint(target) != entry['after']:
                raise guarded.ReleaseError('Concurrent change during recovery') from None
            if data is None:
                target.unlink()
            else:
                guarded.atomic(target, data, entry['before_mode'])
        (layout.backup / 'applied.json').unlink(missing_ok=True)
        guarded.ensure_targets(entries, 'before')
        guarded.receipt(layout, 'failed-apply.json', entries)
        raise guarded.ReleaseError('Update failed; reviewed targets restored') from None


def rollback(layout=Layout()):
    return guarded.rollback(layout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'apply', 'rollback'))
    parser.add_argument('--read-recovery', action='store_true', help='Two-module follow-up; roll back this before the main release')
    args = parser.parse_args()
    print(json.dumps(globals()[args.action](ReadRecoveryLayout() if args.read_recovery else Layout())))


if __name__ == '__main__':
    main()
