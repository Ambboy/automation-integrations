"""Recovery operations and independent ETM work must not deadlock each other."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from automation_integrations.etm_authorization import (
    account_hash, effects_conflict, procurement_effect, unresolved_procurement,
)


class RecoveryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {'state_dir': self.temp.name, 'item_ids': {'etm': 'account'}}
        self.scope = ['owner', 'owner', 'session', 'topic']

    def effect(self, operation, params, **kwargs):
        return procurement_effect(operation, params, **kwargs)

    def write(self, store, row):
        root = Path(self.temp.name, store)
        root.mkdir(exist_ok=True)
        row = {'draft_id': 'earlier', 'scope': self.scope,
               'account_hash': account_hash(self.config), **row}
        (root / (row['draft_id'] + '.json')).write_text(json.dumps(row))
        return row

    def guard(self, operation, params, **kwargs):
        return unresolved_procurement(self.config, self.scope, operation=operation, params=params, **kwargs)

    def test_cancel_is_available_after_create_reservation_or_delivery_uncertainty(self):
        current = self.effect('invoice_create', {'body': {'DocumentFunctionCode': 'D', 'OrderNumber': 'ONE'}})
        for operation, params in (
                ('invoice_create', {'body': {'DocumentFunctionCode': 'P', 'OrderNumber': 'ONE'}}),
                ('invoice_order', {'path': {'id': '1-123'}}),
                ('invoice_delivery', {'path': {'id': '1-123'}})):
            with self.subTest(operation=operation):
                self.assertFalse(effects_conflict(current, self.effect(operation, params)))

    def test_uncertain_cancel_cannot_be_replaced_by_another_cancel_of_same_target(self):
        params = {'body': {'DocumentFunctionCode': 'D', 'OrderNumber': 'ONE'}}
        self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_create',
            'params': params, 'status': 'outcome_unknown',
            'lifecycle': {'target_ids': ['1-123'], 'order_number': 'ONE'}})
        self.assertEqual(self.guard('invoice_create', params)['draft_id'], 'earlier')
        different = {'body': {'DocumentFunctionCode': 'D', 'OrderNumber': 'TWO'}}
        self.assertIsNone(self.guard('invoice_create', different,
            row={'lifecycle': {'target_ids': ['1-456'], 'order_number': 'TWO'}}))

    def test_known_different_document_can_continue_same_document_cannot(self):
        self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_order',
            'params': {'path': {'id': '1-123'}}, 'status': 'outcome_unknown'})
        self.assertIsNone(self.guard('invoice_order', {'path': {'id': '1-456'}}))
        self.assertEqual(self.guard('invoice_order', {'path': {'id': '1-123'},
            'query': {'skl': 25140}})['draft_id'], 'earlier')
        self.assertEqual(self.guard('invoice_delivery', {'path': {'id': '1-123'}})['draft_id'], 'earlier')

    def test_changed_quantity_region_reference_cannot_disguise_replacement(self):
        params = {'items': [{'code': '100', 'quantity': '10'}], 'region': '63',
                  'customer_order_number': 'SAMARA'}
        self.write('etm-writes', {'status': 'accepted_unverified', 'prepared': {'params': params},
            'receipt': {'document_ids': ['1-123'], 'customer_order_number': 'SAMARA'}})
        changed = deepcopy(params)
        changed.update(region='61', customer_order_number='BATAYSK')
        changed['items'][0]['quantity'] = '20'
        self.assertEqual(self.guard('order_checkout', changed)['draft_id'], 'earlier')
        changed['items'][0]['code'] = '200'
        self.assertIsNone(self.guard('order_checkout', changed))

    def test_specification_conflicts_only_with_its_own_replacement_until_cancelled(self):
        row = self.write('etm-writes', {'status': 'specification',
            'prepared': {'params': {'items': [{'code': '100'}]}},
            'receipt': {'document_ids': ['1-123']}})
        self.assertIsNone(self.guard('invoice_order', {'path': {'id': '1-456'}}))
        self.assertIsNotNone(self.guard('order_checkout', {'items': [{'code': '100'}]}))
        row['status'] = 'canceled'
        self.write('etm-writes', row)
        self.assertIsNone(self.guard('order_checkout', {'items': [{'code': '100'}]}))

    def test_foreign_scope_hides_record_but_does_not_block_unrelated_document(self):
        self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_order',
            'params': {'path': {'id': '1-123'}}, 'status': 'outcome_unknown',
            'scope': ['owner', 'owner', 'other-session', 'topic']})
        denied = self.guard('invoice_order', {'path': {'id': '1-123'}})
        self.assertEqual(denied['error'], 'other_unresolved_checkout')
        self.assertNotIn('draft_id', denied)
        self.assertIsNone(self.guard('invoice_order', {'path': {'id': '1-456'}}))

    def test_unidentified_old_submission_is_conservative_but_cancellation_remains_available(self):
        self.write('etm-writes', {'status': 'outcome_unknown', 'prepared': {}})
        self.assertIsNotNone(self.guard('order_checkout', {'items': [{'code': '100'}]}))
        self.assertIsNone(self.guard('invoice_create', {'body': {
            'DocumentFunctionCode': 'D', 'OrderNumber': 'KNOWN'}}))

    def test_known_specification_can_be_reserved_confirmed_replaced_or_annotated(self):
        self.write('etm-writes', {'status': 'specification',
            'prepared': {'params': {'items': [{'code': '100'}], 'customer_order_number': 'ONE'}},
            'receipt': {'document_ids': ['1-123'], 'order_attempted_ids': []}})
        for operation, params in (
                ('invoice_order', {'path': {'id': '1-123'}}),
                ('invoice_approval_update', {'path': {'id': '1-123'}}),
                ('invoice_create', {'body': {'DocumentFunctionCode': 'A', 'OrderNumber': 'ONE'}}),
                ('invoice_create', {'body': {'DocumentFunctionCode': 'C', 'OrderNumber': 'ONE'}})):
            with self.subTest(operation=operation, params=params):
                self.assertIsNone(self.guard(operation, params))
        self.assertIsNotNone(self.guard('order_checkout', {'items': [{'code': '100'}]}))

    def test_verified_live_specification_preflight_can_advance_old_unverified_creation(self):
        self.write('etm-writes', {'status': 'accepted_unverified',
            'prepared': {'params': {'items': [{'code': '100'}], 'customer_order_number': 'ONE'}},
            'receipt': {'document_ids': ['1-123'], 'order_attempted_ids': []}})
        params = {'body': {'DocumentFunctionCode': 'C', 'OrderNumber': 'ONE'}}
        self.assertIsNotNone(self.guard('invoice_create', params))
        self.assertIsNone(self.guard('invoice_create', params, row={'lifecycle': {
            'target_ids': ['1-123'], 'all_targets_specifications': True}}))

    def test_accepted_but_unverified_cancellation_is_not_replayed_with_changed_note(self):
        params = {'body': {'DocumentFunctionCode': 'D', 'OrderNumber': 'ONE'}}
        self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_create',
            'params': params, 'status': 'accepted_unverified'})
        changed = deepcopy(params)
        changed['body']['Remarks'] = 'A different explanation'
        self.assertIsNotNone(self.guard('invoice_create', changed))

    def test_accepted_unverified_reservation_cannot_repeat_with_changed_warehouse_or_note(self):
        row = self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_order',
            'params': {'path': {'id': '1-123'}, 'query': {'skl': 25140}},
            'status': 'accepted_unverified'})
        for query in ({'skl': 29100}, {'skl': 25140, 'tovzak': 'New note'}):
            with self.subTest(query=query):
                self.assertIsNotNone(self.guard('invoice_order', {'path': {'id': '1-123'}, 'query': query}))
        self.assertIsNone(self.guard('invoice_order', {'path': {'id': '1-456'}}))
        self.assertIsNotNone(self.guard('invoice_delivery', {'path': {'id': '1-123'}}))
        self.assertIsNone(self.guard('invoice_create', {'body': {'DocumentFunctionCode': 'D', 'OrderNumber': 'ONE'}},
            row={'lifecycle': {'target_ids': ['1-123']}}))
        row['status'] = 'verified'
        self.write('contract-writes', row)
        self.assertIsNone(self.guard('invoice_delivery', {'path': {'id': '1-123'}}))

    def test_unverified_delivery_blocks_second_same_document_shipment_but_not_independent_document(self):
        self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_delivery',
            'params': {'path': {'id': '1-123'}, 'query': {'adr': 'POINT-1'}},
            'status': 'accepted_unverified'})
        self.assertIsNotNone(self.guard('invoice_delivery', {'path': {'id': '1-123'}, 'query': {'adr': 'POINT-2'}}))
        self.assertIsNotNone(self.guard('invoice_order', {'path': {'id': '1-123'}}))
        self.assertIsNone(self.guard('invoice_delivery', {'path': {'id': '1-456'}}))
        self.assertIsNotNone(self.guard('invoice_create', {'body': {'DocumentFunctionCode': 'C', 'OrderNumber': 'ONE'}},
            row={'lifecycle': {'target_ids': ['1-123']}}))

    def test_comment_can_continue_despite_unknown_purchase_and_does_not_block_purchase(self):
        self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_order',
            'params': {'path': {'id': '1-123'}}, 'status': 'outcome_unknown'})
        comment = {'path': {'id': '1-123'}, 'query': {'text': 'Please check this document'}}
        self.assertIsNone(self.guard('invoice_approval_update', comment))
        self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_approval_update',
            'params': comment, 'status': 'outcome_unknown'})
        self.assertIsNone(self.guard('invoice_order', {'path': {'id': '1-123'}}))
        self.assertIsNotNone(self.guard('invoice_approval_update', comment))
        different = deepcopy(comment)
        different['query']['text'] = 'A different authorized message'
        self.assertIsNone(self.guard('invoice_approval_update', different))
        different['query']['text'] = comment['query']['text']
        different['path']['id'] = '1-456'
        self.assertIsNone(self.guard('invoice_approval_update', different))

    def test_approval_decision_with_comment_is_not_misclassified_as_comment_only(self):
        params = {'path': {'id': '1-123'}, 'query': {'sg': '1', 'text': 'Approve'}}
        self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_approval_update',
            'params': params, 'status': 'outcome_unknown'})
        changed = deepcopy(params)
        changed['query']['text'] = 'Approve with another message'
        self.assertIsNotNone(self.guard('invoice_approval_update', changed))
        changed['query'].pop('sg')
        self.assertIsNone(self.guard('invoice_approval_update', changed))

    def test_generic_primary_or_confirmation_cannot_be_duplicated_with_new_reference(self):
        for function in ('P', 'A'):
            for status in ('accepted_unverified', 'specification'):
                with self.subTest(function=function, status=status):
                    original = {'body': {'DocumentFunctionCode': function, 'OrderNumber': 'ONE',
                        'Order-Lines': [{'SupplierItemCode': '100', 'OrderedQuantity': 10}]}}
                    self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_create',
                        'params': original, 'status': status,
                        'lifecycle': {'target_ids': ['1-123'], 'order_number': 'ONE'}})
                    duplicate = deepcopy(original)
                    duplicate['body'].update(DocumentFunctionCode='P', OrderNumber='TWO')
                    duplicate['body']['Order-Lines'][0]['OrderedQuantity'] = 20
                    self.assertIsNotNone(self.guard('invoice_create', duplicate))
                    self.assertIsNotNone(self.guard('order_checkout', {'items': [{'code': '100', 'quantity': 20}]}))
                    duplicate['body']['Order-Lines'][0]['SupplierItemCode'] = '200'
                    self.assertIsNone(self.guard('invoice_create', duplicate))
                    self.assertIsNone(self.guard('invoice_create', {'body': {
                        'DocumentFunctionCode': 'D', 'OrderNumber': 'ONE'}}))

    def test_different_preflight_verified_reference_can_be_maintained_despite_same_products(self):
        original = {'body': {'DocumentFunctionCode': 'P', 'OrderNumber': 'ONE',
                    'Order-Lines': [{'SupplierItemCode': '100', 'OrderedQuantity': 10}]}}
        self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_create',
            'params': original, 'status': 'accepted_unverified'})
        for function in ('A', 'C', 'D'):
            independent = deepcopy(original)
            independent['body'].update(DocumentFunctionCode=function, OrderNumber='TWO')
            self.assertIsNone(self.guard('invoice_create', independent,
                row={'lifecycle': {'target_ids': ['1-456'], 'order_number': 'TWO'}}))

    def test_known_specification_after_confirmation_can_advance_without_replaying_confirmation(self):
        params = {'body': {'DocumentFunctionCode': 'A', 'OrderNumber': 'ONE',
                          'Order-Lines': [{'SupplierItemCode': '100', 'OrderedQuantity': 10}]}}
        self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_create',
            'params': params, 'status': 'specification',
            'lifecycle': {'target_ids': ['1-123'], 'order_number': 'ONE'}})
        self.assertIsNone(self.guard('invoice_order', {'path': {'id': '1-123'}}))
        self.assertIsNone(self.guard('invoice_create', {'body': {
            'DocumentFunctionCode': 'C', 'OrderNumber': 'ONE'}}))
        self.assertIsNone(self.guard('invoice_approval_update', {'path': {'id': '1-123'}, 'query': {'sg': '1'}}))
        self.assertIsNotNone(self.guard('invoice_create', params))

    def test_unverified_split_reservation_guards_every_returned_or_readback_child(self):
        for result in (
                {'data': {'ids': [{'docid': '1-102'}, {'docid': None}]}},
                {'data': {'createdDoc': [{'invnum': '1-102'}]}},
                {'data': {'id': '1-102'}},
                {'documents': [{'id': '1-102'}]},
                {'reconciliation': {'document_ids': ['1-102']}}):
            with self.subTest(result=result):
                self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_order',
                    'params': {'path': {'id': '1-101'}, 'query': {'skl': 25140}},
                    'status': 'accepted_unverified', 'result': result})
                self.assertIsNotNone(self.guard('invoice_order', {'path': {'id': '1-102'}, 'query': {'skl': 29100}}))
                self.assertIsNotNone(self.guard('invoice_delivery', {'path': {'id': '1-102'}}))
                self.assertIsNone(self.guard('invoice_order', {'path': {'id': '1-103'}}))

    def test_observed_delivery_document_products_allow_independent_new_purchases(self):
        row = self.write('contract-writes', {'service': 'etm', 'operation': 'invoice_delivery',
            'params': {'path': {'id': '1-101'}}, 'status': 'accepted_unverified',
            'result': {'documents': [{'id': '1-101', 'customer_order_number': 'ONE',
                                      'items': [{'gdscode': '100', 'cnt': '10'}]}]}})
        self.assertIsNone(self.guard('order_checkout', {'items': [{'code': '200', 'quantity': 20}]}))
        self.assertIsNotNone(self.guard('order_checkout', {'items': [{'code': '100', 'quantity': 20}]}))
        self.assertIsNotNone(self.guard('invoice_create', {'body': {
            'DocumentFunctionCode': 'P', 'OrderNumber': 'ONE'}}))
        self.assertIsNone(self.guard('invoice_create', {'body': {
            'DocumentFunctionCode': 'P', 'OrderNumber': 'TWO',
            'Order-Lines': [{'SupplierItemCode': '200', 'OrderedQuantity': 20}]}}))
        row['result'] = {}
        self.write('contract-writes', row)
        self.assertIsNotNone(self.guard('order_checkout', {'items': [{'code': '200', 'quantity': 20}]}))

    def test_different_account_and_verified_effect_do_not_conflict(self):
        self.write('etm-writes', {'status': 'outcome_unknown', 'prepared': {}, 'account_hash': 'another'})
        self.assertIsNone(self.guard('order_checkout', {'items': [{'code': '100'}]}))
        self.write('etm-writes', {'status': 'verified', 'prepared': {}})
        self.assertIsNone(self.guard('order_checkout', {'items': [{'code': '100'}]}))

    def test_uncertain_address_creation_does_not_block_procurement(self):
        self.write('contract-writes', {'service': 'etm', 'operation': 'delivery_point_create',
            'params': {'body': {}}, 'status': 'outcome_unknown'})
        self.assertIsNone(self.guard('order_checkout', {'items': [{'code': '100'}]}))
        self.assertIsNone(self.guard('delivery_point_create', {'body': {'address': 'Another address'}}))
        self.assertIsNotNone(self.guard('delivery_point_create', {'body': {}}))


if __name__ == '__main__':
    unittest.main()
