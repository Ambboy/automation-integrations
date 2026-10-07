"""Public document actions are reconciled by reads, including split responses."""
from copy import deepcopy
import tempfile
import unittest

from automation_integrations import etm_lifecycle_actions
from automation_integrations.api_read import Failure


class VaultFixture:
    def __init__(self):
        self.sensitive = []

    def get(self, service):
        if service != 'etm':
            raise AssertionError(service)
        return {'ETM_LOGIN': 'fixture-login', 'ETM_PASSWORD': 'fixture-password'}


class ActionReadHTTP:
    def __init__(self):
        self.calls = []
        self.bodies = {}
        self.listed = {}
        self.comments = []
        self.comments_by_id = {}

    def add(self, ident='1-101', *, status='В подборе', code='24', destination='25140', client='123'):
        number = 'FIXTURE-' + ident
        self.bodies[ident] = {'invnetnum': ident, 'invnum': number, 'cli_code': client,
                             'invStatus': status, 'store': 20100, 'invsum': '100.00',
                             'rows': [{'gdscode': '1001', 'cnt': '10'}]}
        self.listed[number] = [{'id': ident, 'usr_inv_num': number, 'status_name': status,
                                'status_code': code, 'st_dest': destination, 'cli_code': client}]
        return self.listed[number][0]

    def call(self, method, path, *, query=None, **_kwargs):
        self.calls.append((method, path, deepcopy(query)))
        if (method, path) == ('POST', '/user/login'):
            return {'status': {'code': 200}, 'data': {'session': 'fixture-session'}}
        if method != 'GET':
            raise AssertionError('Readback must never submit a business operation')
        if query.get('session-id') != 'fixture-session':
            raise AssertionError('Authenticated session is required')
        if path == '/invoice':
            rows = self.listed.get(query['usr-inv-num'], [])
            data = {'rows': deepcopy(rows), 'records': len(rows)}
        elif path.endswith('/body'):
            ident = path.split('/')[2]
            if ident not in self.bodies:
                raise Failure('etm_api_error', 404, provider_code='404')
            data = deepcopy(self.bodies[ident])
        elif path.endswith('/ps'):
            data = {'comments': deepcopy(self.comments_by_id.get(path.split('/')[2], self.comments)),
                    'agreement': '1'}
        else:
            raise AssertionError(path)
        return {'status': {'code': 200}, 'data': data}


class ActionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {'state_dir': self.tmp.name}
        self.http = ActionReadHTTP()
        self.vault = VaultFixture()
        self.http.add()

    def row(self, operation='invoice_order', *, query=None, result=None, status='accepted_unverified'):
        return {'service': 'etm', 'operation': operation, 'status': status,
                'params': {'path': {'id': '1-101'}, 'query': {'skl': 25140} if query is None else query},
                'result': {'status': {'code': 200}} if result is None else result}

    def reconcile(self, row):
        before = deepcopy(row)
        result = etm_lifecycle_actions.reconcile(row, self.config, http=self.http, vault=self.vault)
        self.assertEqual(row, before, 'Readback must not edit its input receipt')
        self.assertTrue(all(method == 'GET' or path == '/user/login' for method, path, _ in self.http.calls))
        return result

    def test_order_without_returned_ids_uses_explicit_path_and_positive_state(self):
        result = self.reconcile(self.row())
        self.assertEqual(result['status'], 'verified')
        evidence = result['result']['reconciliation']
        self.assertEqual(evidence['document_ids'], ['1-101'])
        self.assertEqual(evidence['target_source'], 'request_path')
        self.assertFalse(evidence['physical_allocation_verified'])
        self.assertFalse(evidence['quantity_baseline_available'])
        self.assertFalse(result['result']['ready_for_pickup'])
        self.assertEqual(sum(path.endswith('/body') for _, path, _ in self.http.calls), 1)

    def test_unknown_order_response_can_be_resolved_using_known_path_without_post(self):
        result = self.reconcile(self.row(result={}, status='outcome_unknown'))
        self.assertEqual(result['status'], 'verified')

    def test_missing_response_ids_cannot_hide_a_split_sibling(self):
        for status in ('accepted_unverified', 'outcome_unknown'):
            with self.subTest(status=status):
                sibling = self.http.add('1-102', status='Спецификация', code='01')
                sibling['usr_inv_num'] = 'FIXTURE-1-101'
                self.http.listed['FIXTURE-1-101'] = [self.http.listed['FIXTURE-1-101'][0], sibling]
                result = self.reconcile(self.row(result={}, status=status))
                self.assertEqual(result['status'], status)
                evidence = result['result']['reconciliation']
                self.assertIn('unreturned_related_documents_unverified', evidence['problems'])
                self.assertEqual(evidence['related_document_ids_as_returned'], ['1-102'])

    def test_split_response_reads_every_returned_document(self):
        self.http.add('1-102')
        self.http.add('1-103')
        result = self.reconcile(self.row(result={'data': {'id': '1-102', 'ids': [{'docid': '1-103'}]}}))
        self.assertEqual(result['status'], 'verified')
        self.assertEqual({doc['id'] for doc in result['result']['documents']}, {'1-102', '1-103'})

    def test_order_note_must_be_present_on_every_returned_document(self):
        self.http.add('1-102')
        note = 'Один непрерывный отрезок 100 м'
        row = self.row(query={'skl': 25140, 'tovzak': note},
                       result={'data': {'ids': [{'docid': '1-101'}, {'docid': '1-102'}]}})
        self.http.bodies['1-101']['ps'] = note
        self.http.comments_by_id['1-102'] = [{'text': note + ' — изменённое условие'}]
        result = self.reconcile(row)
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('1-102:order_note_unverified', result['result']['reconciliation']['problems'])
        self.http.comments_by_id['1-102'] = [{'text': note}]
        self.assertEqual(self.reconcile(row)['status'], 'verified')
        self.assertFalse(any(path == '/invoice/1-101/ps' for _, path, _ in self.http.calls))

    def test_missing_order_note_preserves_unknown_result(self):
        result = self.reconcile(self.row(query={'skl': 25140, 'tovzak': 'Точное условие'},
                                         result={}, status='outcome_unknown'))
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertIn('1-101:order_note_unverified', result['result']['reconciliation']['problems'])

    def test_one_unaccepted_split_prevents_full_order_verification(self):
        self.http.add('1-102', status='Спецификация', code='01')
        result = self.reconcile(self.row(result={'data': {'ids': [{'docid': '1-101'}, {'docid': '1-102'}]}}))
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('1-102:order_acceptance_unverified', result['result']['reconciliation']['problems'])

    def test_partial_malformed_ids_do_not_fall_back_to_false_single_document_success(self):
        result = self.reconcile(self.row(result={'data': {'ids': [{'docid': '1-101'}, {'docid': None}]}}))
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('returned_document_ids_incomplete', result['result']['reconciliation']['problems'])

    def test_empty_explicit_id_array_remains_unverified(self):
        result = self.reconcile(self.row(result={'data': {'ids': []}}))
        self.assertEqual(result['status'], 'accepted_unverified')

    def test_wrong_destination_and_unknown_result_preserve_unknown_state(self):
        self.http.listed['FIXTURE-1-101'][0]['st_dest'] = '29100'
        result = self.reconcile(self.row(status='outcome_unknown'))
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertIn('1-101:destination_unverified', result['result']['reconciliation']['problems'])

    def test_current_store_does_not_substitute_for_receiving_store(self):
        self.http.bodies['1-101']['store'] = 25140
        self.http.listed['FIXTURE-1-101'][0]['st_dest'] = '29100'
        self.assertEqual(self.reconcile(self.row())['status'], 'accepted_unverified')

    def test_delivery_order_1000_requires_explicit_matching_receiving_code(self):
        self.assertEqual(self.reconcile(self.row(query={'skl': 1000}))['status'], 'accepted_unverified')
        self.http.listed['FIXTURE-1-101'][0]['st_dest'] = '1000'
        result = self.reconcile(self.row(query={'skl': 1000}))
        self.assertEqual(result['status'], 'verified')
        self.assertTrue(result['result']['reconciliation']['delivery_requested'])

    def test_missing_destination_does_not_verify_implicit_provider_choice(self):
        self.assertEqual(self.reconcile(self.row(query={}))['status'], 'accepted_unverified')

    def test_canceled_body_is_not_accepted_even_if_list_code_is_reserved(self):
        self.http.bodies['1-101']['invStatus'] = 'Отменен'
        self.assertEqual(self.reconcile(self.row())['status'], 'accepted_unverified')

    def test_missing_exact_list_row_and_body_404_are_not_proof(self):
        self.http.listed.clear()
        self.assertEqual(self.reconcile(self.row())['status'], 'accepted_unverified')
        self.http.bodies.clear()
        with self.assertRaisesRegex(Failure, 'etm_api_error'):
            self.reconcile(self.row())

    def test_split_documents_for_different_clients_remain_unverified(self):
        self.http.add('1-102', client='456')
        result = self.reconcile(self.row(result={'data': {'ids': [{'docid': '1-101'}, {'docid': '1-102'}]}}))
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('document_clients_differ', result['result']['reconciliation']['problems'])

    def test_delivery_id_and_status_do_not_prove_requested_point_or_date(self):
        self.http.listed['FIXTURE-1-101'][0].update(delivery='delivery-fixture',
            delivery_status='accepted', delivery_name='Доставка создана')
        result = self.reconcile(self.row('invoice_delivery', query={
            'adr': 'point-1', 'date': '2026-10-09', 'time': '09:00', 'time_po': '13:00', 'phone': 'fixture'}))
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertEqual(result['result']['documents'][0]['delivery_as_returned']['delivery'], 'delivery-fixture')
        self.assertIn('delivery_point_date_window_binding_unverified', result['result']['reconciliation']['problems'])

    def test_delivery_timeout_remains_unknown_without_exact_binding_readback(self):
        result = self.reconcile(self.row('invoice_delivery', query={'adr': 'point-1'}, status='outcome_unknown'))
        self.assertEqual(result['status'], 'outcome_unknown')

    def test_exact_comment_text_verifies_observable_requested_effect(self):
        self.http.comments = [{'text': 'Один непрерывный отрезок 100 м', 'agreed': ''}]
        result = self.reconcile(self.row('invoice_approval_update', query={'text': 'Один непрерывный отрезок 100 м'}))
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['result']['reconciliation']['matching_comments'], 1)

    def test_comment_prefix_is_not_an_exact_match(self):
        self.http.comments = [{'text': 'Один отрезок; другое количество', 'agreed': ''}]
        result = self.reconcile(self.row('invoice_approval_update', query={'text': 'Один отрезок'}))
        self.assertEqual(result['status'], 'accepted_unverified')

    def test_comment_and_approval_must_both_match_current_requested_state(self):
        self.http.comments = [{'text': 'Согласовано', 'agreed': '1'}]
        query = {'text': 'Согласовано', 'sg': '1'}
        result = self.reconcile(self.row('invoice_approval_update', query=query))
        self.assertEqual(result['status'], 'accepted_unverified')
        self.http.listed['FIXTURE-1-101'][0]['agreed'] = '1'
        self.assertEqual(self.reconcile(self.row('invoice_approval_update', query=query))['status'], 'verified')
        self.http.comments[0]['agreed'] = '2'
        self.assertEqual(self.reconcile(self.row('invoice_approval_update', query=query))['status'], 'accepted_unverified')

    def test_approval_only_reads_current_state_not_stale_comment_or_permission(self):
        self.http.comments = [{'text': 'Старое согласование', 'agreed': '1'}]
        self.http.listed['FIXTURE-1-101'][0]['agreed'] = '2'
        result = self.reconcile(self.row('invoice_approval_update', query={'sg': '1'}))
        self.assertEqual(result['status'], 'accepted_unverified')
        result = self.reconcile(self.row('invoice_approval_update', query={'sg': '2'}))
        self.assertEqual(result['status'], 'verified')

    def test_undocumented_final_status_and_internal_visibility_are_not_assumed(self):
        self.http.comments = [{'text': 'Точный текст', 'agreed': '3'}]
        for query in ({'text': 'Точный текст', 'docStatus': 'agreed'},
                      {'text': 'Точный текст', 'service_message': 'true'},
                      {'text': 'Точный текст', 'sg': '3'}):
            with self.subTest(query=query):
                result = self.reconcile(self.row('invoice_approval_update', query=query))
                self.assertEqual(result['status'], 'accepted_unverified')

    def test_other_service_or_operation_does_not_authenticate(self):
        row = self.row()
        row['service'] = 'other'
        self.assertIsNone(self.reconcile(row))
        row.update(service='etm', operation='invoice_create')
        self.assertIsNone(self.reconcile(row))
        self.assertEqual(self.http.calls, [])


if __name__ == '__main__':
    unittest.main()
