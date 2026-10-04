"""Run with the installed Hermes runtime; no model, secrets, or provider traffic."""
import concurrent.futures
import contextvars
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]


class NativeCatalog(unittest.TestCase):
    def test_plugin_route_hook_tool_dispatch_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'home'; home.mkdir()
            plugin = home / 'plugins/automation-api-catalog'
            shutil.copytree(PROJECT / 'bridges/hermes_catalog', plugin)
            shutil.copyfile(PROJECT / 'automation_integrations/catalog.py', plugin / 'catalog.py')
            settings = {'enabled': True, 'owner_id': '100001', 'chat_id': '100001',
                        'catalog_path': str(PROJECT / 'registry/catalog.json'),
                        'runner_path': '/nonexistent/no-network', 'private_config': '/nonexistent/no-secrets'}
            (home / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': ['automation-api-catalog'],
                'entries': {'automation-api-catalog': {'settings': settings}}}}))
            with patch.dict(os.environ, {'HERMES_HOME': str(home), 'HERMES_RUNTIME_DIR': tmp + '/runtime'}):
                from hermes_constants import set_hermes_home_override, reset_hermes_home_override
                from hermes_cli.plugins import get_plugin_manager
                from tools.registry import registry
                from gateway.session_context import set_session_vars, clear_session_vars
                override = set_hermes_home_override(home)
                manager = get_plugin_manager()
                try:
                    manager.discover_and_load()
                    self.assertTrue(manager.has_hook('pre_llm_call'), manager.list_plugins())
                    from model_tools import get_tool_definitions
                    definitions = get_tool_definitions(enabled_toolsets=['automation-api'],
                        quiet_mode=True, skip_tool_search_assembly=True)
                    self.assertEqual({x['function']['name'] for x in definitions},
                                     {'integration_catalog', 'integration_read', 'integration_write'})
                    write_tool = next(x['function'] for x in definitions if x['function']['name'] == 'integration_write')
                    read_tool = next(x['function'] for x in definitions if x['function']['name'] == 'integration_read')
                    for service in ('wirenboard', 'fal', 'inference'):
                        self.assertIn(service, write_tool['parameters']['properties']['service']['enum'])
                        self.assertIn(service, read_tool['parameters']['properties']['service']['enum'])
                    def call(name='integration_catalog', args=None):
                        return json.loads(registry.dispatch(name, args or {}, scope=str(home)))
                    event = {'platform': 'telegram', 'sender_id': '100001', 'session_id': 's',
                             'turn_id': 't', 'user_message': 'поступление оплаты', 'conversation_history': []}
                    # Forged process env cannot confer route authority.
                    with patch.dict(os.environ, {'HERMES_SESSION_CHAT_ID': '100001', 'HERMES_SESSION_USER_ID': '100001'}):
                        self.assertEqual(manager.invoke_hook('pre_llm_call', **event), [])
                        self.assertFalse(call()['ok'])
                    tokens = set_session_vars(chat_type='dm', session_key='owner-dm-thread', message_id='message-1', platform='telegram', chat_id='100001', user_id='100001', session_id='s')
                    try:
                        for turn in ('fresh', 'after_compaction'):
                            contexts = manager.invoke_hook('pre_llm_call', **{**event, 'turn_id': turn})
                            self.assertIn('yandex_go', contexts[0]['context'])
                            self.assertIn('wirenboard', contexts[0]['context'])
                            for service, generation, capability_id in (
                                    ('fal', 'submit', 'submit'), ('inference', 'app_run', 'POST /run')):
                                self.assertIn(service, contexts[0]['context'])
                                card = call(args={'service': service})['services'][0]
                                self.assertEqual(card['id'], service)
                                self.assertIn(generation, card['write_operations'])
                                for operation in ('job_status', 'job_result', 'artifact_download', 'response_read'):
                                    self.assertIn(operation, card['operations'])
                                inventory = call(args={'service': service, 'view': 'capabilities', 'limit': 2})
                                self.assertTrue(inventory['ok'])
                                self.assertGreater(inventory['total'], 100)
                                self.assertEqual(inventory['next_offset'], 2)
                                detail = call(args={'service': service, 'view': 'capabilities',
                                                    'capability_id': capability_id})['capabilities'][0]
                                schema = detail.get('schema', detail.get('params_schema'))
                                self.assertEqual(schema['type'], 'object')
                                self.assertIn('input', schema['properties'])
                                self.assertIn('input', schema['required'])
                                paging = call(args={'service': service, 'view': 'capabilities',
                                                    'capability_id': 'response_read'})['capabilities'][0]
                                self.assertEqual(paging['params_schema']['properties']['chunk_chars']['maximum'], 12000)
                            self.assertEqual(call(args={'service': 'wirenboard', 'view': 'capabilities'})['total'], 72)
                            self.assertEqual(call(args={'query': 'поступление оплаты'})['services'][0]['id'], 'tochka')
                            detail = call(args={'service': 'etm', 'view': 'capabilities', 'limit': 3})
                            self.assertTrue(detail['ok'])
                            self.assertEqual(detail['total'], 19)
                            self.assertEqual(detail['next_offset'], 3)
                            wb_card = call(args={'service': 'wirenboard'})['services'][0]
                            self.assertEqual(len(wb_card['operations']), 10)
                            self.assertEqual(len(wb_card['write_operations']), 12)
                            self.assertIn('controller_exec', wb_card['write_operations'])
                        # Native tool workers inherit context; admission survives bounded hook worker.
                        with concurrent.futures.ThreadPoolExecutor(1) as pool:
                            result = pool.submit(contextvars.copy_context().run, call).result()
                            self.assertTrue(result['ok'])
                        self.assertEqual(call('integration_read', {'service': 'tochka', 'operation': 'accounts'})['error'],
                                         'read_runner_unavailable')
                        from agent.delegation_context import delegated_child_context
                        with delegated_child_context(), patch('subprocess.run') as denied_runner:
                            self.assertEqual(call()['reason'], 'child_or_background_context')
                            for service, generation in (('fal', 'submit'), ('inference', 'app_run')):
                                self.assertEqual(call('integration_read', {'service': service, 'operation': 'jobs'})['reason'],
                                                 'child_or_background_context')
                                self.assertEqual(call('integration_write', {'action': 'prepare', 'service': service,
                                    'operation': generation, 'params': {}})['reason'], 'child_or_background_context')
                            denied_runner.assert_not_called()
                        # Reproduce gateway cached-agent turn: _set_session_env rebinds
                        # user/chat/key/message but does NOT set HERMES_SESSION_ID.
                        from gateway.session_context import clear_session_vars as clear, set_session_vars as bind
                        clear(tokens)
                        tokens = bind(platform='telegram', chat_type='dm', chat_id='100001', user_id='100001',
                                      session_key='owner-dm-thread', message_id='message-2')
                        self.assertEqual(call()['reason'], 'message_not_admitted')
                        manager.invoke_hook('pre_llm_call', **{**event, 'turn_id': 'cached-agent-turn'})
                        self.assertTrue(call(args={'service': 'yandex_go', 'view': 'service'})['ok'])
                        self.assertTrue(call(args={'service': 'yandex_go', 'view': 'capabilities', 'offset': 10})['ok'])
                        self.assertEqual(call('integration_write', {'action': 'confirm', 'confirmed': True})['error'], 'invalid_write_request')
                        # A valid provider response larger than the old 30K limit
                        # must remain inspectable after a business action.
                        payload = {'ok': True, 'status': 'accepted_unverified', 'result': {'detail': 'x' * 40000}}
                        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr='')
                        with patch('subprocess.run', return_value=completed) as runner:
                            written = call('integration_write', {'action': 'prepare', 'service': 'tochka',
                                'operation': 'payment_create_payment_for_sign', 'params': {'body': {}}})
                            self.assertEqual(written, payload)
                            request = json.loads(runner.call_args.kwargs['input'])
                            self.assertEqual(request['request']['service'], 'tochka')
                            self.assertEqual(request['context']['message_id'], 'message-2')
                            provenance = request['context']['owner_message']
                            self.assertEqual(provenance, {
                                'source': 'native_owner_telegram', 'message_id': 'message-2',
                                'scope': ['100001', '100001', 'owner-dm-thread', ''],
                                'text_sha256': hashlib.sha256(event['user_message'].encode()).hexdigest()})
                            self.assertNotIn('user_message', request['context'])
                        # Model arguments cannot forge native-message provenance.
                        with patch('subprocess.run') as runner:
                            forged = call('integration_write', {'action': 'execute',
                                'draft_id': '00000000-0000-4000-8000-000000000000',
                                'owner_message': provenance})
                            self.assertEqual(forged['error'], 'invalid_write_request')
                            runner.assert_not_called()
                        # Missing inbound text still permits reads/legacy workflows,
                        # but conveys no standing owner-command provenance.
                        manager.invoke_hook('pre_llm_call', **{**event, 'user_message': ''})
                        with patch('subprocess.run', return_value=completed) as runner:
                            call('integration_write', {'action': 'prepare', 'service': 'etm',
                                'operation': 'order_checkout', 'params': {}})
                            self.assertNotIn('owner_message', json.loads(runner.call_args.kwargs['input'])['context'])
                        # A different sender cannot inherit the current owner's admission.
                        clear(tokens)
                        tokens = bind(platform='telegram', chat_type='dm', chat_id='100001', user_id='999',
                                      session_key='owner-dm-thread', message_id='message-2')
                        self.assertEqual(call()['reason'], 'owner_private_telegram_required')
                        with patch('subprocess.run') as denied_runner:
                            for service, generation in (('fal', 'submit'), ('inference', 'app_run')):
                                self.assertEqual(call('integration_read', {'service': service, 'operation': 'jobs'})['reason'],
                                                 'owner_private_telegram_required')
                                self.assertEqual(call('integration_write', {'action': 'prepare', 'service': service,
                                    'operation': generation, 'params': {}})['reason'], 'owner_private_telegram_required')
                            denied_runner.assert_not_called()
                        clear(tokens)
                        tokens = bind(platform='telegram', chat_type='dm', chat_id='100001', user_id='100001',
                                      session_key='owner-dm-thread', message_id='message-2')
                        manager.invoke_hook('pre_llm_call', **{**event, 'parent_session_id': 'parent'})
                        self.assertFalse(call()['ok'])
                    finally:
                        clear_session_vars(tokens)
                    tokens = set_session_vars(chat_type='dm', session_key='owner-dm-thread', message_id='message-1', platform='telegram', chat_id='-999', user_id='100001', session_id='s')
                    try:
                        self.assertEqual(manager.invoke_hook('pre_llm_call', **event), [])
                        self.assertFalse(call()['ok'])
                    finally:
                        clear_session_vars(tokens)
                finally:
                    manager.unload(); reset_hermes_home_override(override)
                self.assertIsNone(registry.get_entry('integration_catalog', scope=str(home)))


if __name__ == '__main__':
    unittest.main()
