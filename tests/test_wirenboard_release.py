import json
import tempfile
import unittest
from pathlib import Path

from ops.wirenboard_release import Layout, ReleaseError, apply, prepare, rollback


class WirenboardReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.layout = Layout(base / 'source', base / 'hermes', base / 'catalog', base / 'catalog/update')
        self.layout.backup.mkdir(parents=True)
        self.layout.home.mkdir(parents=True)
        self.layout.config.write_bytes(b'original config\n')
        self.layout.gateway.write_text(json.dumps({'active_agents': 0, 'status': 'running'}))
        for index, (source, target) in enumerate(self.layout.targets()):
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(f'new bytes {index}\n'.encode())
            if index not in (0, 1, 3):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f'old bytes {index}\n'.encode())
                target.chmod(0o640)
        self.original = self.contents()
        self.session = self.layout.root / 'state/wirenboard-session.json'
        self.session.parent.mkdir()
        self.session.write_bytes(b'rotated-token-state')
        self.unrelated = self.layout.root / 'release/yandex_contract.py'
        self.unrelated.write_bytes(b'other-release-bytes')
        self.prior_receipt = self.layout.backup / 'gateway-before.json'
        self.prior_receipt.write_bytes(b'preexisting-receipt')

    def contents(self):
        return {str(target): target.read_bytes() if target.exists() else None for _, target in self.layout.targets()}

    def assert_non_targets_preserved(self):
        self.assertEqual(self.layout.config.read_bytes(), b'original config\n')
        self.assertEqual(self.session.read_bytes(), b'rotated-token-state')
        self.assertEqual(self.unrelated.read_bytes(), b'other-release-bytes')
        self.assertEqual(self.prior_receipt.read_bytes(), b'preexisting-receipt')

    def test_prepare_apply_rollback_preserves_state_config_receipts_and_other_releases(self):
        result = prepare(self.layout)
        self.assertFalse(result['installed_files_changed'])
        self.assertEqual(self.contents(), self.original)
        manifest = json.loads((self.layout.backup / 'manifest.json').read_text())
        self.assertEqual(manifest['gateway_before']['active_agents'], 0)
        self.assertEqual(len(manifest['entries']), 8)
        apply(self.layout)
        for source, target in self.layout.targets():
            self.assertEqual(target.read_bytes(), source.read_bytes())
        self.assertEqual((self.layout.root / 'private.json').stat().st_mode & 0o777, 0o600)
        self.assert_non_targets_preserved()
        rollback(self.layout)
        self.assertEqual(self.contents(), self.original)
        self.assert_non_targets_preserved()
        self.assertTrue((self.layout.backup / 'applied.json').exists())
        self.assertTrue((self.layout.backup / 'rollback.json').exists())
        for target, old in self.original.items():
            if old is not None:
                self.assertEqual(Path(target).stat().st_mode & 0o777, 0o640)

    def test_apply_rejects_late_target_edit_before_writing_any_target(self):
        prepare(self.layout)
        last_target = self.layout.targets()[-1][1]
        last_target.write_bytes(b'concurrent user edit')
        before = self.contents()
        with self.assertRaises(ReleaseError):
            apply(self.layout)
        self.assertEqual(self.contents(), before)
        self.assertFalse((self.layout.backup / 'applied.json').exists())
        self.assert_non_targets_preserved()

    def test_rollback_rejects_late_target_edit_before_restoring_any_target(self):
        prepare(self.layout)
        apply(self.layout)
        self.layout.targets()[-1][1].write_bytes(b'newer unrelated deployment')
        before = self.contents()
        with self.assertRaises(ReleaseError):
            rollback(self.layout)
        self.assertEqual(self.contents(), before)
        self.assert_non_targets_preserved()

    def test_config_and_busy_gateway_each_block_all_apply_writes(self):
        prepare(self.layout)
        self.layout.config.write_bytes(b'changed config')
        with self.assertRaises(ReleaseError):
            apply(self.layout)
        self.assertEqual(self.contents(), self.original)
        self.assertEqual(self.layout.config.read_bytes(), b'changed config')
        self.layout.config.write_bytes(b'original config\n')
        for active in (1, True, '0', None):
            self.layout.gateway.write_text(json.dumps({'active_agents': active}))
            with self.assertRaises(ReleaseError):
                apply(self.layout)
            self.assertEqual(self.contents(), self.original)

    def test_staged_or_backup_corruption_blocks_all_writes(self):
        prepare(self.layout)
        staged = self.layout.backup / 'staged/07'
        good = staged.read_bytes()
        staged.write_bytes(b'corrupted stage')
        with self.assertRaises(ReleaseError):
            apply(self.layout)
        self.assertEqual(self.contents(), self.original)
        staged.write_bytes(good)
        apply(self.layout)
        before = self.contents()
        (self.layout.backup / 'backups/07').write_bytes(b'corrupted backup')
        with self.assertRaises(ReleaseError):
            rollback(self.layout)
        self.assertEqual(self.contents(), before)

    def test_manifest_cannot_add_session_file_as_target(self):
        prepare(self.layout)
        path = self.layout.backup / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['entries'][-1]['target'] = str(self.session)
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ReleaseError):
            apply(self.layout)
        self.assertEqual(self.contents(), self.original)
        self.assert_non_targets_preserved()

    def test_prepare_never_overwrites_existing_manifest(self):
        prepare(self.layout)
        path = self.layout.backup / 'manifest.json'
        previous = path.read_bytes()
        with self.assertRaises(ReleaseError):
            prepare(self.layout)
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(self.contents(), self.original)

    def test_rollback_preserves_later_unrelated_config_change(self):
        prepare(self.layout)
        apply(self.layout)
        self.layout.config.write_bytes(b'new unrelated config')
        rollback(self.layout)
        self.assertEqual(self.layout.config.read_bytes(), b'new unrelated config')
        self.assertEqual(self.contents(), self.original)
        self.assertEqual(self.session.read_bytes(), b'rotated-token-state')


if __name__ == '__main__':
    unittest.main()
