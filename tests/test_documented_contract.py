"""Provider request examples and boundary checks, without credentials or I/O."""
import copy
import datetime as dt
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from automation_integrations import documented_contract as contract


class DocumentedContractTests(unittest.TestCase):
    def test_yandex_paged_order_filters_are_query_parameters(self):
        request = contract.build('yandex_go', 'order_list', {'query': {
            'limit': 150, 'offset': 300, 'user_id': 'employee-1',
            'sorting_field': 'finished_date', 'sorting_direction': -1,
            'since_datetime': '2026-09-01T00:00:00+03:00',
            'till_datetime': '2026-10-01T00:00:00+03:00'}})
        self.assertEqual(request['method'], 'GET')
        self.assertEqual(request['path'], '/orders/list')
        self.assertEqual(request['query']['offset'], 300)
        self.assertIsNone(request['body'])

    def test_post_reads_remain_read_and_keep_body_vs_query(self):
        ops = contract.operations('yandex_go')
        for name in ('food_list', 'travels_list', 'taxi_report', 'user_phone', 'users_spending_details'):
            self.assertEqual(ops[name]['effect'], 'read')
        request = contract.build('yandex_go', 'food_list', {
            'query': {'limit': 150, 'cursor': 'provider-cursor'},
            'body': {'user_ids': ['one', 'two']}})
        self.assertEqual(request['path'], '/orders/eats/list')
        self.assertEqual(request['body'], {'user_ids': ['one', 'two']})
        self.assertEqual(request['query']['cursor'], 'provider-cursor')
        with self.assertRaises(ValueError):
            contract.validate('yandex_go', 'travels_list', {'body': {'limit': 11}})

    def test_user_create_requires_nested_limit_identity(self):
        body = {'fullname': '', 'phone': '+79990000000', 'is_active': True,
                'limits': [{'limit_id': 'taxi-limit', 'service': 'taxi'}],
                'documents': [{'document_type': 'passport_rus', 'birth_date_str': '1990-02-28'}]}
        self.assertEqual(contract.build('yandex_go', 'user_create', {'body': body})['body'], body)
        invalid = copy.deepcopy(body)
        del invalid['limits'][0]['limit_id']
        with self.assertRaises(ValueError):
            contract.validate('yandex_go', 'user_create', {'body': invalid})
        invalid = copy.deepcopy(body)
        invalid['documents'][0]['birth_date_str'] = '1990-02-30'
        with self.assertRaises(ValueError):
            contract.validate('yandex_go', 'user_create', {'body': invalid})

    def test_vehicle_required_nested_access_and_boolean_serialization(self):
        body = {'vehicles': [{'vehicle_id': 'v1', 'license_plate': 'A123BC',
                'model': 'Car', 'limit_id': 'limit', 'access_type': 'custom',
                'access': [{'entity_type': 'department', 'entity_id': 'd1'}]}]}
        request = contract.build('yandex_go', 'vehicles_bulk_update', {'body': body})
        self.assertEqual(request['path'], '/vehicles/bulk-update')
        del body['vehicles'][0]['access'][0]['entity_id']
        with self.assertRaises(ValueError):
            contract.validate('yandex_go', 'vehicles_bulk_update', {'body': body})
        request = contract.build('yandex_go', 'vehicles_list', {'query': {'include_deleted': False}})
        self.assertEqual(request['query']['include_deleted'], 'false')

    def test_coordinates_and_body_boundaries(self):
        body = {'name': 'Office', 'geo_type': 'circle', 'geo': {'center': [37.6, 55.7], 'radius': 500}}
        contract.validate('yandex_go', 'region_create', {'body': body})
        body['geo']['center'] = [37, 91]
        with self.assertRaises(ValueError):
            contract.validate('yandex_go', 'region_create', {'body': body})
        for bad in (float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                contract.validate('yandex_go', 'zone_lookup', {'query': {'lat': bad, 'lon': 30}})
        with self.assertRaises(ValueError):
            contract.validate('yandex_go', 'taxi_report', {'body': {'ids': ['id'] * 101}})

    def test_promocode_service_limits_and_dates(self):
        end = (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=5)).isoformat()
        body = {'value': 6000, 'count': 5, 'active_until': end}
        with self.assertRaisesRegex(ValueError, 'invalid_promocode_value'):
            contract.validate('yandex_go', 'promocodes_create', {'body': body})
        body['service'] = 'grocery'
        contract.validate('yandex_go', 'promocodes_create', {'body': body})
        body['active_until'] = '2000-01-01'
        with self.assertRaisesRegex(ValueError, 'invalid_promocode_dates'):
            contract.validate('yandex_go', 'promocodes_create', {'body': body})

    def test_special_taxi_workflows_cannot_be_bypassed(self):
        for name in ('order_create', 'order_cancel', 'orders_create', 'flight_search', 'limit_update'):
            with self.assertRaisesRegex(ValueError, 'unsupported_operation'):
                contract.build('yandex_go', name, {'body': {}})
        self.assertNotIn('order_create', contract.operations('yandex_go'))

    def test_saby_rpc_fixed_and_exact_parameter_nesting(self):
        params = {'body': {'Документ': {'Идентификатор': 'doc-1', 'Редакция': {'Идентификатор': 'rev-1'}}}}
        request = contract.build('saby', 'document_read', params)
        revision_only = contract.build('saby', 'document_read', {'body': {'Документ': {'Редакция': {'Идентификатор': 'revision'}}}})
        self.assertEqual(revision_only['body']['params']['Документ']['Редакция']['Идентификатор'], 'revision')
        self.assertEqual(request, {'method': 'POST', 'path': '/service/?srv=1', 'query': {}, 'body': {
            'jsonrpc': '2.0', 'id': 1, 'method': 'СБИС.ПрочитатьДокумент', 'params': params['body']}})
        for invalid in ({'body': {'method': 'СБИС.УдалитьДокумент'}}, {'body': {'Документ': {}}},
                        {'body': {'Документ': {'Идентификатор': 'd'}}, 'path': {'url': 'https://evil.test'}}):
            with self.assertRaises(ValueError):
                contract.build('saby', 'document_read', invalid)

    def test_saby_document_filter_allows_provider_types_and_string_paging(self):
        params = {'body': {'Фильтр': {'Тип': 'Доверенность', 'Направление': 'Входящий',
                  'Навигация': {'РазмерСтраницы': '200', 'Страница': '10'}}}}
        contract.validate('saby', 'documents_list', params)
        for page_size in ('201', '0', '-1', 20):
            invalid = copy.deepcopy(params)
            invalid['body']['Фильтр']['Навигация']['РазмерСтраницы'] = page_size
            with self.assertRaises(ValueError):
                contract.validate('saby', 'documents_list', invalid)
        with self.assertRaises(ValueError):
            contract.validate('saby', 'documents_list', {'body': {'Фильтр': {}}})

    def test_saby_read_never_acquires_default_event_locks(self):
        params = {'body': {'Фильтр': {}}}
        request = contract.build('saby', 'service_stages_list', params)
        self.assertEqual(request['body']['params']['Фильтр']['Блокировать'], 'Нет')
        self.assertEqual(params, {'body': {'Фильтр': {}}})
        with self.assertRaises(ValueError):
            contract.validate('saby', 'service_stages_list', {'body': {'Фильтр': {'Блокировать': 'Да'}}})

    def test_saby_employee_identity_and_hr_boolean_types(self):
        contract.build('saby', 'employee_read', {'body': {'Параметр': {'Сотрудник': {'ИдентификаторИС': 'external'}}}})
        with self.assertRaises(ValueError):
            contract.build('saby', 'employee_read', {'body': {'Параметр': {'Сотрудник': {}}}})
        params = {'body': {'Filter': {'Сотрудник': {'ВнешнийИдентификатор': 'external'},
                                     'ВключаяИнструкции': True}}}
        request = contract.build('saby', 'hr_documents_list_for_person', params)
        self.assertEqual(request['body']['method'], 'ekdapi.DocumentsListForPerson')
        params['body']['Filter']['ВключаяИнструкции'] = 'true'
        with self.assertRaises(ValueError):
            contract.validate('saby', 'hr_documents_list_for_person', params)

    def test_new_saby_department_delete_exact_array(self):
        request = contract.build('saby', 'department_delete', {'body': {'params': {'departments': ['dept-1', 'dept-2']}}})
        self.assertEqual(request['body']['method'], 'sabyDepartment.Delete')
        for params in ({'body': {'params': {}}}, {'body': {'params': {'departments': 'dept-1'}}}):
            with self.assertRaises(ValueError):
                contract.validate('saby', 'department_delete', params)

    def test_saby_signature_binary_validation_and_mutual_exclusion(self):
        params = {'body': {'Документ': {'Идентификатор': 'doc', 'Вложение': [
            {'Файл': {'Имя': 'data.xml', 'ДвоичныеДанные': 'PHhtbC8+'}}]}}}
        contract.validate('saby', 'attachment_write', params)
        file = params['body']['Документ']['Вложение'][0]['Файл']
        file['Ссылка'] = 'https://online.sbis.ru/provider-file'
        with self.assertRaisesRegex(ValueError, 'mutually_exclusive_file_sources'):
            contract.validate('saby', 'attachment_write', params)
        del file['Ссылка']
        file['ДвоичныеДанные'] = 'not base64!'
        with self.assertRaisesRegex(ValueError, 'invalid_base64'):
            contract.validate('saby', 'attachment_write', params)

    def test_saby_action_shape_required_and_single_action(self):
        doc = {'Идентификатор': 'doc', 'Этап': {'Действие': [{'Название': 'Отправить'}]}}
        contract.validate('saby', 'document_action', {'body': {'Документ': doc}})
        doc['Этап']['Действие'].append({'Название': 'Утвердить'})
        with self.assertRaises(ValueError):
            contract.validate('saby', 'document_action', {'body': {'Документ': doc}})

    def test_effects_metadata_and_registry_are_isolated(self):
        ops = contract.operations('saby')
        self.assertEqual(ops['document_action_prepare']['effect'], 'business_write')
        self.assertEqual(ops['power_register']['effect'], 'business_write')
        self.assertEqual(ops['our_company_list']['effect'], 'read')
        ops['document_read']['path'] = 'https://evil.test'
        self.assertEqual(contract.operations('saby')['document_read']['path'], '/service/?srv=1')
        for service in ('yandex_go', 'saby'):
            for row in contract.operations(service).values():
                self.assertIn(row['effect'], ('read', 'business_write'))
                self.assertIn('params_schema', row)
                self.assertTrue(row['source'].startswith('https://'))
                self.assertTrue(row['path'].startswith('/'))

    def test_unsupported_saby_methods_fail_before_network(self):
        with patch('urllib.request.build_opener', side_effect=AssertionError('network touched')):
            for name in ('counterparty_upsert_info', 'task_reassign_tasks', 'department_read',
                         'service_stage_postpone', 'СБИС.Аутентифицировать', 'user_add'):
                with self.assertRaisesRegex(ValueError, 'unsupported_operation'):
                    contract.build('saby', name, {})

    def test_credentials_oversized_non_json_and_unknown_fields_rejected(self):
        for params in ({'body': {'Фильтр': {'Тип': 'x', 'password': 'secret'}}},
                       {'body': {'Фильтр': {'Тип': set()}}},
                       {'body': {'Фильтр': {'Тип': 'x'}}, 'url': 'https://evil.test'}):
            with self.assertRaises(ValueError):
                contract.validate('saby', 'documents_list', params)
        with self.assertRaises(ValueError):
            contract.validate('yandex_go', ['invalid'], {})
        with self.assertRaises(ValueError):
            contract.validate('unknown', 'documents_list', {})


if __name__ == '__main__':
    unittest.main()
