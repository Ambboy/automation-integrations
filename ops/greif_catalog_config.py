# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Guarded install/rollback on Kronstadt. Does not restart the gateway."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

import yaml

PROJECT = Path('/home/operator/workspaces/automation-integrations')
HOME = Path('/home/operator/.hermes')
ROOT = Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')
NAME = 'automation-api-catalog'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def render(before, root):
    cfg = yaml.safe_load(before)
    plugins = cfg.setdefault('plugins', {})
    if NAME not in plugins.setdefault('enabled', []):
        plugins['enabled'].append(NAME)
    plugins.setdefault('entries', {})[NAME] = {'settings': {
        'enabled': True, 'owner_id': '100001', 'chat_id': '100001',
        'catalog_path': str(root / 'release/catalog.json'),
        'runner_path': str(root / 'release/api_read.py'), 'private_config': str(root / 'private.json'),
        'state_dir': str(root / 'state')}}
    tools = cfg.setdefault('platform_toolsets', {}).setdefault('telegram', [])
    if 'automation-api' not in tools:
        tools.append('automation-api')
    text = before.decode()
    for section in ('plugins', 'platform_toolsets'):
        block = yaml.safe_dump({section: cfg[section]}, allow_unicode=True, sort_keys=False)
        pattern = rf'(?ms)^{section}:.*?(?=^[A-Za-z_][A-Za-z_0-9-]*:|\Z)'
        if re.search(pattern, text):
            text, count = re.subn(pattern, lambda _: block + '\n', text); assert count == 1
        else:
            text += '\n' + block
    assert yaml.safe_load(text) == cfg
    return text.encode()


def atomic(path, data):
    tmp = path.with_name(path.name + '.catalog-new')
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def main():
    os.umask(0o077)
    config = HOME / 'config.yaml'; backup = ROOT / 'backup'; plugin = HOME / 'plugins' / NAME
    if sys.argv[1:] == ['apply']:
        assert not backup.exists() and not plugin.exists(), 'Inspect existing deployment'
        assert (ROOT / 'private.json').is_file()
        assert json.loads((ROOT / 'validation.json').read_text())['passed']
        before = config.read_bytes(); after = render(before, ROOT)
        backup.mkdir(mode=0o700)
        (backup / 'config.yaml').write_bytes(before)
        (backup / 'manifest.json').write_text(json.dumps({'before': sha(before), 'after': sha(after)}))
        release = ROOT / 'release'; release.mkdir(mode=0o700)
        shutil.copyfile(PROJECT / 'automation_integrations/api_read.py', release / 'api_read.py')
        for name in ('api_write.py', 'yandex_contract.py', 'extended_api.py', 'confirmed_write.py', 'openapi_contract.py', 'documented_contract.py', 'wirenboard.py', 'wirenboard_http.py', 'wirenboard_control_contract.py', 'wirenboard_shell.py', 'wirenboard_control.py'):
            shutil.copyfile(PROJECT / 'automation_integrations' / name, release / name)
        for name in ('etm_authorization.py', 'etm_document.py', 'etm_order.py', 'etm_workflow.py'):
            shutil.copyfile(PROJECT / 'automation_integrations' / name, release / name)
        for name in ('media_api.py', 'media_runtime.py', 'media_files.py', 'fal_media.py', 'inference_media.py'):
            shutil.copyfile(PROJECT / 'automation_integrations' / name, release / name)
        shutil.copyfile(PROJECT / 'registry/catalog.json', release / 'catalog.json')
        shutil.copytree(PROJECT / 'registry/capabilities', release / 'capabilities')
        shutil.copytree(PROJECT / 'registry/contracts', release / 'contracts')
        shutil.copytree(PROJECT / 'bridges/hermes_catalog', plugin, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(PROJECT / 'automation_integrations/catalog.py', plugin / 'catalog.py')
        assert config.read_bytes() == before, 'Concurrent configuration change'
        atomic(config, after)
    elif sys.argv[1:] == ['rollback']:
        manifest = json.loads((backup / 'manifest.json').read_text())
        assert sha(config.read_bytes()) == manifest['after'], 'Config changed; reconcile later edits'
        atomic(config, (backup / 'config.yaml').read_bytes())
        # Removing from plugins.enabled is not enough: local plugins may auto-load.
        if plugin.exists():
            plugin.rename(ROOT / 'disabled-plugin')
    else:
        raise SystemExit('Use apply or rollback')
    print('Catalog configuration updated. Restart gateway separately when idle.')


if __name__ == '__main__':
    main()
