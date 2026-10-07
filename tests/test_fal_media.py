import base64
import hashlib
import json
from pathlib import Path
import unittest

from automation_integrations import fal_media as fal


class Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0) if self.responses else {}
        if isinstance(response, Exception):
            raise response
        return response


class FalMediaTests(unittest.TestCase):
    def test_documented_surface_covers_both_specs_by_operation_id(self):
        root = Path(__file__).resolve().parents[1] / fal.DOCUMENTED['source_snapshot_dir']
        expected = set()
        for name in ('platform-openapi.json', 'platform-doc-openapi.json'):
            spec = json.loads((root / name).read_text())
            expected.update(row['operationId'] for ops in spec['paths'].values() for method, row in ops.items()
                            if method in ('get', 'put', 'post', 'delete', 'patch'))
        self.assertEqual({row['provider_operation_id'] for row in fal.PLATFORM_OPERATIONS.values()}, expected)
        self.assertEqual(len(expected), 89)
        for source in json.loads((root / 'provenance.json').read_text()):
            self.assertEqual(hashlib.sha256((root / source['file']).read_bytes()).hexdigest(), source['sha256'])

    def test_discovery_and_schema_do_not_limit_models(self):
        for name, params in [('models', {'q': 'training', 'category': 'training', 'limit': 25, 'cursor': 'next'}),
                             ('model_schema', {'endpoint_id': 'new-owner/new-model/arbitrary/version'})]:
            transport = Transport({'models': [{'endpoint_id': 'new-owner/new-model/arbitrary/version',
                'openapi': {'arbitrary': 'schema'}}]})
            result = fal.execute(name, params, {'FAL_KEY': 'api-key'}, transport=transport)
            self.assertEqual(result['models'][0]['openapi'], {'arbitrary': 'schema'})
            self.assertEqual(transport.calls[0][1], 'https://api.fal.ai/v1/models')
        self.assertEqual(transport.calls[0][2]['query']['expand'], 'openapi-3.0')

    def test_model_schema_preserves_fields_that_are_schema_names(self):
        schema = {'models': [{'openapi': {'components': {'schemas': {'Input': {'properties': {
            'token': {'type': 'string'}, 'secret': {'type': 'boolean'}}}}}}}]}
        transport = Transport(schema)
        result = fal.execute('model_schema', {'endpoint_id': 'owner/model'}, {'FAL_KEY': 'key'}, transport=transport)
        self.assertEqual(result, schema)

    def test_submit_preserves_full_input_and_all_platform_controls(self):
        transport = Transport({'request_id': 'request-1', 'status_url': 'https://queue.fal.run/new/model/requests/request-1/status'})
        params = {'endpoint_id': 'new/model/version/edit', 'input': {'prompt': 'Привет',
            'lora': {'url': 'https://example.org/model.safetensors'}, 'arbitrary_model_param': [1, 2]},
            'options': {'webhook_url': 'https://example.org/callback', 'start_timeout': 25, 'priority': 'low',
                'hint': 'runner-1', 'lifecycle': {'expiration_duration_seconds': 3600},
                'store_io': False, 'no_retry': True, 'disable_fallback': True, 'max_queue_length': 10,
                'retry_config': {'timeout': {'retries': 0}}, 'tags': {'PROJECT': 'greif'}}}
        result = fal.execute('submit', params, {'FAL_KEY': 'api-key', 'FAL_ADMIN_KEY': 'admin-key'}, transport=transport)
        method, url, req = transport.calls[0]
        self.assertEqual((method, url), ('POST', 'https://queue.fal.run/new/model/version/edit'))
        self.assertEqual(req['body'], params['input'])
        self.assertEqual(req['headers']['Authorization'], 'Key api-key')
        self.assertEqual(req['headers']['X-Fal-Store-IO'], '0')
        self.assertEqual(req['headers']['X-Fal-Tags'], 'project=greif')
        self.assertEqual(req['query'], {'fal_webhook': 'https://example.org/callback', 'fal_max_queue_length': 10})
        self.assertEqual(result['request_id'], 'request-1')
        self.assertEqual(result['endpoint_id'], params['endpoint_id'])

    def test_status_result_cancel_route_app_not_subpath(self):
        for endpoint, prefix in [('fal-ai/flux/dev', 'fal-ai/flux'),
            ('workflows/person/pipeline/extra', 'workflows/person/pipeline'), ('comfy/person/app', 'comfy/person/app')]:
            for op, suffix, method in [('status', '/status', 'GET'), ('result', '', 'GET'), ('cancel', '/cancel', 'PUT')]:
                transport = Transport({'status': 'CANCELLATION_REQUESTED'})
                fal.execute(op, {'endpoint_id': endpoint, 'request_id': 'r-1', 'logs': True}, {'FAL_KEY': 'key'}, transport=transport)
                self.assertEqual(transport.calls[0][:2], (method, 'https://queue.fal.run/' + prefix + '/requests/r-1' + suffix))

    def test_bad_paths_and_headers_rejected_before_transport(self):
        for endpoint in ['https://evil.example/a', 'fal-ai/../keys', 'fal-ai/%2e%2e', 'fal-ai/model?x=1', 'fal-ai/model#x', 'fal-ai/model\r\nX: x']:
            with self.assertRaises(ValueError):
                fal.validate('submit', {'endpoint_id': endpoint, 'input': {}})
        for params in [{'owner': '..', 'name': 'app'}, {'owner': 'person', 'name': 'a/b'}]:
            with self.assertRaises(ValueError):
                fal.validate('serverless_get_app_queue_info', params)
        with self.assertRaises(ValueError):
            fal.validate('submit', {'endpoint_id': 'fal-ai/model', 'input': {}, 'options': {'hint': 'x\r\nAuthorization: bad'}})
        with self.assertRaises(ValueError):
            fal.validate('submit', {'endpoint_id': 'fal-ai/model', 'input': {}, 'options': {'tags': {'ok': 'a,b'}}})
        with self.assertRaises(ValueError):
            fal.validate('submit', {'endpoint_id': 'fal-ai/model', 'input': {}, 'headers': {'Authorization': 'bad'}})

    def test_admin_key_used_only_for_documented_admin_operation(self):
        transport = Transport({'balance': 12}, {'models': []})
        creds = {'FAL_KEY': 'api-key', 'FAL_ADMIN_KEY': 'admin-key'}
        fal.execute('billing', {'expand': ['credits']}, creds, transport=transport)
        fal.execute('models', {}, creds, transport=transport)
        self.assertEqual(transport.calls[0][2]['headers']['Authorization'], 'Key admin-key')
        self.assertEqual(transport.calls[1][2]['headers']['Authorization'], 'Key api-key')

    def test_api_key_can_attempt_admin_reads_without_preventing_inference(self):
        transport = Transport(Error403 := fal.Error('provider_http_error', 403), {'request_id': 'r-2'})
        with self.assertRaises(fal.Error) as error:
            fal.execute('billing', {}, {'FAL_KEY': 'key'}, transport=transport)
        self.assertEqual(error.exception.status, 403)
        result = fal.execute('submit', {'endpoint_id': 'owner/model', 'input': {}}, {'FAL_KEY': 'key'}, transport=transport)
        self.assertEqual(result['request_id'], 'r-2')
        self.assertEqual(len(transport.calls), 2)

    def test_pricing_union_validates_both_methods_and_rejects_missing_units(self):
        for method, metric in [('unit_price', 'unit_quantity'), ('historical_api_price', 'call_quantity')]:
            p = {'body': {'estimate_type': method, 'endpoints': {'owner/model': {metric: 2}}}}
            transport = Transport({'total_cost': 0.08, 'currency': 'USD'})
            self.assertEqual(fal.execute('estimate', p, {'FAL_KEY': 'key'}, transport=transport)['total_cost'], 0.08)
            self.assertEqual(transport.calls[0][2]['body'], p['body'])
        with self.assertRaises(ValueError):
            fal.validate('estimate', {'body': {'estimate_type': 'unit_price', 'endpoints': {'owner/model': {'call_quantity': 1}}}})

    def test_http_timeout_does_not_retry_paid_request(self):
        transport = Transport(TimeoutError('uncertain response'))
        with self.assertRaises(TimeoutError):
            fal.execute('submit', {'endpoint_id': 'owner/model', 'input': {}}, {'FAL_KEY': 'key'}, transport=transport)
        self.assertEqual(len(transport.calls), 1)

    def test_upload_never_sends_provider_key_to_signed_storage(self):
        params = {'file_name': 'image.png', 'content_type': 'image/png', 'data_base64': base64.b64encode(b'PNG bytes').decode()}
        transport = Transport({'upload_url': 'https://storage.googleapis.com/fal/input?signature=abc',
            'file_url': 'https://v3.fal.media/files/x/image.png'}, '')
        result = fal.execute('upload', params, {'FAL_KEY': 'key'}, transport=transport)
        self.assertEqual(transport.calls[0][1], 'https://rest.fal.ai/storage/upload/initiate')
        self.assertEqual(transport.calls[1][2]['headers'], {'Content-Type': 'image/png'})
        self.assertEqual(transport.calls[1][2]['body'], b'PNG bytes')
        self.assertEqual(result['url'], 'https://v3.fal.media/files/x/image.png')

    def test_upload_rejects_untrusted_signed_url(self):
        params = {'file_name': 'image.png', 'content_type': 'image/png', 'data_base64': 'eA=='}
        for url in ['https://evil.example/x', 'http://storage.googleapis.com/x', 'https://storage.googleapis.com@evil.example/x', 'https://storage.googleapis.com:444/x']:
            transport = Transport({'upload_url': url, 'file_url': 'https://v3.fal.media/files/x'})
            with self.assertRaises(fal.Error):
                fal.execute('upload', params, {'FAL_KEY': 'key'}, transport=transport)
            self.assertEqual(len(transport.calls), 1)

    def test_local_bytes_upload_bypasses_tool_payload_limit_and_validates_size(self):
        transport = Transport({'upload_url': 'https://storage.googleapis.com/fal/input?signature=abc',
                               'file_url': 'https://v3.fal.media/files/x/input.png'}, '')
        payload = b'x' * 64000
        result = fal.upload_file(payload, 'input.png', 'image/png', {'FAL_KEY': 'key'}, transport=transport)
        self.assertEqual(transport.calls[1][2]['body'], payload)
        self.assertEqual(result['size_bytes'], 64000)
        for payload in (b'', b'x' * (8 * 1024 * 1024 + 1), 'not bytes'):
            no_network = Transport()
            with self.assertRaises(ValueError):
                fal.upload_file(payload, 'input.png', 'image/png', {}, transport=no_network)
            self.assertEqual(no_network.calls, [])

    def test_multipart_and_file_download_remain_json_serializable(self):
        params = {'target_path': 'datasets/image.png', 'body': {'file_name': 'image.png', 'content_type': 'image/png', 'data_base64': 'eA=='}}
        transport = Transport({'uploaded': True}, b'dataset')
        fal.execute('serverless_upload_local_file', params, {'FAL_KEY': 'key'}, transport=transport)
        self.assertIn(b'name="file_upload"; filename="image.png"', transport.calls[0][2]['body'])
        self.assertIn(b'\r\n\r\nx\r\n', transport.calls[0][2]['body'])
        result = fal.execute('serverless_download_file', {'file': 'datasets/image.png'}, {'FAL_KEY': 'key'}, transport=transport)
        self.assertEqual(base64.b64decode(result['data_base64']), b'dataset')
        json.dumps(result)

    def test_stream_and_status_stream_parse_sse(self):
        raw = 'event: update\r\ndata: {"value":1}\r\n\r\ndata: {"value":2}\n\ndata: [DONE]\n\n'
        transport = Transport(raw, raw)
        result = fal.execute('stream', {'endpoint_id': 'owner/model', 'input': {}}, {'FAL_KEY': 'key'}, transport=transport)
        self.assertEqual(result, {'events': [{'value': 1}, {'value': 2}]})
        self.assertEqual(transport.calls[0][1], 'https://fal.run/owner/model/stream')
        fal.execute('status_stream', {'endpoint_id': 'owner/model/sub', 'request_id': 'r1'}, {'FAL_KEY': 'key'}, transport=transport)
        self.assertEqual(transport.calls[1][1], 'https://queue.fal.run/owner/model/requests/r1/status/stream')

    def test_non_mutating_posts_are_not_confirmation_operations(self):
        for name in ('estimate', 'estimate_pricing', 'serverless_logs_history', 'serverless_logs_stream'):
            self.assertNotIn(name, fal.WRITE_OPERATIONS)
        for name in ('create_workflow', 'create_compute_instance', 'set_storage_file_acl', 'delete_api_key', 'submit'):
            self.assertIn(name, fal.WRITE_OPERATIONS)

    def test_unsupported_capabilities_are_visible_but_fail_before_secret_or_network(self):
        capabilities = fal.execute('capabilities', {}, {})
        self.assertEqual(capabilities['platform_operations'], 89)
        for op, params in [('realtime', {'endpoint_id': 'owner/model'}), ('http_websocket', {'endpoint_id': 'owner/model'}),
                           ('create_api_key', {'body': {'alias': 'greif'}})]:
            self.assertTrue(capabilities['operations'][op]['unsupported_reason'])
            transport = Transport()
            with self.assertRaises(ValueError):
                fal.execute(op, params, {}, transport=transport)
            self.assertEqual(transport.calls, [])

    def test_keys_listing_redacts_secrets(self):
        transport = Transport({'keys': [{'key_id': 'id', 'key_secret': 'secret-text', 'alias': 'main'}]})
        result = fal.execute('list_api_keys', {}, {'FAL_KEY': 'key'}, transport=transport)
        self.assertEqual(result['keys'][0]['key_secret'], '[REDACTED]')
        self.assertNotIn('secret-text', json.dumps(result))

    def test_public_docs_have_no_auth(self):
        transport = Transport('Model documentation')
        result = fal.execute('model_documentation', {'endpoint_id': 'owner/model/version'}, {'FAL_KEY': 'key'}, transport=transport)
        self.assertEqual(transport.calls[0][2]['headers'], {})
        self.assertEqual(result, {'text': 'Model documentation'})


if __name__ == '__main__':
    unittest.main()
