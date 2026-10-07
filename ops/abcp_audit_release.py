"""CAS ABCP audit update or instruction-only catalog patch; no gateway restart."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


ADAPTER_FILES = ('automation_integrations/abcp_api.py', 'registry/contracts/abcp.json',
                 'registry/capabilities/abcp.json')
CATALOG_FILES = ('registry/catalog.json',)
FILES = ADAPTER_FILES


class GuardError(RuntimeError):
    pass


def read(path):
    path = Path(path)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise GuardError('symlink_rejected')
    if not path.is_file():
        raise GuardError('required_file_missing')
    return path.read_bytes()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data, mode=0o600):
    path = Path(path)
    if path.exists():
        read(path)
    elif path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise GuardError('symlink_rejected')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.audit-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def idle(home):
    state = json.loads(read(home / 'gateway_state.json'))
    if (type(state.get('active_agents')) is not int or state['active_agents'] != 0
            or state.get('active_work') or state.get('restart_requested') is not False
            or state.get('gateway_state') != 'running'):
        raise GuardError('gateway_not_idle')
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(state['updated_at'])).total_seconds()
    except (KeyError, TypeError, ValueError):
        raise GuardError('gateway_state_invalid') from None
    if not -5 <= age <= 60:
        raise GuardError('gateway_state_stale')
    return {'pid': state.get('pid'), 'code_sha': state.get('code_sha')}


def protected(home, root):
    paths = [home / 'config.yaml', root / 'config.json', root / 'credentials.env',
             root / 'release/registry/catalog.json', root / 'release/automation_integrations/abcp_write.py']
    paths += [path for path in (home / 'plugins').rglob('*')
              if path.is_file() and '__pycache__' not in path.parts]
    # A navigation release has one different fixed target; preserve every
    # adapter/schema from the earlier release while changing that catalog.
    paths += [root / 'release' / rel for rel in ADAPTER_FILES if rel not in FILES]
    targets = {root / 'release' / rel for rel in FILES}
    paths = [path for path in paths if path not in targets]
    return {str(path): sha(read(path)) for path in sorted(paths)}


def validate_navigation(old, new):
    before, after = json.loads(old), json.loads(new)
    for catalog in (before, after):
        if (not isinstance(catalog, dict) or not isinstance(catalog.get('services'), list)
                or len(catalog['services']) != 1 or catalog['services'][0].get('id') != 'abcp'):
            raise GuardError('invalid_abcp_catalog')
    previous, current = [], []
    for catalog, instructions in ((before, previous), (after, current)):
        instructions.extend([catalog.pop('instructions', None), catalog['services'][0].pop('instructions', None)])
    if before != after:
        raise GuardError('catalog_change_outside_instructions')
    if (any(not isinstance(value, str) for value in previous + current)
            or current[0] != current[1]
            or any(not new_value.startswith(old_value + ' ') for old_value, new_value in zip(previous, current))):
        raise GuardError('catalog_instruction_change_invalid')


@contextmanager
def locked(root):
    path = root / '.release.lock'
    if path.exists() or path.is_symlink():
        read(path)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a+b') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise GuardError('release_lock_busy') from None
        yield


def prepare(source, backup, home, root):
    with locked(root):
        if backup.exists():
            raise GuardError('backup_already_exists')
        expected = json.loads(read(source / 'expected.json'))
        if set(expected) != set(FILES):
            raise GuardError('invalid_expected_files')
        gateway = idle(home)
        protection = protected(home, root)
        entries, contents = [], []
        for rel in FILES:
            target = root / 'release' / rel
            old, new = read(target), read(source / rel)
            if sha(old) != expected[rel]:
                raise GuardError('installed_file_changed')
            if rel.endswith('.py'):
                compile(new, rel, 'exec')
            else:
                json.loads(new)
            if FILES == CATALOG_FILES:
                validate_navigation(old, new)
            entries.append({'file': rel, 'before': sha(old), 'after': sha(new),
                            'mode': stat.S_IMODE(target.stat().st_mode)})
            contents.append((rel, old, new))
        backup.mkdir(mode=0o700, parents=False)
        for rel, old, new in contents:
            atomic(backup / 'before' / rel, old)
            atomic(backup / 'after' / rel, new)
        manifest = {'version': 1, 'entries': entries, 'protected': protection, 'gateway': gateway}
        atomic(backup / 'manifest.json', encoded(manifest))
        atomic(backup / 'release.py', read(Path(__file__)))
        return {'prepared': True, 'targets': len(entries)}


def transition(backup, home, root, *, rollback=False):
    with locked(root):
        manifest = json.loads(read(backup / 'manifest.json'))
        entries = manifest.get('entries', [])
        if manifest.get('version') != 1 or [row.get('file') for row in entries] != list(FILES):
            raise GuardError('manifest_allowlist_mismatch')
        receipt = backup / ('rollback.json' if rollback else 'applied.json')
        # A crash after the last replacement can precede the applied receipt.
        # The exact all-file CAS below still permits recovery in that case.
        if receipt.exists():
            raise GuardError('release_action_invalid')
        before, after = ('after', 'before') if rollback else ('before', 'after')

        def guards():
            if protected(home, root) != manifest['protected']:
                raise GuardError('protected_file_changed')
            if idle(home) != manifest['gateway']:
                raise GuardError('gateway_identity_changed')

        guards()
        pending = []
        for row in entries:
            target = root / 'release' / row['file']
            old, new = read(target), read(backup / after / row['file'])
            if sha(old) != row[before] or sha(new) != row[after]:
                raise GuardError('cas_or_artifact_mismatch')
            if type(row['mode']) is not int or not 0 <= row['mode'] <= 0o777:
                raise GuardError('manifest_mode_invalid')
            pending.append((row, target, old, new))
        changed = []
        try:
            for row, target, old, new in pending:
                guards()
                if sha(read(target)) != row[before]:
                    raise GuardError('installed_file_changed')
                changed.append((row, target, old))
                atomic(target, new, row['mode'])
            guards()
            if any(sha(read(target)) != row[after] for row, target, _, _ in pending):
                raise GuardError('post_install_hash_mismatch')
        except Exception:
            for row, target, old in reversed(changed):
                current = sha(read(target))
                if current == row[before]:
                    continue
                if current != row[after]:
                    raise GuardError('recovery_concurrent_change') from None
                atomic(target, old, row['mode'])
            raise
        result = {'rolled_back' if rollback else 'applied': True, 'targets': len(entries),
                  'gateway_restarted': False, 'protected_files_unchanged': True,
                  'checked_at': datetime.now(timezone.utc).isoformat(),
                  'files': {row['file']: row[after] for row in entries}}
        atomic(receipt, encoded(result))
        return result


def main():
    global FILES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'apply', 'rollback'))
    parser.add_argument('--source', type=Path)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--home', type=Path, default=Path.home() / '.hermes')
    parser.add_argument('--root', type=Path, default=Path.home() / '.local/share/automation-integrations/abcp')
    parser.add_argument('--catalog-navigation', action='store_true',
                        help='Only the ABCP catalog, with differences restricted to its two instructions fields')
    args = parser.parse_args()
    FILES = CATALOG_FILES if args.catalog_navigation else ADAPTER_FILES
    os.umask(0o077)
    try:
        if args.action == 'prepare':
            if args.source is None:
                raise GuardError('source_required')
            result = prepare(args.source.absolute(), args.backup.absolute(), args.home.absolute(), args.root.absolute())
        else:
            result = transition(args.backup.absolute(), args.home.absolute(), args.root.absolute(),
                                rollback=args.action == 'rollback')
    except GuardError as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1
    except Exception:
        print(json.dumps({'ok': False, 'error': 'release_failed'}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
