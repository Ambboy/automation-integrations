"""Guarded ABCP-only native-plugin installation; never restarts Hermes.

The source is an isolated bundle, not the shared multi-service registry. Private
config.json and credentials.env must already exist outside the bundle. This
installer changes only owned release files, the catalog plugin, and its config.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

import yaml


NAME = 'automation-api-catalog'
OWNER = '999000111'


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class Layout:
    source: Path
    home: Path
    root: Path
    backup: Path

    @property
    def config(self):
        return self.home / 'config.yaml'

    @property
    def plugin(self):
        return self.home / 'plugins' / NAME


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def read(path):
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ReleaseError('Symlinks are not allowed in release paths')
    if not path.exists():
        return None
    if not path.is_file():
        raise ReleaseError('Expected a regular file')
    return path.read_bytes()


def atomic(path, data, mode=0o600):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    read(path)  # Check symlinks immediately before replacement.
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


def encoded(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()


@contextmanager
def locked(layout):
    os.umask(0o077)
    layout.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = layout.root / '.release.lock'
    read(path)
    with path.open('a+b') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ReleaseError('Another ABCP release operation holds the lock') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def render(before, root):
    cfg = yaml.safe_load(before)
    if not isinstance(cfg, dict):
        raise ReleaseError('Hermes config must be an object')
    plugins = cfg.setdefault('plugins', {})
    if NAME not in plugins.setdefault('enabled', []):
        plugins['enabled'].append(NAME)
    entry = plugins.setdefault('entries', {}).setdefault(NAME, {})
    previous = entry.get('settings', {})
    if previous and previous.get('private_config') != str(root / 'config.json'):
        raise ReleaseError('An unrelated API catalog plugin is already configured')
    entry['settings'] = {**previous,
        'enabled': True, 'owner_id': OWNER, 'chat_id': OWNER,
        'catalog_path': str(root / 'release/registry/catalog.json'),
        'runner_path': str(root / 'release/automation_integrations/abcp_api.py'),
        'write_runner_path': str(root / 'release/automation_integrations/abcp_write.py'),
        'private_config': str(root / 'config.json'), 'state_dir': str(root / 'state'),
        'max_request_chars': 2097152, 'max_write_request_chars': 2097152,
        'max_read_output_chars': 100000, 'max_write_output_chars': 100000}
    toolsets = cfg.setdefault('platform_toolsets', {}).setdefault('telegram', ['hermes-telegram'])
    if 'automation-api' not in toolsets:
        toolsets.append('automation-api')
    text = before.decode('utf-8')
    for section in ('plugins', 'platform_toolsets'):
        block = yaml.safe_dump({section: cfg[section]}, allow_unicode=True, sort_keys=False)
        pattern = rf'(?ms)^{section}:.*?(?=^[A-Za-z_][A-Za-z_0-9-]*:|\Z)'
        if re.search(pattern, text):
            text, count = re.subn(pattern, lambda _: block + '\n', text)
            if count != 1:
                raise ReleaseError('Duplicate config section')
        else:
            text += '\n' + block
    if yaml.safe_load(text) != cfg:
        raise ReleaseError('Config rendering changed unrelated settings')
    return text.encode('utf-8')


def bundle_files(layout):
    fixed = ['automation_integrations/__init__.py', 'automation_integrations/catalog.py',
             'automation_integrations/abcp_api.py', 'automation_integrations/abcp_write.py',
             'registry/catalog.json', 'registry/capabilities/abcp.json', 'registry/contracts/abcp.json']
    optional = [str(p.relative_to(layout.source)) for p in
                (layout.source / 'automation_integrations').glob('abcp*.py')]
    paths = sorted(set(fixed + optional))
    pairs = [(layout.source / name, layout.root / 'release' / name) for name in paths]
    pairs += [(layout.source / 'automation_integrations/catalog.py', layout.plugin / 'catalog.py')]
    pairs += [(layout.source / 'bridges/hermes_catalog' / name, layout.plugin / name)
              for name in ('__init__.py', 'plugin.yaml')]
    return pairs


def allowed_target(layout, target):
    if target == layout.config:
        return True
    if target.parent == layout.plugin and target.name in ('catalog.py', '__init__.py', 'plugin.yaml'):
        return True
    try:
        relative = str(target.relative_to(layout.root / 'release'))
    except ValueError:
        return False
    return bool(re.fullmatch(r'automation_integrations/(?:__init__|catalog|abcp[a-z_0-9]*)\.py', relative)
                or relative in ('registry/catalog.json', 'registry/capabilities/abcp.json',
                                'registry/contracts/abcp.json'))


def idle(layout):
    raw = read(layout.home / 'gateway_state.json')
    if raw is None:
        raise ReleaseError('Gateway state is missing; inspect the gateway before installation')
    state = json.loads(raw)
    if type(state.get('active_agents')) is not int or state['active_agents'] != 0:
        raise ReleaseError('Gateway must have zero active agents')


def prepare(layout):
    with locked(layout):
        if layout.backup.exists():
            raise ReleaseError('Backup directory already exists; inspect the previous release')
        before = read(layout.config)
        if before is None:
            raise ReleaseError('Hermes config is missing')
        private = read(layout.root / 'config.json')
        if private is None or not isinstance(json.loads(private), dict):
            raise ReleaseError('Private ABCP config must already exist')
        if stat.S_IMODE((layout.root / 'config.json').stat().st_mode) & 0o077:
            raise ReleaseError('Private ABCP config must not be accessible to group or others')
        catalog = json.loads(read(layout.source / 'registry/catalog.json') or b'{}')
        if catalog.get('schema_version') != 1 or [s.get('id') for s in catalog.get('services', [])] != ['abcp']:
            raise ReleaseError('The bundle must contain an ABCP-only catalog')
        if not catalog.get('agent_name') or not catalog.get('instructions'):
            raise ReleaseError('The ABCP catalog must provide agent_name and instructions')
        config_after = render(before, layout.root)
        if layout.plugin.exists():
            old_settings = yaml.safe_load(before).get('plugins', {}).get('entries', {}).get(NAME, {}).get('settings', {})
            if old_settings.get('private_config') != str(layout.root / 'config.json'):
                raise ReleaseError('Refusing to replace an unowned catalog plugin')
        snapshots = []
        for source, target in bundle_files(layout):
            new = read(source)
            if new is None or not allowed_target(layout, target):
                raise ReleaseError('Required bundle source is missing or outside the allowlist')
            snapshots.append((target, read(target), new))
        snapshots.append((layout.config, before, config_after))
        layout.backup.mkdir(mode=0o700, parents=True)
        entries = []
        for index, (target, old, new) in enumerate(snapshots):
            backup = f'backups/{index:03d}' if old is not None else None
            staged = f'staged/{index:03d}'
            if backup:
                atomic(layout.backup / backup, old)
            atomic(layout.backup / staged, new)
            entries.append({'target': str(target), 'before': digest(old), 'after': digest(new),
                            'backup': backup, 'staged': staged,
                            'before_mode': stat.S_IMODE(target.stat().st_mode) if old is not None else None,
                            'after_mode': stat.S_IMODE(target.stat().st_mode) if old is not None else 0o600})
        atomic(layout.backup / 'manifest.json', encoded({'schema_version': 1, 'entries': entries,
               'prepared_at': datetime.now(timezone.utc).isoformat()}))
        return {'prepared': True, 'targets': len(entries), 'installed_files_changed': False,
                'gateway_restarted': False}


def load_manifest(layout):
    raw = read(layout.backup / 'manifest.json')
    if raw is None:
        raise ReleaseError('Prepare the release first')
    manifest = json.loads(raw)
    entries = manifest.get('entries', [])
    required = {str(t) for _, t in bundle_files(layout) if not t.name.startswith('abcp')}
    required |= {str(layout.config), str(layout.root / 'release/automation_integrations/abcp_api.py'),
                 str(layout.root / 'release/automation_integrations/abcp_write.py'),
                 str(layout.root / 'release/registry/capabilities/abcp.json'),
                 str(layout.root / 'release/registry/contracts/abcp.json')}
    targets = [e.get('target', '') for e in entries]
    if (manifest.get('schema_version') != 1 or len(entries) > 50 or len(set(targets)) != len(targets)
            or not required.issubset(targets) or not entries or targets[-1] != str(layout.config)):
        raise ReleaseError('Invalid ABCP release manifest')
    for index, entry in enumerate(entries):
        if (not allowed_target(layout, Path(entry['target'])) or entry.get('staged') != f'staged/{index:03d}'
                or entry.get('backup') != (f'backups/{index:03d}' if entry.get('before') is not None else None)):
            raise ReleaseError('Manifest does not match the ABCP target allowlist')
        for field in ('before_mode', 'after_mode'):
            if entry[field] is not None and (type(entry[field]) is not int or not 0 <= entry[field] <= 0o777):
                raise ReleaseError('Invalid file mode in release manifest')
    return entries


def ensure_targets(entries, expected):
    for entry in entries:
        if digest(read(Path(entry['target']))) != entry[expected]:
            raise ReleaseError('Concurrent installed file/config change; release rejected')


def transition(layout, *, undo):
    with locked(layout):
        receipt = layout.backup / ('rollback.json' if undo else 'applied.json')
        if receipt.exists():
            raise ReleaseError('This release action already completed')
        if undo and not (layout.backup / 'applied.json').exists():
            raise ReleaseError('Only an applied release can be rolled back')
        entries = load_manifest(layout)
        expected, desired, artifact = ('after', 'before', 'backup') if undo else ('before', 'after', 'staged')
        ensure_targets(entries, expected)
        idle(layout)
        contents = []
        for entry in entries:
            data = read(layout.backup / entry[artifact]) if entry[artifact] else None
            if digest(data) != entry[desired]:
                raise ReleaseError('Staged or backup content changed; release rejected')
            contents.append(data)
        ensure_targets(entries, expected)
        idle(layout)
        changed = []
        try:
            sequence = list(zip(entries, contents))
            if undo:
                sequence.reverse()
            for entry, data in sequence:
                target = Path(entry['target'])
                # CAS is repeated at each replacement, after the all-target preflight.
                if digest(read(target)) != entry[expected]:
                    raise ReleaseError('Concurrent file change during release')
                old = read(target)
                old_mode = stat.S_IMODE(target.stat().st_mode) if old is not None else None
                if data is None:
                    target.unlink()
                else:
                    atomic(target, data, entry[desired + '_mode'])
                changed.append((target, old, old_mode, digest(data)))
            ensure_targets(entries, desired)
        except Exception:
            for target, old, mode, after in reversed(changed):
                if digest(read(target)) != after:
                    raise ReleaseError('Concurrent modification during recovery; inspect the release manifest') from None
                if old is None:
                    target.unlink(missing_ok=True)
                else:
                    atomic(target, old, mode)
            raise
        if not undo:
            (layout.root / 'state').mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic(receipt, encoded({'completed_at': datetime.now(timezone.utc).isoformat(), 'targets': len(entries)}))
        return {'rolled_back' if undo else 'applied': True, 'targets': len(entries),
                'gateway_restarted': False, 'private_config_preserved': True}


def apply(layout):
    return transition(layout, undo=False)


def rollback(layout):
    return transition(layout, undo=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'apply', 'rollback'))
    parser.add_argument('--source', type=Path, required=True, help='Isolated ABCP bundle')
    parser.add_argument('--home', type=Path, default=Path.home() / '.hermes')
    parser.add_argument('--root', type=Path, default=Path.home() / '.local/share/automation-integrations/abcp')
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    layout = Layout(args.source.absolute(), args.home.absolute(), args.root.absolute(),
                    (args.backup or args.root / 'install-20261005-abcp').absolute())
    try:
        result = {'prepare': prepare, 'apply': apply, 'rollback': rollback}[args.action](layout)
    except ReleaseError as exc:
        raise SystemExit(str(exc)) from None
    except (OSError, ValueError, TypeError, KeyError):
        raise SystemExit('ABCP release rejected; inspect paths, hashes and config structure') from None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
