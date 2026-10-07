import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import yaml

from ops.greif_short_voice_release import Layout, stage, change
from ops.wirenboard_release import ReleaseError


class ShortVoiceReleaseTests(unittest.TestCase):
    def layout(self, root):
        source, home, live = root / 'source', root / 'home', root / 'live'
        for folder in (source / 'bridges/hermes_speech', source / 'automation_integrations',
                       home / 'plugins/automation-speech-source', live / 'phase2/release/automation_integrations'):
            folder.mkdir(parents=True)
        for name in ('__init__.py', 'delivery.py', 'plugin.yaml'):
            (source / 'bridges/hermes_speech' / name).write_text('new-' + name)
        for name in ('hermes_speech.py', 'speech.py', 'speech_source.py', 'speech_segments.py'):
            (source / 'automation_integrations' / name).write_text('new-' + name)
        (home / 'plugins/automation-speech-source/__init__.py').write_text('old-plugin')
        (home / 'config.yaml').write_text(yaml.safe_dump({'plugins': {'enabled': ['automation-speech-source', 'other'],
            'entries': {'automation-speech-source': {'settings': {'enabled': True, 'owner_id': '100001', 'state_dir': 'old'}},
                        'other': {'settings': {'preserve': True}}}},
            'stt': {'provider': 'keep'}, 'tts': {'provider': 'keep'}, 'model': {'default': 'keep'}}))
        (home / 'gateway_voice_mode.json').write_text(json.dumps({'telegram:100001': 'voice_only', 'other': 'all'}))
        (home / 'gateway_state.json').write_text(json.dumps({'active_agents': 0}))
        return Layout(source=source, home=home, root=live)

    def test_roundtrip_preserves_other_settings_and_exact_original_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            layout = self.layout(Path(temp))
            config = (layout.home / 'config.yaml').read_bytes()
            modes = (layout.home / 'gateway_voice_mode.json').read_bytes()
            stage(layout)
            self.assertEqual((layout.home / 'config.yaml').read_bytes(), config)
            change(layout)
            actual = yaml.safe_load((layout.home / 'config.yaml').read_text())
            before = yaml.safe_load(config)
            for key in ('stt', 'tts', 'model'):
                self.assertEqual(actual[key], before[key])
            self.assertEqual(actual['plugins']['entries']['other'], before['plugins']['entries']['other'])
            self.assertEqual(json.loads((layout.home / 'gateway_voice_mode.json').read_text())['other'], 'all')
            change(layout, rollback=True)
            self.assertEqual((layout.home / 'config.yaml').read_bytes(), config)
            self.assertEqual((layout.home / 'gateway_voice_mode.json').read_bytes(), modes)
            self.assertEqual((layout.home / 'plugins/automation-speech-source/__init__.py').read_text(), 'old-plugin')
            self.assertFalse((layout.home / 'plugins/automation-speech-source/delivery.py').exists())

    def test_concurrent_change_and_busy_gateway_refuse_before_any_write(self):
        for conflict in ('config', 'busy'):
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as temp:
                layout = self.layout(Path(temp))
                stage(layout)
                if conflict == 'config':
                    with (layout.home / 'config.yaml').open('a') as stream:
                        stream.write('\n# newer change\n')
                else:
                    (layout.home / 'gateway_state.json').write_text(json.dumps({'active_agents': 1}))
                with self.assertRaises(ReleaseError):
                    change(layout)
                self.assertEqual((layout.home / 'plugins/automation-speech-source/__init__.py').read_text(), 'old-plugin')
                self.assertFalse((layout.home / 'plugins/automation-speech-source/delivery.py').exists())

    def test_background_voice_blocks_change_even_when_model_is_idle(self):
        with tempfile.TemporaryDirectory() as temp:
            layout = self.layout(Path(temp))
            stage(layout)
            state = layout.root / 'phase2/sources'
            state.mkdir()
            with sqlite3.connect(state / 'sources.sqlite3') as db:
                db.execute('create table delivery_jobs(state text)')
                db.execute("insert into delivery_jobs values('sending')")
            with self.assertRaisesRegex(ReleaseError, 'Speech jobs'):
                change(layout)
            self.assertEqual((layout.home / 'plugins/automation-speech-source/__init__.py').read_text(), 'old-plugin')
