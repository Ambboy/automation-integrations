import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from ops import greif_voice_length_release as release


class VoiceLengthReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        live = base / 'greif/short-voice'
        self.layout = release.Layout(source=base / 'source', home=base / 'home', root=live,
                                     backup=live / 'update-20261004-voice-length')
        self.layout.home.mkdir()
        self.layout.config.write_bytes(b'# preserve byte for byte\ntts: {provider: automation-speech}\n')
        self.layout.gateway.write_text(json.dumps({'active_agents': 0, 'status': 'running'}))
        for index, (source, target) in enumerate(self.layout.targets()):
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(f'candidate {index}\n'.encode())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f'installed {index}\n'.encode())
            target.chmod(0o640)
        self.protected = {
            self.layout.config: self.layout.config.read_bytes(),
            self.layout.gateway: self.layout.gateway.read_bytes(),
            self.layout.home / 'gateway_voice_mode.json': b'{"telegram:100001":"off"}',
            self.layout.home / 'plugins/automation-speech-source/__init__.py': b'existing plugin dispatcher',
            self.layout.root / 'release/automation_integrations/speech.py': b'provider HTTP timeout 180',
            self.layout.root / 'release/automation_integrations/speech_source.py': b'existing sources store',
            self.layout.root.parent / 'phase2/tts.json': b'existing speech provider configuration',
        }
        for path, data in self.protected.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.original = self.contents()

    def contents(self):
        return {target: target.read_bytes() if target.exists() else None
                for _, target in self.layout.targets()}

    def assert_protected(self):
        for path, data in self.protected.items():
            with self.subTest(path=path):
                self.assertEqual(path.read_bytes(), data)

    def jobs(self, states):
        self.layout.speech_database.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(sqlite3.connect(self.layout.speech_database)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS delivery_jobs (state TEXT)')
            db.execute('DELETE FROM delivery_jobs')
            db.executemany('INSERT INTO delivery_jobs VALUES(?)', [(state,) for state in states])

    def test_roundtrip_changes_only_four_targets_and_restores_exact_bytes_and_modes(self):
        self.jobs(['prepared', 'delivered', 'failed', 'cancelled'])
        expected_targets = {
            self.layout.root / 'release/automation_integrations/hermes_speech.py',
            self.layout.root / 'release/automation_integrations/speech_segments.py',
            self.layout.home / 'plugins/automation-speech-source/delivery.py',
            self.layout.home / 'plugins/automation-speech-source/plugin.yaml',
        }
        self.assertEqual(set(self.original), expected_targets)
        report = release.prepare(self.layout)
        self.assertFalse(report['installed_files_changed'])
        self.assertEqual(self.contents(), self.original)
        self.assert_protected()
        report = release.apply(self.layout)
        self.assertFalse(report['gateway_restarted'])
        self.assertEqual(self.contents(), {target: source.read_bytes() for source, target in self.layout.targets()})
        self.assert_protected()
        release.rollback(self.layout)
        self.assertEqual(self.contents(), self.original)
        self.assert_protected()
        for target in self.original:
            self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_background_jobs_block_apply_and_rollback_even_when_model_idle(self):
        release.prepare(self.layout)
        for state in ('queued', 'synthesizing', 'ready', 'sending'):
            with self.subTest(action='apply', state=state):
                self.jobs([state])
                with self.assertRaisesRegex(release.ReleaseError, 'Speech jobs'):
                    release.apply(self.layout)
                self.assertEqual(self.contents(), self.original)
                self.assert_protected()
        self.jobs(['prepared'])
        release.apply(self.layout)
        installed = self.contents()
        for state in ('queued', 'synthesizing', 'ready', 'sending'):
            with self.subTest(action='rollback', state=state):
                self.jobs([state])
                with self.assertRaisesRegex(release.ReleaseError, 'Speech jobs'):
                    release.rollback(self.layout)
                self.assertEqual(self.contents(), installed)
                self.assert_protected()
        self.jobs(['prepared'])
        release.rollback(self.layout)
        self.assertEqual(self.contents(), self.original)

    def test_staged_snapshot_drift_rejects_before_first_write(self):
        release.prepare(self.layout)
        (self.layout.backup / 'staged/03').write_bytes(b'unreviewed snapshot')
        with self.assertRaisesRegex(release.ReleaseError, 'Staged content changed'):
            release.apply(self.layout)
        self.assertEqual(self.contents(), self.original)
        self.assert_protected()

    def test_installed_snapshot_drift_rejects_before_first_write(self):
        release.prepare(self.layout)
        target = self.layout.targets()[-1][1]
        target.write_bytes(b'concurrent installed update')
        before = self.contents()
        with self.assertRaisesRegex(release.ReleaseError, 'Concurrent installed file change'):
            release.apply(self.layout)
        self.assertEqual(self.contents(), before)
        self.assert_protected()

    def test_backup_snapshot_drift_rejects_rollback_before_first_write(self):
        release.prepare(self.layout)
        release.apply(self.layout)
        before = self.contents()
        (self.layout.backup / 'backups/03').write_bytes(b'changed historical backup')
        with self.assertRaisesRegex(release.ReleaseError, 'Backup content changed'):
            release.rollback(self.layout)
        self.assertEqual(self.contents(), before)
        self.assert_protected()

    def test_busy_gateway_and_changed_config_reject_apply(self):
        release.prepare(self.layout)
        self.layout.gateway.write_text(json.dumps({'active_agents': 1}))
        with self.assertRaisesRegex(release.ReleaseError, 'zero active agents'):
            release.apply(self.layout)
        self.assertEqual(self.contents(), self.original)
        self.layout.gateway.write_text(json.dumps({'active_agents': 0}))
        self.layout.config.write_bytes(b'new concurrent config')
        with self.assertRaisesRegex(release.ReleaseError, 'Hermes config changed'):
            release.apply(self.layout)
        self.assertEqual(self.contents(), self.original)

    def test_rollback_preserves_unrelated_later_config_change(self):
        release.prepare(self.layout)
        release.apply(self.layout)
        self.layout.config.write_bytes(b'new unrelated settings')
        release.rollback(self.layout)
        self.assertEqual(self.layout.config.read_bytes(), b'new unrelated settings')
        self.assertEqual(self.contents(), self.original)

    def test_unreadable_speech_state_fails_closed(self):
        release.prepare(self.layout)
        self.layout.speech_database.parent.mkdir(parents=True, exist_ok=True)
        self.layout.speech_database.write_bytes(b'not a sqlite database')
        with self.assertRaisesRegex(release.ReleaseError, 'Cannot verify'):
            release.apply(self.layout)
        self.assertEqual(self.contents(), self.original)

    def test_cli_routes_only_to_requested_wrapper(self):
        for action in ('prepare', 'apply', 'rollback'):
            output = io.StringIO()
            with self.subTest(action=action), patch('sys.argv', ['voice-length-release', action]), \
                    patch.object(release, action, return_value={'action': action}) as call, \
                    contextlib.redirect_stdout(output):
                release.main()
            call.assert_called_once_with()
            self.assertEqual(json.loads(output.getvalue()), {'action': action})


if __name__ == '__main__':
    unittest.main()
