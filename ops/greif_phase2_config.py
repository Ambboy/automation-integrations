# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Apply/rollback phase 2 after its real smoke. Never restarts services."""
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
import yaml

ROOT = Path('/home/operator/.local/share/automation-integrations/greif/phase2')
HOME = Path('/home/operator/.hermes')
PROJECT = Path('/home/operator/workspaces/automation-integrations')
PLUGIN = HOME / 'plugins/automation-speech-source'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    tmp = path.with_suffix(path.suffix + '.phase2-new')
    with tmp.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def main():
    os.umask(0o077)
    config = HOME / 'config.yaml'
    backup = ROOT / 'backup'
    if sys.argv[1:] == ['apply']:
        assert json.loads((ROOT / 'smoke-report.json').read_text())['passed']
        assert not PLUGIN.exists() and not backup.exists(), 'Existing deployment; inspect before changing'
        before = config.read_bytes()
        cfg = yaml.safe_load(before)
        provider = json.loads((ROOT / 'tts-provider.json').read_text())
        tts = cfg.setdefault('tts', {})
        tts['provider'] = 'automation-speech'
        tts.setdefault('providers', {})['automation-speech'] = provider['providers']['automation-speech']
        plugins = cfg.setdefault('plugins', {})
        plugins.setdefault('enabled', []).append('automation-speech-source')
        plugins.setdefault('entries', {})['automation-speech-source'] = {'settings': {
            'enabled': True, 'owner_id': '100001', 'state_dir': str(ROOT / 'sources')}}
        text = before.decode()
        for section in ['tts', 'plugins']:
            block = yaml.safe_dump({section: cfg[section]}, allow_unicode=True, sort_keys=False)
            pattern = rf'(?ms)^{section}:.*?(?=^[A-Za-z_][A-Za-z_0-9-]*:|\Z)'
            if re.search(pattern, text):
                text, count = re.subn(pattern, lambda _: block + '\n', text)
                assert count == 1
            else:
                text += '\n' + block
        assert yaml.safe_load(text) == cfg
        backup.mkdir(mode=0o700)
        (backup / 'config.yaml').write_bytes(before)
        (backup / 'manifest.json').write_text(json.dumps({'before': sha(before), 'after': sha(text.encode())}, indent=2))
        shutil.copytree(PROJECT / 'bridges/hermes_speech', PLUGIN, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(PROJECT / 'automation_integrations/speech_source.py', PLUGIN / 'speech_source.py')
        assert config.read_bytes() == before, 'Concurrent config edit; do not activate'
        atomic(config, text.encode())
    elif sys.argv[1:] == ['rollback']:
        manifest = json.loads((backup / 'manifest.json').read_text())
        assert sha(config.read_bytes()) == manifest['after'], 'Config changed; reconcile manually'
        atomic(config, (backup / 'config.yaml').read_bytes())
        # Keep the now-disabled plugin as evidence; config removes activation.
    else:
        raise SystemExit('Use apply or rollback')
    print('Configuration updated; gateway restart is a separate step')


if __name__ == '__main__':
    main()
