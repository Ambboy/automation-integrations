import json
from pathlib import Path
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from automation_integrations import confirmed_write as workflow
from automation_integrations.api_read import Failure, HTTP
from automation_integrations import extended_api
from tests.test_api_catalog import FakeHTTP, FakeVault


class Contract:
    @staticmethod
    def operations(service):
        return {'sample_write': {'id': 'POST /sample', 'effect': 'business_write', 'source': 'https://provider.test/docs'},
                'sample_read': {'id': 'GET /sample', 'effect': 'read'}}

    @staticmethod
    def validate(service, operation, params):
        if not isinstance(params, dict) or set(params) != {'body'} or params['body'] != {'amount': 12}:
            raise ValueError('invalid_parameters')
        return params

    @staticmethod
    def build(service, operation, params):
        return {'method': 'POST' if operation == 'sample_write' else 'GET', 'path': '/sample',
                'query': {}, 'body': params['body']}


class ConfirmedWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {'state_dir': self.tmp.name}
        self.context = {'scope': ['owner', 'owner', 'session', 'topic'], 'message_id': '1'}
        self.vault = FakeVault()
        self.patch = patch.object(extended_api, 'contract', return_value=Contract)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.request = {'action': 'prepare', 'service': 'tochka', 'operation': 'sample_write',
                        'params': {'body': {'amount': 12}}}

    def run_action(self, request, *, message='1', http=None, now=1000, context=None):
        return workflow.process(request, context or {**self.context, 'message_id': message}, self.config,
                                http=http, vault=self.vault, clock=lambda: now)

    def prepare(self):
        return self.run_action(self.request)['draft_id']

    def confirm(self, ident, message='2'):
        return self.run_action({'action': 'confirm', 'confirmation_text': 'ПОДТВЕРЖДАЮ ' + ident}, message=message)

    def test_prepare_is_offline_and_exact_confirmation_required(self):
        ident = self.prepare()
        self.assertEqual(self.vault.calls, [])
        with self.assertRaisesRegex(Failure, 'owner_confirmation_required'):
            self.run_action({'action': 'execute', 'draft_id': ident})
        with self.assertRaisesRegex(Failure, 'new_owner_message_required'):
            self.confirm(ident, '1')
        with self.assertRaisesRegex(Failure, 'exact_confirmation_required'):
            self.run_action({'action': 'confirm', 'confirmation_text': 'quoted ПОДТВЕРЖДАЮ ' + ident}, message='2')
        self.assertEqual(self.confirm(ident)['status'], 'confirmed')

    def test_acceptance_is_not_business_verification_and_never_repeated(self):
        ident = self.prepare(); self.confirm(ident)
        http = FakeHTTP({'id': 'provider-object'})
        result = self.run_action({'action': 'execute', 'draft_id': ident}, http=http)
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertTrue(result['provider_accepted'])
        self.assertFalse(result['mutation_verified'])
        again = self.run_action({'action': 'execute', 'draft_id': ident}, http=http)
        self.assertEqual(again, result)
        self.assertEqual(len(http.calls), 1)
        duplicate = self.run_action(self.request)
        self.assertEqual(duplicate['error'], 'existing_unresolved_draft')
        self.assertEqual(duplicate['draft_id'], ident)

    def test_unknown_submission_retains_identity_even_after_expiry(self):
        ident = self.prepare(); self.confirm(ident)
        http = FakeHTTP(Failure('request_timeout'))
        result = self.run_action({'action': 'execute', 'draft_id': ident}, http=http)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.run_action({'action': 'execute', 'draft_id': ident}, http=http, now=9000)
        self.assertEqual(len(http.calls), 1)
        self.assertEqual(self.run_action(self.request, now=9000)['draft_id'], ident)
        with self.assertRaisesRegex(Failure, 'draft_not_confirmable'):
            self.confirm(ident, '3')

    def test_scope_payload_target_and_contract_are_bound(self):
        ident = self.prepare()
        with self.assertRaisesRegex(Failure, 'draft_scope_mismatch'):
            self.run_action({'action': 'status', 'draft_id': ident}, context={**self.context, 'scope': ['owner', 'owner', 'other', 'topic']})
        self.confirm(ident)
        self.config['tochka_environment'] = 'sandbox'
        with self.assertRaisesRegex(Failure, 'draft_contract_or_target_changed'):
            self.run_action({'action': 'execute', 'draft_id': ident})
        self.assertEqual(self.vault.calls, [])
        path = Path(self.tmp.name, 'contract-writes', ident + '.json')
        row = json.loads(path.read_text()); row['params']['body']['amount'] = 99
        path.write_text(json.dumps(row))
        with self.assertRaisesRegex(Failure, 'draft_integrity_failed'):
            self.run_action({'action': 'status', 'draft_id': ident})

    def test_disk_state_precedes_mutation_and_crash_status_is_unknown(self):
        ident = self.prepare(); self.confirm(ident)
        path = Path(self.tmp.name, 'contract-writes', ident + '.json')
        class InspectHTTP:
            def call(inner, *args, **kwargs):
                self.assertEqual(json.loads(path.read_text())['status'], 'submitting')
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                raise RuntimeError('simulated interruption')
        self.assertEqual(self.run_action({'action': 'execute', 'draft_id': ident}, http=InspectHTTP())['status'], 'outcome_unknown')
        row = json.loads(path.read_text()); row['status'] = 'submitting'; path.write_text(json.dumps(row))
        self.assertEqual(self.run_action({'action': 'status', 'draft_id': ident})['last_error'], 'interrupted_submission')

    def test_validation_precedes_credentials_and_write_cannot_use_read(self):
        with self.assertRaises(Failure):
            self.run_action({**self.request, 'params': {'body': {'amount': True}}})
        with self.assertRaisesRegex(Failure, 'write_tool_required'):
            extended_api.execute('tochka', 'sample_write', self.request['params'], self.config, vault=self.vault)
        self.assertEqual(self.vault.calls, [])

    def test_saby_write_never_replays_after_401(self):
        ident = self.run_action({**self.request, 'service': 'saby'})['draft_id']; self.confirm(ident)
        http = FakeHTTP({'token': 'session'}, Failure('authorization_failed', 401))
        result = self.run_action({'action': 'execute', 'draft_id': ident}, http=http)
        self.assertEqual(result['status'], 'rejected')
        self.assertEqual(len(http.calls), 2)
        self.assertFalse(Path(self.tmp.name, 'saby-session.json').exists())

    def test_binary_artifact_is_private_and_html_is_rejected(self):
        result = extended_api.output(b'%PDF-1.7\nfixture\n', [], self.config)
        path = Path(result['artifact']['path'])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.read_bytes(), b'%PDF-1.7\nfixture\n')
        with self.assertRaises(Failure):
            HTTP.decode(b'<html>error</html>', 'binary')
        self.assertEqual(HTTP.decode(b'', 'json'), {})

    def test_preview_preserves_business_destination_and_rejects_false_sandbox(self):
        # A webhook destination is an approval-critical parameter, not a token
        # obtained from Vault. Output redaction must not hide what gets approved.
        url = 'https://merchant.example.test/incoming?channel=invoice'
        with patch.object(Contract, 'validate', side_effect=lambda service, operation, params: params):
            result = self.run_action({**self.request, 'params': {'body': {'url': url}}})
        self.assertEqual(result['preview']['parameters']['body']['url'], url)
        self.config['saby_environment'] = 'sandbox'
        with self.assertRaisesRegex(Failure, 'unsupported_provider_environment'):
            self.run_action({**self.request, 'service': 'saby'})
        self.assertEqual(self.vault.calls, [])

    def test_expired_prepare_cannot_replace_a_submission_in_progress(self):
        ident = self.prepare(); self.confirm(ident)
        entered, release, preparing = threading.Event(), threading.Event(), threading.Event()
        original = Contract.build
        def slow_build(service, operation, params):
            if threading.current_thread().name.startswith('submit') and not release.is_set():
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('test synchronization timeout')
            return original(service, operation, params)
        def replacement():
            preparing.set()
            return self.run_action(self.request, now=1601)
        with patch.object(Contract, 'build', side_effect=slow_build):
            with ThreadPoolExecutor(1, thread_name_prefix='submit') as submits, ThreadPoolExecutor(1) as prepares:
                submission = submits.submit(self.run_action, {'action': 'execute', 'draft_id': ident}, http=FakeHTTP({}))
                self.assertTrue(entered.wait(3))
                retry = prepares.submit(replacement)
                self.assertTrue(preparing.wait(3))
                release.set()
                self.assertEqual(submission.result(3)['status'], 'accepted_unverified')
                self.assertEqual(retry.result(3)['error'], 'existing_unresolved_draft')
        self.assertEqual(len(list(Path(self.tmp.name, 'contract-writes').glob('*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
