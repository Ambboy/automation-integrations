"""Direct ETM procurement keeps draft integrity and prevents uncertain replay."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from automation_integrations import confirmed_write, etm_workflow, extended_api
from automation_integrations.api_read import Failure
from automation_integrations.etm_authorization import procurement_lock
from tests.test_confirmed_write import Contract
from tests.test_etm_workflow import CheckoutFixture


def native_context(message='1', text='Закажи 100 метров провода'):
    scope = ['owner', 'owner', 'session', 'topic']
    return {'scope': scope, 'message_id': message,
            'owner_message': {'source': 'native_owner_telegram', 'scope': list(scope),
                              'message_id': message,
                              'text_sha256': hashlib.sha256(text.encode()).hexdigest()}}


class OwnerCommandCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {'state_dir': self.tmp.name, 'etm_order_authorization': 'owner_command',
                       'etm_proxy': 'socks5h://127.0.0.1:10929', 'item_ids': {'etm': 'fixture'}}
        self.context = native_context()
        self.checkout = CheckoutFixture(self)
        self.request = {'action': 'prepare', 'service': 'etm', 'operation': 'order_checkout',
                        'params': {'items': [{'code': '6510970', 'quantity': 100}],
                                   'region': '34', 'pickup_store': '29100',
                                   'payment_method': 'bill', 'pay_type': 'bill'}}

    def call(self, action, draft_id=None, *, context=None, now=1000):
        request = self.request if action == 'prepare' else {'action': action, 'draft_id': draft_id}
        return etm_workflow.process(request, self.context if context is None else context,
                                    self.config, checkout=self.checkout, clock=lambda: now)

    def path(self, ident):
        return Path(self.tmp.name, 'etm-writes', ident + '.json')

    def row(self, ident):
        return json.loads(self.path(ident).read_text())

    def test_prepare_is_read_only_and_same_message_executes_with_durable_authorization(self):
        preview = self.call('prepare')
        ident = preview['draft_id']
        self.assertEqual(preview['status'], 'prepared')
        self.assertFalse(preview['confirmation_required'])
        self.assertNotIn('confirmation_command', preview)
        self.assertEqual(self.checkout.calls, ['prepare'])
        self.assertNotIn('authorization', self.row(ident))
        execute = self.checkout.execute

        def inspect_before_provider_effect(prepared, on_stage):
            def durable_stage(name, details=None):
                on_stage(name, details)
                if name == 'checkout_submitting':
                    row = self.row(ident)
                    self.assertEqual(row['status'], 'submitting')
                    self.assertEqual(row['approved_hash'], row['prepared_hash'])
                    self.assertEqual(row['authorization'], {
                        'policy': 'owner_command', 'message_id': '1',
                        'text_sha256': self.context['owner_message']['text_sha256']})
            return execute(prepared, durable_stage)

        with patch.object(self.checkout, 'execute', side_effect=inspect_before_provider_effect):
            result = self.call('execute', ident)
        self.assertEqual(result['status'], 'verified')
        self.assertTrue(result['mutation_verified'])
        self.assertEqual(self.row(ident)['confirmed_message'], '1')
        self.assertEqual(self.checkout.calls, ['prepare', 'execute'])

    def test_fresh_owner_request_can_finish_an_older_valid_prepared_draft(self):
        self.config.pop('etm_order_authorization')
        previous = self.call('prepare')
        self.assertTrue(previous['confirmation_required'])
        ident = previous['draft_id']
        self.config['etm_order_authorization'] = 'owner_command'
        current = native_context('2', 'Доделай заказ')
        preview = self.call('status', ident, context=current)
        self.assertFalse(preview['confirmation_required'])
        self.assertEqual(self.call('execute', ident, context=current)['status'], 'verified')
        row = self.row(ident)
        self.assertEqual(row['created_message'], '1')
        self.assertEqual(row['authorization']['message_id'], '2')
        self.assertEqual(row['authorization']['text_sha256'], current['owner_message']['text_sha256'])

    def test_missing_policy_or_native_provenance_preserves_confirmation_gate(self):
        ident = self.call('prepare')['draft_id']
        contexts = [native_context(), {'scope': self.context['scope'], 'message_id': '1'},
                    {**native_context(), 'message_id': '2'}]
        for index, context in enumerate(contexts):
            with self.subTest(index=index):
                self.config['etm_order_authorization'] = '' if index == 0 else 'owner_command'
                preview = self.call('status', ident, context=context)
                self.assertTrue(preview['confirmation_required'])
                self.assertIn('confirmation_command', preview)
                with self.assertRaisesRegex(Failure, '^owner_confirmation_required$'):
                    self.call('execute', ident, context=context)
        self.assertEqual(self.checkout.calls, ['prepare'])
        self.assertEqual(self.row(ident)['status'], 'prepared')

    def test_changed_payload_target_and_expiry_cannot_gain_durable_approval(self):
        ident = self.call('prepare')['draft_id']
        for field, changed in (('etm_proxy', 'different-proxy'),
                               ('item_ids', {'etm': 'different-account'})):
            with self.subTest(field=field):
                previous = self.config[field]
                self.config[field] = changed
                with self.assertRaisesRegex(Failure, '^draft_contract_or_target_changed$'):
                    self.call('execute', ident)
                self.config[field] = previous
        with self.assertRaisesRegex(Failure, '^confirmation_expired$'):
            self.call('execute', ident, now=1601)
        self.assertNotIn('authorization', self.row(ident))
        row = self.row(ident)
        row['prepared']['params']['items'][0]['quantity'] = 200
        self.path(ident).write_text(json.dumps(row))
        with self.assertRaisesRegex(Failure, '^draft_integrity_failed$'):
            self.call('execute', ident)
        self.assertEqual(self.checkout.calls, ['prepare'])

    def test_repeating_verified_execution_in_a_fresh_message_does_not_order_twice(self):
        ident = self.call('prepare')['draft_id']
        self.assertEqual(self.call('execute', ident)['status'], 'verified')
        self.assertEqual(self.call('execute', ident, context=native_context('2'))['status'], 'verified')
        self.assertEqual(self.call('execute', ident)['status'], 'verified')
        self.assertEqual(self.checkout.calls.count('execute'), 1)
        self.assertEqual(self.call('prepare')['draft_id'], ident)

    def test_unknown_submission_cannot_be_replayed_or_replaced_by_new_owner_message(self):
        ident = self.call('prepare')['draft_id']
        self.checkout.error = Failure('request_timeout')
        self.assertEqual(self.call('execute', ident)['status'], 'outcome_unknown')
        new_message = native_context('2', 'Доделай заказ')
        self.assertEqual(self.call('execute', ident, context=new_message)['status'], 'outcome_unknown')
        self.request['params']['items'][0]['quantity'] = 200
        preview = self.call('prepare', context=new_message, now=9000)
        self.assertEqual(preview['status'], 'prepared')
        blocked = self.call('execute', preview['draft_id'], context=new_message, now=9001)
        self.assertEqual(blocked['draft_id'], ident)
        self.assertEqual(self.checkout.calls.count('execute'), 1)

    def test_accepted_checkout_readback_failure_does_not_allow_replacement(self):
        ident = self.call('prepare')['draft_id']
        self.checkout.accept_first = True
        self.checkout.error = Failure('provider_unavailable')
        self.assertEqual(self.call('execute', ident)['status'], 'accepted_unverified')
        newer = native_context('2')
        self.assertEqual(self.call('execute', ident, context=newer)['status'], 'accepted_unverified')
        self.assertEqual(self.call('prepare', context=newer)['draft_id'], ident)
        self.assertEqual(self.call('status', ident, context=newer)['status'], 'verified')
        self.assertEqual(self.checkout.calls, ['prepare', 'execute', 'reconcile'])

    def test_interrupted_selection_is_read_back_without_replaying_the_mutation(self):
        ident = self.call('prepare')['draft_id']
        row = self.row(ident)
        row.update(status='submitting', stage='basket_select_submitting', submitted_at=1001)
        self.path(ident).write_text(json.dumps(row))
        result = self.call('execute', ident)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertFalse(result['checkout_started'])
        self.checkout.basket_matches = False
        self.assertEqual(self.call('status', ident)['status'], 'outcome_unknown')
        self.assertEqual(self.call('prepare')['draft_id'], ident)
        self.checkout.basket_matches = True
        result = self.call('status', ident)
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['result']['order_submitted'])
        self.assertEqual(self.checkout.calls, ['prepare', 'reconcile_basket', 'reconcile_basket'])
        self.assertNotEqual(self.call('prepare')['draft_id'], ident)

    def test_accepted_selection_failure_recovers_as_basket_only_not_unknown_order(self):
        ident = self.call('prepare')['draft_id']
        for saved_status in ('submitting', 'outcome_unknown'):
            with self.subTest(saved_status=saved_status):
                row = self.row(ident)
                row.update(status=saved_status, stage='basket_select_accepted', submitted_at=1001)
                self.path(ident).write_text(json.dumps(row))
                result = self.call('execute', ident)
                self.assertEqual(result['status'], 'blocked')
                self.assertFalse(result['result']['order_submitted'])
                self.assertTrue(result['result']['basket_changed'])
        self.assertEqual(self.checkout.calls, ['prepare'])
        self.assertNotEqual(self.call('prepare')['draft_id'], ident)

    def test_final_checkout_marker_cannot_be_downgraded_to_selection_failure(self):
        ident = self.call('prepare')['draft_id']
        row = self.row(ident)
        row.update(status='submitting', stage='basket_select_accepted',
                   checkout_started=True, submitted_at=1001)
        self.path(ident).write_text(json.dumps(row))
        self.assertEqual(self.call('execute', ident)['status'], 'outcome_unknown')
        self.assertEqual(self.call('status', ident)['status'], 'outcome_unknown')
        self.assertEqual(self.call('prepare')['draft_id'], ident)
        self.assertEqual(self.checkout.calls, ['prepare'])


class OwnerCommandPublicApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {'state_dir': self.tmp.name, 'etm_order_authorization': 'owner_command',
                       'item_ids': {'etm': 'fixture'}}
        self.context = native_context()
        self.checkout = CheckoutFixture(self)
        provider_patch = patch.object(extended_api, 'call', return_value=({'status': {'code': 200}}, []))
        self.provider = provider_patch.start()
        self.addCleanup(provider_patch.stop)
        lifecycle_patch = patch('automation_integrations.etm_lifecycle.reconcile', return_value=None)
        lifecycle_patch.start()
        self.addCleanup(lifecycle_patch.stop)
        preflight_patch = patch('automation_integrations.etm_lifecycle.preflight',
            side_effect=lambda operation, params, config, **kwargs: {
                'target_ids': ['1-123'], 'order_number': params['body']['OrderNumber']})
        preflight_patch.start()
        self.addCleanup(preflight_patch.stop)

    def call(self, request, *, context=None, now=1000):
        return confirmed_write.process(request, self.context if context is None else context,
                                       self.config, clock=lambda: now)

    def prepare(self, operation='invoice_order', params=None, service='etm'):
        return self.call({'action': 'prepare', 'service': service, 'operation': operation,
                          'params': {'path': {'id': 'fixture-document'}} if params is None else params})

    def execute(self, ident, **kwargs):
        return self.call({'action': 'execute', 'draft_id': ident}, **kwargs)

    def row(self, ident):
        return json.loads(Path(self.tmp.name, 'contract-writes', ident + '.json').read_text())

    def checkout_call(self, action='prepare', ident=None, *, context=None):
        request = {'action': action, 'draft_id': ident}
        if action == 'prepare':
            request = {'action': 'prepare', 'service': 'etm', 'operation': 'order_checkout',
                       'params': {'items': [{'code': '6510970', 'quantity': 100}],
                                  'region': '34', 'pickup_store': '29100',
                                  'payment_method': 'bill', 'pay_type': 'bill'}}
        return etm_workflow.process(request, self.context if context is None else context,
                                    self.config, checkout=self.checkout, clock=lambda: 1000)

    def test_public_order_and_delivery_prepare_read_only_then_submit_in_same_turn(self):
        operations = {
            'invoice_order': {'path': {'id': 'fixture-order'}, 'query': {'skl': 29100}},
            'invoice_delivery': {'path': {'id': 'fixture-delivery'}, 'query': {
                'adr': 'fixture-address', 'date': '2026-10-05', 'time': '10:00',
                'time_po': '12:00', 'phone': '+70000000000'}},
        }
        for operation, params in operations.items():
            with self.subTest(operation=operation):
                previous_calls = self.provider.call_count
                preview = self.prepare(operation, params)
                ident = preview['draft_id']
                self.assertEqual(preview['status'], 'prepared')
                self.assertFalse(preview['confirmation_required'])
                self.assertNotIn('confirmation_command', preview)
                self.assertNotIn('authorization', self.row(ident))
                self.assertEqual(self.provider.call_count, previous_calls)

                def submitted(*args, **kwargs):
                    row = self.row(ident)
                    self.assertEqual(row['status'], 'submitting')
                    self.assertEqual(row['approved_hash'], row['payload_hash'])
                    self.assertEqual(row['authorization']['policy'], 'owner_command')
                    return {'status': {'code': 200}}, []

                self.provider.side_effect = submitted
                result = self.execute(ident)
                self.assertEqual(result['status'], 'accepted_unverified')
                self.assertFalse(result['mutation_verified'])
                self.assertEqual(self.provider.call_count, previous_calls + 1)
                self.execute(ident, context=native_context('2'))
                self.assertEqual(self.provider.call_count, previous_calls + 1)

    def test_all_document_lifecycle_actions_follow_the_current_owner_instruction(self):
        for function in ('P', 'A', 'C', 'D'):
            with self.subTest(function=function):
                params = {'body': {'OrderNumber': 'TEST-' + function, 'DocumentFunctionCode': function,
                    'Seller': {'ILN': '4660011519999'}, 'Order-Lines': [
                        {'LineNumber': 1, 'SupplierItemCode': '6510970', 'OrderedQuantity': 100}]}}
                preview = self.prepare('invoice_create', params)
                self.assertFalse(preview['confirmation_required'])
                self.assertNotIn('confirmation_command', preview)
                # Give each documented action an independent target for this policy test.
                if function != 'P':
                    row = self.row(preview['draft_id'])
                    row['lifecycle']['target_ids'] = ['1-' + str(ord(function))]
                    Path(self.tmp.name, 'contract-writes', preview['draft_id'] + '.json').write_text(json.dumps(row))
                with patch('automation_integrations.etm_lifecycle.preflight', return_value=(
                        self.row(preview['draft_id']).get('lifecycle'))):
                    self.assertEqual(self.execute(preview['draft_id'])['status'], 'accepted_unverified')
        self.assertEqual(self.provider.call_count, 4)

    def test_other_providers_require_uuid_even_with_current_native_owner_command(self):
        with patch.object(extended_api, 'contract', return_value=Contract):
            for service in ('tochka', 'saby', 'yandex_go', 'wirenboard'):
                with self.subTest(service=service):
                    preview = self.prepare('sample_write', {'body': {'amount': 12}}, service)
                    self.assertTrue(preview['confirmation_required'])
                    self.assertIn('confirmation_command', preview)
                    with self.assertRaisesRegex(Failure, '^owner_confirmation_required$'):
                        self.execute(preview['draft_id'])
        self.provider.assert_not_called()

    def test_absent_provenance_or_disabled_policy_preserves_public_gate(self):
        ident = self.prepare()['draft_id']
        for context in ({'scope': self.context['scope'], 'message_id': '1'},
                        {**native_context(), 'message_id': '2'}):
            with self.subTest(context=context):
                with self.assertRaisesRegex(Failure, '^owner_confirmation_required$'):
                    self.execute(ident, context=context)
        self.config['etm_order_authorization'] = 'explicit_confirmation'
        with self.assertRaisesRegex(Failure, '^owner_confirmation_required$'):
            self.execute(ident)
        self.provider.assert_not_called()

    def test_fresh_owner_message_can_execute_old_public_preview_without_extra_confirmation(self):
        ident = self.prepare()['draft_id']
        self.assertEqual(self.execute(ident, context=native_context('2'))['status'], 'accepted_unverified')
        self.assertEqual(self.row(ident)['created_message'], '1')
        self.assertEqual(self.row(ident)['authorization']['message_id'], '2')

    def test_public_expiry_target_and_payload_guards_precede_provider_effect(self):
        ident = self.prepare()['draft_id']
        with self.assertRaisesRegex(Failure, '^confirmation_expired$'):
            self.execute(ident, now=1601)
        self.config['item_ids']['etm'] = 'changed-account'
        with self.assertRaisesRegex(Failure, '^draft_contract_or_target_changed$'):
            self.execute(ident)
        self.config['item_ids']['etm'] = 'fixture'
        row = self.row(ident)
        self.assertNotIn('authorization', row)
        row['params']['path']['id'] = 'other-document'
        Path(self.tmp.name, 'contract-writes', ident + '.json').write_text(json.dumps(row))
        with self.assertRaisesRegex(Failure, '^draft_integrity_failed$'):
            self.execute(ident)
        self.provider.assert_not_called()

    def test_public_unknown_result_does_not_resubmit_on_new_owner_message(self):
        ident = self.prepare()['draft_id']
        self.provider.side_effect = Failure('request_timeout')
        self.assertEqual(self.execute(ident)['status'], 'outcome_unknown')
        self.assertEqual(self.execute(ident, context=native_context('2'))['status'], 'outcome_unknown')
        replacement = self.call({'action': 'prepare', 'service': 'etm', 'operation': 'invoice_order',
            'params': {'path': {'id': 'fixture-document'}}}, context=native_context('2'), now=9000)
        self.assertEqual(replacement['draft_id'], ident)
        self.assertEqual(self.provider.call_count, 1)

    def test_readonly_prepare_allows_changes_but_same_document_cannot_replay_unknown_effect(self):
        ident = self.prepare()['draft_id']
        self.provider.side_effect = Failure('request_timeout')
        self.execute(ident)
        for params in ({'path': {'id': 'fixture-document'}, 'query': {'tovzak': 'Новая пометка'}},
                       {'path': {'id': 'fixture-document'}, 'query': {'skl': 1000}}):
            preview = self.prepare(params=params)
            self.assertEqual(preview['status'], 'prepared')
            denied = self.execute(preview['draft_id'])
            self.assertEqual(denied['draft_id'], ident)
            self.assertEqual(denied['error'], 'existing_unresolved_draft')
        independent = self.prepare(params={'path': {'id': 'another-document'}})
        self.assertEqual(self.execute(independent['draft_id'])['status'], 'outcome_unknown')
        self.assertEqual(self.provider.call_count, 2)

    def test_preconfirmed_independent_document_continues_when_another_order_becomes_unknown(self):
        first = self.prepare()['draft_id']
        second = self.prepare(params={'path': {'id': 'second-document'}})['draft_id']
        self.call({'action': 'confirm', 'confirmation_text': 'ПОДТВЕРЖДАЮ ' + second}, context=native_context('2'))
        self.provider.side_effect = Failure('request_timeout')
        self.execute(first)
        result = self.execute(second, context=native_context('2'))
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertIn('submitted_at', self.row(second))
        self.assertEqual(self.provider.call_count, 2)

    def test_unknown_public_order_allows_readonly_website_prepare_but_guards_ambiguous_execute(self):
        public_id = self.prepare()['draft_id']
        self.provider.side_effect = Failure('request_timeout')
        self.execute(public_id)
        preview = self.checkout_call()
        self.assertEqual(preview['status'], 'prepared')
        denied = self.checkout_call('execute', preview['draft_id'])
        self.assertEqual(denied['error'], 'existing_unresolved_draft')
        self.assertEqual(denied['draft_id'], public_id)
        self.assertEqual(self.checkout.calls, ['prepare'])
        self.assertEqual(self.provider.call_count, 1)

    def test_unknown_website_checkout_allows_public_preview_but_guards_ambiguous_execute(self):
        checkout_id = self.checkout_call()['draft_id']
        self.checkout.error = Failure('request_timeout')
        self.checkout_call('execute', checkout_id)
        preview = self.prepare(params={'path': {'id': 'new-document'}})
        self.assertEqual(preview['status'], 'prepared')
        denied = self.execute(preview['draft_id'])
        self.assertEqual(denied['error'], 'existing_unresolved_draft')
        self.assertEqual(denied['draft_id'], checkout_id)
        self.provider.assert_not_called()
        self.assertEqual(self.checkout.calls, ['prepare', 'execute'])

    def test_accepted_public_response_does_not_block_all_future_procurement(self):
        first = self.prepare()['draft_id']
        self.assertEqual(self.execute(first)['status'], 'accepted_unverified')
        self.assertEqual(self.prepare(params={'path': {'id': 'second-document'}})['status'], 'prepared')
        self.assertEqual(self.checkout_call()['status'], 'prepared')
        self.assertEqual(self.provider.call_count, 1)

    def test_website_acceptance_guards_same_document_until_reconciled(self):
        checkout_id = self.checkout_call()['draft_id']
        self.checkout.accept_first = True
        self.checkout.error = Failure('provider_unavailable')
        self.assertEqual(self.checkout_call('execute', checkout_id)['status'], 'accepted_unverified')
        public = self.prepare(params={'path': {'id': 'fixture-1'}})
        self.assertEqual(public['status'], 'prepared')
        self.assertEqual(self.execute(public['draft_id'])['draft_id'], checkout_id)
        self.assertEqual(self.checkout_call('status', checkout_id)['status'], 'verified')
        self.assertEqual(self.execute(public['draft_id'])['status'], 'accepted_unverified')
        self.assertEqual(self.provider.call_count, 1)

    def test_cross_route_guard_preserves_scope_privacy_and_legacy_account_records(self):
        ident = self.prepare()['draft_id']
        self.provider.side_effect = Failure('request_timeout')
        self.execute(ident)
        path = Path(self.tmp.name, 'contract-writes', ident + '.json')
        row = self.row(ident)
        self.assertIn('account_hash', row)
        row.pop('account_hash')
        path.write_text(json.dumps(row))
        foreign = native_context('2')
        foreign['scope'] = ['owner', 'owner', 'another-session', 'another-topic']
        foreign['owner_message']['scope'] = list(foreign['scope'])
        preview = self.checkout_call(context=foreign)
        self.assertEqual(preview['status'], 'prepared')
        result = self.checkout_call('execute', preview['draft_id'], context=foreign)
        self.assertEqual(result['error'], 'other_unresolved_checkout')
        for field in ('draft_id', 'preview', 'result', 'receipt', 'status'):
            self.assertNotIn(field, result)
        local = self.checkout_call()
        self.assertEqual(local['status'], 'prepared')
        self.assertEqual(self.checkout_call('execute', local['draft_id'])['draft_id'], ident)
        self.assertEqual(self.checkout.calls, ['prepare', 'prepare'])

    def test_known_different_account_is_separate_from_unknown_public_order(self):
        ident = self.prepare()['draft_id']
        self.provider.side_effect = Failure('request_timeout')
        self.execute(ident)
        self.config['item_ids']['etm'] = 'another-account'
        self.assertEqual(self.checkout_call()['status'], 'prepared')
        self.assertNotEqual(self.prepare()['draft_id'], ident)

    def test_unknown_print_is_not_an_uncertain_order_and_print_can_continue_during_unknown_order(self):
        printed = self.prepare('invoice_print', {'path': {'id': 'document', 'proc': 'form'}})['draft_id']
        self.provider.side_effect = Failure('request_timeout')
        self.assertEqual(self.execute(printed)['status'], 'outcome_unknown')
        public_id = self.prepare()['draft_id']
        self.assertEqual(self.checkout_call()['status'], 'prepared')
        self.assertEqual(self.execute(public_id)['status'], 'outcome_unknown')
        next_print = self.prepare('invoice_print', {'path': {'id': 'another-document', 'proc': 'form'}})
        self.assertEqual(next_print['status'], 'prepared')
        self.assertEqual(self.execute(next_print['draft_id'])['status'], 'outcome_unknown')
        self.assertEqual(self.provider.call_count, 3)

    def test_uncertain_etm_order_does_not_block_other_provider_with_explicit_confirmation(self):
        public_id = self.prepare()['draft_id']
        self.provider.side_effect = Failure('request_timeout')
        self.execute(public_id)
        self.provider.side_effect = None
        with patch.object(extended_api, 'contract', return_value=Contract):
            unrelated = self.prepare('sample_write', {'body': {'amount': 12}}, 'tochka')
            self.assertTrue(unrelated['confirmation_required'])
            ident = unrelated['draft_id']
            self.call({'action': 'confirm', 'confirmation_text': 'ПОДТВЕРЖДАЮ ' + ident},
                      context=native_context('2'))
            self.assertEqual(self.execute(ident, context=native_context('2'))['status'], 'accepted_unverified')
        self.assertEqual(self.provider.call_count, 2)

    def test_public_and_website_submissions_share_outer_lock_and_recheck_uncertain_result(self):
        public_id = self.prepare()['draft_id']
        checkout_id = self.checkout_call()['draft_id']
        provider_entered, release_provider, website_attempted = (threading.Event() for _ in range(3))

        def slow_uncertain_provider(*args, **kwargs):
            provider_entered.set()
            if not release_provider.wait(5):
                raise AssertionError('test provider was not released')
            raise Failure('request_timeout')

        @contextmanager
        def tracked_lock(config, **kwargs):
            website_attempted.set()
            with procurement_lock(config, **kwargs):
                yield

        self.provider.side_effect = slow_uncertain_provider
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(self.execute, public_id)
            try:
                self.assertTrue(provider_entered.wait(2))
                with patch.object(etm_workflow, 'procurement_lock', tracked_lock):
                    second = pool.submit(self.checkout_call, 'execute', checkout_id)
                    self.assertTrue(website_attempted.wait(2))
                    self.assertFalse(second.done())
                    release_provider.set()
                    self.assertEqual(first.result(timeout=2)['status'], 'outcome_unknown')
                    blocked = second.result(timeout=2)
            finally:
                release_provider.set()
        self.assertEqual(blocked['draft_id'], public_id)
        self.assertEqual(blocked['error'], 'existing_unresolved_draft')
        self.assertEqual(self.checkout.calls, ['prepare'])
        self.assertEqual(self.provider.call_count, 1)


if __name__ == '__main__':
    unittest.main()
