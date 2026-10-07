import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from ops import greif_voice_reload_release as release


class VoiceReloadReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.layout = release.Layout(source=root / 'source', home=root / 'home',
                                     root=root / 'greif/short-voice', backup=root / 'backup')
        self.layout.home.mkdir()
        self.layout.config.write_bytes(b'unchanged config')
        self.layout.gateway.write_text(json.dumps({'active_agents': 0}))
        self.before = {}
        for source, target in self.layout.targets():
            source.parent.mkdir(parents=True, exist_ok=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b'new callback ' + source.name.encode())
            target.write_bytes(b'old callback ' + target.name.encode())
            self.before[target] = target.read_bytes()

    def test_roundtrip_only_delivery_and_manifest_preserving_config(self):
        self.assertEqual({p.name for p in self.before}, {'delivery.py', 'plugin.yaml'})
        release.prepare(self.layout)
        release.apply(self.layout)
        for source, target in self.layout.targets():
            self.assertEqual(source.read_bytes(), target.read_bytes())
        self.assertEqual(self.layout.config.read_bytes(), b'unchanged config')
        release.rollback(self.layout)
        for target, data in self.before.items():
            self.assertEqual(target.read_bytes(), data)

    def test_background_speech_blocks_install(self):
        release.prepare(self.layout)
        db_path = self.layout.speech_database
        db_path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(db_path)) as db, db:
            db.execute('CREATE TABLE delivery_jobs (state TEXT)')
            db.execute("INSERT INTO delivery_jobs VALUES ('synthesizing')")
        with self.assertRaisesRegex(release.ReleaseError, 'Speech jobs'):
            release.apply(self.layout)
        for target, data in self.before.items():
            self.assertEqual(target.read_bytes(), data)

    def test_model_activity_blocks_install(self):
        release.prepare(self.layout)
        self.layout.gateway.write_text(json.dumps({'active_agents': 1}))
        with self.assertRaisesRegex(release.ReleaseError, 'zero active agents'):
            release.apply(self.layout)

    def test_rollback_refuses_to_overwrite_later_plugin_edit(self):
        release.prepare(self.layout)
        release.apply(self.layout)
        first, second = list(self.before)
        second.write_bytes(b'later update')
        first_before = first.read_bytes()
        with self.assertRaisesRegex(release.ReleaseError, 'Concurrent installed file change'):
            release.rollback(self.layout)
        self.assertEqual(first.read_bytes(), first_before)
        self.assertEqual(second.read_bytes(), b'later update')
