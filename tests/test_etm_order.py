from copy import deepcopy
import json
import subprocess
from unittest import TestCase, main
from unittest.mock import patch

from automation_integrations.api_read import Failure
from automation_integrations.etm_order import Checkout, WebsiteClient, validate_params, validate_options, _multipart


PARAMS = {'items': [{'code': '1001', 'quantity': 100}], 'region': '34', 'pickup_store': '29100'}
ENTITY = {'clicode': '123', 'cliName': 'Fixture LLC', 'inn_org': '1234567890', 'kpp_org': '123456789'}
STORE = {'code': '29100', 'name': 'Office fixture', 'address': 'Fixture, Main Street 1',
         'time': '09-18', 'selected': 1, 'pickupAvailable': {'availability': True}}


class FakeWebsite:
    def __init__(self):
        self.calls = []
        self.rows = []
        self.payment_active = True
        self.contract_id = '555'
        self.identity = deepcopy(ENTITY)
        self.receipt = {'createdDoc': [{'invnum': '1-101'}, {'invnum': '1-102'}],
                        'i_dogovor': '555', 'pay_sum': '1234.00'}
        self.bad_store = False
        self.bad_parts = False
        self.checkout_error = None
        self.round_up = False
        self.add_selected = True
        self.ignore_selection = False
        self.selection_error = None
        self.note = ''
        self.statuses = {'1-101': '24', '1-102': '20'}
        self.docs = {'1-101': '60', '1-102': '40'}
        self.shipping_reads = 0
        self.change_on_final_read = False

    def login(self, region):
        self.calls.append(('LOGIN', region))
        return deepcopy(self.identity)

    def basket(self):
        rows = deepcopy(self.rows)
        self.shipping_reads += bool(rows)
        if self.bad_parts:
            for row in rows:
                row['delivery_parts'] = [{'cnt': row['cnt'], 'g-net': None, 'g-num': None}]
        if self.change_on_final_read and self.shipping_reads >= 2:
            rows[0]['delivery_parts'][0]['g-num'] = '999'
        return {'rows': rows, 'records': len(rows), 'stores': [deepcopy(STORE)],
                'cartVersion': 'fixed', 'sum': 12.34 * sum(float(r['cnt']) for r in rows),
                'i_dogovor': '555', 'zapretgo': False}

    def call(self, method, path, *, query=None, form=None):
        self.calls.append((method, path, deepcopy(query), deepcopy(form)))
        if path == '/basket/functionality':
            return {'contract': {'available': True, 'sendKey': 'i_dogovor', 'defaultValue': self.contract_id,
                'value': [{'code': self.contract_id, 'name': 'CONTRACT-FIXTURE'}]},
                'ps': {'available': True, 'sendKey': 'tovzak'}}
        if path == '/basket/order' and method == 'GET':
            return self.basket()
        if path == '/goods/1001':
            return {'gdsCode': '1001', 'gdsNameTitle': 'Fixture white wire', 'gdsUnitName': 'м',
                    'gdsInfoPacks': '100 м', 'gdsCommonAvail': 'На заказ', 'gdsPickup': ''}
        if path == '/goods/1001/price':
            return {'rows': [{'gdscode': 1001, 'pricewnds': 12.34}]}
        if path == '/goods/1001/packs':
            return {'packRestrictShipRate': {'packMinPartSuppl': '1000', 'packPrecision': '1'}}
        if path == '/payment/methods':
            return {'rows': [{'pay_meth': [{'payment_method_code': 'bill', 'paytype': 'bill',
                'payment_method_status': self.payment_active, 'payment_method_name': 'Invoice',
                'payment_method_text': 'By contract'}]}]}
        if path == '/basket/add':
            quantity = '1000' if self.round_up else form['val']
            self.rows.append({'nn': len(self.rows) + 1, 'gdscode': form['gds'], 'cnt': quantity,
                'selected': self.add_selected, 'sum': 12.34 * float(quantity),
                'delivery_parts': [{'cnt': quantity, 'g-net': '1', 'g-num': '101', 'PartNum': '42'}]})
            return {}
        if method == 'POST' and path.startswith('/basket/') and path.endswith('/edit'):
            if self.selection_error:
                raise self.selection_error
            line = path.split('/')[2]
            if not self.ignore_selection:
                next(row for row in self.rows if str(row['nn']) == line)['selected'] = form['selected'] == 'true'
            return {}
        if path == '/basket/order' and method == 'POST':
            if self.checkout_error:
                raise self.checkout_error
            return deepcopy(self.receipt)
        if path.endswith('/ps'):
            if method == 'POST':
                self.note = form['text']
                return {}
            return {'comments': [{'text': self.note}]}
        if path.endswith('/body'):
            ident = path.split('/')[2]
            qty = self.docs[ident]
            return {'invnetnum': ident, 'invnum': '302/' + ident, 'store': 46, 'invStatus': 'В подборе',
                'records': 1, 'cli_code': 123, 'buyer': {'inn': ENTITY['inn_org'], 'kpp': ENTITY['kpp_org']},
                'invsum': float(qty) * 12.34, 'rows': [{'gdscode': '1001', 'cnt': qty}]}
        if path == '/invoice':
            ident = query['usr-inv-num'].split('/')[1]
            return {'rows': [{'id': ident, 'st_code': 46, 'st_dest': 25140 if self.bad_store else 29100,
                'status_code': self.statuses[ident], 'pay_title': 'By CONTRACT-FIXTURE',
                'pay_date': '2026-11-02'}]}
        raise AssertionError((method, path))


class CheckoutTests(TestCase):
    def setUp(self):
        self.web = FakeWebsite()
        self.checkout = Checkout(self.web, sleeper=lambda _: None)
        self.stages = []

    def execute(self, prepared):
        return self.checkout.execute(prepared, on_stage=lambda stage, details: self.stages.append((stage, details)))

    def posted(self, path):
        return [c for c in self.web.calls if c[:2] == ('POST', path)]

    def test_prepare_is_read_only_exact_quote_and_options_hide_basket(self):
        p = self.checkout.prepare(PARAMS)
        self.assertEqual(p['params']['max_total'], '1234.00')
        self.assertEqual(p['preview']['pickup']['address'], STORE['address'])
        self.assertFalse(any(c[0] == 'POST' for c in self.web.calls))
        options = self.checkout.options({'region': '34'})
        self.assertEqual(options['default_contract_id'], '555')
        self.assertEqual(options['pickup_stores'][0]['code'], '29100')
        self.assertNotIn('rows', options)
        self.assertEqual(options['payment_methods'][0]['paytype'], 'bill')

    def test_checkout_posts_one_exact_order_then_verifies_every_split_id(self):
        prepared = self.checkout.prepare({**PARAMS, 'note': 'Белый провод, не заменять'})
        result = self.execute(prepared)
        self.assertEqual(result['status'], 'verified')
        self.assertFalse(result['ready_for_pickup'])
        self.assertEqual(len(result['documents']), 2)
        self.assertEqual(len(self.posted('/basket/order')), 1)
        form = self.posted('/basket/order')[0][3]
        self.assertEqual(form['i_dogovor'], '555')
        self.assertEqual(form['skl'], '29100')
        self.assertEqual(form['payment_method_code'], 'bill')
        self.assertEqual(form['pay-type'], 'bill')
        self.assertNotIn('OrderNumber', form)
        receipt = next(d for stage, d in self.stages if stage == 'checkout_accepted')
        self.assertEqual(receipt['document_ids'], ['1-101', '1-102'])
        self.assertEqual([d['current_store'] for d in result['documents']], [46, 46])
        self.assertEqual([d['pickup_store'] for d in result['documents']], [29100, 29100])

    def test_other_basket_items_and_changed_basket_block_before_any_mutation(self):
        self.web.rows = [{'nn': 1, 'gdscode': '9999', 'cnt': 1, 'selected': True}]
        with self.assertRaisesRegex(Failure, 'other_items'):
            self.checkout.prepare(PARAMS)
        self.assertFalse(self.posted('/basket/add'))
        self.web.rows = []
        p = self.checkout.prepare(PARAMS)
        self.web.rows = [{'nn': 1, 'gdscode': '1001', 'cnt': 100, 'selected': True}]
        with self.assertRaisesRegex(Failure, 'changed_since_prepare'):
            self.execute(p)
        self.assertFalse(self.posted('/basket/order'))

    def unselected_basket(self):
        # Same selection/quantity/line types as the live 2026-10-04 basket;
        # product, price and lot identifiers are independent fixture values.
        self.web.rows = [{'nn': '1', 'gdscode': '1001', 'cnt': '100', 'selected': False,
            'sum': 1234, 'delivery_parts': [{'cnt': 100, 'g-net': '1', 'g-num': '101', 'PartNum': '42'}]}]

    def test_existing_unselected_basket_is_prepared_without_writes_then_selected_and_ordered(self):
        self.unselected_basket()
        prepared = self.checkout.prepare(PARAMS)
        self.assertFalse(prepared['basket_was_empty'])
        self.assertFalse(any(call[0] == 'POST' for call in self.web.calls))
        result = self.execute(prepared)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(len(self.posted('/basket/1/edit')), 1)
        self.assertEqual(self.posted('/basket/1/edit')[0][3], {'selected': 'true'})
        self.assertFalse(self.posted('/basket/add'))
        self.assertEqual(len(self.posted('/basket/order')), 1)
        self.assertEqual([s for s, _ in self.stages][:3],
                         ['basket_select_submitting', 'basket_select_accepted', 'checkout_submitting'])
        calls = [(c[0], c[1]) for c in self.web.calls]
        selected_at = calls.index(('POST', '/basket/1/edit'))
        ordered_at = calls.index(('POST', '/basket/order'))
        self.assertGreaterEqual(calls[selected_at:ordered_at].count(('GET', '/basket/order')), 2)

    def test_newly_added_unselected_row_is_selected_before_checkout(self):
        self.web.add_selected = False
        result = self.execute(self.checkout.prepare(PARAMS))
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(len(self.posted('/basket/add')), 1)
        self.assertEqual(len(self.posted('/basket/1/edit')), 1)
        self.assertEqual(len(self.posted('/basket/order')), 1)

    def test_continuous_cut_with_optional_empty_label_is_requested_and_not_claimed_fulfilled(self):
        self.unselected_basket()
        self.web.rows[0]['delivery_parts'][0]['PartNum'] = ''
        prepared = self.checkout.prepare({**PARAMS, 'continuous_cut': True})
        verification = prepared['preview']['continuous_cut_verification']
        self.assertTrue(verification['requested'])
        self.assertTrue(verification['single_allocation_verified'])
        self.assertFalse(verification['physical_cut_verified'])
        result = self.execute(prepared)
        self.assertEqual(result['status'], 'verified')
        self.assertFalse(result['continuous_cut_verification']['physical_cut_verified'])
        self.assertTrue(result['continuous_cut_verification']['requested'])
        form = self.posted('/basket/order')[0][3]
        self.assertIn('требуется один непрерывный отрезок 100 м', form['tovzak'])
        self.assertNotIn('PartNum', form['tovzak'])
        self.assertEqual(self.web.note, form['tovzak'])

    def test_selected_rows_need_no_selection_write(self):
        self.unselected_basket()
        self.web.rows[0]['selected'] = True
        self.assertEqual(self.execute(self.checkout.prepare(PARAMS))['status'], 'verified')
        self.assertFalse(self.posted('/basket/1/edit'))
        self.assertFalse(self.posted('/basket/add'))

    def test_missing_or_invalid_selection_cannot_be_inferred_from_select_all(self):
        for value in (None, '', [], {}, 1.0, 'yes', 'none'):
            with self.subTest(value=value):
                self.unselected_basket()
                if value is None:
                    self.web.rows[0].pop('selected')
                else:
                    self.web.rows[0]['selected'] = value
                with self.assertRaisesRegex(Failure, '^etm_basket_selection_unverified$'):
                    self.checkout.prepare(PARAMS)
                self.assertFalse(any(c[0] == 'POST' for c in self.web.calls))

    def test_explicit_selection_states_are_checked_even_when_preparation_allows_false(self):
        self.unselected_basket()
        basket = self.web.basket()
        params = validate_params(PARAMS)
        for selected in (True, 1, '1', 'true'):
            with self.subTest(selected=selected):
                basket['rows'][0]['selected'] = selected
                self.checkout._check_orderable(basket, params)
        for selected in (False, 0, '0', 'false'):
            with self.subTest(selected=selected):
                basket['rows'][0]['selected'] = selected
                self.checkout._check_orderable(basket, params, require_selected=False)
                with self.assertRaisesRegex(Failure, '^etm_basket_selection_mismatch$'):
                    self.checkout._check_orderable(basket, params)

    def test_selection_acceptance_requires_selected_readback_before_order(self):
        self.unselected_basket()
        self.web.ignore_selection = True
        with self.assertRaisesRegex(Failure, '^etm_basket_selection_mismatch$'):
            self.execute(self.checkout.prepare(PARAMS))
        self.assertEqual(len(self.posted('/basket/1/edit')), 1)
        self.assertFalse(self.posted('/basket/order'))
        self.assertEqual(self.stages[-1][0], 'basket_select_accepted')

    def test_selection_timeout_is_not_replayed_or_treated_as_order_submission(self):
        self.unselected_basket()
        self.web.selection_error = Failure('etm_portal_transport_unknown')
        with self.assertRaisesRegex(Failure, 'transport_unknown'):
            self.execute(self.checkout.prepare(PARAMS))
        self.assertEqual(len(self.posted('/basket/1/edit')), 1)
        self.assertFalse(self.posted('/basket/order'))
        self.assertEqual(self.stages[-1][0], 'basket_select_submitting')

    def test_selection_readback_rechecks_quantities_price_and_allocation(self):
        for change, expected in (
            (lambda b: b['rows'][0].update(cnt=101), 'quantity_mismatch'),
            (lambda b: b.update(sum=1234.01), 'exceeds_approved_total'),
            (lambda b: b['rows'][0].update(delivery_parts=[]), 'allocation_unverified'),
        ):
            with self.subTest(expected=expected):
                self.setUp()
                self.unselected_basket()
                prepared = self.checkout.prepare(PARAMS)
                original = self.web.call
                def changed_read(method, path, **kwargs):
                    result = original(method, path, **kwargs)
                    if method == 'GET' and path == '/basket/order' and self.posted('/basket/1/edit'):
                        change(result)
                    return result
                with patch.object(self.web, 'call', side_effect=changed_read):
                    with self.assertRaisesRegex(Failure, expected):
                        self.execute(prepared)
                self.assertFalse(self.posted('/basket/order'))

    def test_changed_contract_or_payment_blocks_checkout(self):
        p = self.checkout.prepare(PARAMS)
        self.web.contract_id = '666'
        with self.assertRaisesRegex(Failure, 'contract_unavailable'):
            self.execute(p)
        self.assertFalse(self.posted('/basket/add'))
        self.web.contract_id = '555'
        self.web.payment_active = False
        with self.assertRaisesRegex(Failure, 'payment_unavailable'):
            self.execute(p)
        self.assertFalse(self.posted('/basket/order'))

    def test_provider_quantity_rounding_cannot_create_oversized_order(self):
        p = self.checkout.prepare(PARAMS)
        self.web.round_up = True
        with self.assertRaisesRegex(Failure, 'quantity_mismatch'):
            self.execute(p)
        self.assertFalse(self.posted('/basket/order'))
        self.assertEqual(self.stages[0][0], 'basket_add_submitting')

    def test_final_allocation_change_blocks_checkout(self):
        p = self.checkout.prepare(PARAMS)
        self.web.change_on_final_read = True
        with self.assertRaisesRegex(Failure, 'allocation_changed'):
            self.execute(p)
        self.assertFalse(self.posted('/basket/order'))

    def test_stock_only_rejects_empty_source_ids_and_continuous_cut_always_needs_lot(self):
        for params, expected in [(PARAMS, 'supplier_order_not_authorized'),
                ({**PARAMS, 'continuous_cut': True, 'allow_supplier_order': True}, 'continuous_cut_unverified')]:
            web = FakeWebsite()
            checkout = Checkout(web, sleeper=lambda _: None)
            p = checkout.prepare(params)
            web.bad_parts = True
            with self.assertRaisesRegex(Failure, expected):
                checkout.execute(p, on_stage=lambda *args: None)
            self.assertFalse(any(c[:2] == ('POST', '/basket/order') for c in web.calls))

    def test_network_timeout_is_not_retried(self):
        p = self.checkout.prepare(PARAMS)
        self.web.checkout_error = Failure('etm_portal_transport_unknown')
        with self.assertRaisesRegex(Failure, 'transport_unknown'):
            self.execute(p)
        self.assertEqual(len(self.posted('/basket/order')), 1)
        self.assertEqual(self.stages[-1][0], 'checkout_submitting')

    def test_malformed_receipt_is_recorded_before_readback(self):
        p = self.checkout.prepare(PARAMS)
        self.web.receipt = {'createdDoc': 42}
        result = self.execute(p)
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertFalse(result['receipt']['all_returned_ids_valid'])
        self.assertTrue(any(stage == 'checkout_accepted' for stage, _ in self.stages))

    def test_split_specification_wrong_destination_and_missing_status_remain_unverified(self):
        for change, expected in [(lambda w: w.statuses.update({'1-102': '01'}), 'document_not_accepted_order'),
                (lambda w: setattr(w, 'bad_store', True), 'pickup_store_mismatch'),
                (lambda w: w.statuses.update({'1-102': None}), 'document_status_unverified')]:
            web = FakeWebsite()
            checkout = Checkout(web, sleeper=lambda _: None)
            p = checkout.prepare(PARAMS)
            change(web)
            result = checkout.execute(p, on_stage=lambda *args: None)
            self.assertEqual(result['status'], 'accepted_unverified')
            self.assertTrue(any(expected in problem for problem in result['verification_problems']))

    def test_reconcile_is_read_only_and_rechecks_legal_entity(self):
        p = self.checkout.prepare(PARAMS)
        result = self.execute(p)
        self.web.calls = []
        result = self.checkout.reconcile(p, result['receipt'])
        self.assertEqual(result['status'], 'verified')
        self.assertFalse(any(c[0] == 'POST' for c in self.web.calls))
        self.web.identity['inn_org'] = '9999999999'
        with self.assertRaisesRegex(Failure, 'legal_entity_changed'):
            self.checkout.reconcile(p, result['receipt'])

    def test_strict_offline_validation(self):
        for data in [None, {**PARAMS, 'items': [{'code': '1001', 'quantity': float('nan')}]},
                {**PARAMS, 'items': [{'code': '1001', 'quantity': True}]},
                {**PARAMS, 'currency': 'USD'}, {**PARAMS, 'pay_type': 'card-now'},
                {**PARAMS, 'pickup_store': '../other'}, {**PARAMS, 'override': True}]:
            with self.assertRaises(Failure):
                validate_params(data)
        with self.assertRaises(Failure):
            validate_options({'region': '34', 'url': 'https://other.example'})


class TransportTests(TestCase):
    def test_multipart_cyrillic_body_and_session_stay_on_stdin(self):
        client = WebsiteClient({'etm_proxy': 'socks5h://127.0.0.1:10929'}, vault=object())
        client.session = 'SESSION-FIXTURE'
        client.region = '34'
        result = subprocess.CompletedProcess([], 0, b'{"status":{"code":200},"data":{}}\n200', b'')
        with patch('automation_integrations.etm_order.subprocess.run', return_value=result) as run:
            client.call('POST', '/basket/order', form={'tovzak': 'Белый провод\n100 метров', 'skl': '29100'})
        args, kwargs = run.call_args
        self.assertNotIn('SESSION-FIXTURE', ' '.join(args[0]))
        self.assertNotIn('Белый провод', ' '.join(args[0]))
        stdin = kwargs['input'].decode()
        self.assertIn('Белый провод', stdin)
        self.assertNotIn('\\u0411', stdin)
        self.assertIn('data-binary = ', stdin)
        self.assertNotIn('--location', args[0])

    def test_unconfigured_or_sandbox_route_fails_before_credentials(self):
        with self.assertRaisesRegex(Failure, 'unsupported_provider_environment'):
            WebsiteClient({'etm_environment': 'sandbox'}, vault=object())
        client = WebsiteClient({}, vault=object())
        with self.assertRaisesRegex(Failure, 'proxy_unconfigured'):
            client.call('GET', '/basket/order')

    def test_multipart_rejects_header_injection(self):
        with self.assertRaises(Failure):
            _multipart({'evil\r\nX': 'value'})


if __name__ == '__main__':
    main()
