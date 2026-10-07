"""Orchestration regression tests: no real credentials or provider requests."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from automation_integrations import media_api as media
from automation_integrations.api_read import Failure
from automation_integrations.media_runtime import JobStore, BudgetLedger, account_fingerprint


class Vault:
    def __init__(self):
        self.key = 'fixture-secret-one'
        self.calls = []

    def get(self, service):
        self.calls.append(service)
        return {'FAL_KEY' if service == 'fal' else 'INFERENCE_API_KEY': self.key}


def owner(message='message-1', scope=None):
    scope = scope or ['owner', 'owner', 'owner-session', '']
    return {'scope': scope, 'message_id': message, 'owner_message': {
        'source': 'native_owner_telegram', 'scope': scope, 'message_id': message,
        'text_sha256': hashlib.sha256(b'Generate the requested image').hexdigest()}}


class MediaAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {'state_dir': self.tmp.name, 'media_authorization': 'owner_command'}
        self.vault = Vault()
        self.context = owner()
        self.request = {'action': 'prepare', 'service': 'fal', 'operation': 'submit',
                        'params': {'endpoint_id': 'fal-ai/flux/schnell', 'input': {'prompt': 'A tree'}}}
        self.calls = []
        self.submit_result = {'request_id': 'provider-1', 'status': 'IN_QUEUE'}
        self.status_result = {'status': 'COMPLETED'}
        self.final_result = {'images': [{'url': 'https://v3.fal.media/image.png?signature=PRIVATE'}]}
        self.inference_task_status = 'completed'
        self.inference_task_cost = {'charged': 12500000, 'refunded': 0, 'total': 12500000}
        self.network = patch.object(media, '_call', side_effect=self.call)
        self.mock_call = self.network.start()
        self.addCleanup(self.network.stop)
        self.network_guard = patch('automation_integrations.media_runtime._open_response',
                                   side_effect=AssertionError('Offline tests must not open network connections'))
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)

    def call(self, service, operation, params, secret, transport=None):
        self.calls.append((service, operation, deepcopy(params)))
        if operation == 'estimate':
            return {'total_cost': .25, 'currency': 'USD'} if service == 'fal' else {'confidence': 'exact', 'microcents': 25000000}
        if operation == 'app_get_by_ref':
            return {'id': 'app-one'}
        if operation in ('submit', 'run', 'stream', 'app_run', 'chat_completion'):
            if isinstance(self.submit_result, Exception):
                raise self.submit_result
            return deepcopy(self.submit_result)
        if operation == 'status':
            return deepcopy(self.status_result)
        if operation == 'result':
            if isinstance(self.final_result, Exception):
                raise self.final_result
            return deepcopy(self.final_result)
        if operation == 'task_get':
            return {'id': params['id'], 'status': self.inference_task_status, 'output': {'text': 'done'}}
        if operation == 'task_cost':
            return deepcopy(self.inference_task_cost)
        if operation == 'balance':
            return {'balance': 250000000}
        raise AssertionError('Unexpected fixture operation: ' + operation)

    def prepare(self, request=None, context=None):
        return media.process(request or self.request, context or self.context, self.config, vault=self.vault)

    def execute(self, draft_id, context=None):
        return media.process({'action': 'execute', 'draft_id': draft_id}, context or self.context,
                             self.config, vault=self.vault)

    def test_owner_evidence_and_scope_rejected_before_secrets_or_network(self):
        contexts = [{}, owner(scope=['owner', 'other', 's', '']), owner(scope=['', '', 's', ''])]
        for field, value in (('source', 'model_assertion'), ('message_id', 'old'),
                             ('text_sha256', hashlib.sha256(b'').hexdigest())):
            context = owner()
            context['owner_message'][field] = value
            contexts.append(context)
        for context in contexts:
            with self.subTest(context=context):
                with self.assertRaisesRegex(Failure, 'native_owner_command_required'):
                    media.process(self.request, context, self.config, vault=self.vault)
        self.assertEqual(self.vault.calls, [])
        self.assertEqual(self.calls, [])
        self.assertFalse(media.root(self.config).exists())

    def test_read_cannot_submit_and_invalid_write_fails_before_credentials(self):
        with self.assertRaisesRegex(Failure, 'write_tool_required'):
            media.read('fal', 'submit', self.request['params'], self.config, vault=self.vault)
        bad = deepcopy(self.request)
        bad['params']['endpoint_id'] = 'https://attacker.test/endpoint'
        with self.assertRaises(Failure):
            self.prepare(bad)
        self.assertEqual(self.vault.calls, [])
        self.assertEqual(self.calls, [])

    def test_prepare_execute_is_once_and_same_message_is_idempotent(self):
        draft = self.prepare()
        self.assertTrue(draft['ok'])
        self.assertFalse(draft['confirmation_required'])
        self.assertEqual([call[1] for call in self.calls], ['estimate'])
        self.assertEqual(self.prepare()['draft_id'], draft['draft_id'])
        sent = self.execute(draft['draft_id'])
        self.assertEqual(sent['status'], 'submitted')
        self.assertEqual(sent['provider_job_id'], 'provider-1')
        repeated = self.execute(draft['draft_id'])
        self.assertFalse(repeated['submitted_again'])
        self.assertEqual(sum(call[1] == 'submit' for call in self.calls), 1)
        account = account_fingerprint({'FAL_KEY': self.vault.key})
        self.assertEqual(len(BudgetLedger(media.root(self.config)).snapshot('fal', account=account)['reservations']), 1)

    def test_timeout_is_durable_and_new_message_cannot_replace_unknown_submission(self):
        self.submit_result = Failure('request_timeout')
        draft = self.prepare()
        failed = self.execute(draft['draft_id'])
        self.assertFalse(failed['ok'])
        self.assertEqual(failed['status'], 'outcome_unknown')
        self.execute(draft['draft_id'])
        blocked = self.prepare(context=owner('message-2'))
        self.assertFalse(blocked['ok'])
        self.assertEqual(blocked['error'], 'existing_uncertain_media_job')
        self.assertEqual(blocked['job_id'], draft['job_id'])
        self.assertEqual(sum(call[1] == 'submit' for call in self.calls), 1)
        ledger = BudgetLedger(media.root(self.config)).snapshot('fal')
        self.assertEqual(ledger['reservations'][0]['state'], 'unknown')
        self.assertEqual(JobStore(media.root(self.config)).get(draft['job_id'])['status'], 'outcome_unknown')

    def test_account_change_and_other_scope_do_not_execute_prior_draft(self):
        draft = self.prepare()
        with self.assertRaisesRegex(Failure, 'media_job_scope_mismatch'):
            self.execute(draft['draft_id'], owner(scope=['owner', 'owner', 'other-session', '']))
        self.vault.key = 'fixture-secret-two'
        with self.assertRaisesRegex(Failure, 'media_account_changed'):
            self.execute(draft['draft_id'])
        self.assertEqual(sum(call[1] == 'submit' for call in self.calls), 0)
        self.assertEqual(media.read('fal', 'jobs', {}, self.config, vault=self.vault)['data'], [])
        another = self.prepare()
        self.assertNotEqual(another['job_id'], draft['job_id'])

    def test_expired_or_reused_owner_message_cannot_execute_prepared_draft(self):
        draft = self.prepare()
        with self.assertRaisesRegex(Failure, 'media_owner_message_changed_reprepare_required'):
            self.execute(draft['draft_id'], owner('message-2'))
        with self.assertRaisesRegex(Failure, 'media_preparation_expired'):
            media.process({'action': 'execute', 'draft_id': draft['draft_id']}, self.context, self.config,
                          vault=self.vault, clock=lambda: 10**12)
        self.assertEqual(sum(call[1] == 'submit' for call in self.calls), 0)

    def test_concurrent_execution_sends_once(self):
        draft = self.prepare()
        entered, release = threading.Event(), threading.Event()
        original = self.call
        def held(service, operation, params, secret, transport=None):
            if operation == 'submit':
                entered.set()
                if not release.wait(5):
                    raise AssertionError('Test release missing')
            return original(service, operation, params, secret, transport)
        self.mock_call.side_effect = held
        with ThreadPoolExecutor(max_workers=4) as pool:
            first = pool.submit(self.execute, draft['draft_id'])
            self.assertTrue(entered.wait(3))
            later = [pool.submit(self.execute, draft['draft_id']) for _ in range(3)]
            try:
                for result in later:
                    self.assertFalse(result.result(timeout=3)['submitted_again'])
            finally:
                release.set()
            self.assertEqual(first.result(timeout=3)['status'], 'submitted')
        self.assertEqual(sum(call[1] == 'submit' for call in self.calls), 1)

    def test_fal_completion_retrieves_artifact_references_and_caches_result(self):
        draft = self.prepare()
        self.execute(draft['draft_id'])
        result = media.read('fal', 'job_result', {'job_id': draft['job_id']}, self.config, vault=self.vault)
        self.assertEqual(result['data']['status'], 'completed')
        artifact = result['data']['result']['images'][0]['url']
        self.assertEqual(artifact['status'], 'remote')
        self.assertIn('artifact_id', artifact)
        rendered = json.dumps(result)
        self.assertNotIn('signature=PRIVATE', rendered)
        self.assertNotIn(self.vault.key, rendered)
        before = len(self.calls)
        media.read('fal', 'job_result', {'job_id': draft['job_id']}, self.config, vault=self.vault)
        self.assertEqual(len(self.calls), before)

    def test_fal_terminal_provider_error_is_persisted_without_retrying_result(self):
        draft = self.prepare()
        self.execute(draft['draft_id'])
        self.final_result = Failure('provider_http_error', 422)
        result = media.read('fal', 'job_result', {'job_id': draft['job_id']}, self.config, vault=self.vault)
        self.assertEqual(result['data']['status'], 'failed')
        before = len(self.calls)
        again = media.read('fal', 'job_result', {'job_id': draft['job_id']}, self.config, vault=self.vault)
        self.assertEqual(again['data']['status'], 'failed')
        self.assertEqual(len(self.calls), before)

    def test_artifact_download_is_account_bound_and_passes_no_api_credentials(self):
        draft = self.prepare()
        self.execute(draft['draft_id'])
        result = media.read('fal', 'job_result', {'job_id': draft['job_id']}, self.config, vault=self.vault)
        artifact = result['data']['result']['images'][0]['url']['artifact_id']
        transport = Mock()
        transport.request.return_value = b'\x89PNG\r\n\x1a\nfixture'
        with patch('automation_integrations.media_runtime._public_addresses', return_value=['8.8.8.8']):
            downloaded = media.read('fal', 'artifact_download', {'artifact_id': artifact}, self.config,
                                    vault=self.vault, transport=transport)
        self.assertEqual(downloaded['data']['status'], 'downloaded')
        self.assertEqual(transport.request.call_args.kwargs['headers'], {})
        self.assertNotIn(self.vault.key, repr(transport.request.call_args))
        self.vault.key = 'other-account'
        transport.reset_mock()
        with self.assertRaises(Exception):
            media.read('fal', 'artifact_download', {'artifact_id': artifact}, self.config,
                       vault=self.vault, transport=transport)
        transport.request.assert_not_called()

    def test_inference_balance_and_task_cost_use_microcent_conversion(self):
        balance = media.read('inference', 'balance', {}, self.config, vault=self.vault)
        self.assertEqual(balance['data']['balance_usd'], '2.5')
        self.assertEqual(balance['data']['unit'], 'microcents')
        request = {'action': 'prepare', 'service': 'inference', 'operation': 'app_run',
                   'params': {'app': 'example/model', 'input': {'prompt': 'A tree'}}}
        self.submit_result = {'id': 'task-one', 'status': 'queued'}
        draft = self.prepare(request)
        self.assertEqual(draft['preview']['estimate']['cost_usd'], '0.25')
        self.execute(draft['draft_id'])
        result = media.read('inference', 'job_result', {'job_id': draft['job_id']}, self.config, vault=self.vault)
        self.assertEqual(result['data']['status'], 'completed')
        ledger = BudgetLedger(media.root(self.config)).snapshot('inference')
        self.assertEqual(ledger['reservations'][0]['actual_cost'], '0.125')

    def test_historical_estimate_cannot_authorize_a_hard_spend_cap(self):
        self.config['media_limits'] = {'fal': {'per_task': '1'}}
        draft = self.prepare()
        self.assertEqual(draft['preview']['estimate']['confidence'], 'historical_estimate')
        with self.assertRaises(Failure):
            self.execute(draft['draft_id'])
        self.assertEqual(sum(call[1] == 'submit' for call in self.calls), 0)

    def test_inference_numeric_completed_status_reconciles_net_charged(self):
        request = {'action': 'prepare', 'service': 'inference', 'operation': 'app_run',
                   'params': {'app': 'example/model', 'input': {'prompt': 'A tree'}}}
        self.submit_result = {'id': 'task-numeric', 'status': 0}
        self.inference_task_status = 10
        self.inference_task_cost = {'charged': 25000000, 'refunded': 5000000, 'total': 20000000}
        draft = self.prepare(request)
        self.execute(draft['draft_id'])
        result = media.read('inference', 'job_result', {'job_id': draft['job_id']}, self.config, vault=self.vault)
        self.assertEqual(result['data']['status'], 'completed')
        ledger = BudgetLedger(media.root(self.config)).snapshot('inference')
        self.assertEqual(ledger['reservations'][0]['actual_cost'], '0.2')

    def test_completed_inference_job_retries_only_cost_read_until_settled(self):
        request = {'action': 'prepare', 'service': 'inference', 'operation': 'app_run',
                   'params': {'app': 'example/model', 'input': {'prompt': 'A tree'}}}
        self.submit_result = {'id': 'task-cost-delayed', 'status': 'queued'}
        draft = self.prepare(request)
        self.execute(draft['draft_id'])
        original = self.call
        attempts = []
        def delayed(service, operation, params, secret, transport=None):
            if operation == 'task_cost':
                attempts.append(operation)
                if len(attempts) == 1:
                    raise Failure('provider_unavailable', 503)
            return original(service, operation, params, secret, transport)
        self.mock_call.side_effect = delayed
        first = media.read('inference', 'job_result', {'job_id': draft['job_id']}, self.config, vault=self.vault)
        self.assertEqual(first['data']['status'], 'completed')
        self.assertEqual(first['data']['billing']['state'], 'pending')
        self.assertEqual(BudgetLedger(media.root(self.config)).snapshot('inference')['reservations'][0]['state'], 'reserved')
        second = media.read('inference', 'job_result', {'job_id': draft['job_id']}, self.config, vault=self.vault)
        self.assertEqual(second['data']['billing'], {'state': 'settled', 'cost_usd': '0.125', 'currency': 'USD'})
        self.assertEqual(sum(call[1] == 'app_run' for call in self.calls), 1)
        self.assertEqual(sum(call[1] == 'task_get' for call in self.calls), 1)
        media.read('inference', 'job_status', {'job_id': draft['job_id']}, self.config, vault=self.vault)
        self.assertEqual(len(attempts), 2)

    def test_pinned_app_version_does_not_use_current_store_quote_under_cap(self):
        request = {'action': 'prepare', 'service': 'inference', 'operation': 'app_run',
                   'params': {'app': 'example/model@old-version', 'input': {'prompt': 'A tree'}}}
        self.config['media_limits'] = {'inference': {'per_task': '1'}}
        draft = self.prepare(request)
        estimate = draft['preview']['estimate']
        self.assertEqual(estimate['confidence'], 'unknown')
        self.assertEqual(estimate['reason'], 'version_specific_estimate_unavailable')
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(Failure, 'cost_bound_required_for_budget'):
            self.execute(draft['draft_id'])
        self.assertEqual(self.calls, [])

    def test_large_text_response_can_be_read_completely_without_rewrapping(self):
        text = ('Схема🙂\n"field" ' * 5000)
        account = account_fingerprint({'FAL_KEY': self.vault.key})
        saved = media._bounded({'documentation': text}, self.config, account)
        self.assertTrue(saved['stored'])
        offset, chunks = 0, []
        while offset is not None:
            result = media.read('fal', 'response_read', {'response_id': saved['response_id'],
                'pointer': '/documentation', 'offset': offset, 'chunk_chars': 12000}, self.config, vault=self.vault)
            page = result['data']
            self.assertNotIn('response_id', page)
            self.assertEqual(page['offset_unit'], 'unicode_characters')
            self.assertLess(len(json.dumps(page, ensure_ascii=False).encode()), 48000)
            self.assertEqual(page['text'].encode().decode(), page['text'])
            chunks.append(page['text'])
            offset = page['next_offset']
        self.assertEqual(''.join(chunks), text)
        self.assertEqual(len(list((media.root(self.config) / 'responses').glob('*.json'))), 1)
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(Failure, 'invalid_media_pagination'):
            media.read('fal', 'response_read', {'response_id': saved['response_id'], 'chunk_chars': 12001},
                       self.config, vault=self.vault)

    def test_missing_async_identifier_is_not_reported_as_completed(self):
        self.submit_result = {'unexpected': 'provider acceptance uncertain'}
        draft = self.prepare()
        result = self.execute(draft['draft_id'])
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'outcome_unknown')
        self.execute(draft['draft_id'])
        self.assertEqual(sum(call[1] == 'submit' for call in self.calls), 1)

    def test_synchronous_chat_completion_is_not_treated_as_async_task_id(self):
        request = {'action': 'prepare', 'service': 'inference', 'operation': 'chat_completion',
                   'params': {'model': 'example/model', 'messages': [{'role': 'user', 'content': 'Hello'}]}}
        self.submit_result = {'id': 'chatcmpl-one', 'object': 'chat.completion',
                              'choices': [{'message': {'role': 'assistant', 'content': 'Hello'}}]}
        draft = self.prepare(request)
        result = self.execute(draft['draft_id'])
        self.assertEqual(result['status'], 'completed')
        self.assertIsNone(result['provider_job_id'])


if __name__ == '__main__':
    unittest.main()
