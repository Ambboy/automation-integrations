"""No provider credentials or network: test contract boundaries and wire semantics."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from automation_integrations import inference_media as m
from automation_integrations.media_runtime import MediaError


class FakeHTTP:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({'method': method, 'url': url, **deepcopy(kwargs)})
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


KEY = {'INFSH_API_KEY': 'secret-for-tests'}
ROOT = Path(__file__).resolve().parents[1]


class InferenceContractTests(unittest.TestCase):
    def test_inventory_accounts_for_every_published_method_and_provenance(self):
        spec = json.loads((ROOT / 'docs/media-api-snapshots/inference/openapi.json').read_text())
        cap = json.loads((ROOT / 'registry/capabilities/inference.json').read_text())
        expected = {(method.upper(), path) for path, methods in spec['paths'].items()
                    for method in methods if method in ('get','post','put','patch','delete','head','options')}
        provider_rows = [row for row in cap['capabilities'] if 'method' in row and 'path' in row]
        observed = {(row['method'], row['path']) for row in provider_rows}
        self.assertEqual(expected, observed)
        self.assertEqual(len(cap['capabilities']), cap['total'])
        for row in provider_rows:
            if row['availability'] == 'implemented':
                self.assertIn(row['operation'], m.OPERATIONS)
            else:
                self.assertTrue(row['unsupported_reason'])
        for source in cap['sources']:
            if 'error' in source:
                continue
            raw = (ROOT / source['local_snapshot']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source['sha256'])

    def test_no_arbitrary_url_or_header_passthrough_and_no_path_traversal(self):
        for bad in ('../billing', '%2e%2e', 'a/b', '//evil.example', 'x?token=1', '.', '..', 'x\\y'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                m.validate('task_get', {'id': bad})
        for params in ({'id':'task1','url':'https://evil.example'}, {'id':'task1','headers':{}}):
            with self.assertRaises(ValueError):
                m.validate('task_get',params)
        with self.assertRaises(ValueError):
            m.validate('GET /admin/users',{})

    def test_dynamic_app_ref_version_function_and_infra_forwarded(self):
        params={'app':'new-provider/future-model@v99','input':{'nested':[1,{'foo':'bar'}]},
                'function':'edit','setup':{'precision':'fp16'},'infra':'private_first',
                'workers':['worker1'],'session':'new','session_timeout':3600,
                'webhook':'https://our.example/callback'}
        http=FakeHTTP({'data':{'id':'task1','status':2},'messages':[]})
        result=m.execute('app_run',params,KEY,transport=http)
        self.assertEqual(result['id'],'task1')
        call=http.calls[0]
        self.assertEqual(call['url'],'https://api.inference.sh/run')
        self.assertEqual(call['query'],{'wait':'false'})
        self.assertEqual(call['body'],params)
        self.assertEqual(call['headers']['Authorization'],'Bearer secret-for-tests')
        self.assertNotIn('wait',params)

    def test_no_sync_or_streaming_submissions_and_no_implicit_retry(self):
        with self.assertRaises(ValueError):m.validate('app_run',{'app':'a/b','input':{},'wait':True})
        with self.assertRaises(ValueError):m.validate('agent_run',{'agent':'a/b','input':{},'stream':True})
        with self.assertRaises(ValueError):m.validate('app_run',{'app':'a/b','input':{},'session_timeout':20})
        http=FakeHTTP(MediaError('request_timeout'))
        with self.assertRaises(MediaError):m.execute('app_run',{'app':'a/b','input':{}},KEY,transport=http)
        self.assertEqual(len(http.calls),1)

    def test_model_schema_secret_named_properties_remain_inspectable(self):
        value={'id':'app1','version':{'input_schema':{'type':'object','properties':{
            'password':{'type':'string'},'api_key':{'type':'string','description':'Test secret-for-tests'}}}},
            'access_token':'actual-live-token'}
        result=m.execute('app_get',{'id':'app1'},KEY,transport=FakeHTTP({'data':value}))
        self.assertEqual(result['version']['input_schema']['properties']['password'],{'type':'string'})
        self.assertEqual(result['version']['input_schema']['properties']['api_key']['description'],'Test [redacted]')
        self.assertEqual(result['access_token'],'[redacted]')

    def test_get_query_json_is_serialized_as_single_values(self):
        request=m.build_request('store_apps',{'limit':20,'filters':[{'field':'category','value':'image','operator':'eq'}],
                                            'search':{'term':'flux','fields':['name']},'include_private':False})
        self.assertEqual(json.loads(request['query']['filters'])[0]['value'],'image')
        self.assertEqual(json.loads(request['query']['search'])['term'],'flux')
        self.assertEqual(request['query']['include_private'],'false')
        self.assertIsNone(request['body'])

    def test_read_post_and_write_get_are_classified_by_effect(self):
        self.assertNotIn('estimate',m.WRITE_OPERATIONS)
        self.assertNotIn('task_list_post',m.WRITE_OPERATIONS)
        self.assertNotIn('engine_resources',m.WRITE_OPERATIONS)
        self.assertIn('skill_resolve',m.WRITE_OPERATIONS) # Auto-import and refresh writes.
        self.assertIn('task_cancel',m.WRITE_OPERATIONS)
        self.assertNotIn('task_cancel',m.GENERATION_OPERATIONS)
        self.assertIn('agent_run',m.GENERATION_OPERATIONS)
        self.assertIn('tool_approve',m.GENERATION_OPERATIONS)

    def test_pricing_preserves_unknown_range_and_microcent_units(self):
        for estimate in ({'confidence':'exact','microcents':2000000},
                         {'confidence':'range','min':150000,'max':1500000},
                         {'confidence':'unknown','depends_on':['outputs']}):
            http=FakeHTTP({'data':estimate,'messages':[]})
            self.assertEqual(m.execute('estimate',{'appId':'app1','input':{},'function':'run'},KEY,transport=http),estimate)
            self.assertNotIn('Authorization',http.calls[0]['headers'])
        self.assertEqual(m.microcents_to_usd(1000000000),'10.00000000')  # Synthetic round balance.
        self.assertEqual(m.microcents_to_usd(50000),'0.00050000')
        with self.assertRaises(ValueError):m.microcents_to_usd(True)

    def test_openai_model_list_and_agent_card_keep_raw_data(self):
        value={'object':'list','data':[{'id':'acme/model'}]}
        self.assertEqual(m.execute('chat_models',{},KEY,transport=FakeHTTP(value)),value)
        value={'name':'a/b','capabilities':{'streaming':True}}
        self.assertEqual(m.execute('agent_card',{'id':'a'},KEY,transport=FakeHTTP(value)),value)

    def test_envelope_unwrap_redacts_key_and_preserves_empty_results(self):
        self.assertEqual(m.execute('task_list',{},KEY,transport=FakeHTTP({'data':[],'messages':[]})),[])
        response={'data':{'output':'key=secret-for-tests','api_key':'other-secret'},'messages':[]}
        result=m.execute('task_get',{'id':'a'},KEY,transport=FakeHTTP(response))
        self.assertEqual(result,{'output':'key=[redacted]','api_key':'[redacted]'})

    def test_problem_and_mcp_http200_errors_are_not_success(self):
        for response in ({'type':'https://api.inference.sh/errors/forbidden','status':403,'detail':'secret-for-tests'},
                         {'data':{'error':True,'content':'tool error'},'messages':[]}):
            if 'data' in response:
                # Result-level tool failure is checked after unwrapping.
                http=FakeHTTP(response)
                with self.assertRaises(MediaError):m.execute('mcp_tool_call',{'slug':'github','tool':'search','arguments':{}},KEY,transport=http)
            else:
                with self.assertRaises(MediaError) as cm:m.execute('balance',{},KEY,transport=FakeHTTP(response))
                self.assertEqual(cm.exception.status,403)
                self.assertNotIn('secret-for-tests',str(cm.exception))

    def test_template_and_trigger_parameters_preserve_structure(self):
        request=m.build_request('mcp_tool_call',{'slug':'github','tool':'search','arguments':{'q':'test'}})
        self.assertEqual(request['body'],{'q':'test'})
        with self.assertRaises(ValueError):m.validate('trigger_create',{'name':'daily','type':'cron','action':'run_app','app_id':'app1'})
        request=m.build_request('trigger_create',{'name':'daily','type':'cron','action':'run_app','app_id':'app1','config':{'expression':'0 9 * * *'}})
        self.assertEqual(request['body']['app_id'],'app1')

    def test_text_routes_are_not_parsed_as_json(self):
        http=FakeHTTP('# Skill content')
        result=m.execute('skill_content',{'namespace':'acme','name':'skill'},KEY,transport=http)
        self.assertEqual(result['content'],'# Skill content')
        self.assertEqual(http.calls[0]['response_kind'],'text')

    def test_upload_two_stage_no_credential_forwarding(self):
        row={'id':'file1','uri':'https://cloud.inference.sh/file1.txt',
             'upload_url':'https://storage.googleapis.com/test/file1?signature=abc'}
        http=FakeHTTP({'data':[row],'messages':[]},'')
        result=m.upload_file(b'hello','file.txt','text/plain',KEY,transport=http)
        self.assertEqual(result,{'id':'file1','uri':'https://cloud.inference.sh/file1.txt'})
        self.assertEqual(http.calls[0]['body']['files'][0]['size'],5)
        self.assertEqual(http.calls[1]['body'],b'hello')
        self.assertEqual(http.calls[1]['headers'],{'Content-Type':'text/plain'})
        self.assertEqual(http.calls[1]['method'],'PUT')
        self.assertNotIn('upload_url',result)

    def test_upload_rejects_foreign_hosts_and_errors_not_retried(self):
        for url in ['https://evil.example/x','http://cloud.inference.sh/x','https://user:pass@cloud.inference.sh/x']:
            http=FakeHTTP({'data':[{'uri':'https://cloud.inference.sh/x','upload_url':url}]})
            with self.assertRaises(MediaError):m.upload_file(b'1','a.txt','text/plain',KEY,transport=http)
            self.assertEqual(len(http.calls),1)
        http=FakeHTTP({'data':[{'uri':'https://cloud.inference.sh/x','upload_url':'https://cloud.inference.sh/x?sig=a'}]},MediaError('request_timeout'))
        with self.assertRaises(MediaError):m.upload_file(b'1','a.txt','text/plain',KEY,transport=http)
        self.assertEqual(len(http.calls),2)

    def test_validation_occurs_before_credentials(self):
        with self.assertRaises(ValueError):m.execute('task_get',{'id':'../bad'},{},transport=FakeHTTP())
        with self.assertRaises(MediaError):m.execute('task_get',{'id':'ok'},{},transport=FakeHTTP())
        with self.assertRaises(ValueError):m.validate('file_upload',{'content_base64':'!!!','filename':'a','content_type':'text/plain'})
        with self.assertRaises(ValueError):m.upload_file(b'1','../a','text/plain',KEY,transport=FakeHTTP())

    def test_metadata_copies_do_not_change_executable_authority(self):
        row=m.operation_contract('task_get');row['path']='https://evil.example/'
        self.assertEqual(m.build_request('task_get',{'id':'x'})['url'],'https://api.inference.sh/tasks/x')
        self.assertEqual(m.task_state({'status':10}),'completed')
        self.assertEqual(m.task_state({'status':11}),'failed')
        self.assertEqual(m.task_state({'status':12}),'cancelled')
        self.assertEqual(m.task_state({'status':2}),'queued')


if __name__=='__main__':unittest.main()
