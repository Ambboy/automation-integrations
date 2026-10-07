"""The public route uses explicit skl and verifies every mutation without replay."""
from copy import deepcopy
import json
import unittest

from automation_integrations.api_read import Failure
from automation_integrations.etm_order import Checkout
from automation_integrations.etm_public_order import PublicCheckout


ENTITY = {'clicode': '123', 'cliName': 'Fixture LLC',
          'inn_org': '1234567890', 'kpp_org': '123456789'}
CONTRACT = {'id': '000120240101000001', 'name': 'TEST/REGION/0001-2024'}
PARAMS = {'items': [{'code': '1001', 'quantity': '100'}], 'region': '61',
          'pickup_store': '25140', 'contract_id': CONTRACT['id'], 'payment_method': 'bill',
          'pay_type': 'bill', 'currency': 'RUB', 'note': '', 'allow_supplier_order': False,
          'continuous_cut': False, 'customer_order_number': 'GR-FIXTURE-1234'}


class VaultFixture:
    def __init__(self):
        self.sensitive = ['fixture-login', 'fixture-password']

    def get(self, service):
        if service != 'etm':
            raise AssertionError(service)
        return {'ETM_LOGIN': 'fixture-login', 'ETM_PASSWORD': 'fixture-password'}


class WebFixture:
    def __init__(self):
        self.config = {}
        self.vault = VaultFixture()
        self.calls = []
        self.documents = {}
        self.contract_bound = True
        self.profile_contract = {'id': CONTRACT['id'], 'num': CONTRACT['name'], 'from': '08.02.2024'}
        self.preflight_contract = CONTRACT['id']
        self.not_reservable = False
        self.preflight_physical = True
        self.preflight_bad_quantity = False
        self.preflight_bad_price = False
        self.late_second_price = False
        self.bad_final_destination = False
        self.bad_price = False
        self.duplicate_body_rows = False

    def login(self, region):
        if region != '61':
            raise AssertionError(region)
        return deepcopy(ENTITY)

    def call(self, method, path, *, query=None, form=None):
        self.calls.append((method, path, deepcopy(query), deepcopy(form)))
        if method != 'GET':
            raise AssertionError('Public checkout must not write through the website or basket')
        if path == '/user/profile':
            return {'contracts': [deepcopy(self.profile_contract)]}
        if path == '/info/city/61':
            return {'name': 'Ростов-на-Дону', 'class17': 'ЮГРСТ', 'rows': [
                {'id': '25140', 'address': 'г. Батайск, ул. Куйбышева, д.141',
                 'available_pick': True, 'time': 'Пн.-Пт.8-18'}]}
        if path == '/basket/functionality':
            return {'contract': {'available': True, 'sendKey': 'i_dogovor',
                'defaultValue': CONTRACT['id'], 'value': [{'code': CONTRACT['id'], 'name': CONTRACT['name']}]},
                'ps': {'available': True, 'sendKey': 'tovzak'}}
        if path == '/payment/methods':
            return {'rows': [{'pay_meth': [{'payment_method_code': 'bill', 'paytype': 'bill',
                'payment_method_status': True, 'payment_method_name': 'Счет по договору',
                'payment_method_text': 'По действующему договору'}]}]}
        if path == '/goods/1001':
            return {'gdsCode': '1001', 'gdsNameTitle': 'Fixture cable', 'gdsUnitName': 'м',
                    'gdsInfoPacks': '100 м', 'gdsCommonAvail': 'По запросу'}
        if path == '/goods/1001/price':
            return {'rows': [{'gdscode': '1001', 'pricewnds': '12.34'}]}
        if path == '/goods/1001/packs':
            return {'packRestrictShipRate': {'packMinPartSuppl': '1000'}}
        if path == '/invoice':
            ident = query['usr-inv-num'].removeprefix('302/')
            doc = self.documents[ident]
            return {'rows': [{'id': ident, 'st_code': '46', 'st_dest': doc['destination'],
                'status_code': '24' if doc['ordered'] else '01',
                'pay_title': 'По договору ' + CONTRACT['name'] if self.contract_bound else '',
                'pay_date': '2026-11-01' if self.contract_bound else ''}]}
        if path.startswith('/invoice/'):
            ident, action = path.split('/')[2:]
            doc = self.documents[ident]
            if action == 'body':
                quantities = [60, 40] if self.duplicate_body_rows else [doc['quantity']]
                return {'invnetnum': ident, 'invnum': '302/' + ident, 'cli_code': ENTITY['clicode'],
                    'buyer': {'inn': ENTITY['inn_org'], 'kpp': ENTITY['kpp_org']}, 'store': '46',
                    'invStatus': 'В подборе' if doc['ordered'] else 'Спецификация', 'records': len(quantities),
                    'invsum': str(doc['quantity'] * (99 if self.bad_price else 12.34)),
                    'rows': [{'gdscode': '1001', 'cnt': str(quantity), 'gdsname': 'Fixture cable'}
                             for quantity in quantities]}
            if action == 'order':
                row = {'gdscode': '1001', 'cnt': str(doc['quantity'] + (1 if self.preflight_bad_quantity else 0)),
                       'g-net': '1' if self.preflight_physical else '0',
                       'g-num': '42' if self.preflight_physical else '0'}
                changed_price = self.preflight_bad_price or (self.late_second_price and ident == '1-102'
                    and self.documents['1-101']['ordered'])
                return {'i_dogovor': self.preflight_contract if self.contract_bound else 'основной',
                    'qpay': 'bill', 'qop': '29100',
                    'invStoreSum': str(doc['quantity'] * (99 if changed_price else 12.34)),
                    # The original bug: a portal-only office list cannot veto public skl.
                    'stores': [{'code': '29100', 'selected': 0,
                                'pickupAvailable': {'availability': True}}],
                    'can-reserve': {'rows': [] if self.not_reservable else [row]},
                    'not-reserve': {'rows': [row] if self.not_reservable else []}}
            if action == 'ps':
                return {'comments': [{'text': doc['remarks']}]}
        raise AssertionError((method, path))


class PublicFixture:
    def __init__(self, web):
        self.web = web
        self.calls = []
        self.split = False
        self.create_unknown = False
        self.order_unknown = False
        self.unknown_order_id = None
        self.create_already_ordered = False
        self.extra_bad_id = False
        self.reserve_split = False

    def call(self, method, path, *, query=None, body=None, **_kwargs):
        self.calls.append((method, path, deepcopy(query), deepcopy(body)))
        if (method, path) == ('POST', '/user/login'):
            return {'status': {'code': 200}, 'data': {'session': 'public-session-secret'}}
        if query.get('session-id') != 'public-session-secret':
            raise AssertionError('Public requests must use the authenticated public session')
        if path == '/invoice/create':
            if self.create_unknown:
                raise Failure('etm_proxy_request_failed')
            quantities = [60, 40] if self.split else [100]
            for index, quantity in enumerate(quantities, 101):
                self.web.documents['1-' + str(index)] = {'quantity': quantity,
                    'ordered': self.create_already_ordered,
                    'destination': '25140' if self.create_already_ordered else '29100',
                    'remarks': body['Remarks']}
            rows = [{'docid': ident} for ident in self.web.documents]
            if self.extra_bad_id:
                rows.append({'docid': None})
            return {'status': {'code': 200}, 'data': {'id': '1-101', 'ids': rows}}
        ident = path.split('/')[2]
        if path != '/invoice/' + ident + '/order' or query.get('skl') != '25140':
            raise AssertionError((method, path, query))
        self.web.documents[ident].update(ordered=True,
            destination='29100' if self.web.bad_final_destination else query['skl'])
        if self.order_unknown or self.unknown_order_id == ident:
            raise Failure('etm_proxy_request_failed')
        if self.reserve_split:
            self.web.documents[ident]['quantity'] = 60
            self.web.documents['1-102'] = {**deepcopy(self.web.documents[ident]), 'quantity': 40}
            return {'status': {'code': 200}, 'data': {'ids': [{'docid': ident}, {'docid': '1-102'}]}}
        return {'code': 200, 'message': ''}


class PublicCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.web = WebFixture()
        self.portal = Checkout(self.web, sleeper=lambda _: None)
        self.http = PublicFixture(self.web)
        self.checkout = PublicCheckout(self.web, self.portal, http=self.http)
        self.stages = []

    def prepare(self, **overrides):
        params = {**deepcopy(PARAMS), **overrides}
        contract, fields = self.portal._features(params)
        return self.checkout.prepare(params, ENTITY, contract, fields, {'rows': []})

    def execute(self, prepared):
        return self.checkout.execute(prepared,
            on_stage=lambda stage, details: self.stages.append((stage, deepcopy(details))))

    def orders(self):
        return [c for c in self.http.calls if c[1].endswith('/order')]

    def test_prepare_is_read_only_uses_real_contract_number_and_customer_reference(self):
        prepared = self.prepare()
        self.assertEqual(self.http.calls, [])
        self.assertTrue(all(c[0] == 'GET' for c in self.web.calls))
        self.assertEqual(prepared['route'], 'public_api')
        body = prepared['create_body']
        self.assertEqual(body['OrderNumber'], PARAMS['customer_order_number'])
        self.assertEqual(body['ContractNumber'], CONTRACT['name'])
        self.assertEqual(body['ContractDate'], '2024-02-08')
        self.assertNotEqual(body['ContractNumber'], CONTRACT['id'])
        self.assertNotIn('DeliveryPoint', body)
        self.assertIn('Только из складского наличия', body['Remarks'])
        self.assertEqual(body['Seller'], {'ILN': '4660011519999'})
        self.assertEqual(body['Order-Lines'][0]['OrderedQuantity'], '100')
        self.assertIn('Customer system reference', prepared['preview']['customer_order_number_kind'])
        self.assertFalse(prepared['preview']['items'][0]['availability_is_allocation'])

    def test_public_order_can_select_bataysk_despite_portal_only_offering_volgograd(self):
        result = self.execute(self.prepare())
        self.assertEqual(result['status'], 'verified')
        self.assertTrue(result['document_created'])
        self.assertTrue(result['reservation_request_sent'])
        self.assertTrue(result['final_order_verified'])
        self.assertEqual(result['documents'][0]['pickup_store'], '25140')
        self.assertEqual(len(self.orders()), 1)
        self.assertEqual(self.orders()[0][2]['skl'], '25140')
        self.assertFalse(any(c[0] != 'GET' for c in self.web.calls))
        self.assertEqual(self.stages[0][0], 'checkout_submitting')
        self.assertEqual(self.stages[1][0], 'checkout_accepted')
        self.assertEqual(self.stages[1][1]['created_document_ids'], ['1-101'])

    def test_unbound_contract_stops_after_creation_before_reservation(self):
        self.web.contract_bound = False
        result = self.execute(self.prepare())
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('1-101:contract_mismatch_in_preflight', result['verification_problems'])
        self.assertTrue(result['document_created'])
        self.assertFalse(result['reservation_request_sent'])
        self.assertEqual(self.orders(), [])

    def test_all_split_documents_are_preflighted_reserved_and_verified(self):
        self.http.split = True
        result = self.execute(self.prepare(note='Не заменять'))
        self.assertEqual(result['status'], 'verified')
        self.assertEqual([c[1] for c in self.orders()], ['/invoice/1-101/order', '/invoice/1-102/order'])
        self.assertEqual([d['id'] for d in result['documents']], ['1-101', '1-102'])
        self.assertEqual(result['total_vat'], '1234.00')
        self.assertEqual(result['receipt']['created_document_ids'], ['1-101', '1-102'])
        self.assertEqual(result['receipt']['ordered_document_ids'], ['1-101', '1-102'])

    def test_additional_documents_returned_by_reservation_are_recorded_and_read(self):
        self.http.reserve_split = True
        result = self.execute(self.prepare())
        self.assertEqual(result['status'], 'verified')
        self.assertEqual([d['id'] for d in result['documents']], ['1-101', '1-102'])
        self.assertEqual(result['receipt']['document_ids'], ['1-101', '1-102'])
        self.assertEqual(result['receipt']['created_document_ids'], ['1-101'])
        self.assertEqual(len(self.orders()), 1)
        last_receipt = next(data for stage, data in reversed(self.stages) if stage == 'checkout_accepted')
        self.assertEqual(last_receipt['document_ids'], ['1-101', '1-102'])

    def test_unknown_creation_is_never_retried(self):
        self.http.create_unknown = True
        prepared = self.prepare()
        with self.assertRaisesRegex(Failure, '^etm_proxy_request_failed$'):
            self.execute(prepared)
        with self.assertRaisesRegex(Failure, '^etm_public_checkout_already_submitted$'):
            self.execute(prepared)
        self.assertEqual(sum(c[1] == '/invoice/create' for c in self.http.calls), 1)
        self.assertEqual([stage for stage, _ in self.stages], ['checkout_submitting'])

    def test_unknown_reservation_keeps_receipt_and_reconciles_without_post(self):
        self.http.order_unknown = True
        prepared = self.prepare()
        with self.assertRaisesRegex(Failure, '^etm_proxy_request_failed$'):
            self.execute(prepared)
        receipt = next(data for stage, data in reversed(self.stages) if stage == 'checkout_accepted')
        self.assertEqual(receipt['order_attempted_ids'], ['1-101'])
        self.assertEqual(receipt['created_document_ids'], ['1-101'])
        calls = len(self.http.calls)
        result = self.checkout.reconcile(prepared, receipt)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(len(self.http.calls), calls)
        self.assertEqual(len(self.orders()), 1)

    def test_second_split_price_is_rechecked_after_first_reservation(self):
        self.http.split = True
        self.web.late_second_price = True
        result = self.execute(self.prepare())
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertEqual([c[1] for c in self.orders()], ['/invoice/1-101/order'])
        self.assertIn('1-102:document_price_changed_in_preflight', result['verification_problems'])
        self.assertEqual([d['status_code'] for d in result['documents']], ['24', '01'])
        self.assertEqual(result['receipt']['ordered_document_ids'], ['1-101'])
        self.assertEqual(result['receipt']['created_document_ids'], ['1-101', '1-102'])

    def test_unknown_second_split_keeps_all_ids_and_never_repeats_first_reservation(self):
        self.http.split = True
        self.http.unknown_order_id = '1-102'
        prepared = self.prepare()
        with self.assertRaisesRegex(Failure, '^etm_proxy_request_failed$'):
            self.execute(prepared)
        receipt = next(data for stage, data in reversed(self.stages) if stage == 'checkout_accepted')
        self.assertEqual(receipt['ordered_document_ids'], ['1-101'])
        self.assertEqual(receipt['order_attempted_ids'], ['1-101', '1-102'])
        self.assertEqual(receipt['created_document_ids'], ['1-101', '1-102'])
        result = self.checkout.reconcile(prepared, receipt)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual([c[1] for c in self.orders()], ['/invoice/1-101/order', '/invoice/1-102/order'])

    def test_created_accepted_order_is_verified_without_preflight_or_second_reservation(self):
        self.http.create_already_ordered = True
        result = self.execute(self.prepare(allow_supplier_order=True))
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(self.orders(), [])
        self.assertFalse(any(c[1].endswith('/order') for c in self.web.calls))
        self.assertFalse(result['reservation_request_sent'])

    def test_autoaccepted_stock_only_order_without_allocation_proof_is_not_verified(self):
        self.http.create_already_ordered = True
        result = self.execute(self.prepare())
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('1-101:physical_allocation_unverified_for_created_order', result['verification_problems'])
        self.assertEqual(self.orders(), [])
        self.assertFalse(any(c[1].endswith('/order') for c in self.web.calls))

    def test_autoaccepted_continuous_cut_without_allocation_proof_is_not_verified(self):
        self.http.create_already_ordered = True
        result = self.execute(self.prepare(allow_supplier_order=True, continuous_cut=True))
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('1-101:physical_allocation_unverified_for_created_order', result['verification_problems'])
        self.assertEqual(self.orders(), [])

    def test_unallocated_prepaid_document_is_not_reserved(self):
        self.web.not_reservable = True
        result = self.execute(self.prepare(allow_supplier_order=True))
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('1-101:document_allocation_unverified', result['verification_problems'])
        self.assertEqual(self.orders(), [])

    def test_stock_only_requires_physical_allocation(self):
        self.web.preflight_physical = False
        result = self.execute(self.prepare())
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('1-101:document_physical_allocation_unverified', result['verification_problems'])
        self.assertEqual(self.orders(), [])

    def test_explicit_preflight_contract_mismatch_overrides_earlier_document_binding(self):
        self.web.preflight_contract = '999999999'
        result = self.execute(self.prepare())
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('1-101:contract_mismatch_in_preflight', result['verification_problems'])
        self.assertEqual(self.orders(), [])

    def test_price_change_in_latest_preflight_stops_before_reservation(self):
        self.web.preflight_bad_price = True
        result = self.execute(self.prepare())
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('1-101:document_price_changed_in_preflight', result['verification_problems'])
        self.assertEqual(self.orders(), [])

    def test_requested_continuous_cut_cannot_be_split_between_documents(self):
        self.http.split = True
        result = self.execute(self.prepare(continuous_cut=True))
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('continuous_cut_split_across_document_rows', result['verification_problems'])
        self.assertEqual(self.orders(), [])

    def test_ordinary_duplicate_product_rows_are_aggregated_for_preflight(self):
        self.web.duplicate_body_rows = True
        result = self.execute(self.prepare())
        self.assertEqual(result['status'], 'verified')
        self.assertEqual([row['quantity'] for row in result['documents'][0]['items']], ['60', '40'])
        self.assertEqual(len(self.orders()), 1)

    def test_invalid_returned_id_keeps_valid_receipt_but_never_reserves(self):
        self.http.extra_bad_id = True
        result = self.execute(self.prepare())
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertEqual(result['receipt']['created_document_ids'], ['1-101'])
        self.assertIn('final_document_ids_incomplete', result['verification_problems'])
        self.assertEqual(self.orders(), [])

    def test_final_destination_must_be_verified_even_after_public_success(self):
        self.web.bad_final_destination = True
        result = self.execute(self.prepare())
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('1-101:pickup_store_mismatch', result['verification_problems'])
        self.assertEqual(len(self.orders()), 1)

    def test_wrong_contract_profile_prevents_even_public_authentication(self):
        self.web.profile_contract['num'] = 'OTHER-CONTRACT'
        with self.assertRaisesRegex(Failure, '^etm_public_contract_unverified$'):
            self.prepare()
        self.assertEqual(self.http.calls, [])

    def test_result_and_durable_stages_do_not_include_credentials_or_public_session(self):
        result = self.execute(self.prepare())
        visible = json.dumps([result, self.stages], ensure_ascii=False) + repr(self.checkout)
        for secret in ('fixture-login', 'fixture-password', 'public-session-secret'):
            self.assertNotIn(secret, visible)
        self.assertIn('public-session-secret', self.web.vault.sensitive)


if __name__ == '__main__':
    unittest.main()
