from copy import deepcopy
import tempfile
import unittest
from unittest.mock import patch

from automation_integrations import confirmed_write, openapi_contract as contract
from automation_integrations.etm_document import body_schema, preview_details, supplement, validate_body


BODY = {'OrderNumber': 'USER-123', 'DocumentFunctionCode': 'P',
        'Seller': {'ILN': '4660011519999'}, 'Remarks': 'Белый провод, без замены',
        'Order-Lines': [{'LineNumber': '1', 'SupplierItemCode': '6510970',
                         'OrderedQuantity': '100', 'UnitOfMeasure': '006'}],
        'TotalLines': '1'}


class EtmDocumentTests(unittest.TestCase):
    def check(self, body):
        contract.validate_schema(body, body_schema())
        validate_body(body)

    def test_documented_create_and_modify_codes_preserve_exact_document_number(self):
        for code in 'PADC':
            body = {**BODY, 'DocumentFunctionCode': code}
            self.check(body)
            request = contract.build('etm', 'invoice_create', {'body': body})
            self.assertEqual(request['path'], '/invoice/create')
            self.assertEqual(request['body'], body)
            self.assertNotIn('session-id', request['query'])

    def test_invalid_quantity_and_document_totals(self):
        for change in (
            lambda b: b['Order-Lines'][0].update(OrderedQuantity='0'),
            lambda b: b['Order-Lines'][0].update(OrderedQuantity='-100'),
            lambda b: b['Order-Lines'][0].update(OrderedQuantity=True),
            lambda b: b['Order-Lines'][0].pop('SupplierItemCode'),
            lambda b: b['Order-Lines'].append(deepcopy(b['Order-Lines'][0])),
            lambda b: b.update(TotalLines='2'),
            lambda b: b.update(OrderNumber=''),
            lambda b: b['Seller'].update(ILN='invented'),
            lambda b: b.update(DocumentFunctionCode='DELETE'),
            lambda b: b.update(OrderDate='2026-02-30'),
            lambda b: b.update(payment_method_code='bill'),
        ):
            body = deepcopy(BODY)
            change(body)
            with self.assertRaises(ValueError):
                self.check(body)

    def test_source_and_limitations_disclose_payment_and_split_document_boundary(self):
        row = contract.operations('etm')['invoice_create']
        self.assertIsNone(row['unsupported_reason'])
        self.assertIn('Работа с заказами', row['supplemental_contract_source'])
        self.assertIn('visible', ' '.join(row['limitations']))
        self.assertIn('split', ' '.join(row['limitations']))

    def test_customer_number_matches_exact_provider_alphabet(self):
        self.check({**BODY, 'OrderNumber': 'A-БЁ/12.3-4'})
        for number in ('А-123', 'a-123', 'USER_123', 'USER 123', 'ABC\n'):
            with self.subTest(number=number), self.assertRaises(ValueError):
                self.check({**BODY, 'OrderNumber': number})

    def test_latest_manual_does_not_impose_older_text_or_decimal_limits(self):
        body = deepcopy(BODY)
        body['OrderNumber'] = '12345678901234567890'
        body['Remarks'] = 'Провод без замены. ' * 10
        body['Order-Lines'][0].update(OrderedQuantity='0.125',
                                     ItemDescription='Провод монтажный ' * 10)
        self.check(body)

    def test_product_identity_requires_documented_key_and_manufacturer_pair(self):
        body = deepcopy(BODY)
        line = body['Order-Lines'][0]
        line.pop('SupplierItemCode')
        line['EAN'] = '4601234567890'
        with self.assertRaises(ValueError):
            self.check(body)
        line['ManufacturerArticle'] = 'LLE-MR16-5'
        with self.assertRaises(ValueError):
            self.check(body)
        line['ManufacturerCod'] = '432'
        self.check(body)
        line['ManufacturerCod'] = ''
        with self.assertRaises(ValueError):
            self.check(body)

    def test_modifying_actions_name_visible_target_and_effect(self):
        for code, phrase in [('P', 'первичный'), ('A', 'Подтвердить'),
                             ('D', 'Отказаться'), ('C', 'согласованные условия')]:
            with self.subTest(code=code):
                preview = preview_details({**BODY, 'DocumentFunctionCode': code})
                self.assertEqual(preview['affected_order_number'], BODY['OrderNumber'])
                self.assertIn(phrase, preview['business_action'])

    def test_confirmation_preview_discloses_destructive_effect_before_network(self):
        for code, phrase in [('C', 'согласованные условия'), ('D', 'Отказаться')]:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as state:
                with patch('automation_integrations.extended_api.call',
                           side_effect=AssertionError('Preparation must be offline')):
                    draft = confirmed_write.process(
                        {'action': 'prepare', 'service': 'etm', 'operation': 'invoice_create',
                         'params': {'body': {**BODY, 'DocumentFunctionCode': code}}},
                        {'scope': ['owner', 'owner', 'session', 'topic'], 'message_id': '1'},
                        {'state_dir': state})
                self.assertEqual(draft['status'], 'prepared')
                self.assertEqual(draft['preview']['affected_order_number'], BODY['OrderNumber'])
                self.assertIn(phrase, draft['preview']['business_action'])

    def test_supplement_is_idempotent_without_changing_raw_vendor_schema(self):
        row = contract.operations('etm')['invoice_create']
        raw = deepcopy(row['request_body'])
        supplement(row)
        supplement(row)
        self.assertEqual(row['params_schema']['required'].count('body'), 1)
        self.assertEqual(row['request_body'], raw)


if __name__ == '__main__':
    unittest.main()
