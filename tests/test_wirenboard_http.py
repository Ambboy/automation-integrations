import io
import json
import shlex
import ssl
import subprocess
import types
import unittest
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

from automation_integrations import wirenboard_http as transport


class WirenboardHTTPTests(unittest.TestCase):
    SECRET = 'private-jwt-value'

    def call(self, method='GET', path='/users/me/', route='direct', **kwargs):
        return transport.call(method, path, headers={'Authorization': 'Bearer ' + self.SECRET},
                              config={'wirenboard_transport': route}, **kwargs)

    def response(self, raw=b'{"id":"user"}', status=200):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = status
        response.headers = {}
        response.read.return_value = raw
        opener = MagicMock()
        opener.open.return_value = response
        return opener, response

    def remote_response(self, data=None, status=200):
        return subprocess.CompletedProcess([], 0, stdout=json.dumps(
            {'ok': True, 'status': status, 'data': data}).encode(), stderr=None)

    def test_direct_fixed_origin_tls_no_proxy_and_bounded_read(self):
        opener, response = self.response()
        with patch('urllib.request.build_opener', return_value=opener) as build:
            self.assertEqual(self.call(), {'id': 'user'})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://wirenboard.cloud/api/v1/users/me/')
        self.assertEqual(request.get_header('Authorization'), 'Bearer ' + self.SECRET)
        self.assertEqual(opener.open.call_args.kwargs, {'timeout': 25})
        response.read.assert_called_once_with(2 * 1024 * 1024 + 1)
        handlers = build.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsInstance(handlers[1], urllib.request.HTTPRedirectHandler)
        self.assertTrue(handlers[2]._context.check_hostname)
        self.assertEqual(handlers[2]._context.verify_mode, ssl.CERT_REQUIRED)

    def test_ssh_credentials_only_stdin_constant_command_and_no_local_http(self):
        with patch('subprocess.run', return_value=self.remote_response({'id': 'user'})) as run, \
                patch('urllib.request.build_opener') as direct:
            self.assertEqual(self.call(route='ssh:example-hermes'), {'id': 'user'})
        argv = run.call_args.args[0]
        self.assertEqual(argv[:9], ['/usr/bin/ssh', '-T', '-o', 'BatchMode=yes', '-o',
                                   'ConnectTimeout=8', 'example-hermes', 'python3', '-c'])
        self.assertEqual(shlex.split(argv[9]), [transport._REMOTE_SCRIPT])
        self.assertNotIn(self.SECRET, str(argv))
        self.assertNotIn('StrictHostKeyChecking=no', str(argv))
        params = run.call_args.kwargs
        self.assertEqual(json.loads(params['input'])['headers']['Authorization'], 'Bearer ' + self.SECRET)
        self.assertEqual(params['timeout'], 40)
        self.assertEqual(params['stderr'], subprocess.DEVNULL)
        direct.assert_not_called()

    def test_refresh_token_only_in_stdin(self):
        with patch('subprocess.run', return_value=self.remote_response({'access': 'new-token'})) as run:
            result = self.call('POST', '/auth/token/refresh/', route='ssh:example-hermes',
                               body={'refresh': self.SECRET})
        self.assertEqual(result, {'access': 'new-token'})
        self.assertNotIn(self.SECRET, str(run.call_args.args))
        self.assertEqual(json.loads(run.call_args.kwargs['input'])['body'], {'refresh': self.SECRET})

    def test_configuration_and_paths_fail_before_network(self):
        invalid = [
            ('GET', 'https://attacker.invalid/users/me/'),
            ('GET', '//attacker.invalid/users/me/'),
            ('GET', '/controllers/../users/me/'),
            ('GET', '/controllers/%2e%2e/'),
            ('GET', '/users/me/?redirect=https://attacker.invalid'),
            ('GET', '/controllers/ABC/tcp-tunnels/'),
            ('POST', '/auth/login/'),
            ('DELETE', '/controllers/ABC/tcp-tunnels/ssh/'),
            ('get', '/users/me/'),
            ('POST', '/organizations/'),
        ]
        with patch('subprocess.run') as run, patch('urllib.request.build_opener') as direct:
            for method, path in invalid:
                with self.subTest(method=method, path=path), self.assertRaises(transport.TransportFailure) as error:
                    self.call(method, path, route='ssh:example-hermes')
                self.assertEqual(error.exception.code, 'unsupported_endpoint')
            for config in ({}, {'wirenboard_transport': 'ssh:attacker.invalid'},
                           {'wirenboard_transport': 'direct', 'wirenboard_base_url': 'https://attacker.invalid'}):
                with self.assertRaises(transport.TransportFailure):
                    transport.call('GET', '/users/me/', config=config)
        run.assert_not_called()
        direct.assert_not_called()

    def test_all_allowed_read_paths(self):
        org = '12345678-1234-4321-9876-123456789abc'
        cases = [('/users/me/', {}), ('/organizations/', {}),
                 ('/controllers/', {'organization_id': org, 'search': 'room & kitchen',
                                   'serial_number': 'WB_8-test', 'page': 2, 'page_size': 20}),
                 ('/controllers-count/', {}), ('/controllers/WB_8-test/', {}),
                 ('/controllers/WB_8-test/diagnostic/', {}),
                 ('/controllers/WB_8-test/last-metrics-time/', {}),
                 ('/controllers/WB_8-test/services/', {}),
                 ('/groups/', {'organization_id': org}), ('/groups/' + org + '/', {})]
        for path, query in cases:
            with self.subTest(path=path), patch('subprocess.run', return_value=self.remote_response([])):
                self.assertEqual(self.call(path=path, query=query, route='ssh:example-hermes'), [])

    def test_system_metrics_post_serializes_json(self):
        opener, _ = self.response(raw=b'[]')
        body = {'name': 'load15', 'start': '2026-10-04T00:00:00Z', 'stop': '2026-10-04T01:00:00Z'}
        with patch('urllib.request.build_opener', return_value=opener):
            self.assertEqual(self.call('POST', '/controllers/WB8/system-metrics/', body=body), [])
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(json.loads(request.data), body)
        self.assertEqual(request.get_header('Content-type'), 'application/json; charset=utf-8')

    def test_only_documented_management_routes_are_dispatched(self):
        group = '12345678-1234-4321-9876-123456789abc'
        cases = [
            ('PATCH', '/controllers/WB8/', {'description': 'Room controller'}),
            ('DELETE', '/controllers/WB8/', None),
            ('POST', '/controllers/WB8/request-diagnostic/', None),
            ('POST', '/controllers/WB8/services/', {'port': 8080, 'name': 'Dashboard'}),
            ('PATCH', '/controllers/WB8/services/8080/', {'name': 'Renamed dashboard'}),
            ('DELETE', '/controllers/WB8/services/65535/', None),
            ('POST', '/groups/', {'name': 'Room', 'organization': group}),
            ('PATCH', '/groups/' + group + '/', {'name': 'Hall'}),
            ('DELETE', '/groups/' + group + '/', None),
            ('POST', '/groups/' + group + '/attach-controllers/', {'controllers': ['WB8']}),
            ('POST', '/groups-detach-from-controllers/', {'controllers': ['WB8']}),
            ('POST', '/controllers/WB8/tcp-tunnels/ssh/', None),
            ('POST', '/controllers/WB8/tcp-tunnels/http/', None),
        ]
        for method, path, body in cases:
            with self.subTest(method=method, path=path), \
                    patch('subprocess.run', return_value=self.remote_response({})) as run:
                self.assertEqual(self.call(method, path, body=body, route='ssh:example-hermes'), {})
            request = json.loads(run.call_args.kwargs['input'])
            self.assertEqual((request['method'], request['path'], request['body']), (method, path, body))
            run.assert_called_once()

    def test_management_allowlist_rejects_arbitrary_targets_and_undocumented_methods(self):
        group = '12345678-1234-4321-9876-123456789abc'
        cases = [
            ('PUT', '/controllers/WB8/'),
            ('POST', '/controllers/'),
            ('GET', '/controllers/WB8/services/8080/'),
            ('POST', '/controllers/WB8/services/8080/'),
            ('PATCH', '/controllers/WB8/services/0/'),
            ('PATCH', '/controllers/WB8/services/65536/'),
            ('PATCH', '/controllers/WB8/services/00022/'),
            ('POST', '/controllers/WB8/tcp-tunnels/22/'),
            ('POST', '/controllers/WB8/tcp-tunnels/https/'),
            ('POST', '/controllers/WB8/tcp-tunnels/ssh/../http/'),
            ('POST', '/controllers/WB8/tcp-tunnels/ssh/?target=elsewhere'),
            ('POST', '/controllers/WB8/reboot/'),
            ('PATCH', '/controllers/WB8/diagnostic/'),
            ('DELETE', '/groups/'),
            ('DELETE', '/groups/' + group + '/attach-controllers/'),
            ('PATCH', 'https://attacker.invalid/controllers/WB8/'),
            ('POST', '//attacker.invalid/groups/'),
            ('PATCH', '/controllers/WB8%2f..%2fWB9/'),
        ]
        with patch('subprocess.run') as run, patch('urllib.request.build_opener') as direct:
            for method, path in cases:
                with self.subTest(method=method, path=path), self.assertRaises(transport.TransportFailure) as error:
                    self.call(method, path, body={}, route='ssh:example-hermes')
                self.assertEqual(error.exception.code, 'unsupported_endpoint')
        run.assert_not_called()
        direct.assert_not_called()

    def test_management_bodies_are_typed_and_bounded_before_network(self):
        cases = [
            ('PATCH', '/controllers/WB8/', None),
            ('PATCH', '/controllers/WB8/', []),
            ('PATCH', '/controllers/WB8/', {'description': 'x' * 65536}),
            ('POST', '/controllers/WB8/services/', 'port=8080'),
            ('POST', '/groups/', None),
            ('POST', '/groups-detach-from-controllers/', ['WB8']),
            ('POST', '/controllers/WB8/request-diagnostic/', {'command': 'reboot'}),
            ('POST', '/controllers/WB8/tcp-tunnels/ssh/', {'host': 'attacker.invalid'}),
            ('DELETE', '/controllers/WB8/', {'serial_number': 'WB9'}),
        ]
        with patch('subprocess.run') as run, patch('urllib.request.build_opener') as direct:
            for method, path, body in cases:
                with self.subTest(method=method, path=path), self.assertRaises(transport.TransportFailure) as error:
                    self.call(method, path, body=body, route='ssh:example-hermes')
                self.assertIn(error.exception.code, ('invalid_parameters', 'invalid_request'))
        run.assert_not_called()
        direct.assert_not_called()

    def test_empty_204_is_successful_direct_and_ssh(self):
        opener, response = self.response(raw=b'', status=204)
        with patch('urllib.request.build_opener', return_value=opener):
            self.assertIsNone(self.call('DELETE', '/controllers/WB8/services/8080/'))
        response.read.assert_called_once_with(2 * 1024 * 1024 + 1)
        request = {'method': 'DELETE', 'path': '/controllers/WB8/services/8080/',
                   'headers': {}, 'query': {}, 'body': None}
        worker_result = self.run_worker(json.dumps(request).encode(), opener)
        self.assertEqual(worker_result, {'ok': True, 'status': 204, 'data': None})
        ssh_response = subprocess.CompletedProcess([], 0, stdout=json.dumps(worker_result).encode())
        with patch('subprocess.run', return_value=ssh_response):
            self.assertIsNone(self.call('DELETE', request['path'], route='ssh:example-hermes'))

    def test_empty_200_is_allowed_only_where_documented(self):
        cases = [
            ('POST', '/controllers/WB8/request-diagnostic/', None, True),
            ('POST', '/groups-detach-from-controllers/', {'controllers': ['WB8']}, True),
            ('GET', '/controllers/WB8/', None, False),
            ('GET', '/controllers/WB8/services/', None, False),
            ('PATCH', '/controllers/WB8/', {'description': 'New'}, False),
            ('DELETE', '/controllers/WB8/', None, False),
            ('POST', '/controllers/WB8/tcp-tunnels/ssh/', None, False),
            ('POST', '/groups/12345678-1234-4321-9876-123456789abc/attach-controllers/', {'controllers': ['WB8']}, False),
        ]
        for method, path, body, allowed in cases:
            opener, _ = self.response(raw=b'', status=200)
            with self.subTest(method=method, path=path), patch('urllib.request.build_opener', return_value=opener):
                if allowed:
                    self.assertIsNone(self.call(method, path, body=body))
                else:
                    with self.assertRaises(transport.TransportFailure) as error:
                        self.call(method, path, body=body)
                    self.assertEqual(error.exception.code, 'invalid_json')

    def test_mutations_do_not_retry_after_authentication_or_uncertain_network_failure(self):
        failures = [urllib.error.HTTPError('https://wirenboard.cloud/', 401, self.SECRET, {}, io.BytesIO()),
                    urllib.error.URLError(self.SECRET)]
        for failure in failures:
            opener, _ = self.response()
            opener.open.side_effect = failure
            with self.subTest(kind=type(failure).__name__), \
                    patch('urllib.request.build_opener', return_value=opener), \
                    self.assertRaises(transport.TransportFailure) as error:
                self.call('PATCH', '/controllers/WB8/', body={'description': 'New'})
            self.assertIn(error.exception.code, ('authentication_failed', 'network_error'))
            self.assertNotIn(self.SECRET, str(error.exception))
            opener.open.assert_called_once()

    def test_rejects_unexpected_query_body_and_header_inputs(self):
        cases = [
            {'path': '/controllers/', 'query': {'next': 'https://attacker.invalid'}},
            {'path': '/controllers/', 'query': {'page': True}},
            {'path': '/controllers/', 'query': {'page_size': 101}},
            {'path': '/controllers/', 'query': {'organization_id': '../private'}},
            {'path': '/controllers/', 'query': {'search': '\nprivate'}},
            {'path': '/controllers-count/', 'query': {'page': 1}},
            {'path': '/users/me/', 'body': {'change': True}},
            {'method': 'POST', 'path': '/auth/token/refresh/', 'body': {'refresh': self.SECRET, 'url': 'https://attacker.invalid'}},
            {'method': 'POST', 'path': '/controllers/WB8/system-metrics/', 'body': {'name': 'write'}},
            {'path': '/users/me/', 'headers': {'Host': 'attacker.invalid'}},
            {'path': '/users/me/', 'headers': {'Authorization': 'Bearer secret\nX-Test: value'}},
            {'path': '/users/me/', 'headers': {'Authorization': 'A', 'authorization': 'B'}},
        ]
        with patch('subprocess.run') as run, patch('urllib.request.build_opener') as direct:
            for case in cases:
                with self.subTest(case=case), self.assertRaises(transport.TransportFailure):
                    transport.call(case.pop('method', 'GET'), config={'wirenboard_transport': 'ssh:example-hermes'}, **case)
        run.assert_not_called()
        direct.assert_not_called()

    def test_redirect_is_never_followed(self):
        for status in (301, 302, 303, 307, 308):
            opener, _ = self.response()
            def redirect(*args, **kwargs):
                return transport._worker['NoRedirect']().redirect_request(
                    args[0], None, status, '', {}, 'https://' + self.SECRET + '@attacker.invalid/')
            opener.open.side_effect = redirect
            with self.subTest(status=status), patch('urllib.request.build_opener', return_value=opener), \
                    self.assertRaises(transport.TransportFailure) as error:
                self.call()
            self.assertEqual(error.exception.code, 'redirect_refused')
            self.assertEqual(error.exception.status, status)
            self.assertNotIn(self.SECRET, str(error.exception))
            opener.open.assert_called_once()

    def test_http_errors_are_classified_without_body_or_url(self):
        for status, code in [(400, 'provider_http_error'), (401, 'authentication_failed'),
                             (403, 'access_denied'), (404, 'resource_not_found'),
                             (429, 'rate_limited'), (500, 'provider_unavailable'),
                             (503, 'provider_unavailable'), (304, 'redirect_refused')]:
            opener, _ = self.response()
            provider_body = io.BytesIO(self.SECRET.encode())
            opener.open.side_effect = urllib.error.HTTPError(
                'https://' + self.SECRET + '@wirenboard.cloud/', status, self.SECRET,
                {'Retry-After': '99999999'}, provider_body)
            with self.subTest(status=status), patch('urllib.request.build_opener', return_value=opener), \
                    self.assertRaises(transport.TransportFailure) as error:
                self.call()
            self.assertEqual(error.exception.code, code)
            self.assertEqual(error.exception.status, status)
            self.assertEqual(error.exception.retry_after, 86400 if status == 429 else None)
            self.assertNotIn(self.SECRET, str(error.exception))
            self.assertTrue(provider_body.closed)

    def test_response_size_and_json_validation(self):
        for raw, code in [(b'x' * (2 * 1024 * 1024 + 1), 'response_too_large'),
                          (self.SECRET.encode(), 'invalid_json'), (b'\xff', 'invalid_json'),
                          (b'{"value":NaN}', 'invalid_json')]:
            opener, _ = self.response(raw=raw)
            with self.subTest(code=code), patch('urllib.request.build_opener', return_value=opener), \
                    self.assertRaises(transport.TransportFailure) as error:
                self.call()
            self.assertEqual(error.exception.code, code)
            self.assertNotIn(self.SECRET, str(error.exception))

    def test_ssh_failure_has_no_fallback_no_retry_and_no_diagnostics(self):
        for failure in [subprocess.CompletedProcess([], 255, stdout=self.SECRET.encode(), stderr=self.SECRET),
                        subprocess.TimeoutExpired('ssh ' + self.SECRET, 40, output=self.SECRET),
                        OSError(self.SECRET)]:
            options = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure}
            with self.subTest(failure=type(failure).__name__), patch('subprocess.run', **options) as run, \
                    patch('urllib.request.build_opener') as direct, self.assertRaises(transport.TransportFailure) as error:
                self.call(route='ssh:example-hermes')
            self.assertEqual(error.exception.code, 'wirenboard_ssh_request_failed')
            self.assertNotIn(self.SECRET, str(error.exception))
            run.assert_called_once()
            direct.assert_not_called()

    def test_ssh_sanitizes_invalid_worker_output(self):
        cases = [b'private-jwt-value', b'[]',
                 b'{"ok":true,"status":302,"data":{}}',
                 b'{"ok":false,"status":401,"code":"private-jwt-value","retry_after":null}',
                 b'{"ok":false,"status":429,"code":"rate_limited","retry_after":999999}',
                 b'{"ok":false,"status":true,"code":"authentication_failed","retry_after":null}']
        for raw in cases:
            response = subprocess.CompletedProcess([], 0, stdout=raw)
            with self.subTest(raw=raw), patch('subprocess.run', return_value=response), \
                    self.assertRaises(transport.TransportFailure) as error:
                self.call(route='ssh:example-hermes')
            self.assertEqual(error.exception.code, 'wirenboard_ssh_request_failed')
            self.assertNotIn(self.SECRET, str(error.exception))

    def test_ssh_preserves_only_safe_error_fields(self):
        response = subprocess.CompletedProcess([], 0, stdout=json.dumps(
            {'ok': False, 'status': 429, 'code': 'rate_limited', 'retry_after': 23}).encode())
        with patch('subprocess.run', return_value=response), self.assertRaises(transport.TransportFailure) as error:
            self.call(route='ssh:example-hermes')
        self.assertEqual((error.exception.code, error.exception.status, error.exception.retry_after),
                         ('rate_limited', 429, 23))

    def test_ssh_refuses_oversized_worker_output(self):
        response = subprocess.CompletedProcess([], 0, stdout=b'x' * (transport._MAX_OUTPUT + 1))
        with patch('subprocess.run', return_value=response), self.assertRaises(transport.TransportFailure) as error:
            self.call(route='ssh:example-hermes')
        self.assertEqual(error.exception.code, 'response_too_large')

    def test_direct_network_and_tls_setup_errors_are_sanitized(self):
        for failure in (OSError(self.SECRET), ssl.SSLError(self.SECRET)):
            with patch('urllib.request.build_opener', side_effect=failure), \
                    self.assertRaises(transport.TransportFailure) as error:
                self.call()
            self.assertEqual(error.exception.code, 'network_error')
            self.assertNotIn(self.SECRET, str(error.exception))

    def run_worker(self, raw, opener):
        output = io.BytesIO()
        with patch('sys.stdin', types.SimpleNamespace(buffer=io.BytesIO(raw))), \
                patch('sys.stdout', types.SimpleNamespace(buffer=output)), \
                patch('urllib.request.build_opener', return_value=opener):
            exec(compile(transport._REMOTE_SCRIPT, '<test-wb-worker>', 'exec'), {'__name__': '__main__'})
        return json.loads(output.getvalue())

    def test_remote_worker_standalone_protocol_and_bounded_stdin(self):
        opener, _ = self.response(raw=b'{"description":"\xd0\xba\xd1\x83\xd1\x85\xd0\xbd\xd1\x8f"}')
        request = {'method': 'GET', 'path': '/users/me/', 'headers': {}, 'query': {}, 'body': None}
        self.assertEqual(self.run_worker(json.dumps(request).encode(), opener),
                         {'ok': True, 'status': 200, 'data': {'description': 'кухня'}})
        opener.reset_mock()
        self.assertEqual(self.run_worker(b'x' * 65537, opener)['code'], 'invalid_request')
        opener.open.assert_not_called()

    def test_remote_worker_error_contains_no_request_or_exception(self):
        opener, _ = self.response()
        opener.open.side_effect = urllib.error.URLError(self.SECRET)
        request = {'method': 'GET', 'path': '/users/me/', 'headers': {'Authorization': self.SECRET},
                   'query': {}, 'body': None}
        result = self.run_worker(json.dumps(request).encode(), opener)
        self.assertEqual(result, {'ok': False, 'code': 'network_error', 'status': None, 'retry_after': None})
        self.assertNotIn(self.SECRET, json.dumps(result))


if __name__ == '__main__':
    unittest.main()
