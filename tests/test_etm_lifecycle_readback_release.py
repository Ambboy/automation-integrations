import json
from pathlib import Path
import tempfile
import unittest

from ops import etm_lifecycle_readback_release as release


class EtmLifecycleReadbackReleaseTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.layout = release.Layout(source=base / 'source', home=base / 'home',
                                     root=base / 'catalog', backup=base / 'patch')
        self.layout.home.mkdir()
        self.layout.config.write_bytes(b'config: preserve\n')
        self.layout.gateway.write_text(json.dumps({'active_agents': 0}))
        self.source, self.target = self.layout.targets()[0]
        self.source.parent.mkdir(parents=True)
        self.target.parent.mkdir(parents=True)
        self.source.write_bytes(b'corrected lifecycle\n')
        self.target.write_bytes(b'initial lifecycle\n')
        self.target.chmod(0o640)
        self.preserved = {
            self.layout.root / 'update-20261007-etm-lifecycle/manifest.json': b'original manifest\n',
            self.layout.root / 'update-20261007-etm-lifecycle/applied.json': b'original receipt\n',
            self.layout.root / 'release/catalog.json': b'original catalog\n',
            self.layout.root / 'release/etm_lifecycle_actions.py': b'companion module\n',
            self.layout.root / 'private.json': b'private reference\n',
        }
        for path, content in self.preserved.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def assert_preserved(self):
        for path, content in self.preserved.items():
            self.assertEqual(path.read_bytes(), content, str(path))

    def test_only_lifecycle_module_changes_and_parent_release_remains_valid(self):
        self.assertEqual(self.layout.targets(), [(
            self.layout.source / 'automation_integrations/etm_lifecycle.py',
            self.layout.root / 'release/etm_lifecycle.py')])
        result = release.prepare(self.layout)
        self.assertEqual(result['targets'], 1)
        self.assertFalse(result['installed_files_changed'])
        self.assertEqual(self.target.read_bytes(), b'initial lifecycle\n')
        self.assert_preserved()
        applied = release.guarded.apply(self.layout)
        self.assertFalse(applied['gateway_restarted'])
        self.assertTrue(applied['config_preserved'])
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())
        self.assert_preserved()
        self.layout.config.write_bytes(b'later config\n')
        release.guarded.rollback(self.layout)
        self.assertEqual(self.target.read_bytes(), b'initial lifecycle\n')
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.layout.config.read_bytes(), b'later config\n')
        self.assert_preserved()

    def test_apply_rejects_concurrent_module_change(self):
        release.prepare(self.layout)
        self.target.write_bytes(b'concurrent lifecycle correction\n')
        with self.assertRaisesRegex(release.guarded.ReleaseError, 'Concurrent installed file change'):
            release.guarded.apply(self.layout)
        self.assertEqual(self.target.read_bytes(), b'concurrent lifecycle correction\n')
        self.assertFalse((self.layout.backup / 'applied.json').exists())
        self.assert_preserved()

    def test_rollback_rejects_newer_module_instead_of_overwriting_it(self):
        release.prepare(self.layout)
        release.guarded.apply(self.layout)
        self.target.write_bytes(b'newer lifecycle correction\n')
        with self.assertRaisesRegex(release.guarded.ReleaseError, 'Concurrent installed file change'):
            release.guarded.rollback(self.layout)
        self.assertEqual(self.target.read_bytes(), b'newer lifecycle correction\n')
        self.assert_preserved()

    def test_incremental_patch_requires_an_installed_lifecycle_module(self):
        self.target.unlink()
        with self.assertRaisesRegex(release.guarded.ReleaseError, 'full ETM lifecycle release'):
            release.prepare(self.layout)
        self.assertFalse(self.layout.backup.exists())
        self.assert_preserved()


if __name__ == '__main__':
    unittest.main()
