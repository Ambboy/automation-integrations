import json
from pathlib import Path
import tempfile
import unittest

from ops import etm_owner_command_release as release


class OwnerCommandReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.layout = release.Layout(home=base / 'home', root=base / 'catalog', backup=base / 'backup')
        self.layout.home.mkdir()
        self.layout.root.mkdir()
        self.layout.config.write_text('fixture: unchanged\n')
        self.layout.gateway.write_text(json.dumps({'active_agents': 0}))
        self.private = {'state_dir': 'fixture-state', 'item_ids': {'etm': 'opaque-reference'},
                        'wirenboard_transport': 'preserve-this'}
        (self.layout.root / 'private.json').write_text(json.dumps(self.private))
        self.layout.skill.parent.mkdir(parents=True)
        self.original_skill = '# ETM\n\n' + release.OLD_APPROVAL + '\n' + release.OLD_CUT + '\n'
        self.layout.skill.write_text(self.original_skill)

    def test_staged_install_changes_only_policy_and_rolls_back_exactly(self):
        before_private = (self.layout.root / 'private.json').read_bytes()
        self.assertFalse(release.prepare(self.layout)['installed_files_changed'])
        self.assertEqual((self.layout.root / 'private.json').read_bytes(), before_private)
        result = release.guarded.apply(self.layout)
        self.assertTrue(result['config_preserved'])
        self.assertEqual(json.loads((self.layout.root / 'private.json').read_text()),
                         {**self.private, 'etm_order_authorization': 'owner_command'})
        self.assertIn(release.NEW_APPROVAL, self.layout.skill.read_text())
        self.assertNotIn(release.OLD_APPROVAL, self.layout.skill.read_text())
        self.assertTrue((self.layout.root / 'release/etm_authorization.py').exists())
        release.guarded.rollback(self.layout)
        self.assertEqual((self.layout.root / 'private.json').read_bytes(), before_private)
        self.assertEqual(self.layout.skill.read_text(), self.original_skill)
        self.assertEqual(self.layout.config.read_text(), 'fixture: unchanged\n')

    def test_concurrent_skill_change_or_busy_gateway_prevents_apply(self):
        release.prepare(self.layout)
        self.layout.gateway.write_text(json.dumps({'active_agents': 1}))
        with self.assertRaises(release.guarded.ReleaseError):
            release.guarded.apply(self.layout)
        self.layout.gateway.write_text(json.dumps({'active_agents': 0}))
        self.layout.skill.write_text(self.original_skill + 'Another user change\n')
        with self.assertRaises(release.guarded.ReleaseError):
            release.guarded.apply(self.layout)
        self.assertEqual(json.loads((self.layout.root / 'private.json').read_text()), self.private)
        self.assertFalse((self.layout.root / 'release/etm_authorization.py').exists())


if __name__ == '__main__':
    unittest.main()
