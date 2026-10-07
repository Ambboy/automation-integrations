"""Independent business regressions for ETM allocation and split-document readback."""
from copy import deepcopy
import unittest

from automation_integrations.api_read import Failure
from automation_integrations.etm_order import Checkout, validate_params


class SplitDocuments:
    def __init__(self):
        self.identity = {'clicode': '5', 'inn_org': '6', 'kpp_org': '7'}
        self.calls = []
        self.bodies, self.listings, self.comments = {}, {}, {}
        for index, (quantity, amount) in enumerate(((40, '525.60'), (60, '788.40')), 1):
            ident = f'46-{index}'
            self.bodies[ident] = {
                'invnum': f'302/fixture-{index}', 'invnetnum': ident, 'cli_code': '5',
                'buyer': {'inn': '6', 'kpp': '7'}, 'store': 46, 'invStatus': 'В сборке',
                'rows': [{'gdscode': '6510970', 'cnt': quantity}], 'records': 1, 'invsum': amount,
            }
            self.listings[ident] = {'id': ident, 'st_code': 46, 'st_dest': '29100',
                'pay_title': 'Оплата по договору fixture', 'pay_date': '2026-10-06', 'status_code': '15'}
            self.comments[ident] = [{'text': 'Не заменять товар'}]

    def login(self, _region):
        return deepcopy(self.identity)

    def call(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if method != 'GET':
            raise AssertionError('Reconciliation must not mutate the provider')
        if path == '/invoice':
            number = kwargs['query']['usr-inv-num']
            ident = next(key for key, body in self.bodies.items() if body['invnum'] == number)
            return {'rows': [deepcopy(self.listings[ident])]}
        _, _, ident, kind = path.split('/')
        if kind == 'body':
            return deepcopy(self.bodies[ident])
        if kind == 'ps':
            return {'comments': deepcopy(self.comments[ident])}
        raise AssertionError('Unexpected fixture route')


class ETMCheckoutReviewTests(unittest.TestCase):
    def setUp(self):
        self.client = SplitDocuments()
        self.checkout = Checkout(self.client)
        self.params = validate_params({'items': [{'code': '6510970', 'quantity': 100}],
            'region': '34', 'pickup_store': '29100', 'contract_id': '123', 'max_total': 2000})
        self.prepared = {'params': self.params, 'preview': {'legal_entity': deepcopy(self.client.identity),
            'contract': {'name': 'договору fixture'}, 'pickup': {'code': '29100'}}}
        self.receipt = {'document_ids': ['46-1', '46-2'], 'all_returned_ids_valid': True,
            'i_dogovor': '123', 'expected_total_vat': '1314.00', 'note': 'Не заменять товар'}

    def reconcile(self):
        return self.checkout.reconcile(self.prepared, self.receipt)

    def test_split_stock_transfer_verifies_destination_and_every_document(self):
        result = self.reconcile()
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['total_vat'], '1314.00')
        self.assertFalse(result['ready_for_pickup'])
        self.assertEqual(len(result['documents']), 2)
        self.assertEqual([d['pickup_store'] for d in result['documents']], ['29100', '29100'])
        self.assertEqual([d['current_store'] for d in result['documents']], [46, 46])
        self.assertTrue(all(method == 'GET' for method, _, _ in self.client.calls))

    def test_matching_source_does_not_verify_wrong_destination(self):
        self.client.bodies['46-2']['store'] = 29100
        self.client.listings['46-2'].update(st_code=29100, st_dest='25140')
        result = self.reconcile()
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertIn('46-2:pickup_store_mismatch', result['verification_problems'])

    def test_null_unknown_and_rejected_status_never_become_verified(self):
        for status in (None, '', '999', False, '101'):
            with self.subTest(status=status):
                self.client.listings['46-2']['status_code'] = status
                self.assertEqual(self.reconcile()['status'], 'accepted_unverified')

    def test_note_words_in_contradictory_or_separate_comments_do_not_match(self):
        for comments in ([{'text': 'Можно заменять товар. Не готово.'}],
                         [{'text': 'Не'}, {'text': 'заменять товар'}]):
            with self.subTest(comments=comments):
                self.client.comments['46-2'] = comments
                self.assertIn('46-2:order_note_unverified', self.reconcile()['verification_problems'])
        self.client.comments['46-2'] = [{'text': 'НЕ заменять — товар.'}]
        self.assertEqual(self.reconcile()['status'], 'verified')

    def test_each_split_document_requires_contract_payment_terms(self):
        self.client.listings['46-2']['pay_date'] = ''
        self.assertIn('46-2:contract_payment_terms_unverified', self.reconcile()['verification_problems'])
        self.client.listings['46-2']['pay_date'] = '2026-10-06'
        self.client.listings['46-2']['pay_title'] = 'Предоплата'
        self.assertIn('46-2:contract_payment_terms_unverified', self.reconcile()['verification_problems'])

    def test_split_quantities_cannot_hide_missing_or_extra_items(self):
        self.client.bodies['46-2']['rows'][0]['cnt'] = 59
        self.assertIn('final_quantities_mismatch', self.reconcile()['verification_problems'])
        self.client.bodies['46-2']['rows'][0].update(gdscode='9999999', cnt=60)
        self.assertIn('final_quantities_mismatch', self.reconcile()['verification_problems'])

    def test_changed_entity_is_rejected_before_document_reads(self):
        self.client.identity['clicode'] = '999'
        with self.assertRaisesRegex(Failure, '^etm_legal_entity_changed$'):
            self.reconcile()
        self.assertEqual(self.client.calls, [])

    def basket(self, network, lot):
        return {'rows': [{'nn': 1, 'gdscode': '6510970', 'cnt': 100, 'selected': True,
            'delivery_parts': [{'cnt': 100, 'g-net': network, 'g-num': lot, 'PartNum': 'fixture-drum'}]}],
            'sum': '1314.00', 'stores': [{'code': '29100', 'selected': True, 'address': 'fixture',
                                        'pickupAvailable': {'availability': True}}]}

    def test_stock_only_requires_valid_physical_lot_identifiers(self):
        for value in (None, '', 0, 0.0, '0.0', '0', False, 'unknown'):
            for network, lot in ((value, value), ('46', value), (value, '12')):
                with self.subTest(network=network, lot=lot):
                    with self.assertRaisesRegex(Failure, '^etm_supplier_order_not_authorized$'):
                        self.checkout._check_orderable(self.basket(network, lot), self.params)
        self.checkout._check_orderable(self.basket('46', '12'), self.params)

    def test_supplier_permission_does_not_prove_continuous_physical_cut(self):
        params = {**self.params, 'allow_supplier_order': True}
        self.checkout._check_orderable(self.basket(0, 0), params)
        params['continuous_cut'] = True
        with self.assertRaisesRegex(Failure, '^etm_continuous_cut_unverified$'):
            self.checkout._check_orderable(self.basket(0, 0), params)
        self.checkout._check_orderable(self.basket('46', '12'), params)
        basket = self.basket('46', '12')
        basket['rows'][0]['delivery_parts'][0].pop('PartNum')
        self.checkout._check_orderable(basket, params)
        basket['rows'][0]['delivery_parts'][0]['PartNum'] = ''
        self.checkout._check_orderable(basket, params)
        basket['rows'][0]['delivery_parts'] = [
            {'cnt': 40, 'g-net': '46', 'g-num': '12', 'PartNum': ''},
            {'cnt': 60, 'g-net': '46', 'g-num': '13', 'PartNum': ''}]
        with self.assertRaisesRegex(Failure, '^etm_continuous_cut_unavailable$'):
            self.checkout._check_orderable(basket, params)


if __name__ == '__main__':
    unittest.main()
