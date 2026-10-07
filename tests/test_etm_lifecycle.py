"""Lifecycle recovery reads exact provider documents without replaying writes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from automation_integrations import confirmed_write, etm_lifecycle
from automation_integrations.api_read import Failure
from automation_integrations.api_write import save
from automation_integrations.etm_authorization import account_hash


REFERENCE = 'AI-LIFECYCLE-FIXTURE'


class VaultFixture:
    def __init__(self):
        self.sensitive = ['fixture-login', 'fixture-password']

    def get(self, service):
        if service != 'etm':
            raise AssertionError(service)
        return {'ETM_LOGIN': 'fixture-login', 'ETM_PASSWORD': 'fixture-password'}


class ReadOnlyHTTP:
    """Exercise the real Reader contract; any business request fails the test."""
    def __init__(self):
        self.calls = []
        self.listed = []
        self.bodies = {}
        self.pages = None
        self.reference = REFERENCE

    def add(self, ident='1-101', *, reference=REFERENCE, status='Спецификация',
            client='123', code='01', listed=True):
        body = {'invnetnum': ident, 'invnum': reference, 'cli_code': client,
                'invStatus': status, 'store': 20100, 'invsum': '100.00', 'paysum': '0',
                'rows': [{'gdscode': '1001', 'cnt': '10'}]}
        self.bodies[ident] = body
        if listed:
            self.listed.append({'id': ident, 'usr_inv_num': reference, 'status_code': code,
                                'status_name': status, 'st_dest': '25140', 'pay': '0',
                                'operations': {'cancel': True, 'edit': True}})
        return body

    def data(self, path, query):
        if path == '/invoice':
            if query.get('usr-inv-num') != self.reference:
                raise AssertionError('Use the exact customer reference, not an ETM ID')
            if self.pages is not None:
                return deepcopy(self.pages[query['page']])
            return {'records': len(self.listed), 'rows': deepcopy(self.listed)}
        if path.startswith('/invoice/') and path.endswith('/body'):
            ident = path.split('/')[2]
            if ident not in self.bodies:
                raise Failure('etm_api_error', 404, provider_code='404')
            return deepcopy(self.bodies[ident])
        raise AssertionError((path, query))

    def call(self, method, path, *, query=None, **kwargs):
        self.calls.append((method, path, deepcopy(query)))
        if (method, path) == ('POST', '/user/login'):
            if query != {'log': 'fixture-login', 'pwd': 'fixture-password'}:
                raise AssertionError('Login credentials did not come from Vault')
            return {'status': {'code': 200}, 'data': {'session': 'fixture-session'}}
        if method != 'GET':
            raise AssertionError('Recovery must not send a business request: ' + method + ' ' + path)
        if query.get('session-id') != 'fixture-session':
            raise AssertionError('Reader must use the authenticated session')
        return {'status': {'code': 200}, 'data': self.data(path, query)}


class WebFixture:
    def __init__(self, http):
        self.http = http
        self.calls = []

    def login(self, region):
        self.calls.append(('login', region))
        if region != '61':
            raise AssertionError(region)
        return {'clicode': '123'}

    def call(self, method, path, *, query=None):
        self.calls.append((method, path))
        if method != 'GET':
            raise AssertionError('Checkout status must not send a business request')
        return self.http.data(path, query)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {'state_dir': self.tmp.name, 'item_ids': {'etm': 'fixture-account'},
                       'etm_order_authorization': 'owner_command',
                       'etm_proxy': 'socks5h://127.0.0.1:10929'}
        self.http = ReadOnlyHTTP()
        self.vault = VaultFixture()

    def params(self, function='D'):
        return {'body': {'OrderNumber': REFERENCE, 'DocumentFunctionCode': function,
                         'Seller': {'ILN': '4660011519999'},
                         'Order-Lines': [{'LineNumber': 1, 'SupplierItemCode': '1001',
                                          'OrderedQuantity': 10}]}}

    def source(self, ids=('1-101',), *, name='source', reference=REFERENCE,
               status='accepted_unverified', account=None):
        path = Path(self.tmp.name, 'etm-writes', name + '.json')
        path.parent.mkdir(exist_ok=True)
        row = {'draft_id': name, 'status': status,
               'account_hash': account or account_hash(self.config),
               'scope': ['owner', 'owner', 'session', 'topic'],
               'prepared': {'params': {'region': '61', 'customer_order_number': reference}},
               'receipt': {'customer_order_number': reference, 'document_ids': list(ids),
                           'all_returned_ids_valid': True, 'order_attempted_ids': [],
                           'retained_evidence': 'immutable receipt fixture'},
               'result': {'provider_detail': 'must survive recovery'}}
        save(path, row)
        return path, row

    def preflight(self, function='D'):
        return etm_lifecycle.preflight('invoice_create', self.params(function), self.config,
                                       http=self.http, vault=self.vault)

    def row(self, function='D', ids=('1-101',), returned=()):
        return {'service': 'etm', 'operation': 'invoice_create',
                'params': self.params(function), 'status': 'accepted_unverified',
                'lifecycle': {'function': function, 'order_number': REFERENCE,
                              'target_ids': list(ids), 'client_code': '123'},
                'result': {'status': {'code': 200},
                           'data': {'ids': [{'docid': ident} for ident in returned]}}}

    def generic_source(self, function='P', ids=('1-101',), *, name='generic-source',
                       operation='invoice_create', status='specification', account=None,
                       reference=REFERENCE):
        row = self.row(function, ids=ids if function == 'A' else (), returned=ids)
        row.update(draft_id=name, status=status, account_hash=account or account_hash(self.config),
                   created_at=1000, submitted_at=1001, operation=operation)
        row['params']['body']['OrderNumber'] = reference
        if operation == 'invoice_order':
            row['params'] = {'path': {'id': ids[0]}, 'query': {'skl': 25140}}
        row['result']['reconciliation'] = {'status': status, 'read_only': True, 'fixture_history': True}
        path = Path(self.tmp.name, 'contract-writes', name + '.json')
        path.parent.mkdir(exist_ok=True)
        save(path, row)
        return path, row

    def reconcile(self, row):
        return etm_lifecycle.reconcile(row, self.config, http=self.http, vault=self.vault)

    def test_reader_authenticates_once_and_uses_session_only_for_reads(self):
        self.http.add()
        reader = etm_lifecycle.Reader(self.config, http=self.http, vault=self.vault)
        data = reader.read('/invoice', {'usr-inv-num': REFERENCE, 'rows': 100, 'page': 1})
        self.assertEqual(data['records'], 1)
        self.assertEqual([method for method, _, _ in self.http.calls], ['POST', 'GET'])
        self.assertIn('fixture-session', self.vault.sensitive)

    def test_cancel_preflight_resolves_unique_customer_reference(self):
        self.http.add()
        target = self.preflight()
        self.assertEqual(target['target_ids'], ['1-101'])
        self.assertEqual(target['client_code'], '123')
        self.assertEqual(target['order_number'], REFERENCE)
        self.assertFalse(target['already_complete'])

    def test_current_body_status_takes_precedence_over_stale_canceled_listing(self):
        self.http.add()
        self.http.listed[0]['status_name'] = 'Расторгнут'
        target = self.preflight()
        self.assertFalse(target['already_complete'])
        result = self.reconcile(self.row())
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertFalse(result['result']['reconciliation']['verified'])

    def test_ambiguous_unlinked_customer_reference_rejects_before_mutation(self):
        self.http.add('1-101')
        self.http.add('1-102')
        with self.assertRaisesRegex(Failure, 'etm_customer_order_number_ambiguous'):
            self.preflight()
        self.assertEqual([path for _, path, _ in self.http.calls], ['/user/login', '/invoice'])

    def test_known_split_reads_every_exact_document(self):
        self.http.add('1-101')
        self.http.add('1-102')
        self.source(('1-101', '1-102'))
        target = self.preflight()
        self.assertEqual(target['target_ids'], ['1-101', '1-102'])
        self.assertEqual(len(target['documents']), 2)

    def test_extra_document_with_same_reference_does_not_expand_known_target(self):
        self.http.add('1-101')
        self.http.add('1-102')
        self.source()
        with self.assertRaisesRegex(Failure, 'etm_customer_order_number_ambiguous'):
            self.preflight()

    def test_empty_search_falls_back_to_known_id_but_verifies_its_number(self):
        self.http.add(reference='OTHER-REFERENCE', listed=False)
        self.source()
        with self.assertRaisesRegex(Failure, 'identity_mismatch|reference_mismatch'):
            self.preflight()

    def test_native_display_number_may_differ_from_verified_customer_reference(self):
        self.http.add()
        self.http.bodies['1-101']['invnum'] = '302/NATIVE-NUMBER'
        target = self.preflight()
        self.assertEqual(target['documents'][0]['number'], '302/NATIVE-NUMBER')
        self.assertEqual(target['documents'][0]['customer_order_number'], REFERENCE)

    def test_body_with_different_document_id_is_rejected(self):
        self.http.add()
        self.http.bodies['1-101']['invnetnum'] = '1-999'
        with self.assertRaisesRegex(Failure, 'etm_lifecycle_document_unverified'):
            self.preflight()

    def test_list_client_must_match_body_client(self):
        self.http.add()
        self.http.listed[0]['cli_code'] = '456'
        with self.assertRaisesRegex(Failure, 'etm_lifecycle_document_identity_mismatch'):
            self.preflight()

    def test_mismatched_list_id_cannot_be_bound_to_read_body(self):
        self.http.add()
        reader = etm_lifecycle.Reader(self.config, http=self.http, vault=self.vault)
        with self.assertRaisesRegex(Failure, 'etm_lifecycle_document_identity_mismatch'):
            etm_lifecycle._document(reader, '1-101', {**self.http.listed[0], 'id': '1-999'})

    def test_foreign_account_source_cannot_make_ambiguous_documents_trusted(self):
        self.http.add('1-101')
        self.http.add('1-102')
        self.source(('1-101', '1-102'), account='another-account-hash')
        with self.assertRaisesRegex(Failure, 'etm_customer_order_number_ambiguous'):
            self.preflight()

    def test_replacement_rejects_nonreplaceable_provider_state(self):
        self.http.add(status='Отгружен', code='30')
        with self.assertRaisesRegex(Failure, 'etm_document_not_replaceable'):
            self.preflight('C')

    def test_replace_accepts_specification_and_both_bill_spellings(self):
        for status, code in (('Спецификация', '01'), ('Счёт на оплату', '02'), ('Счет на оплату', '02')):
            with self.subTest(status=status):
                self.http.listed.clear()
                self.http.add(status=status, code=code)
                self.assertEqual(self.preflight('C')['target_ids'], ['1-101'])

    def test_explicit_provider_cancel_prohibition_is_respected(self):
        self.http.add()
        self.http.listed[0]['operations']['cancel'] = False
        with self.assertRaisesRegex(Failure, 'etm_provider_cancellation_unavailable'):
            self.preflight()

    def test_duplicate_ids_and_incomplete_pagination_are_not_valid_evidence(self):
        self.http.add()
        row = deepcopy(self.http.listed[0])
        for pages, error in (
                ({1: {'records': 2, 'rows': [row, row]}}, 'duplicate_document_id'),
                ({1: {'records': 2, 'rows': [row]}, 2: {'records': 2, 'rows': []}}, 'listing_incomplete')):
            with self.subTest(error=error):
                self.http.pages = pages
                with self.assertRaisesRegex(Failure, error):
                    self.preflight()

    def test_already_canceled_owner_command_is_read_only_and_durable(self):
        self.http.add(status='Расторгнут', code='99')
        path, source = self.source()
        scope = ['owner', 'owner', 'session', 'topic']
        context = {'scope': scope, 'message_id': '1', 'owner_message': {
            'source': 'native_owner_telegram', 'scope': scope, 'message_id': '1',
            'text_sha256': hashlib.sha256('Отмени точную заявку'.encode()).hexdigest()}}
        prepared = confirmed_write.process(
            {'action': 'prepare', 'service': 'etm', 'operation': 'invoice_create', 'params': self.params()},
            context, self.config, http=self.http, vault=self.vault, clock=lambda: 1000)
        self.assertFalse(prepared['confirmation_required'])
        self.assertTrue(prepared['lifecycle']['already_complete'])
        result = confirmed_write.process({'action': 'execute', 'draft_id': prepared['draft_id']},
            context, self.config, http=self.http, vault=self.vault, clock=lambda: 1000)
        self.assertEqual(result['status'], 'canceled')
        self.assertTrue(result['mutation_verified'])
        saved = json.loads(path.read_text())
        self.assertEqual(saved['status'], 'canceled')
        self.assertEqual(saved['receipt'], source['receipt'])
        self.assertTrue(all(method == 'GET' or endpoint == '/user/login'
                            for method, endpoint, _ in self.http.calls))

    def test_cancellation_resolves_only_linked_source_and_preserves_receipt(self):
        self.http.add(status='Отменён', code='99')
        path, source = self.source()
        unrelated_path, unrelated = self.source(name='unrelated', reference='OTHER-REFERENCE')
        foreign_path, foreign = self.source(name='foreign', account='another-account-hash')
        result = self.reconcile(self.row())
        self.assertEqual(result['status'], 'canceled')
        self.assertTrue(result['result']['reconciliation']['verified'])
        saved = json.loads(path.read_text())
        self.assertEqual(saved['receipt'], source['receipt'])
        self.assertEqual(saved['recovery']['previous_status'], 'accepted_unverified')
        self.assertEqual(saved['recovery']['canceled_document_ids'], ['1-101'])
        self.assertEqual(saved['result']['provider_detail'], 'must survive recovery')
        self.assertEqual(json.loads(unrelated_path.read_text()), unrelated)
        self.assertEqual(json.loads(foreign_path.read_text()), foreign)

    def test_partial_split_cancellation_does_not_release_source(self):
        self.http.add('1-101', status='Отменен', code='99')
        self.http.add('1-102')
        path, source = self.source(('1-101', '1-102'))
        result = self.reconcile(self.row(ids=('1-101', '1-102')))
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertFalse(result['result']['reconciliation']['verified'])
        self.assertEqual(json.loads(path.read_text()), source)

    def test_replacement_requires_old_canceled_and_reads_all_new_ids(self):
        self.http.add('1-101', status='Расторгнут', code='99')
        self.http.add('1-102')
        self.http.add('1-103')
        path, source = self.source()
        result = self.reconcile(self.row('C', returned=('1-102', '1-103')))
        self.assertEqual(result['status'], 'replaced')
        self.assertEqual({doc['id'] for doc in result['result']['documents']}, {'1-101', '1-102', '1-103'})
        saved = json.loads(path.read_text())
        self.assertEqual(saved['status'], 'replaced')
        self.assertEqual(saved['recovery']['replacement_document_ids'], ['1-102', '1-103'])
        self.assertEqual(saved['receipt'], source['receipt'])

    def test_replacement_without_old_cancellation_does_not_resolve(self):
        self.http.add('1-101')
        self.http.add('1-102')
        path, source = self.source()
        result = self.reconcile(self.row('C', returned=('1-102',)))
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertFalse(result['result']['reconciliation']['verified'])
        self.assertEqual(json.loads(path.read_text()), source)

    def test_missing_document_is_never_proof_of_cancellation(self):
        path, source = self.source()
        with self.assertRaisesRegex(Failure, 'etm_api_error'):
            self.reconcile(self.row())
        self.assertEqual(json.loads(path.read_text()), source)

    def test_empty_listing_with_known_live_body_does_not_claim_cancellation(self):
        self.http.add(listed=False)
        result = self.reconcile(self.row())
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertFalse(result['result']['reconciliation']['verified'])

    def test_generic_primary_result_becomes_known_specification_without_ordering(self):
        self.http.add()
        row = self.row('P', ids=(), returned=('1-101',))
        result = self.reconcile(row)
        self.assertEqual(result['status'], 'specification')
        self.assertFalse(result['result']['reconciliation']['verified'])
        self.assertTrue(result['result']['reconciliation']['read_only'])
        self.assertEqual(result['lifecycle']['target_ids'], ['1-101'])

    def test_cancel_closes_linked_generic_creation_confirmation_and_order_receipts(self):
        self.http.add(status='Отменен', code='99')
        sources = [self.generic_source(function, name='source-' + function) for function in ('P', 'A')]
        sources.append(self.generic_source(name='order', operation='invoice_order', status='outcome_unknown'))
        result = self.reconcile(self.row())
        self.assertEqual(result['status'], 'canceled')
        for path, original in sources:
            with self.subTest(source=path.name):
                saved = json.loads(path.read_text())
                self.assertEqual(saved['status'], 'canceled')
                self.assertEqual(saved['result']['data'], original['result']['data'])
                self.assertEqual(saved['result']['status'], original['result']['status'])
                self.assertEqual(saved['params'], original['params'])
                self.assertEqual(saved['recovery']['previous_reconciliation'], original['result']['reconciliation'])
                self.assertFalse(saved['recovery']['original_operation_completion_verified'])
                self.assertTrue(saved['result']['reconciliation']['document_cancellation_verified'])

    def test_cancel_does_not_resolve_generic_other_account_reference_or_partial_receipt(self):
        self.http.add(status='Отменен', code='99')
        excluded = [self.generic_source(name='foreign', account='other-account'),
                    self.generic_source(name='unrelated', reference='OTHER-REFERENCE'),
                    self.generic_source(name='partial', ids=('1-101', '1-102'))]
        malformed_path, malformed = self.generic_source(name='malformed')
        malformed['result']['data']['ids'].append({'docid': None})
        save(malformed_path, malformed)
        excluded.append((malformed_path, malformed))
        lost_path, lost = self.generic_source(name='lost-order', operation='invoice_order', status='outcome_unknown')
        lost['result'] = {'status': {'code': 200}}
        save(lost_path, lost)
        excluded.append((lost_path, lost))
        self.assertEqual(self.reconcile(self.row())['status'], 'canceled')
        for path, original in excluded:
            with self.subTest(source=path.name):
                self.assertEqual(json.loads(path.read_text()), original)

    def test_split_generic_primary_receipt_makes_exact_cancel_target_unambiguous(self):
        self.http.add('1-101')
        self.http.add('1-102')
        path, original = self.generic_source(ids=('1-101', '1-102'))
        self.assertEqual(self.preflight()['target_ids'], ['1-101', '1-102'])
        for body in self.http.bodies.values():
            body['invStatus'] = 'Отменён'
        self.assertEqual(self.reconcile(self.row(ids=('1-101', '1-102')))['status'], 'canceled')
        saved = json.loads(path.read_text())
        self.assertEqual(saved['status'], 'canceled')
        self.assertEqual(saved['result']['data'], original['result']['data'])

    def test_generic_primary_and_confirmation_own_status_can_resolve_cancellation(self):
        self.http.add(status='Отменён', code='99')
        for function in ('P', 'A'):
            with self.subTest(function=function):
                path, original = self.generic_source(function, name='own-' + function)
                updates = self.reconcile(original)
                self.assertEqual(updates['status'], 'canceled')
                self.assertTrue(updates['result']['reconciliation']['document_cancellation_verified'])
                self.assertFalse(updates['result']['reconciliation']['original_operation_completion_verified'])
                # Model confirmed_write's subsequent save of its in-memory row.
                save(path, {**original, **updates})
                saved = json.loads(path.read_text())
                self.assertEqual(saved['recovery']['canceled_document_ids'], ['1-101'])
                self.assertEqual(saved['result']['data'], original['result']['data'])

    def test_incomplete_generic_confirmation_cannot_resolve_itself_as_canceled(self):
        self.http.add(status='Отменён', code='99')
        _, row = self.generic_source('A')
        row['result']['data']['ids'].append({'docid': None})
        result = self.reconcile(row)
        self.assertNotEqual(result['status'], 'canceled')

    def test_generic_primary_replace_then_cancel_uses_children_preserves_provider_receipt(self):
        self.http.add('1-101', status='Расторгнут', code='99')
        self.http.add('1-102')
        self.http.add('1-103')
        path, original = self.generic_source()
        replacement = self.row('C', returned=('1-102', '1-103'))
        self.assertEqual(self.reconcile(replacement)['status'], 'replaced')
        saved = json.loads(path.read_text())
        self.assertEqual(saved['status'], 'replaced')
        self.assertEqual(saved['result']['data'], original['result']['data'])
        self.assertEqual(self.preflight()['target_ids'], ['1-102', '1-103'])
        # Re-reading the old P must not interpret canceled ancestors as the
        # current replacement's cancellation, even before C is saved terminal.
        self.assertNotEqual(self.reconcile(saved)['status'], 'canceled')
        self.reconcile(self.row('D', ids=('1-101',)))
        self.assertEqual(json.loads(path.read_text()), saved)
        for ident in ('1-102', '1-103'):
            self.http.bodies[ident]['invStatus'] = 'Отменен'
        self.assertEqual(self.reconcile(self.row('D', ids=('1-102', '1-103')))['status'], 'canceled')
        done = json.loads(path.read_text())
        self.assertEqual(done['status'], 'canceled')
        self.assertEqual(done['result']['data'], original['result']['data'])
        self.assertEqual(done['recovery']['canceled_document_ids'], ['1-102', '1-103'])
        self.assertEqual(done['recovery_history'][0]['replacement_document_ids'], ['1-102', '1-103'])
        self.assertEqual(self.preflight()['target_ids'], ['1-102', '1-103'])

    def test_checkout_known_specification_and_cancel_are_read_only(self):
        _, row = self.source()
        web = WebFixture(self.http)
        for status, code, expected in (('Спецификация', '01', 'specification'),
                                       ('Отменён', '99', 'canceled')):
            with self.subTest(status=status):
                self.http.listed.clear()
                self.http.add(status=status, code=code)
                result = etm_lifecycle.reconcile_checkout(row, self.config,
                                                          checkout=SimpleNamespace(client=web))
                self.assertEqual(result['status'], expected)
                self.assertFalse(result['final_order_verified'])
                self.assertFalse(result['ready_for_pickup'])
                self.assertEqual(result['document_cancellation_verified'], expected == 'canceled')
        self.assertTrue(all(method in ('login', 'GET') for method, _ in web.calls))

    def test_checkout_attempted_reserve_remains_uncertain_even_if_body_is_specification(self):
        self.http.add()
        _, row = self.source()
        row['receipt']['order_attempted_ids'] = ['1-101']
        result = etm_lifecycle.reconcile_checkout(row, self.config,
            checkout=SimpleNamespace(client=WebFixture(self.http)))
        self.assertIsNone(result)

    def test_checkout_reconciliation_rejects_other_client(self):
        self.http.add(client='456')
        _, row = self.source()
        with self.assertRaisesRegex(Failure, 'etm_lifecycle_document_identity_mismatch'):
            etm_lifecycle.reconcile_checkout(row, self.config,
                checkout=SimpleNamespace(client=WebFixture(self.http)))

    def test_confirmation_cannot_switch_to_different_target(self):
        self.http.add()
        original = self.preflight()
        for field, changed in (('target_ids', ['1-999']), ('client_code', '456'),
                               ('order_number', 'OTHER-REFERENCE'), ('function', 'C')):
            with self.subTest(field=field), self.assertRaisesRegex(Failure, 'etm_lifecycle_target_changed'):
                etm_lifecycle.assert_same_target(original, {**deepcopy(original), field: changed})

    def managed_cancel_fixture(self):
        draft = '12345678-1234-4234-8234-123456789abc'
        reference = 'AI-' + draft.replace('-', '').upper()
        self.http.reference = reference
        self.http.add('1-101', reference=reference, listed=False)
        self.http.add('1-102', reference=reference)
        path, source = self.source(name=draft, reference=reference)
        params = self.params()
        params['body']['OrderNumber'] = reference
        return path, source, params

    def managed_preflight(self, params):
        return etm_lifecycle.preflight('invoice_create', params, self.config, http=self.http, vault=self.vault)

    def test_managed_reference_discovery_retains_both_unpaid_specifications(self):
        path, source, params = self.managed_cancel_fixture()
        self.http.bodies['1-102']['invsum'] = '100.79'
        self.http.bodies['1-102']['rows'][0]['cnt'] = '10.000'
        target = self.managed_preflight(params)
        self.assertEqual(target['target_ids'], ['1-101', '1-102'])
        self.assertEqual(target['discovered_document_ids'], ['1-102'])
        self.assertIn('neither is assumed superseded', target['identity_resolution'])
        self.assertTrue(target['all_targets_specifications'])
        self.assertFalse(target['already_complete'])
        self.assertEqual(json.loads(path.read_text()), source)

    def test_managed_discovery_rejects_changed_body_identity_items_payment_or_status(self):
        _, _, params = self.managed_cancel_fixture()
        original = deepcopy(self.http.bodies['1-102'])
        changes = [('cli_code', '456'), ('invnum', 'OTHER-REFERENCE'),
                   ('paysum', '0.01'), ('paysum', None), ('invStatus', 'В подборе'),
                   ('rows', [{'gdscode': '1001', 'cnt': '11'}]),
                   ('rows', [{'gdscode': '1002', 'cnt': '10'}]),
                   ('rows', [{'gdscode': '1001', 'cnt': 'NaN'}])]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                self.http.bodies['1-102'] = {**deepcopy(original), key: value}
                with self.assertRaisesRegex(Failure, 'ambiguous'):
                    self.managed_preflight(params)
        self.http.bodies['1-102'] = original
        self.http.listed[0]['operations']['cancel'] = False
        with self.assertRaisesRegex(Failure, 'ambiguous'):
            self.managed_preflight(params)

    def test_managed_discovery_rejects_unknown_incomplete_or_attempted_source(self):
        path, source, params = self.managed_cancel_fixture()
        for field, value in (('all_returned_ids_valid', False), ('order_attempted_ids', ['1-101']),
                             ('order_attempted_ids', None), ('document_ids', ['1-101', '1-103'])):
            with self.subTest(field=field):
                changed = deepcopy(source)
                changed['receipt'][field] = value
                save(path, changed)
                with self.assertRaises(Failure):
                    self.managed_preflight(params)
        save(path, source)
        self.http.add('1-103', reference=self.http.reference)
        with self.assertRaisesRegex(Failure, 'ambiguous'):
            self.managed_preflight(params)

    def test_managed_discovery_does_not_extend_manual_references_or_other_actions(self):
        path, source, params = self.managed_cancel_fixture()
        for function in ('A', 'C'):
            with self.subTest(function=function):
                changed = deepcopy(params)
                changed['body']['DocumentFunctionCode'] = function
                with self.assertRaisesRegex(Failure, 'ambiguous'):
                    self.managed_preflight(changed)
        # A matching arbitrary customer number is not proof of our UUID scheme.
        source['draft_id'] = '87654321-1234-4234-8234-123456789abc'
        save(path, source)
        with self.assertRaisesRegex(Failure, 'ambiguous'):
            self.managed_preflight(params)

    def test_managed_discovery_never_releases_original_after_only_one_cancellation(self):
        path, source, params = self.managed_cancel_fixture()
        target = self.managed_preflight(params)
        row = self.row(ids=tuple(target['target_ids']))
        row['params'] = params
        row['lifecycle'] = target
        self.http.bodies['1-101']['invStatus'] = 'Отменен'
        result = self.reconcile(row)
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertEqual(json.loads(path.read_text()), source)
        self.http.bodies['1-102']['invStatus'] = 'Отменен'
        result = self.reconcile(row)
        self.assertEqual(result['status'], 'canceled')
        self.assertEqual({doc['id'] for doc in result['result']['documents']}, {'1-101', '1-102'})
        recovered = json.loads(path.read_text())
        self.assertEqual(recovered['receipt'], source['receipt'])
        self.assertEqual(recovered['status'], 'canceled')

    def test_partial_external_cancellation_keeps_discovered_target_recoverable(self):
        _, _, params = self.managed_cancel_fixture()
        self.http.bodies['1-101']['invStatus'] = 'Отменен'
        target = self.managed_preflight(params)
        self.assertEqual(target['target_ids'], ['1-101', '1-102'])
        self.assertFalse(target['all_targets_specifications'])
        self.assertFalse(target['already_complete'])

    def test_original_checkout_status_cannot_ignore_active_discovered_sibling(self):
        _, source, _ = self.managed_cancel_fixture()
        self.http.bodies['1-101']['invStatus'] = 'Отменен'
        checkout = SimpleNamespace(client=WebFixture(self.http))
        result = etm_lifecycle.reconcile_checkout(source, self.config, checkout=checkout)
        self.assertIsNone(result)
        self.http.bodies['1-102']['invStatus'] = 'Отменен'
        result = etm_lifecycle.reconcile_checkout(source, self.config, checkout=checkout)
        self.assertEqual(result['status'], 'canceled')
        self.assertEqual({doc['id'] for doc in result['documents']}, {'1-101', '1-102'})

    def test_managed_discovery_rejects_existing_replacement_family(self):
        path, source, params = self.managed_cancel_fixture()
        source['recovery_history'] = [{'canceled_document_ids': ['1-99']}]
        save(path, source)
        with self.assertRaisesRegex(Failure, 'ambiguous'):
            self.managed_preflight(params)


if __name__ == '__main__':
    unittest.main()
