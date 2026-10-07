import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ops import wirenboard_control_release as release
from ops import wirenboard_release as read_release


class WirenboardControlReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.layout = release.Layout(base / 'source', base / 'hermes', base / 'catalog',
                                     base / 'catalog/update-20261004-wirenboard-control')
        self.layout.home.mkdir(parents=True)
        self.layout.config.write_bytes(b'full-api config\n')
        self.layout.gateway.write_text(json.dumps({'active_agents': 0, 'status': 'running'}))
        for index, (source, target) in enumerate(self.layout.targets()):
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(f'control candidate {index}\n'.encode())
            if index >= 3:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f'current full-api {index}\n'.encode())
                target.chmod(0o640)
        self.original = self.contents()
        self.protected = {
            self.layout.root / 'state/wirenboard-session.json': b'rotated refresh cache',
            self.layout.root / 'state/wirenboard-writes/existing.json': b'existing approved draft',
            self.layout.root / 'private.json': b'existing private config',
            self.layout.root / 'release/api_read.py': b'current full-api read dispatcher',
            self.layout.root / 'release/confirmed_write.py': b'existing business write workflow',
            self.layout.root / 'release/yandex_contract.py': b'existing Yandex contract',
            self.layout.root / 'release/contracts/saby.json': b'existing Saby contract',
            self.layout.root / 'release/capabilities/etm.json': b'existing ETM inventory',
            self.layout.root / 'update-20261004-wirenboard/manifest.json': b'existing read release receipt',
            self.layout.config: b'full-api config\n',
            self.layout.gateway: self.layout.gateway.read_bytes(),
        }
        for path, data in self.protected.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def contents(self):
        return {target: target.read_bytes() if target.exists() else None
                for source, target in self.layout.targets()}

    def assert_protected(self):
        for path, data in self.protected.items():
            with self.subTest(path=path):
                self.assertEqual(path.read_bytes(), data)

    def test_exact_target_set_and_separate_backup_namespace(self):
        self.assertIsInstance(self.layout, read_release.Layout)
        self.assertEqual(release.Layout().backup.name, 'update-20261004-wirenboard-control')
        self.assertNotEqual(release.Layout().backup, read_release.Layout().backup)
        paths = [target for source, target in self.layout.targets()]
        self.assertEqual(paths, [
            self.layout.root / 'release' / name for name in
            ('wirenboard_control_contract.py', 'wirenboard_shell.py', 'wirenboard_control.py',
             'wirenboard_http.py', 'wirenboard.py', 'api_write.py',
             'capabilities/wirenboard.json', 'catalog.json')
        ] + [self.layout.home / 'plugins/automation-api-catalog' / name
             for name in ('__init__.py', 'plugin.yaml')])
        self.assertTrue(set(paths).isdisjoint(self.protected))

    def test_prepare_apply_rollback_preserves_current_reads_provider_files_credentials_and_drafts(self):
        prepared = release.prepare(self.layout)
        self.assertEqual(prepared['targets'], 10)
        self.assertFalse(prepared['installed_files_changed'])
        self.assertEqual(self.contents(), self.original)
        self.assert_protected()
        applied = release.apply(self.layout)
        self.assertFalse(applied['gateway_restarted'])
        for source, target in self.layout.targets():
            self.assertEqual(target.read_bytes(), source.read_bytes())
        self.assert_protected()
        release.rollback(self.layout)
        self.assertEqual(self.contents(), self.original)
        self.assert_protected()
        for target, data in self.original.items():
            if data is not None:
                self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_late_installed_change_blocks_all_targets(self):
        release.prepare(self.layout)
        last_target = self.layout.targets()[-1][1]
        last_target.write_bytes(b'concurrent plugin update')
        before = self.contents()
        with self.assertRaises(release.ReleaseError):
            release.apply(self.layout)
        self.assertEqual(self.contents(), before)
        self.assert_protected()

    def test_manifest_cannot_redirect_target_to_existing_write_draft(self):
        release.prepare(self.layout)
        path = self.layout.backup / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['entries'][0]['target'] = str(self.layout.root / 'state/wirenboard-writes/existing.json')
        path.write_text(json.dumps(manifest))
        with self.assertRaises(release.ReleaseError):
            release.apply(self.layout)
        self.assertEqual(self.contents(), self.original)
        self.assert_protected()

    def test_source_changes_after_staging_do_not_change_the_reviewed_release(self):
        release.prepare(self.layout)
        expected = {target: source.read_bytes() for source, target in self.layout.targets()}
        for source, target in self.layout.targets():
            source.write_bytes(b'unreviewed later source')
        release.apply(self.layout)
        self.assertEqual(self.contents(), expected)
        self.assert_protected()

    def test_busy_gateway_blocks_apply_without_touching_targets(self):
        release.prepare(self.layout)
        self.layout.gateway.write_text(json.dumps({'active_agents': 1}))
        with self.assertRaises(release.ReleaseError):
            release.apply(self.layout)
        self.assertEqual(self.contents(), self.original)
        self.assertEqual((self.layout.root / 'state/wirenboard-writes/existing.json').read_bytes(), b'existing approved draft')

    def test_cli_routes_to_control_wrappers_and_preserves_guard_errors(self):
        for action in ('prepare', 'apply', 'rollback'):
            output = io.StringIO()
            with self.subTest(action=action), patch('sys.argv', ['control-release', action]), \
                    patch.object(release, action, return_value={'action': action}) as called, \
                    contextlib.redirect_stdout(output):
                release.main()
            called.assert_called_once_with()
            self.assertEqual(json.loads(output.getvalue()), {'action': action})
        with patch('sys.argv', ['control-release', 'apply']), \
                patch.object(release, 'apply', side_effect=release.ReleaseError('Concurrent installed file change')), \
                self.assertRaisesRegex(SystemExit, 'Concurrent installed file change'):
            release.main()


if __name__ == '__main__':
    unittest.main()
