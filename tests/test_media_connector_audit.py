"""Contract drift and reliability regressions; no provider calls or credentials."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from automation_integrations import fal_media, inference_media, media_api, media_runtime
from automation_integrations.api_read import Failure


class Response(io.BytesIO):
    def __init__(self, data=b'{}', status=200, **headers):
        super().__init__(data)
        self.status = status
        self.headers = headers

    def getheader(self, name, default=None):
        return self.headers.get(name, default)


class MediaTransportAuditTests(unittest.TestCase):
    def test_partial_success_body_is_not_accepted_as_json_or_media(self):
        for kind, body in [('json', b'{}'), ('binary', b'\x89PNG\r\n\x1a\npartial')]:
            response = Response(body, **{'Content-Length': str(len(body) + 12)})
            connection = Mock()
            with self.subTest(kind=kind), patch.object(media_runtime, '_open_response', return_value=(response, connection)) as opened:
                with self.assertRaisesRegex(media_runtime.MediaError, 'incomplete_provider_response'):
                    media_runtime.MediaHTTP().request('GET', 'https://api.fal.ai/v1/models', response_kind=kind)
                opened.assert_called_once()
                connection.close.assert_called_once()

    def test_partial_media_is_not_cached_as_successful_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = media_runtime.ArtifactStore(tmp)
            artifact = store.register('https://v3.fal.media/file.png', 'job')
            response = Response(b'\x89PNG\r\n\x1a\npartial', **{'Content-Length': '100'})
            with patch.object(media_runtime, '_public_addresses', return_value=['8.8.8.8']), \
                    patch.object(media_runtime, '_open_response', return_value=(response, Mock())):
                with self.assertRaisesRegex(media_runtime.MediaError, 'incomplete_provider_response'):
                    store.download_registered(artifact['id'])
            self.assertEqual(store.get(artifact['id'])['status'], 'remote')
            self.assertEqual(list(store.root.glob('*.png')), [])

    def test_head_and_no_content_allow_metadata_length_without_body(self):
        for method, status in [('HEAD', 200), ('DELETE', 204)]:
            response = Response(b'', status, **{'Content-Length': '100'})
            with self.subTest(method=method), patch.object(media_runtime, '_open_response', return_value=(response, Mock())):
                self.assertEqual(media_runtime.MediaHTTP().request(method, 'https://api.fal.ai/v1/models'), {})

    def test_retry_after_supports_http_date_and_survives_tool_boundary(self):
        now = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        response = Response(b'private body', 429, **{'Retry-After': 'Wed, 07 Oct 2026 12:01:30 GMT'})
        with patch.object(media_runtime.time, 'time', return_value=now), \
                patch.object(media_runtime, '_open_response', return_value=(response, Mock())):
            with self.assertRaises(Failure) as raised:
                media_api._call('fal', 'models', {}, {'FAL_KEY': 'fixture-key'})
        self.assertEqual(raised.exception.code, 'rate_limited')
        self.assertEqual(raised.exception.retry_after, 90)
        self.assertEqual(raised.exception.status, 429)
        self.assertNotIn('private', str(raised.exception))

    def test_boolean_query_values_use_wire_json_spelling(self):
        with patch.object(media_runtime, '_open_response', return_value=(Response(), Mock())) as opened:
            media_runtime.MediaHTTP().request('GET', 'https://api.fal.ai/v1/models',
                                             query={'flag': False, 'options': [True, False]})
        self.assertTrue(opened.call_args.args[1].endswith('flag=false&options=true&options=false'))

    def test_inference_upload_accepts_valid_new_bucket_without_forwarding_key(self):
        signed = 'https://new-account.r2.cloudflarestorage.com/object?signature=fixture'
        payload = {'data': [{'uri': 'https://cloud.inference.sh/output.png', 'upload_url': signed}]}
        responses = [(Response(json.dumps(payload).encode()), Mock()), (Response(b''), Mock())]
        with patch.object(media_runtime, '_open_response', side_effect=responses) as opened:
            result = media_api._call('inference', 'file_upload',
                {'filename': 'a.png', 'content_type': 'image/png', 'content_base64': 'eA=='},
                {'INFSH_API_KEY': 'fixture-key'})
        self.assertEqual(result['uri'], 'https://cloud.inference.sh/output.png')
        self.assertEqual(opened.call_args_list[1].args[1], signed)
        self.assertNotIn('Authorization', opened.call_args_list[1].args[2])
        self.assertNotIn('upload_url', result)


class MediaContractAuditTests(unittest.TestCase):
    def test_fal_start_timeout_uses_current_official_header(self):
        transport = Mock()
        transport.request.return_value = {'request_id': 'request-1'}
        fal_media.execute('submit', {'endpoint_id': 'fal-ai/model', 'input': {},
                          'options': {'start_timeout': .5}}, {'FAL_KEY': 'fixture'}, transport=transport)
        headers = transport.request.call_args.kwargs['headers']
        self.assertEqual(headers['X-Fal-Request-Start-Timeout'], '0.5')
        self.assertNotIn('X-Fal-Request-Timeout', headers)

    def test_fal_nonfinite_nested_input_fails_before_transport(self):
        for number in [float('nan'), float('inf'), -float('inf')]:
            transport = Mock()
            with self.subTest(number=number), self.assertRaisesRegex(ValueError, 'invalid_parameters'):
                fal_media.execute('submit', {'endpoint_id': 'fal-ai/model', 'input': {'scale': number}}, {}, transport=transport)
            transport.request.assert_not_called()

    def test_fal_new_sort_metrics_and_cursor_contracts(self):
        transport = Mock()
        transport.request.return_value = {'models': [], 'next_cursor': 'next-page'}
        result = fal_media.execute('models', {'sort': 'recent', 'cursor': 'previous', 'limit': 10},
                                   {'FAL_KEY': 'fixture'}, transport=transport)
        self.assertEqual(result['next_cursor'], 'next-page')
        self.assertEqual(transport.request.call_args.kwargs['query']['sort'], 'recent')
        with self.assertRaises(ValueError):
            fal_media.validate('models', {'sort': 'unsupported'})
        transport.request.return_value = '# HELP gpu metric\n'
        result = fal_media.execute('get_compute_metrics', {'compute_cluster': 'my-cluster'},
                                   {'FAL_KEY': 'fixture'}, transport=transport)
        self.assertEqual(result, {'text': '# HELP gpu metric\n'})
        self.assertEqual(transport.request.call_args.args[:2], ('GET', 'https://api.fal.ai/v1/compute/metrics'))
        self.assertNotIn('get_compute_metrics', fal_media.WRITE_OPERATIONS)

    def test_task_files_query_and_destructive_method_stay_separate(self):
        read = inference_media.build_request('task_files', {'id': 'task1', 'role': 'output'})
        delete = inference_media.build_request('task_files_delete', {'id': 'task1', 'role': 'output'})
        self.assertEqual((read['method'], read['query'], read['body']), ('GET', {'role': 'output'}, None))
        self.assertEqual((delete['method'], delete['query'], delete['body']), ('DELETE', {'role': 'output'}, None))
        self.assertIn('task_files_delete', inference_media.WRITE_OPERATIONS)
        remove = inference_media.build_request('task_delete', {'id': 'task1', 'files': False})
        self.assertEqual((remove['method'], remove['query'], remove['body']), ('DELETE', {'files': 'false'}, None))
        with self.assertRaises(Failure):
            media_api.validate('inference', 'task_files_delete', {'id': 'task1'})
        with self.assertRaises(ValueError):
            inference_media.validate('task_files', {'id': 'task1', 'role': 'all'})

    def test_current_sources_have_integrity_and_retired_routes_are_explicit(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'docs/media-api-snapshots/2026-10-07/manifest.json').read_text())
        self.assertEqual(len(manifest['sources']), 65)
        for source in manifest['sources']:
            raw = (root / source['local_snapshot']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source['sha256'])
        caps = json.loads((root / 'registry/capabilities/inference.json').read_text())
        self.assertEqual(len(caps['retired_capabilities']), 10)
        self.assertTrue(all(row['availability'] == 'retired' for row in caps['retired_capabilities']))
        methods = [row for row in caps['capabilities'] if row.get('method') in ('TRACE', 'CONNECT', 'QUERY')]
        self.assertEqual(len(methods), 57)
        self.assertTrue(all(row['availability'] == 'not_implemented' for row in methods))
        for provider in ('fal', 'inference'):
            inventory = json.loads((root / 'registry/capabilities' / (provider + '.json')).read_text())
            ids = [row['id'] for row in inventory['capabilities']]
            self.assertEqual(len(ids), len(set(ids)))
            runtime = next(row for row in inventory['capabilities'] if row['id'] == 'operation_schema')
            self.assertEqual(runtime['params_schema']['required'], ['operation'])


class FlowLifecycleAuditTests(unittest.TestCase):
    def test_queued_agent_message_tracks_its_answer_without_repeating_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {'state_dir': tmp, 'media_authorization': 'owner_command'}
            scope = ['owner', 'owner', 'session', '']
            context = {'scope': scope, 'message_id': 'one', 'owner_message': {
                'source': 'native_owner_telegram', 'scope': scope, 'message_id': 'one',
                'text_sha256': hashlib.sha256(b'Run the agent').hexdigest()}}
            vault = Mock()
            vault.get.return_value = {'INFSH_API_KEY': 'fixture-key'}
            user = {'id': 'message1', 'chat_id': 'chat1', 'role': 'user', 'status': 'queued', 'order': 10}
            earlier = {'id': 'earlier', 'role': 'assistant', 'status': 'ready', 'order': 9}
            later_user = {'id': 'other-user', 'role': 'user', 'status': 'ready', 'order': 11}
            later_answer = {'id': 'other-answer', 'role': 'assistant', 'status': 'ready', 'order': 12}
            own_answer = {'id': 'answer', 'role': 'assistant', 'status': 'ready', 'order': 11}
            pages = iter([
                {'items': [earlier, user]},
                {'items': [earlier, dict(user, status='ready'), later_user, later_answer]},
                {'items': [earlier, dict(user, status='ready'), own_answer]},
            ])
            calls = []
            def request(service, operation, params, secret, transport=None):
                calls.append(operation)
                if operation == 'agent_run':
                    return {'user_message': user}
                if operation == 'chat_get':
                    return {'id': 'chat1', 'status': 'idle'}
                if operation == 'chat_messages':
                    return next(pages)
                raise AssertionError(operation)

            with patch.object(media_api, '_call', side_effect=request):
                draft = media_api.process({'action': 'prepare', 'service': 'inference', 'operation': 'agent_run',
                    'params': {'agent': 'owner/agent', 'input': {'text': 'hello'}}}, context, config, vault=vault)
                sent = media_api.process({'action': 'execute', 'draft_id': draft['job_id']}, context, config, vault=vault)
                self.assertEqual((sent['status'], sent['provider_job_id']), ('submitted', 'message1'))
                for expected in ['queued', 'running', 'completed']:
                    result = media_api.read('inference', 'job_result', {'job_id': draft['job_id']}, config, vault=vault)
                    self.assertEqual(result['data']['status'], expected)
                self.assertEqual(result['data']['result']['messages'], [own_answer])
                before = len(calls)
                media_api.read('inference', 'job_result', {'job_id': draft['job_id']}, config, vault=vault)
                self.assertEqual(len(calls), before)
                self.assertEqual(calls.count('agent_run'), 1)
                self.assertNotIn('task_get', calls)
                self.assertNotIn('task_cost', calls)

    def test_failed_or_cancelled_tasks_reconcile_real_cost_instead_of_releasing_spend(self):
        for state in ['failed', 'cancelled']:
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                config = {'state_dir': tmp}
                jobs = media_runtime.JobStore(media_api.root(config))
                row, _ = jobs.prepare('fixture', {'operation': 'app_run', 'params': {}}, account='account', provider='inference')
                jobs.mark_submitting(row['job_id'], account='account')
                jobs.submitted(row['job_id'], 'task1', account='account')
                row = jobs.save_result(row['job_id'], {'status': 11}, account='account', state=state)
                ledger = media_runtime.BudgetLedger(media_api.root(config))
                ledger.reserve(row['job_id'], 'inference', '.2', account='account')
                with patch.object(media_api, '_call', return_value={'charged': 10000000, 'refunded': 5000000}):
                    row = media_api._reconcile_inference_cost(row, config, {}, None)
                self.assertEqual(row['metadata']['billing']['cost_usd'], '0.05')
                self.assertEqual(ledger.snapshot('inference')['reservations'][0]['state'], 'settled')

    def test_flow_tracks_flow_id_enum_and_parent_task_cost_without_resubmission(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {'state_dir': tmp, 'media_authorization': 'owner_command'}
            scope = ['owner', 'owner', 'session', '']
            context = {'scope': scope, 'message_id': 'one', 'owner_message': {
                'source': 'native_owner_telegram', 'scope': scope, 'message_id': 'one',
                'text_sha256': hashlib.sha256(b'Run this flow').hexdigest()}}
            vault = Mock()
            vault.get.return_value = {'INFSH_API_KEY': 'fixture-key'}
            calls = []
            states = iter([2, 3])

            def request(service, operation, params, secret, transport=None):
                calls.append((operation, params))
                if operation == 'flow_run':
                    return {'id': 'flow-run1', 'task_id': 'parent-task1', 'status': 1}
                if operation == 'flow_run_get':
                    return {'id': 'flow-run1', 'task_id': 'parent-task1', 'status': next(states), 'output': {'text': 'done'}}
                if operation == 'task_cost':
                    return {'charged': 10000000, 'refunded': 0}
                raise AssertionError(operation)

            with patch.object(media_api, '_call', side_effect=request):
                draft = media_api.process({'action': 'prepare', 'service': 'inference', 'operation': 'flow_run',
                    'params': {'flow': 'flow1', 'input': {}}}, context, config, vault=vault)
                sent = media_api.process({'action': 'execute', 'draft_id': draft['job_id']}, context, config, vault=vault)
                self.assertEqual((sent['status'], sent['provider_job_id']), ('submitted', 'flow-run1'))
                status = media_api.read('inference', 'job_status', {'job_id': draft['job_id']}, config, vault=vault)
                self.assertEqual(status['data']['status'], 'running')
                result = media_api.read('inference', 'job_result', {'job_id': draft['job_id']}, config, vault=vault)
                self.assertEqual(result['data']['status'], 'completed')
                self.assertEqual(result['data']['billing']['cost_usd'], '0.1')
                self.assertIn(('task_cost', {'taskID': 'parent-task1'}), calls)
                count = len(calls)
                media_api.read('inference', 'job_result', {'job_id': draft['job_id']}, config, vault=vault)
                self.assertEqual(len(calls), count)
                self.assertEqual(sum(op == 'flow_run' for op, _ in calls), 1)


if __name__ == '__main__':
    unittest.main()
