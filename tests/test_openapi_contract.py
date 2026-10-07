"""Offline regression tests; fixtures contain only official sample identifiers."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from automation_integrations.openapi_contract import build, operations, validate, validate_schema

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = '40817810802000000008/044525104'
PAYMENT = {'body': {'Data': {
    'accountCode': '40702810840020002503', 'bankCode': '044525104',
    'counterpartyBankBic': '044525104', 'counterpartyAccountNumber': '40702810840020002504',
    'counterpartyName': 'ООО "БАЙКАЛ-СЕРВИС ТК"', 'paymentAmount': 700.33,
    'paymentDate': '2018-03-29', 'paymentPurpose': 'Оплата по счету № 1. Без НДС',
    'paymentNumber': 9195,
}}}
RECEIPT = {'body': {'Data': {
    'customerCode': '300000092', 'amount': 1234.00, 'purpose': 'Перевод за оказанные услуги',
    'paymentMode': ['sbp', 'card'], 'taxSystemCode': 'osn', 'ttl': 10080,
    'Client': {'email': 'ivanov@example.com'},
    'Items': [{'name': 'Услуга', 'amount': 1234.00, 'quantity': 1,
               'vatType': 'none', 'paymentMethod': 'full_payment', 'paymentObject': 'service'}],
    'Supplier': {'phone': '+79999999999', 'name': 'ООО Альтер', 'taxCode': '660000000000'},
}}}


class ContractTests(unittest.TestCase):
    def test_all_official_methods_are_accounted_for_with_provenance(self):
        for service, count in [('etm', 19), ('tochka', 71)]:
            with self.subTest(service=service):
                inventory = json.loads((ROOT / 'registry/capabilities' / (service + '.json')).read_text())
                rows = operations(service)
                self.assertEqual(len(rows), count)
                supplemental = inventory.get('supplemental_operations', {})
                official = [r for r in inventory['capabilities'] if r['id'] not in supplemental]
                self.assertEqual({r['id'] for r in rows.values()}, {r['id'] for r in official})
                for row in inventory['capabilities']:
                    if row['id'] in supplemental:
                        self.assertEqual(supplemental[row['id']]['execution'], 'integration_read')
                        self.assertTrue(row['source'].startswith('https://www.etm.ru/api/ipro/'))
                for name, row in rows.items():
                    self.assertRegex(name, r'^[a-z][a-z0-9_]{0,79}$')
                    self.assertFalse(row['live_verified'])
                    self.assertEqual(row['validation'], 'offline_schema_only')
                    self.assertTrue(row['source'].startswith('https://'))
                    self.assertNotIn('"$ref"', json.dumps(row))
                metadata = json.loads((ROOT / 'registry/contracts' / (service + '.json')).read_text())
                self.assertTrue(all(len(source['sha256']) == 64 for source in metadata['sources']))

    def test_contract_metadata_cannot_change_execution(self):
        rows = operations('etm')
        rows['catalog_search']['path'] = '//attacker.example/'
        rows['catalog_search']['params_schema']['additionalProperties'] = True
        self.assertEqual(build('etm', 'catalog_search', {})['path'], '/catalog')
        with self.assertRaises(ValueError):
            build('etm', 'catalog_search', {'url': 'https://attacker.example'})

    def test_official_payment_request_and_exact_fixed_transport(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('No network in validation')):
            request = build('tochka', 'payment_create_payment_for_sign', PAYMENT)
        self.assertEqual(request['method'], 'POST')
        self.assertEqual(request['path'], '/payment/v1.0/for-sign')
        self.assertEqual(request['body'], PAYMENT['body'])
        self.assertEqual(request['query'], {})
        self.assertEqual(request['headers'], {})
        self.assertEqual(operations('tochka')['payment_create_payment_for_sign']['effect'], 'business_write')

    def test_financial_nested_required_bounds_types_and_dates(self):
        for field, value in [('bankCode', '123'), ('paymentDate', '2018-02-30'),
                             ('paymentAmount', True), ('paymentNumber', 0),
                             ('paymentNumber', 1000000), ('paymentPurpose', '')]:
            with self.subTest(field=field, value=value):
                body = deepcopy(PAYMENT)
                body['body']['Data'][field] = value
                with self.assertRaises(ValueError):
                    validate('tochka', 'payment_create_payment_for_sign', body)
        for body in ({}, {'body': {}}, {'body': {'Data': {}}}):
            with self.assertRaises(ValueError):
                validate('tochka', 'payment_create_payment_for_sign', body)

    def test_receipt_nested_arrays_enums_ref_siblings_and_patterns(self):
        name = 'acquiring_create_payment_operation_with_receipt'
        self.assertEqual(build('tochka', name, RECEIPT)['body'], RECEIPT['body'])
        for mutation in (
            lambda d: d.update(paymentMode=[]),
            lambda d: d.update(paymentMode=['unsupported']),
            lambda d: d.update(ttl=44641),
            lambda d: d['Client'].update(email='invalid'),
            lambda d: d['Items'][0].update(quantity=0),
            lambda d: d['Items'][0].update(vatType='vat999'),
            lambda d: d['Supplier'].update(taxCode='abcdefghij'),
            lambda d: d['Supplier'].pop('phone'),
        ):
            body = deepcopy(RECEIPT)
            mutation(body['body']['Data'])
            with self.assertRaises(ValueError):
                validate('tochka', name, body)

    def test_doc_examples_do_not_coerce_string_money_to_number(self):
        body = deepcopy(RECEIPT)
        body['body']['Data']['amount'] = '1234.00'
        with self.assertRaises(ValueError):
            validate('tochka', 'acquiring_create_payment_operation_with_receipt', body)

    def test_closing_document_anyof_requires_a_complete_document_variant(self):
        params = {'body': {'Data': {'accountId': ACCOUNT, 'customerCode': '300000092',
            'SecondSide': {'taxCode': '660000000000', 'type': 'ip'},
            'Content': {'Act': {'Positions': [{'positionName': 'Услуга',
                'unitCode': 'шт.', 'ndsKind': 'without_nds', 'price': 100,
                'quantity': 1, 'totalAmount': 100}], 'totalAmount': 100, 'number': '1'}}}}}
        validate('tochka', 'invoice_create_closing_document', params)
        params['body']['Data']['Content']['Act']['Positions'][0].pop('quantity')
        with self.assertRaises(ValueError):
            validate('tochka', 'invoice_create_closing_document', params)
        params['body']['Data']['Content'] = {'UnknownDocumentType': {}}
        with self.assertRaises(ValueError):
            validate('tochka', 'invoice_create_closing_document', params)

    def test_report_generation_metadata_and_required_date_fields(self):
        params = {'body': {'Data': {'Statement': {'accountId': ACCOUNT,
            'startDateTime': '2019-01-01', 'endDateTime': '2019-01-31'}}}}
        request = build('tochka', 'open_banking_init_statement', params)
        self.assertEqual(request['path'], '/open-banking/v1.0/statements')
        self.assertEqual(operations('tochka')['open_banking_init_statement']['effect'], 'report_generation')
        self.assertEqual(operations('etm')['catalog_job_create']['effect'], 'report_generation')
        with self.assertRaises(ValueError):
            validate('etm', 'catalog_job_create', {'path': {'procedure': 'arbitrary-rpc'}})

    def test_pdf_files_and_etm_group_print_have_explicit_response_contract(self):
        for op in ('invoice_get_invoice', 'invoice_get_closing_document'):
            request = build('tochka', op, {'path': {'customerCode': '300000092',
                'documentId': '1cf95c4f-e794-4407-bac4-0829f19bd2be'}})
            self.assertEqual(request['response_kind'], 'binary')
            self.assertEqual(request['method'], 'GET')
        request = build('etm', 'invoice_print', {'path': {'id': '123', 'proc': 'bill'},
            'query': {'ch2': '456', 'ch40': '789'}})
        self.assertEqual(request['response_kind'], 'pdf_or_json')
        self.assertEqual(request['query']['ch40'], '789')
        with self.assertRaises(ValueError):
            build('etm', 'invoice_print', {'path': {'id': '123', 'proc': 'bill'}, 'query': {'ch41': '890'}})

    def test_etm_document_body_supplements_null_openapi_with_provider_manual(self):
        row = operations('etm')['invoice_create']
        self.assertIsNone(row['unsupported_reason'])
        self.assertIn('24.01.2025', row['supplemental_contract_source'])
        self.assertIsNone(row['request_body']['content']['application/json']['schema'])
        self.assertIn('Order-Lines', row['params_schema']['properties']['body']['required'])
        with self.assertRaises(ValueError):
            build('etm', 'invoice_create', {'body': {'invented': 'document'}})
        self.assertFalse(any(row['unsupported_reason'] for row in operations('etm').values()))
        self.assertFalse(any(row['unsupported_reason'] for row in operations('tochka').values()))

    def test_bank_account_slash_is_quoted_and_never_becomes_route(self):
        request = build('tochka', 'open_banking_get_account_info', {'path': {'accountId': ACCOUNT}})
        self.assertEqual(request['path'], '/open-banking/v1.0/accounts/40817810802000000008%2F044525104')
        for value in ('..', '../balances', 'x/../balances', '%2e%2e', '%252e%252e',
                      'x?url=https://example.com', 'x#fragment', 'x\\..\\balances', '\r\nHost:evil'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build('tochka', 'open_banking_get_account_info', {'path': {'accountId': value}})
        self.assertIn('%D0', build('etm', 'goods_get', {'path': {'id': 'Артикул А'}})['path'])

    def test_complete_query_filters_and_provider_pagination(self):
        request = build('tochka', 'acquiring_get_subscription_list', {'query': {
            'customerCode': '300000092', 'page': 2, 'perPage': 1000, 'recurring': False}})
        self.assertEqual(request['query'], {'customerCode': '300000092', 'page': '2',
            'perPage': '1000', 'recurring': 'false'})
        self.assertEqual(build('etm', 'invoice_list', {'query': {
            'd1': '2026-10-01', 'd2': '2026-10-03', 'status': 'wait', 'cprStatus': 'agreed',
            'sidx': 'inv-date', 'sord': 'desc', 'rows': 500, 'page': 2}})['query']['rows'], '500')
        for value in (0, -1, True, '2'):
            with self.assertRaises(ValueError):
                build('tochka', 'acquiring_get_subscription_list', {'query': {
                    'customerCode': '300000092', 'page': value}})

    def test_documented_customer_code_header_without_header_injection(self):
        request = build('tochka', 'consent_get_all_consents_list', {'headers': {'customer-code': '300000092'}})
        self.assertEqual(request['headers'], {'customer-code': '300000092'})
        for headers in ({'Host': 'other.example'}, {'customer-code': 'x\r\nHost: evil'},
                        {'Authorization': 'Bearer example'}, {'Cookie': 'sid=example'}):
            with self.assertRaises(ValueError):
                build('tochka', 'consent_get_all_consents_list', {'headers': headers})

    def test_credentials_and_caller_routing_are_never_accepted(self):
        for params in ({'url': 'https://example.com'}, {'method': 'DELETE'},
                       {'path': {'session-id': 'example'}}, {'query': {'pwd': 'example'}}):
            with self.assertRaises(ValueError):
                build('etm', 'catalog_search', params)
        body = deepcopy(PAYMENT)
        body['body']['Data']['jwt'] = 'example'
        with self.assertRaisesRegex(ValueError, '^credentials_not_allowed$'):
            validate('tochka', 'payment_create_payment_for_sign', body)
        self.assertEqual(build('etm', 'login_check', {})['query'], {})
        for service, operation in (('../etm', 'search'), ('etm', 'GET /whatever'), ('tochka', 'arbitrary_rpc')):
            with self.assertRaises(ValueError):
                build(service, operation, {})

    def test_json_inputs_reject_nonfinite_surrogates_and_nonjson(self):
        for amount in (float('nan'), float('inf'), object()):
            body = deepcopy(PAYMENT)
            body['body']['Data']['paymentAmount'] = amount
            with self.assertRaises(ValueError):
                validate('tochka', 'payment_create_payment_for_sign', body)
        with self.assertRaises(ValueError):
            validate_schema('\ud800', {'type': 'string'})

    def test_const_and_datetime(self):
        op = 'consent_create_new_consent'
        params = {'body': {'Data': {'permissions': ['ReadAccountsBasic'],
            'status': 'AwaitingAuthorisation', 'expirationDateTime': '2027-01-01T06:06:06+00:00'},
            'Risks': {'documented_free_form': True}}}
        validate('tochka', op, params)
        params['body']['Data']['status'] = 'Authorised'
        with self.assertRaises(ValueError):
            validate('tochka', op, params)
        for value in ('2027-01-01', '2027-01-01T06:06:06', '2027-02-30T00:00:00Z'):
            with self.assertRaises(ValueError):
                validate_schema(value, {'type': 'string', 'format': 'date-time'})


class SchemaValidatorTests(unittest.TestCase):
    def test_combinators_additional_properties_and_array_constraints(self):
        schema = {'type': 'object', 'required': ['items'], 'additionalProperties': False,
            'properties': {'items': {'type': 'array', 'minItems': 1, 'maxItems': 2,
                'uniqueItems': True, 'items': {'oneOf': [
                    {'type': 'integer', 'minimum': 1, 'maximum': 10},
                    {'type': 'string', 'enum': ['approved']}]}}}}
        validate_schema({'items': [1, 'approved']}, schema)
        for value in ({}, {'items': []}, {'items': [1, 1]}, {'items': [0]},
                      {'items': [True]}, {'items': [1], 'other': 1}, {'items': [1, 2, 3]}):
            with self.assertRaises(ValueError):
                validate_schema(value, schema)
        with self.assertRaises(ValueError):
            validate_schema(1, {'oneOf': [{'type': 'integer'}, {'type': 'number'}]})
        validate_schema('ok', {'anyOf': [{'type': 'integer'}, {'type': 'string'}]})
        validate_schema(2, {'allOf': [{'type': 'integer'}, {'minimum': 2}]})
        with self.assertRaises(ValueError):
            validate_schema(1, {'allOf': [{'type': 'integer'}, {'minimum': 2}]})
        validate_schema({'known': 1, 'extra': 'ok'}, {'type': 'object',
            'properties': {'known': {'type': 'integer'}}, 'additionalProperties': {'type': 'string'}})
        with self.assertRaises(ValueError):
            validate_schema({'extra': 3}, {'additionalProperties': {'type': 'string'}})

    def test_openapi_exclusive_bounds_nullable_and_no_remote_refs(self):
        for schema in ({'type': 'number', 'minimum': 0, 'exclusiveMinimum': True},
                       {'type': 'number', 'exclusiveMinimum': 0}):
            validate_schema(0.1, schema)
            with self.assertRaises(ValueError):
                validate_schema(0, schema)
        validate_schema(None, {'type': 'string', 'nullable': True})
        validate_schema(None, {'type': ['string', 'null']})
        validate_schema(0.3, {'type': 'number', 'multipleOf': 0.1})
        with self.assertRaises(ValueError):
            validate_schema(True, {'enum': [1]})
        with patch('urllib.request.urlopen', side_effect=AssertionError('Remote refs forbidden')):
            with self.assertRaisesRegex(ValueError, '^unsupported_schema$'):
                validate_schema({}, {'$ref': 'https://attacker.example/schema'})


if __name__ == '__main__':
    unittest.main()
