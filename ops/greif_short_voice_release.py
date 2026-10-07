# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Guarded short-voice release. Stage first; apply only with an idle gateway.

No service or network operations. Only our speech plugin and its settings change.
An immutable provider snapshot and byte-exact rollback evidence are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml

from ops.wirenboard_release import atomic, checked_bytes, fingerprint, json_bytes, ReleaseError


@dataclass(frozen=True)
class Layout:
    source: Path = Path(__file__).resolve().parents[1]
    home: Path = Path('/home/operator/.hermes')
    root: Path = Path('/home/operator/.local/share/automation-integrations/greif')

    @property
    def release(self):
        return self.root / 'short-voice/release'

    @property
    def backup(self):
        return self.root / 'short-voice/backup'


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def stage(layout=Layout()):
    os.umask(0o077)
    if layout.backup.exists() or layout.release.exists():
        raise ReleaseError('Short-voice staging already exists; inspect before repeating')
    config_path = layout.home / 'config.yaml'
    modes_path = layout.home / 'gateway_voice_mode.json'
    config_bytes = checked_bytes(config_path)
    cfg = yaml.safe_load(config_bytes)
    modes_bytes = checked_bytes(modes_path)
    modes = json.loads(modes_bytes) if modes_bytes is not None else {}
    entry = cfg['plugins']['entries']['automation-speech-source']
    settings = entry.setdefault('settings', {})
    settings.update({
        'segmented_delivery': True,
        'audio_dir': str(layout.root / 'short-voice/audio'),
        'tts_argv': [str(layout.root / 'venv/bin/python'), str(layout.release / 'command.py'),
                     'tts-parts', '--input', '{input_file}', '--output-dir', '{output_dir}',
                     '--config', str(layout.root / 'phase2/tts.json')],
        'default_mode': 'voice_only',
        'synthesis_timeout': 5400,
        'delivery_timeout': 90,
    })
    # The plugin now owns automatic voice delivery; native TTS would duplicate it.
    modes['telegram:100001'] = 'off'
    text = config_bytes.decode()
    block = yaml.safe_dump({'plugins': cfg['plugins']}, allow_unicode=True, sort_keys=False)
    text, count = re.subn(r'(?ms)^plugins:.*?(?=^[A-Za-z_][A-Za-z_0-9-]*:|\Z)',
                          lambda _: block + '\n', text)
    if count != 1 or yaml.safe_load(text) != cfg:
        raise ReleaseError('Could not preserve unrelated configuration')
    # Start with the working standalone provider, replacing only speech modules.
    shutil.copytree(layout.root / 'phase2/release', layout.release,
                    ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('hermes_speech.py', 'speech.py', 'speech_source.py', 'speech_segments.py'):
        shutil.copyfile(layout.source / 'automation_integrations' / name,
                        layout.release / 'automation_integrations' / name)
    targets = []
    plugin = layout.home / 'plugins/automation-speech-source'
    for source in sorted((layout.source / 'bridges/hermes_speech').glob('*')):
        if source.is_file() and source.suffix in {'.py', '.yaml'}:
            targets.append((plugin / source.name, source.read_bytes()))
    targets.append((plugin / 'speech_source.py', (layout.source / 'automation_integrations/speech_source.py').read_bytes()))
    targets.extend([(modes_path, json_bytes(modes)), (config_path, text.encode())])
    layout.backup.mkdir(mode=0o700, parents=True)
    entries = []
    for index, (target, new) in enumerate(targets):
        old = checked_bytes(target)
        before_file, after_file = f'{index:02d}.before', f'{index:02d}.after'
        if old is not None:
            atomic(layout.backup / before_file, old)
        atomic(layout.backup / after_file, new)
        entries.append({'target': str(target), 'before': digest(old), 'after': digest(new),
                        'before_file': before_file, 'after_file': after_file})
    manifest = {'entries': entries, 'provider_sha': {
        str(p.relative_to(layout.release)): fingerprint(p)
        for p in layout.release.rglob('*') if p.is_file()}}
    atomic(layout.backup / 'manifest.json', json_bytes(manifest))
    return {'staged': True, 'targets': len(entries), 'production_changed': False}


def change(layout, rollback=False):
    os.umask(0o077)
    manifest = json.loads((layout.backup / 'manifest.json').read_text())
    before, after = ('after', 'before') if rollback else ('before', 'after')
    entries = manifest['entries']
    # A whole pass before the first write protects concurrent config/plugin edits.
    for entry in entries:
        target = Path(entry['target'])
        allowed = target.parent == layout.home / 'plugins/automation-speech-source' or target in {
            layout.home / 'config.yaml', layout.home / 'gateway_voice_mode.json'}
        if not allowed or fingerprint(target) != entry[before]:
            raise ReleaseError('Installed files changed; reconcile before applying this release')
        data = checked_bytes(layout.backup / entry[after + '_file'])
        if digest(data) != entry[after]:
            raise ReleaseError('Release backup or staged bytes changed')
    state = json.loads((layout.home / 'gateway_state.json').read_text())
    if type(state.get('active_agents')) is not int or state['active_agents'] != 0:
        raise ReleaseError('Gateway must have zero active agents')
    # Background audio outlives the model turn and is not counted by Hermes.
    database = layout.root / 'phase2/sources/sources.sqlite3'
    if database.exists():
        db = sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True)
        try:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='delivery_jobs'").fetchone():
                busy = db.execute("SELECT COUNT(*) FROM delivery_jobs WHERE state IN "
                                  "('queued','synthesizing','ready','sending')").fetchone()[0]
                if busy:
                    raise ReleaseError('Speech jobs are still active; keep the gateway running until they finish')
        finally:
            db.close()
    for relative, expected in manifest['provider_sha'].items():
        if fingerprint(layout.release / relative) != expected:
            raise ReleaseError('Provider snapshot changed')
    for entry in entries:
        target = Path(entry['target'])
        if entry[after] is None:
            target.unlink(missing_ok=True)
        else:
            atomic(target, (layout.backup / entry[after + '_file']).read_bytes())
    for entry in entries:
        if fingerprint(Path(entry['target'])) != entry[after]:
            raise ReleaseError('Post-write verification failed')
    atomic(layout.backup / ('rolled-back.json' if rollback else 'applied.json'), json_bytes({'ok': True}))
    return {'rolled_back' if rollback else 'applied': True, 'targets': len(entries), 'gateway_restarted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'apply', 'rollback'))
    args = parser.parse_args()
    layout = Layout()
    result = stage(layout) if args.action == 'stage' else change(layout, args.action == 'rollback')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
