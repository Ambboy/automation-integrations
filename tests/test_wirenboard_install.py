"""Exercise full installer/updater in temporary homes, never the live release."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ops import greif_catalog_config as install
from ops import update_catalog_release as update


PROJECT = Path(__file__).resolve().parents[1]
MANAGEMENT = ('wirenboard_control_contract.py', 'wirenboard_shell.py', 'wirenboard_control.py')


class WirenboardInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'hermes'
        self.state = Path(self.tmp.name) / 'catalog'
        self.home.mkdir()
        self.state.mkdir()
        (self.home / 'config.yaml').write_text('model: keep-existing-model\n')
        (self.home / 'gateway_state.json').write_text(json.dumps({'active_agents': 0}))
        (self.state / 'private.json').write_text('{"fixture":true}\n')
        (self.state / 'validation.json').write_text('{"passed":true}\n')
        self.protected = {
            self.state / 'private.json': b'{"fixture":true}\n',
            self.state / 'state/wirenboard-session.json': b'existing rotated session',
            self.state / 'state/wirenboard-writes/existing.json': b'existing approved draft',
            self.state / 'state/etm-writes/existing.json': b'existing ETM draft',
        }
        for path, data in self.protected.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def fresh_install(self):
        with patch.multiple(install, PROJECT=PROJECT, HOME=self.home, ROOT=self.state), \
                patch('sys.argv', ['install', 'apply']), contextlib.redirect_stdout(io.StringIO()):
            install.main()

    def update_action(self, action):
        with patch.multiple(update, P=PROJECT, H=self.home, R=self.state, B=self.state / 'update-fixture'), \
                patch('sys.argv', ['update', action]), contextlib.redirect_stdout(io.StringIO()):
            update.main()

    def assert_private_state_preserved(self):
        for path, data in self.protected.items():
            with self.subTest(path=path):
                self.assertEqual(path.read_bytes(), data)

    def test_fresh_install_includes_management_dependencies_and_loadable_dispatchers(self):
        self.fresh_install()
        release = self.state / 'release'
        for name in (*MANAGEMENT, 'wirenboard.py', 'wirenboard_http.py',
                     'etm_document.py', 'etm_order.py', 'etm_workflow.py'):
            self.assertEqual((release / name).read_bytes(), (PROJECT / 'automation_integrations' / name).read_bytes())
        self.assertEqual((release / 'capabilities/wirenboard.json').read_bytes(),
                         (PROJECT / 'registry/capabilities/wirenboard.json').read_bytes())
        self.assertTrue((release / 'contracts/etm.json').is_file())
        script = ('import api_read, api_write, wirenboard_control, wirenboard_control_contract, '
                  'wirenboard_shell, etm_workflow; '
                  'assert "wirenboard" in api_read.OPERATIONS; '
                  'assert "controller_update" in wirenboard_control_contract.OPERATIONS')
        result = subprocess.run([sys.executable, '-c', script], cwd=self.tmp.name,
                                env={**os.environ, 'PYTHONPATH': str(release)},
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('keep-existing-model', (self.home / 'config.yaml').read_text())
        self.assert_private_state_preserved()

    def test_regular_update_installs_dependencies_before_write_dispatcher_and_maps_inventory(self):
        self.fresh_install()
        release = self.state / 'release'
        for name in MANAGEMENT:
            (release / name).unlink()
        config_before = (self.home / 'config.yaml').read_bytes()
        writes = []
        original_atomic = update.atomic
        def record(path, data):
            writes.append(path)
            original_atomic(path, data)
        with patch.object(update, 'atomic', side_effect=record):
            self.update_action('apply')
        for name in MANAGEMENT:
            target = release / name
            self.assertEqual(target.read_bytes(), (PROJECT / 'automation_integrations' / name).read_bytes())
            self.assertLess(writes.index(target), writes.index(release / 'api_write.py'))
            self.assertLess(writes.index(target), writes.index(release / 'api_read.py'))
        self.assertEqual((release / 'capabilities/wirenboard.json').read_bytes(),
                         (PROJECT / 'registry/capabilities/wirenboard.json').read_bytes())
        self.assertEqual((release / 'catalog.json').read_bytes(), (PROJECT / 'registry/catalog.json').read_bytes())
        self.assertEqual((self.home / 'config.yaml').read_bytes(), config_before)
        self.assert_private_state_preserved()
        self.update_action('rollback')
        self.assertTrue(all(not (release / name).exists() for name in MANAGEMENT))
        self.assertTrue((release / 'etm_workflow.py').is_file())
        self.assertEqual((self.home / 'config.yaml').read_bytes(), config_before)
        self.assert_private_state_preserved()


if __name__ == '__main__':
    unittest.main()
