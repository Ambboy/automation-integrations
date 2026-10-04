import base64
import json
import re
import subprocess
import types
import unittest
from unittest.mock import patch

from automation_integrations.wirenboard_shell import ShellFailure, ShellTransport, _REMOTE_SCRIPT


class Response:
    def __init__(self, status=200, headers=None, data=None):
        self.status_code, self.headers = status, headers or {}
        self.data = {'id': 'terminal-id', 'client_id': 'terminal-client-id'} if data is None else data
        self.closed = False

    def close(self):
        self.closed = True

    def iter_content(self, size):
        yield json.dumps(self.data).encode()


class Session:
    def __init__(self, responses=None):
        self.responses = list(responses or [Response()])
        self.cookies = {'tunnel_key': 'COOKIE_SECRET'}
        self.gets, self.posts = [], []
        self.trust_env = True
        self.closed = False

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return Response()

    def close(self):
        self.closed = True


class WebSocket:
    def __init__(self, output='root\n', exit_code=0, error=None):
        self.output, self.exit_code, self.error = output, exit_code, error
        self.messages = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def send(self, message):
        self.messages.append(json.loads(message))

    def recv(self, timeout):
        if self.error:
            raise self.error
        launcher = self.messages[-1]['data']
        encoded = launcher.split('printf %s ', 1)[1].split(' | base64', 1)[0]
        script = base64.b64decode(encoded).decode()
        start = re.search(r'__WB_START_[0-9a-f]+__', script).group()
        end = re.search(r'__WB_END_[0-9a-f]+__', script).group()
        return launcher + '\r\n' + start + '\r\n' + self.output + '\n' + end + ':' + str(self.exit_code) + '\r\n'


class WirenboardShellTests(unittest.TestCase):
    def setUp(self):
        self.worker = {'__name__': 'test_worker'}
        exec(_REMOTE_SCRIPT, self.worker)
        self.request = {'serial_number': 'A6OBXTJV', 'tunnel_url': 'https://a6obxtjv.ssh.wirenboard.cloud/?key=URL_SECRET',
                        'command': ['id', '-u'], 'credentials': {}, 'timeout': 30}

    def perform(self, session=None, websocket=None):
        session = session or Session()
        websocket = websocket or WebSocket()
        connect = unittest.mock.Mock(return_value=websocket)
        modules = {'requests': types.SimpleNamespace(Session=lambda: session),
                   'websockets.sync.client': types.SimpleNamespace(connect=connect)}
        with patch.dict('sys.modules', modules):
            result = self.worker['perform'](self.request)
        return result, session, websocket, connect

    def test_terminal_protocol_frames_result_preserves_exit_and_tls(self):
        result, session, socket, connect = self.perform(websocket=WebSocket(output='test\n', exit_code=7))
        self.assertEqual(result, {'stdout': 'test\n', 'exit_code': 7})
        self.assertFalse(session.trust_env)
        self.assertTrue(session.closed)
        self.assertTrue(session.gets[0][1]['verify'])
        self.assertFalse(session.gets[0][1]['allow_redirects'])
        self.assertTrue(session.posts[0][1]['verify'])
        self.assertFalse(session.posts[0][1]['allow_redirects'])
        self.assertEqual(set(session.posts[0][1]['files']), {'username', 'password', 'privatekey', 'passphrase'})
        self.assertTrue(connect.call_args.args[0].startswith('wss://a6obxtjv.ssh.wirenboard.cloud/ws?'))
        self.assertIsNone(connect.call_args.kwargs['proxy'])
        self.assertEqual(socket.messages[0], {'resize': [160, 50]})

    def test_arbitrary_or_wrong_controller_tunnel_url_rejected_before_network(self):
        for url in ['http://a6obxtjv.ssh.wirenboard.cloud/', 'https://other.ssh.wirenboard.cloud/',
                    'https://a6obxtjv.ssh.wirenboard.cloud.evil.test/', 'https://user@a6obxtjv.ssh.wirenboard.cloud/',
                    'https://a6obxtjv.ssh.wirenboard.cloud:444/', 'https://a6obxtjv.ssh.wirenboard.cloud/#fragment',
                    'https://127.0.0.1/', 'https://a6obxtjv.ssh.wirenboard.cloud/\r\n']:
            self.request['tunnel_url'] = url
            with self.assertRaises(self.worker['WorkerFailure']):
                self.worker['validate'](self.request)

    def test_foreign_redirect_does_not_receive_credentials_or_cookie(self):
        session = Session([Response(302, {'Location': 'https://example.com/leak'})])
        with self.assertRaises(self.worker['WorkerFailure']) as error:
            self.perform(session=session)
        self.assertEqual(error.exception.code, 'untrusted_tunnel_origin')
        self.assertEqual(len(session.gets), 1)
        self.assertEqual(session.posts, [])
        self.assertTrue(session.closed)

    def test_same_origin_redirect_allowed_and_private_fields_redacted(self):
        session = Session([Response(302, {'Location': '/'}), Response()])
        self.request['credentials'] = {'password': 'OVERRIDE_SECRET'}
        socket = WebSocket(output='URL_SECRET COOKIE_SECRET OVERRIDE_SECRET terminal-id terminal-client-id')
        result, session, _, _ = self.perform(session, socket)
        self.assertEqual(len(session.gets), 2)
        self.assertNotIn('SECRET', result['stdout'])
        self.assertNotIn('terminal-id', result['stdout'])

    def test_no_retry_after_command_send_failure(self):
        session, socket = Session(), WebSocket(error=TimeoutError('SENSITIVE_DETAILS'))
        with self.assertRaises(self.worker['WorkerFailure']) as error:
            self.perform(session, socket)
        self.assertEqual(error.exception.code, 'shell_outcome_unknown')
        self.assertNotIn('SENSITIVE_DETAILS', str(error.exception))
        self.assertEqual(len(session.posts), 1)
        self.assertEqual(len(socket.messages), 2)

    def test_stdout_bound_and_false_completion_markers(self):
        parser = self.worker['extract_result']
        self.assertIsNone(parser('echo START END:0\n', 'START', 'END'))
        self.assertIsNone(parser('START\nEND:999\n', 'START', 'MISSING'))
        with self.assertRaises(self.worker['WorkerFailure']):
            parser('START\n' + 'x' * 65537 + '\nEND:0\n', 'START', 'END')
        self.assertEqual(parser('START\n\x1b[31mhello\x1b[0m\nEND:4\n', 'START', 'END'), ('hello', 4))

    def test_live_auth_failure_shape_is_classified_without_provider_status(self):
        with self.assertRaises(self.worker['WorkerFailure']) as error:
            self.worker['terminal_ids']({'id': None, 'encoding': None, 'status': 'PRIVATE_STATUS',
                                         'error_code': 'error.auth_failed'})
        self.assertEqual(error.exception.code, 'ssh_authentication_failed')
        self.assertNotIn('PRIVATE_STATUS', str(error.exception))
        with self.assertRaises(self.worker['WorkerFailure']) as error:
            self.worker['terminal_ids']({'id': None, 'status': 'PRIVATE_STATUS', 'error_code': 'error.other'})
        self.assertEqual(error.exception.code, 'terminal_session_rejected')
        self.assertEqual(self.worker['terminal_ids']({'id': 123, 'client_id': 'client-id'}),
                         {'id': '123', 'client_id': 'client-id'})

    def test_shell_values_only_stdin_and_worker_errors_never_expose_stderr(self):
        response = subprocess.CompletedProcess([], 0, stdout=json.dumps({'ok': True, 'data': {'stdout': '0\n', 'exit_code': 0}}), stderr='SECRET')
        with patch('subprocess.run', return_value=response) as run:
            result = ShellTransport().call('A6OBXTJV', self.request['tunnel_url'], ['printf', 'COMMAND_SECRET'],
                                           {'password': 'PASSWORD_SECRET'})
        self.assertEqual(result['exit_code'], 0)
        argv = run.call_args.args[0]
        for secret in ['URL_SECRET', 'COMMAND_SECRET', 'PASSWORD_SECRET']:
            self.assertNotIn(secret, repr(argv))
            self.assertIn(secret, run.call_args.kwargs['input'])
        response.returncode = 1
        with patch('subprocess.run', return_value=response):
            with self.assertRaises(ShellFailure) as error:
                ShellTransport().call('A6OBXTJV', self.request['tunnel_url'], ['id'])
        self.assertNotIn('SECRET', str(error.exception))

    def test_invalid_inputs_never_launch_ssh(self):
        with patch('subprocess.run') as run:
            for kwargs in [{'command': []}, {'command': ['id\x00']}, {'command': ['id'], 'timeout': 31},
                           {'command': ['id'], 'timeout': True}, {'command': ['id'], 'credentials': {'unexpected': 'x'}}]:
                with self.assertRaises(ShellFailure):
                    ShellTransport().call('A6OBXTJV', self.request['tunnel_url'], **kwargs)
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
