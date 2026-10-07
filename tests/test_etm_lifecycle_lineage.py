"""Replacement lineage remains usable for subsequent exact-target recovery."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from automation_integrations import etm_lifecycle
from automation_integrations.api_read import Failure
from automation_integrations.api_write import save
from automation_integrations.etm_authorization import account_hash
from tests import test_etm_lifecycle as fixtures

REFERENCE = fixtures.REFERENCE


class LifecycleLineageTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    params = fixtures.LifecycleTests.params
    source = fixtures.LifecycleTests.source
    row = fixtures.LifecycleTests.row
    preflight = fixtures.LifecycleTests.preflight
    reconcile = fixtures.LifecycleTests.reconcile

    def persist_transition(self, row, updates, *, name='replacement', created_at=1000, account=None):
        row = {**deepcopy(row), **deepcopy(updates), 'draft_id': name,
               'created_at': created_at, 'account_hash': account or account_hash(self.config)}
        path = Path(self.tmp.name, 'contract-writes', name + '.json')
        path.parent.mkdir(exist_ok=True)
        save(path, row)
        return row

    def cancel_body(self, ident):
        self.http.bodies[ident]['invStatus'] = 'Отменён'
        for row in self.http.listed:
            if row['id'] == ident:
                row.update(status_name='Отменён', status_code='99')

    def test_replace_split_then_cancel_targets_children_and_preserves_original_receipt(self):
        self.http.add('1-101', status='Расторгнут', code='99')
        self.http.add('1-102')
        self.http.add('1-103')
        path, original = self.source()
        replacement = self.row('C', returned=('1-102', '1-103'))
        updates = self.reconcile(replacement)
        self.assertEqual(updates['status'], 'replaced')
        self.persist_transition(replacement, updates)
        cancel_target = self.preflight('D')
        self.assertEqual(cancel_target['target_ids'], ['1-102', '1-103'])
        self.assertFalse(cancel_target['already_complete'])
        self.cancel_body('1-102')
        self.cancel_body('1-103')
        cancellation = self.row('D', ids=('1-102', '1-103'))
        result = self.reconcile(cancellation)
        self.assertEqual(result['status'], 'canceled')
        recovered = json.loads(path.read_text())
        self.assertEqual(recovered['status'], 'canceled')
        self.assertEqual(recovered['receipt'], original['receipt'])
        self.assertEqual(recovered['recovery']['canceled_document_ids'], ['1-102', '1-103'])
        self.assertEqual(recovered['recovery_history'][0]['replacement_document_ids'], ['1-102', '1-103'])
        already = self.preflight('D')
        self.assertEqual(already['target_ids'], ['1-102', '1-103'])
        self.assertTrue(already['already_complete'])

    def test_repeated_replacement_uses_current_generation_and_ignores_proven_history(self):
        self.http.add('1-101', status='Расторгнут', code='99')
        self.http.add('1-102')
        path, original = self.source()
        first = self.row('C', returned=('1-102',))
        self.persist_transition(first, self.reconcile(first), name='first', created_at=1000)
        self.assertEqual(self.preflight('C')['target_ids'], ['1-102'])
        self.cancel_body('1-102')
        self.http.add('1-103')
        second = self.row('C', ids=('1-102',), returned=('1-103',))
        self.persist_transition(second, self.reconcile(second), name='second', created_at=2000)
        for function in ('C', 'D'):
            with self.subTest(function=function):
                self.assertEqual(self.preflight(function)['target_ids'], ['1-103'])
        self.assertEqual(etm_lifecycle._lineage(self.config, REFERENCE),
                         ({'1-103'}, {'1-101', '1-102'}))
        recovered = json.loads(path.read_text())
        self.assertEqual(recovered['receipt'], original['receipt'])
        self.assertEqual(recovered['recovery']['replacement_document_ids'], ['1-103'])
        self.assertEqual(len(recovered['recovery_history']), 1)

    def test_crash_after_source_replacement_then_child_cancellation_remains_recoverable(self):
        self.http.add('1-101', status='Расторгнут', code='99')
        self.http.add('1-102')
        path, _ = self.source()
        replacement = self.row('C', returned=('1-102',))
        # Provider acceptance/result is durable before source reconciliation.
        # Simulate a crash before the wrapper saves its own `replaced` state.
        pending = self.persist_transition(replacement, {}, name='interrupted-C')
        self.assertEqual(self.reconcile(pending)['status'], 'replaced')
        self.assertEqual(json.loads(path.read_text())['status'], 'replaced')
        self.assertEqual(self.preflight('D')['target_ids'], ['1-102'])
        self.cancel_body('1-102')
        self.assertEqual(self.reconcile(self.row('D', ids=('1-102',)))['status'], 'canceled')
        canceled_source = json.loads(path.read_text())
        self.assertEqual(canceled_source['status'], 'canceled')
        # A later cancellation must not make the already-created replacement
        # permanently unverifiable or revive its source as an active order.
        recovered = self.reconcile(pending)
        self.assertEqual(recovered['status'], 'replaced')
        self.assertTrue(recovered['result']['reconciliation']['verified'])
        self.assertEqual(json.loads(path.read_text()), canceled_source)
        self.persist_transition(pending, recovered, name='interrupted-C')
        done = self.preflight('D')
        self.assertEqual(done['target_ids'], ['1-102'])
        self.assertTrue(done['already_complete'])

    def test_lineage_does_not_accept_untracked_extra_document_with_same_reference(self):
        self.http.add('1-101', status='Расторгнут', code='99')
        self.http.add('1-102')
        self.source()
        replacement = self.row('C', returned=('1-102',))
        self.persist_transition(replacement, self.reconcile(replacement))
        self.http.add('1-103')
        with self.assertRaisesRegex(Failure, 'etm_customer_order_number_ambiguous'):
            self.preflight('D')

    def test_foreign_account_replacement_cannot_expand_or_redirect_lineage(self):
        self.http.add('1-101')
        self.http.add('1-102')
        self.source()
        foreign = self.row('C', ids=('1-101',), returned=('1-102',))
        self.persist_transition(foreign, {'status': 'replaced'}, account='another-account')
        self.assertEqual(etm_lifecycle._lineage(self.config, REFERENCE), ({'1-101'}, set()))
        with self.assertRaisesRegex(Failure, 'etm_customer_order_number_ambiguous'):
            self.preflight('D')

    def test_incomplete_original_ids_are_never_released_by_cancellation(self):
        self.http.add(status='Отменён', code='99')
        path, source = self.source()
        source['receipt']['all_returned_ids_valid'] = False
        save(path, source)
        result = self.reconcile(self.row())
        self.assertEqual(result['status'], 'canceled')
        # This exact cancellation can be verified, but it cannot prove the
        # original creation's unknown omitted documents were all canceled.
        self.assertEqual(json.loads(path.read_text()), source)

    def test_checkout_status_does_not_release_incomplete_original_ids(self):
        self.http.add(status='Отменён', code='99')
        _, source = self.source()
        source['receipt']['all_returned_ids_valid'] = False
        result = etm_lifecycle.reconcile_checkout(source, self.config,
            checkout=SimpleNamespace(client=fixtures.WebFixture(self.http)))
        self.assertTrue(result is None or result.get('status') not in ('canceled', 'replaced', 'verified'))

    def test_malformed_replacement_response_cannot_resolve_original_creation(self):
        self.http.add('1-101', status='Отменён', code='99')
        self.http.add('1-102')
        path, source = self.source()
        replacement = self.row('C', returned=('1-102',))
        replacement['result']['data']['ids'].append({'docid': 'MALFORMED'})
        result = self.reconcile(replacement)
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertFalse(result['result']['reconciliation']['verified'])
        self.assertEqual(json.loads(path.read_text()), source)

    def test_partial_child_cancellation_does_not_claim_complete_replacement_cancellation(self):
        self.http.add('1-101', status='Расторгнут', code='99')
        self.http.add('1-102')
        self.http.add('1-103')
        path, _ = self.source()
        replacement = self.row('C', returned=('1-102', '1-103'))
        self.persist_transition(replacement, self.reconcile(replacement))
        before = json.loads(path.read_text())
        self.cancel_body('1-102')
        cancellation = self.reconcile(self.row('D', ids=('1-102', '1-103')))
        self.assertEqual(cancellation['status'], 'accepted_unverified')
        self.assertFalse(cancellation['result']['reconciliation']['verified'])
        self.assertEqual(json.loads(path.read_text()), before)
        self.assertEqual(self.preflight('D')['target_ids'], ['1-102', '1-103'])


if __name__ == '__main__':
    unittest.main()
