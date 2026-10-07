# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Stage/apply/rollback only the Wiren Board integration release; never restart Hermes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1]
HERMES_HOME = Path('/home/operator/.hermes')
ROOT = Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')
BACKUP = ROOT / 'update-20261004-wirenboard'


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class Layout:
    source: Path = SOURCE
    home: Path = HERMES_HOME
    root: Path = ROOT
    backup: Path = BACKUP

    @property
    def config(self) -> Path:
        return self.home / 'config.yaml'

    @property
    def gateway(self) -> Path:
        return self.home / 'gateway_state.json'

    def targets(self) -> list[tuple[Path, Path]]:
        release = self.root / 'release'
        plugin = self.home / 'plugins/automation-api-catalog'
        # Install dependencies before the runner; publish catalog and plugin last.
        return [
            (self.source / 'automation_integrations' / name, release / name)
            for name in ('wirenboard_http.py', 'wirenboard.py', 'api_read.py')
        ] + [
            (self.source / 'registry/capabilities/wirenboard.json', release / 'capabilities/wirenboard.json'),
            (self.source / 'registry/catalog.json', release / 'catalog.json'),
            (self.backup / 'candidate-private.json', self.root / 'private.json'),
            (self.source / 'bridges/hermes_catalog/__init__.py', plugin / '__init__.py'),
            (self.source / 'bridges/hermes_catalog/plugin.yaml', plugin / 'plugin.yaml'),
        ]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_bytes(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ReleaseError('Refusing a symlink release target or artifact')
    if not path.exists():
        return None
    if not path.is_file():
        raise ReleaseError('Expected a regular release file')
    return path.read_bytes()


def fingerprint(path: Path) -> str | None:
    data = checked_bytes(path)
    return sha(data) if data is not None else None


def atomic(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Write in the same directory and fsync both file and directory."""
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def gateway_state(layout: Layout, *, idle: bool = False) -> dict:
    data = checked_bytes(layout.gateway)
    if data is None:
        raise ReleaseError('Gateway state is missing')
    state = json.loads(data)
    if not isinstance(state, dict):
        raise ReleaseError('Gateway state must be an object')
    if idle and (type(state.get('active_agents')) is not int or state['active_agents'] != 0):
        raise ReleaseError('Gateway must have zero active agents')
    return state


def prepare(layout: Layout = Layout()) -> dict:
    os.umask(0o077)
    manifest_path = layout.backup / 'manifest.json'
    if manifest_path.exists() or manifest_path.is_symlink():
        raise ReleaseError('A release manifest already exists; inspect the recorded release')
    if layout.backup.is_symlink():
        raise ReleaseError('Refusing a symlink backup directory')
    for directory in ('backups', 'staged'):
        if (layout.backup / directory).exists():
            raise ReleaseError('Release staging already exists; inspect before retrying')
    config_sha = fingerprint(layout.config)
    if config_sha is None:
        raise ReleaseError('Hermes config is missing')
    state = gateway_state(layout)
    # Read all inputs before creating any staging artifacts.
    snapshots = []
    for source, target in layout.targets():
        new = checked_bytes(source)
        if new is None:
            raise ReleaseError('A required release source is missing')
        old = checked_bytes(target)
        mode = stat.S_IMODE(target.stat().st_mode) if old is not None else None
        snapshots.append((target, old, new, mode))
    layout.backup.mkdir(mode=0o700, parents=True, exist_ok=True)
    layout.backup.chmod(0o700)
    (layout.backup / 'backups').mkdir(mode=0o700)
    (layout.backup / 'staged').mkdir(mode=0o700)
    entries = []
    for index, (target, old, new, mode) in enumerate(snapshots):
        backup_name = f'backups/{index:02d}' if old is not None else None
        staged_name = f'staged/{index:02d}'
        if backup_name is not None:
            atomic(layout.backup / backup_name, old)
        atomic(layout.backup / staged_name, new)
        entries.append({
            'target': str(target), 'backup': backup_name, 'staged': staged_name,
            'before': sha(old) if old is not None else None, 'after': sha(new),
            'before_mode': mode,
            'after_mode': 0o600 if target == layout.root / 'private.json' else (mode if mode is not None else 0o600),
        })
    manifest = {
        'schema_version': 1, 'prepared_at': timestamp(), 'config_sha': config_sha,
        'gateway_before': state, 'entries': entries,
    }
    atomic(manifest_path, json_bytes(manifest))
    return {'prepared': True, 'targets': len(entries), 'installed_files_changed': False}


def load_manifest(layout: Layout) -> dict:
    raw = checked_bytes(layout.backup / 'manifest.json')
    if raw is None:
        raise ReleaseError('Prepare the release first')
    manifest = json.loads(raw)
    entries = manifest.get('entries', [])
    expected = [str(target) for _, target in layout.targets()]
    if manifest.get('schema_version') != 1 or [e.get('target') for e in entries] != expected:
        raise ReleaseError('Manifest does not match the exact Wiren Board target allowlist')
    for index, entry in enumerate(entries):
        if entry.get('staged') != f'staged/{index:02d}':
            raise ReleaseError('Invalid staged artifact path')
        expected_backup = f'backups/{index:02d}' if entry.get('before') is not None else None
        if entry.get('backup') != expected_backup:
            raise ReleaseError('Invalid backup artifact path')
    return manifest


def ensure_targets(entries: list[dict], expected: str) -> None:
    # Complete this pass for every target BEFORE changing the first target.
    for entry in entries:
        if fingerprint(Path(entry['target'])) != entry[expected]:
            raise ReleaseError('Concurrent installed file change; no release files were written')


def ensure_config(layout: Layout, manifest: dict) -> None:
    if fingerprint(layout.config) != manifest['config_sha']:
        raise ReleaseError('Hermes config changed; no release files were written')


def receipt(layout: Layout, name: str, entries: list[dict]) -> None:
    atomic(layout.backup / name, json_bytes({'completed_at': timestamp(), 'targets': len(entries)}))


def apply(layout: Layout = Layout()) -> dict:
    os.umask(0o077)
    if (layout.backup / 'applied.json').exists():
        raise ReleaseError('This release already has an apply receipt')
    manifest = load_manifest(layout)
    entries = manifest['entries']
    ensure_targets(entries, 'before')
    ensure_config(layout, manifest)
    gateway_state(layout, idle=True)
    staged = []
    for entry in entries:
        data = checked_bytes(layout.backup / entry['staged'])
        if data is None or sha(data) != entry['after']:
            raise ReleaseError('Staged content changed; no release files were written')
        staged.append(data)
    ensure_targets(entries, 'before')
    ensure_config(layout, manifest)
    gateway_state(layout, idle=True)
    for entry, data in zip(entries, staged):
        target = Path(entry['target'])
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic(target, data, entry['after_mode'])
    ensure_targets(entries, 'after')
    if fingerprint(layout.config) != manifest['config_sha']:
        raise ReleaseError('Hermes config changed during apply; config was not overwritten')
    receipt(layout, 'applied.json', entries)
    return {'applied': True, 'targets': len(entries), 'config_preserved': True, 'gateway_restarted': False}


def rollback(layout: Layout = Layout()) -> dict:
    os.umask(0o077)
    if (layout.backup / 'rollback.json').exists():
        raise ReleaseError('This release already has a rollback receipt')
    manifest = load_manifest(layout)
    entries = manifest['entries']
    ensure_targets(entries, 'after')
    gateway_state(layout, idle=True)
    # Config is never a rollback target; preserve even unrelated later edits.
    config_before = fingerprint(layout.config)
    backups = []
    for entry in entries:
        data = checked_bytes(layout.backup / entry['backup']) if entry['backup'] else None
        if (sha(data) if data is not None else None) != entry['before']:
            raise ReleaseError('Backup content changed; no release files were written')
        backups.append(data)
    ensure_targets(entries, 'after')
    gateway_state(layout, idle=True)
    for entry, data in zip(entries, backups):
        target = Path(entry['target'])
        if data is None:
            target.unlink()
        else:
            atomic(target, data, entry['before_mode'])
    ensure_targets(entries, 'before')
    if fingerprint(layout.config) != config_before:
        raise ReleaseError('Hermes config changed during rollback; config was not overwritten')
    receipt(layout, 'rollback.json', entries)
    return {'rolled_back': True, 'targets': len(entries), 'config_preserved': True, 'gateway_restarted': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'apply', 'rollback'))
    args = parser.parse_args()
    try:
        result = {'prepare': prepare, 'apply': apply, 'rollback': rollback}[args.action]()
    except ReleaseError as exc:
        raise SystemExit(str(exc)) from None
    except (OSError, ValueError, KeyError, TypeError):
        # Do not expose private configuration or gateway content through errors.
        raise SystemExit('Release guard rejected the action; inspect target/config/staging hashes and gateway idle state.')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
