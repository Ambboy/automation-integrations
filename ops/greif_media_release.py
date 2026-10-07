# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Add fal/inference to the existing catalog; frozen, CAS-guarded release/rollback."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT = Path('/home/operator/workspaces/automation-integrations')
HOME = Path('/home/operator/.hermes')
ROOT = Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')
RELEASE = ROOT / 'update-20261004-media' / 'deployment'
MODULES = ('media_api.py', 'media_runtime.py', 'media_files.py', 'fal_media.py', 'inference_media.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.media-release-tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def destinations(project=PROJECT, root=ROOT, home=HOME):
    plugin = home / 'plugins/automation-api-catalog'
    pairs = {project / 'automation_integrations' / name: root / 'release' / name
             for name in (*MODULES, 'api_read.py', 'api_write.py')}
    pairs[project / 'automation_integrations/catalog.py'] = plugin / 'catalog.py'
    pairs[project / 'registry/catalog.json'] = root / 'release/catalog.json'
    pairs.update({project / 'bridges/hermes_catalog' / n: plugin / n
                  for n in ('__init__.py', 'plugin.yaml')})
    for category in ('capabilities', 'contracts'):
        for service in ('fal', 'inference'):
            pairs[project / 'registry' / category / (service + '.json')] = root / 'release' / category / (service + '.json')
    return pairs


def prepare(project=PROJECT, root=ROOT, home=HOME, release=RELEASE, *, limits=None):
    if (release / 'manifest.json').exists():
        raise ValueError('release_already_prepared')
    pairs = destinations(project, root, home)
    payloads = [(str(source), target, source.read_bytes()) for source, target in pairs.items()]
    private_path = root / 'private.json'
    private = json.loads(private_path.read_text())
    # Reuse the already verified canonical Vaultwarden item. No credential value
    # enters the registry, release source, command line or manifest.
    items = private.setdefault('item_ids', {})
    for service in ('fal', 'inference'):
        if service in items and items[service] != 'e06835f1-a55f-48df-b433-b71b3c53f551':
            raise ValueError('existing_media_credential_binding_requires_review')
        items[service] = 'e06835f1-a55f-48df-b433-b71b3c53f551'
    private['media_authorization'] = 'owner_command'
    if limits is not None:
        private['media_limits'] = limits
    payloads.append(('generated_private_config', private_path,
                     (json.dumps(private, ensure_ascii=False, indent=2) + '\n').encode()))
    release.mkdir(mode=0o700, parents=True, exist_ok=True)
    entries = []
    for index, (source, target, after) in enumerate(payloads):
        before = target.read_bytes() if target.exists() else None
        if before is not None:
            atomic(release / f'{index}.before', before)
        atomic(release / f'{index}.after', after)
        entries.append({'source': source, 'target': str(target), 'index': index,
                        'before': sha(before) if before is not None else None,
                        'after': sha(after)})
    changed = {entry['target'] for entry in entries}
    protected = {}
    for directory in (root / 'release', home / 'plugins/automation-api-catalog',
                      home / 'plugins/automation-speech-source', home / 'plugins/automation-topic-style'):
        if directory.exists():
            for path in directory.rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts and str(path) not in changed:
                    protected[str(path)] = sha(path.read_bytes())
    protected[str(home / 'config.yaml')] = sha((home / 'config.yaml').read_bytes())
    manifest = {'entries': entries, 'protected': protected}
    atomic(release / 'manifest.json', json.dumps(manifest, indent=2).encode())
    return {'prepared': len(entries), 'protected': len(protected)}


def apply(release=RELEASE, *, rollback=False):
    manifest = json.loads((release / 'manifest.json').read_text())
    for path, expected in manifest['protected'].items():
        if not Path(path).exists() or sha(Path(path).read_bytes()) != expected:
            raise ValueError('protected_file_changed: ' + path)
    for entry in manifest['entries']:
        target = Path(entry['target'])
        actual = sha(target.read_bytes()) if target.exists() else None
        expected = entry['after'] if rollback else entry['before']
        if actual != expected:
            raise ValueError('concurrent_target_change: ' + str(target))
        blob = release / (str(entry['index']) + ('.before' if rollback else '.after'))
        wanted = entry['before'] if rollback else entry['after']
        if wanted is not None and sha(blob.read_bytes()) != wanted:
            raise ValueError('release_snapshot_changed')
    for entry in manifest['entries']:
        target = Path(entry['target'])
        if rollback and entry['before'] is None:
            target.unlink()
        else:
            atomic(target, (release / (str(entry['index']) + ('.before' if rollback else '.after'))).read_bytes())
    for entry in manifest['entries']:
        target = Path(entry['target'])
        if (sha(target.read_bytes()) if target.exists() else None) != entry['before' if rollback else 'after']:
            raise ValueError('installed_hash_mismatch')
    return {'rolled_back' if rollback else 'installed': len(manifest['entries'])}


def fix_reader(project=PROJECT, root=ROOT, release=RELEASE):
    """One guarded runner correction; each invocation starts a fresh process."""
    patch = release / 'reader-fix'
    if patch.exists():
        raise ValueError('reader_fix_already_recorded')
    manifest = json.loads((release / 'manifest.json').read_text())
    target = root / 'release/api_read.py'
    entry = next(row for row in manifest['entries'] if row['target'] == str(target))
    before, after = target.read_bytes(), (project / 'automation_integrations/api_read.py').read_bytes()
    if sha(before) != entry['after']:
        raise ValueError('reader_changed_concurrently')
    patch.mkdir(mode=0o700)
    atomic(patch / '0.before', before)
    atomic(patch / '0.after', after)
    atomic(patch / 'manifest.json', json.dumps({'entries': [{'target': str(target), 'index': 0,
        'before': sha(before), 'after': sha(after)}], 'protected': manifest['protected']}, indent=2).encode())
    return apply(patch)


def main():
    os.umask(0o077)
    action = sys.argv[1] if len(sys.argv) == 2 else ''
    if action == 'prepare':
        result = prepare()
    elif action == 'fix-reader':
        result = fix_reader()
    elif action in ('apply', 'rollback'):
        state = subprocess.run(['systemctl', 'is-active', 'hermes-gateway.service'], capture_output=True, text=True)
        if state.stdout.strip() not in ('inactive', 'failed'):
            raise SystemExit('Stop the idle gateway before applying the prepared release.')
        if action == 'rollback' and (RELEASE / 'reader-fix/manifest.json').exists():
            apply(RELEASE / 'reader-fix', rollback=True)
        result = apply(rollback=action == 'rollback')
    else:
        raise SystemExit('Use prepare, apply, fix-reader or rollback')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
