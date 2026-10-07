import copy
import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from automation_integrations import abcp_write as workflow


class AbcpWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {'state_dir': self.tmp.name, 'base_url': 'https://fixture.abcp.ru',
                       'userlogin': 'fixture', 'userpsw': 'private-fixture-credential'}
        self.context = {'scope': ['owner', 'owner', 'session', 'topic'], 'message_id': '1'}
        self.metadata = {'id': 'sample_write', 'effect': 'business_write',
                         'method': 'POST', 'path': '/cp/order', 'source': 'https://abcp.ru/docs'}
        self.request = {'action': 'prepare', 'operation': 'sample_write',
                        'params': {'positions': [{'code': 'fixture-item', 'quantity': 2}]}}
        self.validation = patch.object(workflow.api, 'validate', side_effect=self.validate)
        self.validation.start()
        self.addCleanup(self.validation.stop)
        self.operations = patch.object(workflow.api, 'operation', side_effect=lambda _: copy.deepcopy(self.metadata))
        self.operations.start()
        self.addCleanup(self.operations.stop)
        self.target = patch.object(workflow.api, 'fingerprint', side_effect=lambda config: workflow.digest({
            key: value for key, value in config.items() if key in ('base_url', 'userlogin', 'userpsw')}))
        self.target.start()
        self.addCleanup(self.target.stop)
        self.transport = patch.object(workflow.api, 'execute', return_value={
            'ok': True, 'business_status': 'accepted_unverified',
            'provider_called': True, 'data': {'orderId': 81}})
        self.execute = self.transport.start()
        self.addCleanup(self.transport.stop)

    @staticmethod
    def validate(operation, params, *, write):
        if operation != 'sample_write' or not isinstance(params, dict) or 'positions' not in params or not write:
            raise workflow.api.AbcpError('invalid_parameters')
        return copy.deepcopy(params)

    def action(self, request, *, message='1', now=1000, context=None):
        return workflow.process(request, context or {**self.context, 'message_id': message},
                                self.config, clock=lambda: now)

    def prepare(self):
        return self.action(self.request)['draft_id']

    def confirm(self, ident, **kwargs):
        return self.action({'action': 'confirm', 'confirmation_text': 'ПОДТВЕРЖДАЮ ' + ident},
                           message=kwargs.pop('message', '2'), **kwargs)

    def submit(self, ident, **kwargs):
        return self.action({'action': 'execute', 'draft_id': ident}, **kwargs)

    def status(self, ident, **kwargs):
        return self.action({'action': 'status', 'draft_id': ident}, **kwargs)

    def path(self, ident):
        return Path(self.tmp.name, 'abcp-writes', ident + '.json')

    def native(self, text, *, message='1'):
        return {**self.context, 'message_id': message, 'owner_message': {
            'source': 'native_owner_telegram', 'message_id': message,
            'scope': self.context['scope'], 'text_sha256': hashlib.sha256(text.encode()).hexdigest()}}

    def test_prepare_is_offline_has_full_preview_and_requires_new_exact_confirmation(self):
        draft = self.action(self.request)
        ident = draft['draft_id']
        self.assertEqual(draft['preview']['parameters'], self.request['params'])
        self.assertTrue(draft['confirmation_required'])
        self.assertFalse(draft['provider_called'])
        self.execute.assert_not_called()
        with self.assertRaisesRegex(workflow.api.AbcpError, 'owner_confirmation_required'):
            self.submit(ident)
        with self.assertRaisesRegex(workflow.api.AbcpError, 'new_owner_message_required'):
            self.confirm(ident, message='1')
        with self.assertRaisesRegex(workflow.api.AbcpError, 'exact_confirmation_required'):
            self.action({'action': 'confirm', 'confirmation_text': ' ПОДТВЕРЖДАЮ ' + ident}, message='2')
        with self.assertRaisesRegex(workflow.api.AbcpError, 'invalid_write_request'):
            self.action({'action': 'execute', 'draft_id': ident, 'confirmed': True})
        self.assertEqual(self.confirm(ident)['status'], 'confirmed')
        self.execute.assert_not_called()

    def test_native_confirmation_must_match_actual_new_owner_message(self):
        ident = self.prepare()
        with self.assertRaisesRegex(workflow.api.AbcpError, 'native_confirmation_mismatch'):
            self.confirm(ident, context=self.native('Какой статус?', message='2'))
        self.assertEqual(self.confirm(ident, context=self.native('ПОДТВЕРЖДАЮ ' + ident, message='2'))['status'],
                         'confirmed')

    def test_exact_bridge_prepare_accepts_only_optional_abcp_service(self):
        request = {**self.request, 'service': 'abcp'}
        result = self.action(request, context=self.native('Подготовь заказ'))
        self.assertEqual(result['status'], 'prepared')
        self.assertEqual(result['service'], 'abcp')
        with self.assertRaisesRegex(workflow.api.AbcpError, 'invalid_write_request'):
            self.action({**self.request, 'service': 'another'})
        with self.assertRaisesRegex(workflow.api.AbcpError, 'invalid_write_request'):
            self.action({'action': 'status', 'draft_id': result['draft_id'], 'service': 'abcp'})
        self.execute.assert_not_called()

    def test_preview_masks_business_password_and_summarizes_uploaded_bytes(self):
        content = b'part,price\nfixture,12\n' * 1000
        self.request['params'].update(password='private-new-password', file={
            'filename': 'pricelist.csv', 'content_type': 'text/csv',
            'content_base64': base64.b64encode(content).decode()})
        result = self.action(self.request)
        preview = result['preview']['parameters']
        self.assertEqual(preview['password'], '[redacted]')
        self.assertEqual(preview['file']['filename'], 'pricelist.csv')
        self.assertEqual(preview['file']['content_base64'], {
            'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
        self.assertNotIn('private-new-password', json.dumps(result))
        stored = json.loads(self.path(result['draft_id']).read_text())
        self.assertEqual(stored['params'], self.request['params'])

    def test_large_result_is_stored_completely_with_stable_pagination(self):
        payload = [{'id': i, 'description': 'x' * 3000} for i in range(30)]
        self.execute.return_value = {'ok': True, 'business_status': 'partial', 'data': payload}
        ident = self.prepare()
        self.confirm(ident)
        result = self.submit(ident)
        self.assertTrue(result['result']['stored_complete'])
        self.assertIsNone(result['result']['data'])
        result_id = result['result']['result_id']
        self.assertEqual(self.status(ident)['result']['result_id'], result_id)
        page = workflow.api.result_page(self.config, {'result_id': result_id, 'limit': 5})
        self.assertEqual(page['data'], payload[:5])
        self.assertEqual(page['next_offset'], 5)

    def test_invalid_scope_wrong_message_and_read_operation_rejected(self):
        for scope in (['owner', 'group', 'session', 'topic'], ['owner', 'owner', '', 'topic'], ['owner']):
            with self.assertRaisesRegex(workflow.api.AbcpError, 'invalid_write_context'):
                self.action(self.request, context={**self.context, 'scope': scope})
        self.metadata['effect'] = 'read'
        with self.assertRaisesRegex(workflow.api.AbcpError, 'write_operation_required'):
            self.prepare()
        self.execute.assert_not_called()

    def test_acceptance_is_durable_and_never_repeated_or_replaced_after_expiry(self):
        ident = self.prepare()
        self.confirm(ident)
        first = self.submit(ident)
        self.assertEqual(first['status'], 'accepted_unverified')
        self.assertTrue(first['provider_accepted'])
        self.assertFalse(first['mutation_verified'])
        self.assertEqual(self.submit(ident, now=9000), first)
        self.execute.assert_called_once()
        blocker = self.action(self.request, now=9000)
        self.assertEqual(blocker['draft_id'], ident)
        self.assertEqual(blocker['error'], 'existing_unresolved_draft')

    def test_partial_success_cannot_be_retried_or_duplicated(self):
        self.execute.return_value = {'ok': False, 'business_status': 'partial', 'provider_called': True,
                                     'data': {'orders': [81], 'errors': [{'item': 2, 'code': 'no_stock'}]}}
        ident = self.prepare()
        self.confirm(ident)
        result = self.submit(ident)
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(result['partial_success'])
        self.assertEqual(result['result']['data']['orders'], [81])
        self.submit(ident)
        self.execute.assert_called_once()
        self.assertEqual(self.action(self.request)['draft_id'], ident)

    def test_explicit_unknown_result_is_preserved_and_never_replaced(self):
        self.execute.return_value = {'ok': False, 'business_status': 'outcome_unknown',
                                     'provider_called': True, 'http_status': 200,
                                     'data': {'confirmSend': False, 'orderId': 81}}
        ident = self.prepare()
        self.confirm(ident)
        result = self.submit(ident)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(result['result']['data'], {'confirmSend': False, 'orderId': 81})
        self.submit(ident)
        self.execute.assert_called_once()
        self.assertEqual(self.action(self.request, now=9000)['draft_id'], ident)

    def test_provider_rejection_is_terminal_but_allows_new_corrected_attempt(self):
        self.execute.return_value = {'ok': False, 'business_status': 'provider_rejected',
                                     'provider_called': True, 'data': {'errorCode': 4}}
        ident = self.prepare()
        self.confirm(ident)
        self.assertEqual(self.submit(ident)['status'], 'provider_rejected')
        self.submit(ident)
        self.execute.assert_called_once()
        self.assertNotEqual(self.prepare(), ident)

    def test_uncertain_http_and_network_errors_are_unknown_without_retry(self):
        for error in (workflow.api.AbcpError('transport_failure'),
                      workflow.api.AbcpError('http_error', http_status=500),
                      workflow.api.AbcpError('http_error', http_status=429),
                      RuntimeError('private-credential-must-not-leak')):
            with self.subTest(error=type(error).__name__):
                self.request['params']['attempt'] = str(id(error))
                ident = self.prepare()
                self.confirm(ident)
                self.execute.side_effect = error
                result = self.submit(ident)
                self.assertEqual(result['status'], 'outcome_unknown')
                self.assertNotIn('private-credential', json.dumps(result))
                count = self.execute.call_count
                self.submit(ident)
                self.assertEqual(self.execute.call_count, count)
                self.assertEqual(self.action(self.request, now=9000)['draft_id'], ident)

    def test_durable_submission_precedes_network_and_crash_recovery_is_unknown(self):
        ident = self.prepare()
        self.confirm(ident)
        def inspect(*args, **kwargs):
            row = json.loads(self.path(ident).read_text())
            self.assertEqual(row['status'], 'submitting')
            self.assertEqual(self.path(ident).stat().st_mode & 0o777, 0o600)
            raise SystemExit('simulated process death')
        self.execute.side_effect = inspect
        with self.assertRaises(SystemExit):
            self.submit(ident)
        result = self.status(ident)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(result['last_error'], 'interrupted_submission')
        self.submit(ident)
        self.execute.assert_called_once()

    def test_failed_submission_persistence_prevents_the_provider_call(self):
        ident = self.prepare()
        self.confirm(ident)
        original = workflow._save
        def save(path, row):
            if row['status'] == 'submitting':
                raise OSError('disk unavailable')
            return original(path, row)
        with patch.object(workflow, '_save', side_effect=save):
            with self.assertRaises(OSError):
                self.submit(ident)
        self.execute.assert_not_called()
        self.assertEqual(self.status(ident)['status'], 'confirmed')

    def test_scope_payload_contract_target_and_preview_are_bound(self):
        ident = self.prepare()
        with self.assertRaisesRegex(workflow.api.AbcpError, 'draft_scope_mismatch'):
            self.status(ident, context={**self.context, 'scope': ['owner', 'owner', 'different', 'topic']})
        self.confirm(ident)
        self.config['userpsw'] = 'rotated'
        with self.assertRaisesRegex(workflow.api.AbcpError, 'draft_contract_or_target_changed'):
            self.submit(ident)
        self.config['userpsw'] = 'private-fixture-credential'
        self.metadata['path'] = '/different'
        with self.assertRaisesRegex(workflow.api.AbcpError, 'draft_contract_or_target_changed'):
            self.submit(ident)
        row = json.loads(self.path(ident).read_text())
        row['preview']['parameters']['positions'][0]['quantity'] = 99
        self.path(ident).write_text(json.dumps(row))
        with self.assertRaisesRegex(workflow.api.AbcpError, 'draft_integrity_failed'):
            self.status(ident)
        self.execute.assert_not_called()

    def test_expired_unsubmitted_draft_can_be_replaced_but_not_executed(self):
        ident = self.prepare()
        self.confirm(ident)
        with self.assertRaisesRegex(workflow.api.AbcpError, 'confirmation_expired'):
            self.submit(ident, now=1601)
        other = self.action(self.request, now=1601)['draft_id']
        self.assertNotEqual(ident, other)
        self.execute.assert_not_called()

    def test_account_duplicate_guard_crosses_scopes_without_exposing_draft(self):
        ident = self.prepare()
        result = self.action(self.request, context={**self.context,
                             'scope': ['owner', 'owner', 'other-session', 'other-topic']})
        self.assertEqual(result['error'], 'other_unresolved_intent')
        self.assertNotIn(ident, json.dumps(result))

    def test_simultaneous_duplicate_prepare_creates_one_draft(self):
        barrier = threading.Barrier(2)
        def prepare():
            barrier.wait(timeout=3)
            return self.action(self.request)
        with ThreadPoolExecutor(2) as pool:
            results = [future.result(4) for future in (pool.submit(prepare), pool.submit(prepare))]
        self.assertEqual(sum(result['ok'] for result in results), 1)
        self.assertEqual(len(list(self.path('unused').parent.glob('*.json'))), 1)

    def test_global_lock_prevents_prepare_replacement_and_simultaneous_submit(self):
        ident = self.prepare()
        self.confirm(ident)
        entered, release, preparing = threading.Event(), threading.Event(), threading.Event()
        def submit(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('test synchronization timeout')
            return {'ok': True, 'business_status': 'accepted_unverified', 'data': {'id': 81}}
        def prepare():
            preparing.set()
            return self.action(self.request, now=1601)
        self.execute.side_effect = submit
        with ThreadPoolExecutor(3) as pool:
            first = pool.submit(self.submit, ident)
            self.assertTrue(entered.wait(3))
            duplicate = pool.submit(prepare)
            again = pool.submit(self.submit, ident)
            self.assertTrue(preparing.wait(3))
            release.set()
            self.assertEqual(first.result(4)['status'], 'accepted_unverified')
            self.assertEqual(duplicate.result(4)['error'], 'existing_unresolved_draft')
            self.assertEqual(again.result(4)['status'], 'accepted_unverified')
        self.execute.assert_called_once()

    def test_corrupted_state_fails_closed_without_another_call(self):
        self.prepare()
        damaged = self.path('damaged')
        damaged.write_text('{not json')
        self.request['params']['changed'] = True
        with self.assertRaisesRegex(workflow.api.AbcpError, 'draft_integrity_failed'):
            self.prepare()
        self.execute.assert_not_called()

    def test_owner_command_requires_native_provenance_and_same_initial_message(self):
        self.config['write_policy'] = 'owner_command'
        ident = self.prepare()
        with self.assertRaisesRegex(workflow.api.AbcpError, 'owner_confirmation_required'):
            self.submit(ident)
        forged = {**self.context, 'owner_message': True}
        with self.assertRaisesRegex(workflow.api.AbcpError, 'owner_confirmation_required'):
            self.submit(ident, context=forged)
        with self.assertRaisesRegex(workflow.api.AbcpError, 'owner_confirmation_required'):
            self.submit(ident, context=self.native('Оформи заказ', message='2'))
        result = self.submit(ident, context=self.native('Оформи заказ'))
        self.assertEqual(result['status'], 'accepted_unverified')
        self.execute.assert_called_once()

    def test_cli_is_clean_json_and_unexpected_errors_do_not_leak_secrets(self):
        payload = json.dumps({'request': self.request, 'context': self.context})
        with patch.object(workflow.api, 'load_config', return_value=self.config), \
                patch('sys.stdin', io.StringIO(payload)), patch('sys.stdout', new_callable=io.StringIO) as stdout:
            self.assertEqual(workflow.main(['fixture-config']), 0)
            self.assertEqual(json.loads(stdout.getvalue())['status'], 'prepared')
        with patch.object(workflow.api, 'load_config', side_effect=RuntimeError('secret')), \
                patch('sys.stdin', io.StringIO(payload)), patch('sys.stdout', new_callable=io.StringIO) as stdout:
            self.assertEqual(workflow.main(['fixture-config']), 0)
            self.assertEqual(json.loads(stdout.getvalue()), {'ok': False, 'error': 'write_runner_failed'})


if __name__ == '__main__':
    unittest.main()
