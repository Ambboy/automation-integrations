import concurrent.futures
import contextlib
from contextlib import contextmanager
import contextvars
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import yaml

from automation_integrations.catalog import Catalog
from ops import abcp_release as release
from ops import abcp_native_probe as native_probe


PROJECT = Path(__file__).resolve().parents[1]


def catalog_document():
    return {'schema_version': 1, 'version': 'abcp-test', 'agent_name': 'ABCP Agent',
            'instructions': 'ABCP: сначала integration_catalog, затем integration_read. Запись — integration_write.',
            'services': [{'id': 'abcp', 'name': 'ABCP', 'summary': 'Запчасти, заказы и склад',
                          'instructions': 'Использовать проверенные операции.',
                          'operations': {'orders_version': {'params': {}}}, 'write_operations': {}}]}


class FakeContext:
    def __init__(self, settings):
        self.settings = settings
        self.tools = {}
        self.schemas = {}
        self.hooks = {}

    def get_config(self, name, default=None):
        return self.settings.get(name, default)

    def register_tool(self, name, toolset, schema, handler):
        self.schemas[name] = schema
        self.tools[name] = handler

    def register_hook(self, name, handler):
        self.hooks[name] = handler

    def on_unload(self, handler):
        self.unload = handler


@contextmanager
def session(**overrides):
    values = {'HERMES_SESSION_PLATFORM': 'telegram', 'HERMES_SESSION_CHAT_TYPE': 'dm',
              'HERMES_SESSION_USER_ID': release.OWNER, 'HERMES_SESSION_CHAT_ID': release.OWNER,
              'HERMES_SESSION_KEY': 'owner-chat', 'HERMES_SESSION_MESSAGE_ID': 'msg-1',
              'HERMES_SESSION_ID': 'session-1'}
    values.update(overrides)
    tokens = [(var, var.set(value)) for key, value in values.items() for var in [contextvars.ContextVar(key)]]
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


class AbcpBridgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.path = self.home / 'catalog.json'
        self.path.write_text(json.dumps(catalog_document()))
        self.ctx = FakeContext({'enabled': True, 'owner_id': release.OWNER, 'chat_id': release.OWNER,
            'catalog_path': str(self.path), 'runner_path': str(self.home / 'abcp_api.py'),
            'write_runner_path': str(self.home / 'abcp_write.py'),
            'private_config': str(self.home / 'config.json'), 'max_request_chars': 2097152})
        spec = importlib.util.spec_from_file_location('abcp_test_plugin',
                    PROJECT / 'bridges/hermes_catalog/__init__.py', submodule_search_locations=[])
        self.plugin = importlib.util.module_from_spec(spec)
        constants = types.ModuleType('hermes_constants')
        constants.get_hermes_home = lambda: self.home
        delegation = types.ModuleType('agent.delegation_context')
        delegation.is_delegated_child_context = lambda: False
        fake_catalog = types.ModuleType('abcp_test_plugin.catalog')
        fake_catalog.Catalog = Catalog
        modules = {'abcp_test_plugin': self.plugin, 'abcp_test_plugin.catalog': fake_catalog,
                   'hermes_constants': constants, 'agent.delegation_context': delegation}
        patcher = patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        spec.loader.exec_module(self.plugin)
        self.plugin.register(self.ctx)
        self.event = {'session_id': 'session-1', 'platform': 'telegram',
                      'sender_id': release.OWNER, 'user_message': 'Проверь заказы'}

    def call(self, name, args):
        return json.loads(self.ctx.tools[name](args))

    def test_abcp_only_schemas_and_context(self):
        for name in ('integration_read', 'integration_write'):
            self.assertEqual(self.ctx.schemas[name]['parameters']['properties']['service']['enum'], ['abcp'])
        rendered = json.dumps(self.ctx.schemas, ensure_ascii=False)
        for other in ('fal/inference', 'ETM', 'Wiren Board', 'Точка', 'Грейфа'):
            self.assertNotIn(other, rendered)
        with session():
            result = self.ctx.hooks['pre_llm_call'](**self.event)
            self.assertIn('ABCP Agent', result['context'])
            self.assertNotIn('Грейфа', result['context'])
            self.assertEqual(self.call('integration_catalog', {})['services'][0]['id'], 'abcp')

    def test_default_catalog_context_retains_existing_agent_behavior(self):
        context = Catalog(PROJECT / 'registry/catalog.json').context()
        self.assertIn('Грейфа', context)
        self.assertIn('ЭТМ', context)

    def test_authorization_denial_does_not_start_runner(self):
        with patch.object(self.plugin.subprocess, 'run') as runner:
            self.assertEqual(self.call('integration_read', {'service': 'abcp'})['reason'],
                             'owner_private_telegram_required')
            with session(HERMES_SESSION_USER_ID='other'):
                self.ctx.hooks['pre_llm_call'](**self.event)
                self.assertFalse(self.call('integration_write', {'action': 'prepare'})['ok'])
            with session():
                self.assertEqual(self.call('integration_read', {'service': 'abcp'})['reason'], 'message_not_admitted')
                self.ctx.hooks['pre_llm_call'](**self.event)
                with patch.object(sys.modules['agent.delegation_context'], 'is_delegated_child_context', return_value=True):
                    self.assertEqual(self.call('integration_catalog', {})['reason'], 'child_or_background_context')
            runner.assert_not_called()

    def test_read_write_routing_limits_and_worker_admission(self):
        completed = subprocess.CompletedProcess([], 0, stdout='{"ok":true}', stderr='')
        with session(), patch.object(self.plugin.subprocess, 'run', return_value=completed) as runner:
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                pool.submit(contextvars.copy_context().run, lambda: self.ctx.hooks['pre_llm_call'](**self.event)).result()
            self.assertTrue(self.call('integration_read', {'service': 'abcp', 'operation': 'orders_version',
                                'params': {'batch': 'x' * 20000}})['ok'])
            self.assertEqual(runner.call_args.args[0][1], str(self.home / 'abcp_api.py'))
            self.assertTrue(self.call('integration_write', {'action': 'prepare', 'service': 'abcp',
                                                          'operation': 'create'})['ok'])
            self.assertEqual(runner.call_args.args[0][1], str(self.home / 'abcp_write.py'))
            payload = json.loads(runner.call_args.kwargs['input'])
            self.assertEqual(payload['context']['scope'][0], release.OWNER)
            runner.reset_mock()
            self.assertEqual(self.call('integration_read', {'service': 'etm'})['error'], 'invalid_read_request')
            self.assertEqual(self.call('integration_write', {'action': 'prepare', 'service': 'etm'})['error'], 'invalid_write_request')
            self.assertEqual(self.call('integration_write', {'action': 'confirm'})['error'], 'invalid_write_request')
            self.assertEqual(self.call('integration_read', {'service': 'abcp', 'params': {'large': 'x' * 2097152}})['error'],
                             'request_too_large')
            runner.assert_not_called()

    def test_confirmation_enters_only_through_authenticated_new_message(self):
        completed = subprocess.CompletedProcess([], 0, stdout='{"ok":true}', stderr='')
        with session(), patch.object(self.plugin.subprocess, 'run', return_value=completed) as runner:
            self.ctx.hooks['pre_llm_call'](**{**self.event, 'user_message': 'ПОДТВЕРЖДАЮ draft nonce'})
            payload = json.loads(runner.call_args.kwargs['input'])
            self.assertEqual(payload['request']['action'], 'confirm')
            self.assertEqual(payload['context']['message_id'], 'msg-1')


class AbcpReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.layout = release.Layout(base / 'bundle', base / 'hermes', base / 'runtime', base / 'backup')
        self.layout.home.mkdir()
        self.original = b'# preserved header\ntts:\n  provider: automation-speech\nplugins:\n  enabled: [automation-speech-source]\n  entries:\n    automation-speech-source:\n      settings:\n        enabled: true\nplatform_toolsets:\n  telegram: [hermes-telegram]\n  cli: [hermes-cli]\nother:\n  keep: true\n'
        self.layout.config.write_bytes(self.original)
        (self.layout.home / 'gateway_state.json').write_text('{"active_agents":0}')
        self.layout.root.mkdir()
        self.private = self.layout.root / 'config.json'
        self.private.write_text('{"credentials_file":"private-env"}')
        self.private.chmod(0o600)
        for source, target in release.bundle_files(self.layout):
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text('test content\n')
        (self.layout.source / 'registry/catalog.json').write_text(json.dumps(catalog_document()))

    def snapshot(self):
        targets = [t for _, t in release.bundle_files(self.layout)] + [self.layout.config]
        return {str(t): t.read_bytes() if t.exists() else None for t in targets}

    def test_apply_and_rollback_preserve_speech_and_credentials(self):
        baseline = self.snapshot()
        self.assertFalse(release.prepare(self.layout)['installed_files_changed'])
        self.assertEqual(self.snapshot(), baseline)
        self.assertFalse(release.apply(self.layout)['gateway_restarted'])
        cfg = yaml.safe_load(self.layout.config.read_bytes())
        old = yaml.safe_load(self.original)
        self.assertEqual(cfg['tts'], old['tts'])
        self.assertEqual(cfg['plugins']['entries']['automation-speech-source'],
                         old['plugins']['entries']['automation-speech-source'])
        self.assertEqual(cfg['platform_toolsets']['cli'], ['hermes-cli'])
        self.assertEqual(cfg['plugins']['entries'][release.NAME]['settings']['owner_id'], release.OWNER)
        self.assertEqual(self.private.read_text(), '{"credentials_file":"private-env"}')
        release.rollback(self.layout)
        self.assertEqual(self.snapshot(), baseline)
        self.assertTrue((self.layout.root / 'state').is_dir())

    def test_missing_telegram_toolsets_preserve_native_defaults(self):
        for before in (b'tts: {provider: automation-speech}\n',
                       b'platform_toolsets: {cli: [hermes-cli]}\n'):
            with self.subTest(before=before):
                cfg = yaml.safe_load(release.render(before, self.layout.root))
                self.assertEqual(cfg['platform_toolsets']['telegram'], ['hermes-telegram', 'automation-api'])
        cfg = yaml.safe_load(release.render(b'platform_toolsets: {telegram: [custom-tool]}\n', self.layout.root))
        self.assertEqual(cfg['platform_toolsets']['telegram'], ['custom-tool', 'automation-api'])

    def test_config_cas_denies_apply_and_rollback(self):
        release.prepare(self.layout)
        self.layout.config.write_bytes(self.original + b'late: true\n')
        before = self.snapshot()
        with self.assertRaisesRegex(release.ReleaseError, 'Concurrent'):
            release.apply(self.layout)
        self.assertEqual(self.snapshot(), before)
        self.layout.config.write_bytes(self.original)
        release.apply(self.layout)
        self.layout.config.write_bytes(self.layout.config.read_bytes() + b'late: true\n')
        before = self.snapshot()
        with self.assertRaisesRegex(release.ReleaseError, 'Concurrent'):
            release.rollback(self.layout)
        self.assertEqual(self.snapshot(), before)

    def test_reviewed_bundle_is_pinned_and_busy_gateway_denies_install(self):
        release.prepare(self.layout)
        source = self.layout.source / 'automation_integrations/abcp_api.py'
        expected = source.read_bytes()
        source.write_bytes(b'late source change')
        (self.layout.home / 'gateway_state.json').write_text('{"active_agents":1}')
        before = self.snapshot()
        with self.assertRaisesRegex(release.ReleaseError, 'zero active'):
            release.apply(self.layout)
        self.assertEqual(self.snapshot(), before)
        (self.layout.home / 'gateway_state.json').write_text('{"active_agents":0}')
        release.apply(self.layout)
        self.assertEqual((self.layout.root / 'release/automation_integrations/abcp_api.py').read_bytes(), expected)

    def test_manifest_cannot_redirect_into_credentials(self):
        release.prepare(self.layout)
        path = self.layout.backup / 'manifest.json'
        doc = json.loads(path.read_text())
        doc['entries'][0]['target'] = str(self.private)
        path.write_text(json.dumps(doc))
        before = self.snapshot()
        with self.assertRaises(release.ReleaseError):
            release.apply(self.layout)
        self.assertEqual(self.snapshot(), before)

    def test_partial_install_failure_restores_original_files(self):
        release.prepare(self.layout)
        before = self.snapshot()
        original_atomic = release.atomic

        def interrupted(path, data, mode=0o600):
            if path == self.layout.plugin / '__init__.py':
                raise OSError('simulated full filesystem')
            return original_atomic(path, data, mode)

        with patch.object(release, 'atomic', side_effect=interrupted), self.assertRaises(OSError):
            release.apply(self.layout)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.layout.backup / 'applied.json').exists())

    def test_symlink_source_is_refused_before_any_installation(self):
        source = self.layout.source / 'automation_integrations/abcp_api.py'
        source.unlink()
        source.symlink_to(self.private)
        before = self.snapshot()
        with self.assertRaisesRegex(release.ReleaseError, 'Symlinks'):
            release.prepare(self.layout)
        self.assertEqual(self.snapshot(), before)

    def test_lock_and_wrong_catalog_deny_prepare(self):
        with release.locked(self.layout), self.assertRaisesRegex(release.ReleaseError, 'lock'):
            release.prepare(self.layout)
        document = catalog_document()
        document['services'][0]['id'] = 'etm'
        (self.layout.source / 'registry/catalog.json').write_text(json.dumps(document))
        with self.assertRaisesRegex(release.ReleaseError, 'ABCP-only'):
            release.prepare(self.layout)


class NativeProbeSummaryTests(unittest.TestCase):
    def test_exception_cannot_print_provider_or_credential_material(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'safe-summary.json'
            stdout = io.StringIO()
            with patch.object(native_probe, 'probe', side_effect=RuntimeError('SECRET provider payload')):
                with patch('sys.argv', ['abcp-probe', '--output', str(output)]), \
                        contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as stopped:
                    native_probe.main()
            self.assertEqual(stopped.exception.code, 1)
            self.assertNotIn('SECRET', stdout.getvalue() + output.read_text())
            self.assertEqual(json.loads(output.read_text())['error'], 'native_probe_failed')
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)


@unittest.skipUnless(os.environ.get('HERMES_NATIVE_TEST') == '1', 'Requires the installed Hermes runtime')
class NativeAbcpBridgeTests(unittest.TestCase):
    def test_native_abcp_registration_dispatch_context_and_unload(self):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import get_plugin_manager
        from tools.registry import registry
        from model_tools import get_tool_definitions
        from gateway.session_context import set_session_vars, clear_session_vars
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / 'hermes'
            home.mkdir()
            plugin = home / 'plugins' / release.NAME
            shutil.copytree(PROJECT / 'bridges/hermes_catalog', plugin, ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copyfile(PROJECT / 'automation_integrations/catalog.py', plugin / 'catalog.py')
            catalog = home / 'catalog.json'
            catalog.write_text(json.dumps(catalog_document()))
            settings = {'enabled': True, 'owner_id': release.OWNER, 'chat_id': release.OWNER,
                        'catalog_path': str(catalog), 'runner_path': '/nonexistent/abcp_api.py',
                        'write_runner_path': '/nonexistent/abcp_write.py', 'private_config': '/nonexistent/config.json'}
            (home / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': [release.NAME],
                         'entries': {release.NAME: {'settings': settings}}}}))
            with patch.dict(os.environ, {'HERMES_HOME': str(home), 'HERMES_RUNTIME_DIR': temporary + '/runtime'}):
                override = set_hermes_home_override(home)
                manager = get_plugin_manager()
                try:
                    manager.discover_and_load()
                    definitions = get_tool_definitions(enabled_toolsets=['automation-api'], quiet_mode=True,
                                                       skip_tool_search_assembly=True)
                    self.assertEqual({d['function']['name'] for d in definitions},
                                     {'integration_catalog', 'integration_read', 'integration_write'})
                    for definition in definitions:
                        function = definition['function']
                        if function['name'] != 'integration_catalog':
                            self.assertEqual(function['parameters']['properties']['service']['enum'], ['abcp'])

                    def call(name='integration_catalog', args=None):
                        return json.loads(registry.dispatch(name, args or {}, scope=str(home)))

                    event = {'platform': 'telegram', 'sender_id': release.OWNER, 'session_id': 's',
                             'turn_id': 't', 'user_message': 'Проверь заказы ABCP', 'conversation_history': []}
                    self.assertFalse(call()['ok'])
                    tokens = set_session_vars(chat_type='dm', session_key='owner', message_id='m1',
                                             platform='telegram', chat_id=release.OWNER,
                                             user_id=release.OWNER, session_id='s')
                    try:
                        contexts = manager.invoke_hook('pre_llm_call', **event)
                        self.assertIn('ABCP Agent', contexts[0]['context'])
                        self.assertNotIn('Грейфа', contexts[0]['context'])
                        self.assertEqual(call(args={'service': 'abcp'})['services'][0]['id'], 'abcp')
                        with concurrent.futures.ThreadPoolExecutor(1) as pool:
                            self.assertTrue(pool.submit(contextvars.copy_context().run, call).result()['ok'])
                        self.assertEqual(call('integration_read', {'service': 'abcp', 'operation': 'orders_version'})['error'],
                                         'read_runner_unavailable')
                        from agent.delegation_context import delegated_child_context
                        with delegated_child_context():
                            self.assertEqual(call()['reason'], 'child_or_background_context')
                    finally:
                        clear_session_vars(tokens)
                finally:
                    manager.unload()
                    reset_hermes_home_override(override)
                self.assertIsNone(registry.get_entry('integration_catalog', scope=str(home)))


if __name__ == '__main__':
    unittest.main()
