import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ops import etm_region_release as release


class EtmRegionReleaseTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.layout = release.Layout(source=base / 'source', home=base / 'home',
                                     root=base / 'catalog', backup=base / 'update')
        self.layout.home.mkdir()
        self.layout.root.mkdir()
        self.layout.config.write_bytes(b'config: preserve\n')
        self.layout.gateway.write_text(json.dumps({'active_agents': 0}))
        for source, target in self.layout.targets()[:len(release.RUNNER_FILES)]:
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(('new ' + source.name + '\n').encode())
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.name != 'etm_public_order.py':
                target.write_bytes(('previous ' + target.name + '\n').encode())
                target.chmod(0o640)
        for name in release.REGISTRY_FILES:
            source = self.layout.source / 'registry' / name
            target = self.layout.root / 'release' / name
            source.parent.mkdir(parents=True, exist_ok=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(json.dumps({'service': 'etm', 'revision': 'new', 'kind': name}))
            target.write_text(json.dumps({'service': 'etm', 'revision': 'old', 'kind': name}))
            target.chmod(0o640)
        self.source_catalog = self.layout.source / 'registry/catalog.json'
        self.installed_catalog = self.layout.root / 'release/catalog.json'
        self.other_service = {'id': 'foreign', 'instructions': ['Preserve newer service behavior.'],
                              'operations': {'foreign_read': {'version': 9}}}
        self.original_catalog = {'schema_version': 1, 'version': 'fixture+other.7+confirm.3',
                                 'metadata': {'installed_annotation': 'preserve'},
                                 'services': [{'id': 'etm', 'instructions': ['Old advice.']},
                                              self.other_service]}
        self.new_etm = {'id': 'etm', 'instructions': ['Region and public API order route.']}
        self.source_catalog.write_text(json.dumps({
            **self.original_catalog, 'version': 'fixture+other.7+confirm.3+etm-region.1',
            'services': [self.new_etm, self.other_service]}))
        self.installed_catalog.write_text(json.dumps(self.original_catalog))
        self.installed_catalog.chmod(0o640)
        self.layout.skill.parent.mkdir(parents=True)
        self.original_skill = ('# Existing ETM instructions\n\n'
                               'Owner-authored ordering rules stay verbatim.\n\n'
                               + release.OLD_DESTINATION + '\n'
                               '- Existing warrants and correspondence rules.\n\n'
                               '## Unrelated notes\nPreserve these too.\n')
        self.layout.skill.write_text(self.original_skill)
        self.layout.skill.chmod(0o640)
        self.original = self.contents()
        self.foreign = {
            self.layout.root / 'private.json': b'private reference: preserve\n',
            self.layout.root / 'release/api_write.py': b'newer write router: preserve\n',
            self.layout.root / 'release/wirenboard.py': b'foreign runner: preserve\n',
            self.layout.root / 'state/etm-writes/existing.json': b'existing durable draft\n',
            self.layout.home / 'plugins/automation-api-catalog/__init__.py': b'newer bridge\n',
            self.layout.home / 'plugins/automation-api-catalog/plugin.yaml': b'newer plugin metadata\n',
        }
        for path, data in self.foreign.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def contents(self):
        return {target: target.read_bytes() if target.exists() else None
                for _, target in self.layout.targets()}

    def assert_foreign_preserved(self):
        for path, data in self.foreign.items():
            self.assertEqual(path.read_bytes(), data, str(path))

    def test_exact_targets_install_and_rollback_preserve_unrelated_content(self):
        expected = {self.layout.root / 'release' / name for name in release.RUNNER_FILES}
        expected.update(self.layout.root / 'release' / name for name in release.REGISTRY_FILES)
        expected.add(self.installed_catalog)
        self.assertEqual(set(self.contents()), expected | {self.layout.skill})
        self.assertEqual(len(self.layout.targets()), 9)
        self.assertFalse(release.prepare(self.layout)['installed_files_changed'])
        self.assertEqual(self.contents(), self.original)
        candidate = (self.layout.backup / 'candidate-etm-skill.md').read_text()
        self.assertEqual(candidate, self.original_skill.replace(
            release.OLD_DESTINATION, release.NEW_DESTINATION + '\n' + release.PUBLIC_ORDER_REFERENCE))
        result = release.guarded.apply(self.layout)
        self.assertTrue(result['config_preserved'])
        self.assertFalse(result['gateway_restarted'])
        for source, target in self.layout.targets():
            self.assertEqual(target.read_bytes(), source.read_bytes())
        installed = json.loads(self.installed_catalog.read_text())
        self.assertEqual(installed['services'], [self.new_etm, self.other_service])
        self.assertEqual(installed['metadata'], self.original_catalog['metadata'])
        self.assertEqual(installed['version'], self.original_catalog['version'] + '+etm-region.1')
        self.assert_foreign_preserved()
        # Rollback preserves unrelated configuration edits made after installation.
        self.layout.config.write_bytes(b'later config: preserve\n')
        release.guarded.rollback(self.layout)
        self.assertEqual(self.contents(), self.original)
        self.assertFalse((self.layout.root / 'release/etm_public_order.py').exists())
        self.assertEqual(self.layout.config.read_bytes(), b'later config: preserve\n')
        for path, data in self.original.items():
            if data is not None:
                self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assert_foreign_preserved()

    def test_concurrent_skill_edit_blocks_all_apply_writes(self):
        release.prepare(self.layout)
        self.layout.skill.write_text(self.original_skill + '\nConcurrent owner change.\n')
        before = self.contents()
        with self.assertRaises(release.guarded.ReleaseError):
            release.guarded.apply(self.layout)
        self.assertEqual(self.contents(), before)
        self.assertFalse((self.layout.backup / 'applied.json').exists())
        self.assert_foreign_preserved()

    def test_config_change_and_busy_gateway_block_all_apply_writes(self):
        release.prepare(self.layout)
        self.layout.config.write_bytes(b'concurrent config\n')
        with self.assertRaises(release.guarded.ReleaseError):
            release.guarded.apply(self.layout)
        self.assertEqual(self.contents(), self.original)
        self.assertEqual(self.layout.config.read_bytes(), b'concurrent config\n')
        self.layout.config.write_bytes(b'config: preserve\n')
        self.layout.gateway.write_text(json.dumps({'active_agents': 1}))
        with self.assertRaises(release.guarded.ReleaseError):
            release.guarded.apply(self.layout)
        self.assertEqual(self.contents(), self.original)
        self.assert_foreign_preserved()

    def test_rollback_will_not_remove_concurrently_updated_public_module(self):
        release.prepare(self.layout)
        release.guarded.apply(self.layout)
        new_module = self.layout.root / 'release/etm_public_order.py'
        new_module.write_bytes(b'newer public API module\n')
        before = self.contents()
        with self.assertRaises(release.guarded.ReleaseError):
            release.guarded.rollback(self.layout)
        self.assertEqual(self.contents(), before)
        self.assert_foreign_preserved()

    def test_changed_skill_contract_is_rejected_before_staging(self):
        for text in (self.original_skill.replace(release.OLD_DESTINATION, 'Changed destination advice.'),
                     self.original_skill + release.OLD_DESTINATION):
            with self.subTest(text=text):
                self.layout.skill.write_text(text)
                before = self.contents()
                with self.assertRaises(release.guarded.ReleaseError):
                    release.prepare(self.layout)
                self.assertEqual(self.contents(), before)
                self.assertFalse(self.layout.backup.exists())
        self.assert_foreign_preserved()

    def test_missing_new_module_is_rejected_before_staging(self):
        (self.layout.source / 'automation_integrations/etm_public_order.py').unlink()
        with self.assertRaises(release.guarded.ReleaseError):
            release.prepare(self.layout)
        self.assertFalse(self.layout.backup.exists())
        self.assertEqual(self.contents(), self.original)
        self.assert_foreign_preserved()

    def test_non_etm_service_difference_is_rejected_before_staging(self):
        catalog = json.loads(self.source_catalog.read_text())
        catalog['services'][1]['instructions'] = ['Stale unrelated instructions.']
        self.source_catalog.write_text(json.dumps(catalog))
        with self.assertRaisesRegex(release.guarded.ReleaseError, 'Non-ETM catalog entries differ'):
            release.prepare(self.layout)
        self.assertFalse(self.layout.backup.exists())
        self.assertEqual(self.contents(), self.original)
        self.assert_foreign_preserved()

    def test_candidate_keeps_installed_version_suffixes_missing_from_source(self):
        installed = json.loads(self.installed_catalog.read_text())
        installed['version'] += '+later-unrelated-release.5'
        installed['deployment_note'] = 'Added only on the installed side'
        self.installed_catalog.write_text(json.dumps(installed))
        release.prepare(self.layout)
        release.guarded.apply(self.layout)
        actual = json.loads(self.installed_catalog.read_text())
        self.assertEqual(actual['version'], installed['version'] + '+etm-region.1')
        self.assertEqual(actual['deployment_note'], installed['deployment_note'])
        self.assertEqual(actual['services'], [self.new_etm, self.other_service])
        self.assert_foreign_preserved()

    def test_concurrent_catalog_edit_blocks_all_apply_writes(self):
        release.prepare(self.layout)
        catalog = json.loads(self.installed_catalog.read_text())
        catalog['services'][1]['instructions'].append('Another deployment after staging.')
        self.installed_catalog.write_text(json.dumps(catalog))
        before = self.contents()
        with self.assertRaises(release.guarded.ReleaseError):
            release.guarded.apply(self.layout)
        self.assertEqual(self.contents(), before)
        self.assertFalse((self.layout.backup / 'applied.json').exists())
        self.assert_foreign_preserved()

    def test_catalog_change_during_candidate_creation_cannot_publish_stale_services(self):
        original_prepare = release.guarded.prepare

        def concurrent_prepare(layout):
            catalog = json.loads(self.installed_catalog.read_text())
            catalog['services'][1]['instructions'].append('Concurrent service update.')
            self.installed_catalog.write_text(json.dumps(catalog))
            return original_prepare(layout)

        with patch.object(release.guarded, 'prepare', side_effect=concurrent_prepare):
            with self.assertRaisesRegex(release.guarded.ReleaseError, 'changed while preparing'):
                release.prepare(self.layout)
        before = self.contents()
        with self.assertRaises(release.guarded.ReleaseError):
            release.guarded.apply(self.layout)
        self.assertEqual(self.contents(), before)
        self.assertFalse((self.layout.backup / 'manifest.json').exists())
        self.assert_foreign_preserved()


if __name__ == '__main__':
    unittest.main()
