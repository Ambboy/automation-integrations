"""Exercise the media release in an isolated filesystem, never the live gateway."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ops import greif_media_release as release


class MediaReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.project, self.root, self.home = base / 'project', base / 'catalog', base / 'hermes'
        self.prepared = base / 'prepared'
        self.root.mkdir()
        self.home.mkdir()
        self.config_bytes = b'plugins:\n  enabled: [speech, topics, automation-api-catalog]\nother: keep\n'
        (self.home / 'config.yaml').write_bytes(self.config_bytes)
        self.private = {'item_ids': {'yandex_go': 'existing-fixture-item'}, 'state_dir': '/private/state',
                        'unrelated': {'policy': 'preserve'}, 'fixture_marker': 'not-a-real-secret'}
        (self.root / 'private.json').write_text(json.dumps(self.private))
        self.pairs = release.destinations(self.project, self.root, self.home)
        for index, (source, target) in enumerate(self.pairs.items()):
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text('new source fixture ' + str(index))
            if target.name in ('api_read.py', 'api_write.py', 'catalog.json', '__init__.py', 'plugin.yaml', 'catalog.py'):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('old installed fixture ' + str(index))
        self.protected = [self.root / 'release/existing_provider.py',
                          self.home / 'plugins/automation-speech-source/voice.py',
                          self.home / 'plugins/automation-topic-style/topics.py']
        for index, path in enumerate(self.protected):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('unrelated bytes ' + str(index))
        self.before = {path: path.read_bytes() if path.exists() else None for path in self.pairs.values()}
        self.before[self.root / 'private.json'] = (self.root / 'private.json').read_bytes()

    def prepare(self, **kwargs):
        return release.prepare(self.project, self.root, self.home, self.prepared, **kwargs)

    def test_prepare_freezes_release_apply_preserves_others_and_rollback_restores(self):
        self.prepare(limits={'fal': {'per_task': '1.00'}})
        for path, data in self.before.items():
            self.assertEqual(path.read_bytes() if path.exists() else None, data)
        # Source work may continue after preparation; apply uses reviewed bytes.
        source, target = next(iter(self.pairs.items()))
        frozen = source.read_bytes()
        source.write_bytes(b'future source change')
        installed = release.apply(self.prepared)
        self.assertEqual(installed['installed'], len(self.pairs) + 1)
        self.assertEqual(target.read_bytes(), frozen)
        self.assertEqual((self.home / 'config.yaml').read_bytes(), self.config_bytes)
        for index, path in enumerate(self.protected):
            self.assertEqual(path.read_text(), 'unrelated bytes ' + str(index))
        private = json.loads((self.root / 'private.json').read_text())
        self.assertEqual(private['unrelated'], self.private['unrelated'])
        self.assertEqual(private['item_ids']['yandex_go'], self.private['item_ids']['yandex_go'])
        self.assertEqual(private['media_authorization'], 'owner_command')
        self.assertEqual(private['media_limits'], {'fal': {'per_task': '1.00'}})
        self.assertIn('fal', private['item_ids'])
        self.assertIn('inference', private['item_ids'])
        self.assertNotIn('not-a-real-secret', (self.prepared / 'manifest.json').read_text())
        release.apply(self.prepared, rollback=True)
        for path, data in self.before.items():
            self.assertEqual(path.read_bytes() if path.exists() else None, data)
        self.assertEqual((self.home / 'config.yaml').read_bytes(), self.config_bytes)

    def test_apply_preflight_refuses_concurrent_target_and_protected_changes(self):
        self.prepare()
        target = self.root / 'release/api_read.py'
        target.write_bytes(b'operator changed target')
        with self.assertRaisesRegex(ValueError, 'concurrent_target_change'):
            release.apply(self.prepared)
        self.assertEqual(target.read_bytes(), b'operator changed target')
        self.assertFalse((self.root / 'release/media_api.py').exists())
        target.write_bytes(self.before[target])
        self.protected[0].write_bytes(b'operator changed unrelated provider')
        with self.assertRaisesRegex(ValueError, 'protected_file_changed'):
            release.apply(self.prepared)
        self.assertFalse((self.root / 'release/media_api.py').exists())

    def test_corrupt_snapshot_and_rollback_after_later_edits_fail_closed(self):
        self.prepare()
        original = (self.prepared / '0.after').read_bytes()
        (self.prepared / '0.after').write_bytes(b'corrupt prepared release')
        with self.assertRaisesRegex(ValueError, 'release_snapshot_changed'):
            release.apply(self.prepared)
        self.assertFalse((self.root / 'release/media_api.py').exists())
        (self.prepared / '0.after').write_bytes(original)
        release.apply(self.prepared)
        target = self.root / 'release/api_read.py'
        target.write_bytes(b'later deployed change')
        with self.assertRaisesRegex(ValueError, 'concurrent_target_change'):
            release.apply(self.prepared, rollback=True)
        self.assertEqual(target.read_bytes(), b'later deployed change')
        self.assertTrue((self.root / 'release/media_api.py').exists())

    def test_rebinding_existing_credentials_and_duplicate_prepare_are_rejected(self):
        changed = deepcopy(self.private)
        changed['item_ids']['fal'] = 'another-existing-binding'
        (self.root / 'private.json').write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'existing_media_credential_binding_requires_review'):
            self.prepare()
        self.assertFalse(self.prepared.exists())
        (self.root / 'private.json').write_text(json.dumps(self.private))
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'release_already_prepared'):
            self.prepare()

    def test_cli_refuses_apply_while_gateway_is_active(self):
        with patch('sys.argv', ['greif_media_release.py', 'apply']), \
                patch.object(release.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout='active\n')), \
                patch.object(release, 'apply') as apply:
            with self.assertRaisesRegex(SystemExit, 'Stop the idle gateway'):
                release.main()
            apply.assert_not_called()


if __name__ == '__main__':
    unittest.main()
