import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse

from automation_integrations import abcp_api as api


class Response(io.BytesIO):
    def __init__(self, data, status=200, content_type='application/json'):
        super().__init__(data if isinstance(data, bytes) else json.dumps(data).encode())
        self.status = status
        self.headers = {'Content-Type': content_type}


class Opener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, **kwargs):
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class Transport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        p = self.root/'credentials.env'
        p.write_text('ABCP_API_HOST=test.public.api.abcp.ru\nABCP_API_LOGIN=private-login\nABCP_API_PASSWORD_MD5=abcdefSECRET\n')
        p.chmod(0o600)
        self.config = {'credentials_file': str(p), 'state_dir': str(self.root/'state')}
        self.row = {'path': '/orders/version', 'method': 'GET', 'effect': 'read', 'auth': 'abcp',
                    'parameters': {'type': 'object', 'additionalProperties': True}}
        self.mock = patch.object(api, 'operation', side_effect=lambda _: self.row)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def call(self, data, params=None, **kwargs):
        opener = Opener(Response(data))
        result = api.execute(self.config, 'test_op', params or {}, opener=opener, **kwargs)
        return result, opener.requests[0]

    def test_php_arrays_and_auth_in_query(self):
        _, request = self.call({'version':2}, {'positions':[{'number':'A B','quantity':2}]})
        pairs = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        self.assertEqual(pairs['positions[0][number]'], ['A B'])
        self.assertEqual(pairs['userpsw'], ['abcdefSECRET'])
        self.assertIsNone(request.data)

    def test_json_and_form_request_content_types(self):
        self.row.update(method='POST', effect='read', path='/advices/batch', encoding='json')
        _, request = self.call([], {'articles':[{'brand':'Mahle','number':'OC90'}]})
        self.assertEqual(json.loads(request.data)['userlogin'], 'private-login')
        self.assertIn('application/json', request.headers['Content-type'])
        self.row['encoding']='form'
        _, request = self.call([], {'ids':[4,5]})
        self.assertIn('ids%5B0%5D=4', request.data.decode())

    def test_csv_serialization(self):
        self.row['parameter_serialization'] = {'orderIds':'csv'}
        _, request = self.call([], {'orderIds':[1,2]})
        self.assertIn('orderIds=1%2C2', request.full_url)

    def test_path_substitution_and_multipart_auth_query(self):
        self.row.update(path='/cp/usercatalogs/{catalogId}/upload', path_parameters=['catalogId'],
                        method='POST', effect='business_write', encoding='multipart', auth_location='query',
                        file_fields=['file'])
        result, request = self.call({'status':1}, {'catalogId':3,'file':{'filename':'a.csv','content_base64':'eCx5Cg=='}}, write=True)
        self.assertIn('/cp/usercatalogs/3/upload?', request.full_url)
        self.assertNotIn(b'abcdefSECRET', request.data)
        self.assertIn(b'x,y\n', request.data)
        self.assertEqual(result['business_status'],'accepted_unverified')

    def test_validation_blocks_credential_override_before_network(self):
        for params in ({'userpsw':'evil'},{'foo[userpsw]':'evil'},{'host':'elsewhere'}, {'ids':[float('nan')]}):
            with self.subTest(params=params), self.assertRaises(api.AbcpError):
                api.validate('test_op',params)
        self.row['effect']='business_write'
        with self.assertRaisesRegex(api.AbcpError, 'write_tool_required'):
            api.execute(self.config, 'test_op', {})

    def test_partial_is_not_failure_and_keeps_orders(self):
        self.row.update(method='POST', effect='business_write')
        result, _ = self.call({'status':0, 'errorMessage':'one failed', 'orders':[{'id':123}]}, write=True)
        self.assertEqual(result['business_status'],'partial')
        self.assertEqual(result['data']['orders'][0]['id'],123)

    def test_http_error_body_preserved_for_partial_success(self):
        self.row.update(method='POST', effect='business_write')
        err = urllib.error.HTTPError('https://invalid/?userpsw=abcdefSECRET',400,'bad',{'Content-Type':'application/json'},
                                     io.BytesIO(b'{"status":0,"orders":[{"id":1}]}'))
        result = api.execute(self.config,'test_op',{},write=True,opener=Opener(err))
        self.assertEqual(result['business_status'],'partial')

    def test_non_json_error_never_leaks_url(self):
        error = urllib.error.URLError('https://private/?userpsw=abcdefSECRET')
        opener = Opener(error)
        with self.assertRaises(api.AbcpError) as raised:
            api.execute(self.config,'test_op',{},opener=opener)
        self.assertNotIn('SECRET',str(raised.exception))
        self.assertEqual(len(opener.requests),1)

    def test_response_secret_redaction_and_business_error(self):
        result,_ = self.call({'errorCode':102,'errorMessage':'private-login abcdefSECRET','userpsw':'abcdefSECRET'})
        self.assertFalse(result['ok'])
        self.assertNotIn('abcdefSECRET',json.dumps(result))
        self.assertNotIn('private-login',json.dumps(result))

    def test_redirect_and_server_error(self):
        for status in (302,503):
            opener = Opener(Response({'message':'unavailable'},status=status))
            with self.assertRaises(api.AbcpError):
                api.execute(self.config,'test_op',{},opener=opener)
            self.assertEqual(len(opener.requests),1)

    def test_binary_result_saved_privately(self):
        self.row['response_kind']='binary_or_json'
        result,_ = self.call(b'%PDF-1.4\nfixture')
        p=Path(result['data']['artifact_path'])
        self.assertEqual(p.read_bytes(),b'%PDF-1.4\nfixture')
        self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_large_result_paging_is_complete(self):
        data=[{'id':i,'text':'x'*2000} for i in range(70)]
        saved=api.bound_result(self.config,{'ok':True,'data':data})
        self.assertTrue(saved['stored_complete'])
        ids=[];offset=0
        while offset is not None:
            result=api.result_page(self.config,{'result_id':saved['result_id'],'offset':offset})
            ids.extend(x['id'] for x in result['data']);offset=result['next_offset']
        self.assertEqual(ids,list(range(70)))

    def test_absent_extra_service_credentials_are_explicit(self):
        self.row['auth']='carcare'
        with self.assertRaisesRegex(api.AbcpError,'credentials_not_configured_carcare'):
            api.execute(self.config,'test_op',{})

    def test_business_password_is_permitted_but_return_masked(self):
        self.row.update(method='POST',effect='business_write')
        result,request=self.call({'status':1,'password':'new-customer-password'}, {'password':'new-customer-password'},write=True)
        self.assertIn('password=new-customer-password',request.data.decode())
        self.assertEqual(result['data']['password'],'[redacted]')

    def test_documented_cart_union_keeps_required_and_unknown_field_constraints(self):
        self.row = api._contract()['operations']['ts_admin_post_cp_ts_cart_update']
        valid = {'positionId': 1, 'quantity': 2, 'clientId': 3}
        self.assertEqual(api.validate('test_op', valid, write=True), valid)
        for params, error in [({'clientId': 3}, 'missing_required_parameter'),
                              ({**valid, 'unexpected': 4}, 'unknown_parameter'),
                              ({'positionId': 1, 'quantity': 2}, 'invalid_parameter_type')]:
            with self.subTest(params=params), self.assertRaisesRegex(api.AbcpError, error):
                api.validate('test_op', params, write=True)

    def test_nested_union_applies_sibling_schema_constraints(self):
        for union in ('anyOf', 'oneOf'):
            self.row['parameters'] = {'type': 'object', 'properties': {'payload': {
                'type': 'object', 'properties': {'clientId': {'type': 'integer'},
                    'guestId': {'type': 'integer'}, 'quantity': {'type': 'integer', 'minimum': 1}},
                'additionalProperties': False, 'required': ['quantity'],
                union: [{'required': ['clientId']}, {'required': ['guestId']}]}}}
            with self.subTest(union=union):
                api.validate('test_op', {'payload': {'clientId': 1, 'quantity': 2}})
                for value in ({'clientId': 1}, {'clientId': 1, 'quantity': 0},
                              {'clientId': 1, 'quantity': 2, 'unknown': True}):
                    with self.assertRaises(api.AbcpError):
                        api.validate('test_op', {'payload': value})
        with self.assertRaisesRegex(api.AbcpError, 'invalid_parameter_type'):
            api.validate('test_op', {'payload': {'clientId': 1, 'guestId': 2, 'quantity': 3}})

    def test_uppercase_vinqu_error_and_read_entity_status_zero(self):
        result, _ = self.call({'Error': 'Request was rejected'})
        self.assertFalse(result['ok'])
        self.assertEqual(result['business_status'], 'provider_rejected')
        result, _ = self.call({'status': 0, 'id': 123})
        self.assertTrue(result['ok'])
        self.assertEqual(result['business_status'], 'read')

    def test_per_item_write_errors_classify_partial_and_rejection_without_retry(self):
        self.row.update(method='POST', effect='business_write')
        for data, expected in [([{'success': True, 'id': 1}, {'success': False}], 'partial'),
                               ([{'success': False}, {'Error': 'Rejected'}], 'provider_rejected')]:
            with self.subTest(expected=expected):
                opener = Opener(Response(data))
                result = api.execute(self.config, 'test_op', {}, write=True, opener=opener)
                self.assertEqual(result['business_status'], expected)
                self.assertEqual(len(opener.requests), 1)

    def test_supplier_position_failure_remains_uncertain_without_retry(self):
        self.row.update(path='/cp/orders/online', method='POST', effect='business_write')
        for states, expected in [([True, False], 'partial'), ([False, False], 'outcome_unknown'),
                                 ([True, True], 'accepted_unverified')]:
            with self.subTest(states=states):
                data = [{'number': 'supplier-order', 'positions': [{'confirmSend': value} for value in states]}]
                opener = Opener(Response(data))
                result = api.execute(self.config, 'test_op', {}, write=True, opener=opener)
                self.assertEqual(result['business_status'], expected)
                self.assertFalse(result['mutation_verified'])
                self.assertEqual(len(opener.requests), 1)


if __name__=='__main__':
    unittest.main()
