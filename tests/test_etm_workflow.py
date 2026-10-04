from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from automation_integrations import etm_workflow
from automation_integrations.api_read import Failure


class CheckoutFixture:
    def __init__(self, test):
        self.test = test
        self.calls = []
        self.error = None
        self.accept_first = False
        self.basket_first = False
        self.basket_accepted = True
        self.before_checkout_error = False
        self.basket_matches = True
        self.basket_reconciliation_error = None

    def prepare(self, params):
        self.calls.append('prepare')
        return {'params': params, 'preview': {'items': params['items'],
                'pickup_address': 'Волгоград, Университетский проспект, 85',
                'total_ceiling': '1314.00', 'payment': 'bill', 'contract': 'fixture'},
                'checkout_fields': {'skl': '29100', 'payment_method_code': 'bill'}}

    def execute(self, prepared, on_stage):
        self.calls.append('execute')
        if self.basket_first:
            on_stage('basket_add_submitting')
            if not self.basket_accepted:
                raise self.error or Failure('request_timeout')
            on_stage('basket_add_accepted')
            if self.before_checkout_error:
                raise self.error or Failure('etm_basket_quantity_mismatch')
        on_stage('checkout_submitting')
        saved = json.loads(next(Path(self.test.tmp.name, 'etm-writes').glob('*.json')).read_text())
        self.test.assertEqual(saved['status'], 'submitting')
        self.test.assertEqual(saved['stage'], 'checkout_submitting')
        self.test.assertTrue(saved['checkout_started'])
        if self.accept_first:
            on_stage('checkout_accepted', {'ids': ['fixture-1', 'fixture-2']})
        if self.error:
            raise self.error
        return {'status': 'verified', 'documents': ['fixture-1', 'fixture-2'],
                'total': '1314.00', 'ready_for_pickup': False}

    def reconcile(self, prepared, receipt):
        self.calls.append('reconcile')
        return {'status': 'verified', 'documents': receipt['ids'], 'ready_for_pickup': False}

    def reconcile_basket(self, prepared):
        self.calls.append('reconcile_basket')
        if self.basket_reconciliation_error:
            raise self.basket_reconciliation_error
        return {'status': 'blocked' if self.basket_matches else 'outcome_unknown',
                'order_submitted': False, 'basket_changed': True,
                'reason': 'etm_basket_add_reconciled' if self.basket_matches else 'etm_basket_add_unresolved',
                'items': prepared['params']['items'] if self.basket_matches else [],
                'matches_expected': self.basket_matches}


class EtmWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {'state_dir': self.tmp.name, 'etm_proxy': 'socks5h://127.0.0.1:10929',
                       'item_ids': {'etm': 'fixture'}}
        self.context = {'scope': ['owner', 'owner', 'session', 'topic'], 'message_id': '1'}
        self.checkout = CheckoutFixture(self)
        self.request = {'action': 'prepare', 'service': 'etm', 'operation': 'order_checkout',
                        'params': {'items': [{'code': '6510970', 'quantity': 100}],
                                   'region': '34', 'pickup_store': '29100',
                                   'payment_method': 'bill', 'pay_type': 'bill'}}

    def run_action(self, request, message='1', now=1000, context=None):
        return etm_workflow.process(request, context or {**self.context, 'message_id': message},
                                    self.config, checkout=self.checkout, clock=lambda: now)

    def prepared(self):
        return self.run_action(self.request)['draft_id']

    def confirm(self, ident, message='2'):
        return self.run_action({'action': 'confirm', 'confirmation_text': 'ПОДТВЕРЖДАЮ ' + ident}, message)

    def test_native_confirmation_and_exact_scope_are_required(self):
        ident = self.prepared()
        with self.assertRaisesRegex(Failure, 'owner_confirmation_required'):
            self.run_action({'action': 'execute', 'draft_id': ident})
        with self.assertRaisesRegex(Failure, 'new_owner_message_required'):
            self.confirm(ident, '1')
        with self.assertRaisesRegex(Failure, 'exact_confirmation_required'):
            self.run_action({'action': 'confirm', 'confirmation_text': 'Цитата: ПОДТВЕРЖДАЮ ' + ident}, '2')
        with self.assertRaisesRegex(Failure, 'draft_scope_mismatch'):
            self.run_action({'action': 'status', 'draft_id': ident},
                            context={**self.context, 'scope': ['owner', 'owner', 'session', 'other']})
        self.assertEqual(self.checkout.calls, ['prepare'])
        self.confirm(ident)
        result = self.run_action({'action': 'execute', 'draft_id': ident})
        self.assertTrue(result['mutation_verified'])
        self.assertFalse(result['result']['ready_for_pickup'])
        self.run_action({'action': 'execute', 'draft_id': ident})
        self.assertEqual(self.checkout.calls, ['prepare', 'execute'])

    def test_unknown_submit_blocks_replacement_even_after_expiry(self):
        ident = self.prepared()
        self.confirm(ident)
        self.checkout.error = Failure('request_timeout')
        result = self.run_action({'action': 'execute', 'draft_id': ident})
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(self.run_action(self.request, now=9000)['draft_id'], ident)
        self.run_action({'action': 'execute', 'draft_id': ident}, now=9000)
        self.assertEqual(self.checkout.calls.count('execute'), 1)

    def test_receipt_survives_failed_readback_and_status_is_read_only(self):
        ident = self.prepared()
        self.confirm(ident)
        self.checkout.accept_first = True
        self.checkout.error = Failure('provider_unavailable')
        result = self.run_action({'action': 'execute', 'draft_id': ident})
        self.assertEqual(result['status'], 'accepted_unverified')
        result = self.run_action({'action': 'status', 'draft_id': ident})
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['result']['documents'], ['fixture-1', 'fixture-2'])
        self.assertEqual(self.checkout.calls, ['prepare', 'execute', 'reconcile'])

    def test_receipt_cannot_be_reconciled_with_changed_account_or_proxy(self):
        ident = self.prepared()
        self.confirm(ident)
        self.checkout.accept_first = True
        self.checkout.error = Failure('provider_unavailable')
        self.run_action({'action': 'execute', 'draft_id': ident})
        original = deepcopy(self.config)
        for field in ('item_ids', 'etm_proxy'):
            self.config[field] = {'etm': 'another-account'} if field == 'item_ids' else 'another-proxy'
            with self.subTest(field=field), self.assertRaisesRegex(Failure, 'draft_contract_or_target_changed'):
                self.run_action({'action': 'status', 'draft_id': ident})
            self.config[field] = original[field]
        self.assertNotIn('reconcile', self.checkout.calls)

    def test_unresolved_checkout_blocks_changed_intent_and_other_scope_without_disclosure(self):
        ident = self.prepared()
        self.confirm(ident)
        self.checkout.error = Failure('request_timeout')
        self.run_action({'action': 'execute', 'draft_id': ident})
        different = deepcopy(self.request)
        different['params']['items'][0]['quantity'] = 200
        same_scope = self.run_action(different, message='3', now=9000)
        self.assertEqual(same_scope['draft_id'], ident)
        other_scope = self.run_action(different, now=9000, context={
            'scope': ['owner', 'owner', 'another-session', 'other-topic'], 'message_id': '4'})
        self.assertEqual(other_scope['error'], 'other_unresolved_checkout')
        for field in ('draft_id', 'preview', 'result', 'receipt', 'status'):
            self.assertNotIn(field, other_scope)
        self.assertEqual(self.checkout.calls, ['prepare', 'execute'])

    def test_second_preconfirmed_draft_cannot_execute_after_first_becomes_unknown(self):
        first = self.prepared()
        second_request = deepcopy(self.request)
        second_request['params']['items'][0]['quantity'] = 200
        second = self.run_action(second_request, message='2')['draft_id']
        self.confirm(first, '3')
        self.confirm(second, '4')
        self.checkout.error = Failure('request_timeout')
        self.run_action({'action': 'execute', 'draft_id': first})
        blocked = self.run_action({'action': 'execute', 'draft_id': second})
        self.assertEqual(blocked['error'], 'existing_unresolved_draft')
        self.assertEqual(blocked['draft_id'], first)
        self.assertEqual(self.checkout.calls.count('execute'), 1)

    def test_unresolved_identity_survives_code_version_change_and_other_account_is_separate(self):
        ident = self.prepared()
        self.confirm(ident)
        self.checkout.error = Failure('request_timeout')
        self.run_action({'action': 'execute', 'draft_id': ident})
        from unittest.mock import patch
        with patch.object(etm_workflow, 'VERSION', etm_workflow.VERSION + 1):
            self.assertEqual(self.run_action(self.request)['draft_id'], ident)
        self.config['item_ids']['etm'] = 'other-account'
        other = self.run_action(self.request)
        self.assertEqual(other['status'], 'prepared')
        self.assertNotEqual(other['draft_id'], ident)

    def test_restart_during_submit_never_sends_again(self):
        ident = self.prepared()
        path = Path(self.tmp.name, 'etm-writes', ident + '.json')
        data = json.loads(path.read_text())
        data.update(status='submitting', submitted_at=1001, stage='checkout_submitting')
        path.write_text(json.dumps(data))
        result = self.run_action({'action': 'execute', 'draft_id': ident})
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(self.checkout.calls, ['prepare'])

    def test_accepted_basket_failure_allows_new_preview_without_replaying_old_execute(self):
        self.checkout.basket_first = True
        self.checkout.before_checkout_error = True
        for code in ('etm_basket_quantity_mismatch', 'etm_requested_payment_unavailable',
                     'etm_allocation_unverified', 'etm_portal_transport_unknown'):
            with self.subTest(code=code):
                ident = self.prepared()
                self.confirm(ident)
                self.checkout.error = Failure(code)
                result = self.run_action({'action': 'execute', 'draft_id': ident})
                self.assertEqual(result['status'], 'blocked')
                self.assertFalse(result['checkout_started'])
                self.assertFalse(result['result']['order_submitted'])
                self.assertTrue(result['result']['basket_changed'])
                self.assertEqual(result['result']['reason'], code)
                self.assertNotIn('confirmation_command', result)
                calls = list(self.checkout.calls)
                self.assertEqual(self.run_action({'action': 'execute', 'draft_id': ident}), result)
                self.assertEqual(self.checkout.calls, calls)
                with self.assertRaisesRegex(Failure, 'draft_not_confirmable'):
                    self.confirm(ident, '3')
                fresh = self.run_action(self.request, message='4')
                self.assertEqual(fresh['status'], 'prepared')
                self.assertNotEqual(fresh['draft_id'], ident)

    def test_restart_after_accepted_basket_cannot_become_unknown_final_checkout(self):
        ident = self.prepared()
        path = Path(self.tmp.name, 'etm-writes', ident + '.json')
        row = json.loads(path.read_text())
        row.update(status='submitting', submitted_at=1001, stage='basket_add_accepted')
        row.pop('checkout_started')  # Pre-upgrade durable record.
        path.write_text(json.dumps(row))
        result = self.run_action({'action': 'execute', 'draft_id': ident})
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['result']['order_submitted'])
        self.assertEqual(self.checkout.calls, ['prepare'])
        self.assertEqual(self.run_action(self.request, message='2')['status'], 'prepared')

    def test_basket_add_timeout_stays_unknown_and_final_submit_timeout_never_downgrades(self):
        ident = self.prepared()
        self.confirm(ident)
        self.checkout.basket_first = True
        self.checkout.basket_accepted = False
        result = self.run_action({'action': 'execute', 'draft_id': ident})
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertFalse(result['checkout_started'])
        self.assertEqual(self.run_action(self.request, message='3')['draft_id'], ident)
        path = Path(self.tmp.name, 'etm-writes', ident + '.json')
        row = json.loads(path.read_text())
        row.update(status='submitting', stage='checkout_submitting', checkout_started=True)
        path.write_text(json.dumps(row))
        result = self.run_action({'action': 'execute', 'draft_id': ident})
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertTrue(result['checkout_started'])
        self.assertEqual(self.checkout.calls.count('execute'), 1)

    def test_basket_timeout_readback_can_release_only_exact_existing_inventory(self):
        ident = self.prepared()
        self.confirm(ident)
        self.checkout.basket_first = True
        self.checkout.basket_accepted = False
        self.run_action({'action': 'execute', 'draft_id': ident})
        self.checkout.basket_matches = False
        result = self.run_action({'action': 'status', 'draft_id': ident})
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertFalse(result['result']['matches_expected'])
        self.assertEqual(self.run_action(self.request, message='3')['draft_id'], ident)
        self.checkout.basket_matches = True
        result = self.run_action({'action': 'status', 'draft_id': ident})
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['result']['order_submitted'])
        self.assertTrue(result['result']['matches_expected'])
        self.assertNotIn('confirmation_command', result)
        self.assertEqual(self.checkout.calls.count('execute'), 1)
        self.assertEqual(self.checkout.calls.count('reconcile_basket'), 2)
        self.assertEqual(self.run_action(self.request, message='4')['status'], 'prepared')

    def test_basket_reconciliation_failure_preserves_unknown_and_uses_original_account(self):
        ident = self.prepared()
        self.confirm(ident)
        self.checkout.basket_first = True
        self.checkout.basket_accepted = False
        self.run_action({'action': 'execute', 'draft_id': ident})
        self.checkout.basket_reconciliation_error = Failure('etm_portal_transport_unknown')
        result = self.run_action({'action': 'status', 'draft_id': ident})
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(result['last_error'], 'etm_portal_transport_unknown')
        self.config['item_ids']['etm'] = 'another-account'
        with self.assertRaisesRegex(Failure, 'draft_contract_or_target_changed'):
            self.run_action({'action': 'status', 'draft_id': ident})
        self.assertEqual(self.checkout.calls.count('reconcile_basket'), 1)

    def test_final_order_timeout_never_uses_basket_reconciliation(self):
        ident = self.prepared()
        self.confirm(ident)
        self.checkout.error = Failure('etm_portal_transport_unknown')
        result = self.run_action({'action': 'execute', 'draft_id': ident})
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertTrue(result['checkout_started'])
        result = self.run_action({'action': 'status', 'draft_id': ident})
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertNotIn('reconcile_basket', self.checkout.calls)
        self.assertEqual(self.run_action(self.request, message='3')['draft_id'], ident)

    def test_target_payload_and_expiration_bound_to_approval(self):
        ident = self.prepared()
        self.confirm(ident)
        with self.assertRaisesRegex(Failure, 'confirmation_expired'):
            self.run_action({'action': 'execute', 'draft_id': ident}, now=1601)
        self.config['item_ids']['etm'] = 'changed'
        with self.assertRaisesRegex(Failure, 'draft_contract_or_target_changed'):
            self.run_action({'action': 'execute', 'draft_id': ident})
        path = Path(self.tmp.name, 'etm-writes', ident + '.json')
        data = json.loads(path.read_text())
        data['prepared']['checkout_fields']['skl'] = 'another-city'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(Failure, 'draft_integrity_failed'):
            self.run_action({'action': 'execute', 'draft_id': ident})

    def test_duplicate_prepare_same_message_and_new_deliberate_order(self):
        ident = self.prepared()
        self.assertEqual(self.run_action(self.request)['draft_id'], ident)
        self.confirm(ident)
        self.run_action({'action': 'execute', 'draft_id': ident})
        self.assertEqual(self.run_action(self.request)['draft_id'], ident)
        self.assertNotEqual(self.run_action(self.request, message='3')['draft_id'], ident)


if __name__ == '__main__':
    unittest.main()
