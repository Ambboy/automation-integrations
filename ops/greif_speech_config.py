# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Explicit, guarded configuration apply/rollback; never restarts any service."""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path('/home/operator/.local/share/automation-integrations/greif')
HOME = Path('/home/operator/.hermes')
BACKUP = ROOT / 'backups/20261003-before-voice'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    temp = path.with_name(path.name + '.speech-new')
    with temp.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def main():
    os.umask(0o077)
    if sys.argv[1:] not in [['apply'], ['rollback']]:
        raise SystemExit('Use apply or rollback; service restart is separate')
    config, modes = HOME / 'config.yaml', HOME / 'gateway_voice_mode.json'
    manifest_path = BACKUP / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    current = config.read_bytes()
    if sys.argv[1] == 'apply':
        assert json.loads((ROOT / 'native-smoke/report.json').read_text())['passed']
        assert digest(current) == manifest['config_sha256'], 'Config changed since backup'
        assert modes.exists() == manifest['voice_modes_existed'], 'Voice modes changed since backup'
        if modes.exists():
            assert modes.read_bytes() == (BACKUP / modes.name).read_bytes()
        patch = json.loads((ROOT / 'provider-config.json').read_text())
        parsed = yaml.safe_load(current)
        rendered = current.decode()
        for section, update in patch.items():
            merged = dict(parsed.get(section) or {})
            if 'providers' in update:
                update['providers'] = {**merged.get('providers', {}), **update['providers']}
            merged.update(update)
            block = yaml.safe_dump({section: merged}, allow_unicode=True, sort_keys=False)
            pattern = rf'(?ms)^{section}:.*?(?=^[A-Za-z_][A-Za-z_0-9-]*:|\Z)'
            if section in parsed:
                rendered, count = re.subn(pattern, lambda _: block + '\n', rendered)
                assert count == 1
            else:
                rendered += '\n' + block
            parsed[section] = merged
        assert yaml.safe_load(rendered) == parsed
        voice_modes = json.loads(modes.read_text()) if modes.exists() else {}
        voice_modes['telegram:100001'] = 'voice_only'
        config_data = rendered.encode()
        modes_data = (json.dumps(voice_modes, indent=2) + '\n').encode()
        manifest.update(applied_config_sha256=digest(config_data), applied_modes_sha256=digest(modes_data))
        # Persist recovery information before either production write.
        atomic(manifest_path, json.dumps(manifest, indent=2).encode())
        atomic(config, config_data)
        atomic(modes, modes_data)
    else:
        assert digest(current) == manifest['applied_config_sha256'], 'Config changed; reconcile manually'
        assert digest(modes.read_bytes()) == manifest['applied_modes_sha256'], 'Modes changed; reconcile manually'
        atomic(config, (BACKUP / config.name).read_bytes())
        if manifest['voice_modes_existed']:
            atomic(modes, (BACKUP / modes.name).read_bytes())
        else:
            modes.unlink()
    print('Speech configuration ' + sys.argv[1] + ' complete; restart gateway separately')


if __name__ == '__main__':
    main()
