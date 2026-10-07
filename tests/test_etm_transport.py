"""Exercise curl's real config parser using a loopback-only HTTP fixture."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from automation_integrations.api_read import BASES, Failure, HTTP


class EchoHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.respond()

    def respond(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        self.server.requests.append({
            'method': self.command, 'path': self.path,
            'headers': self.headers, 'body': body,
        })
        status = 302 if self.path == '/redirect' else 200
        raw = json.dumps({'status': {'code': 200}, 'data': {'received': True}}).encode('utf-8')
        self.send_response(status)
        if status == 302:
            self.send_header('Location', '/unexpected-redirect-target')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@unittest.skipUnless(Path('/usr/bin/curl').is_file(), 'real curl is required')
class ETMCurlTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), EchoHandler)
        cls.server.requests = []
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.server.requests.clear()
        self.calls = []
        self.real_run = subprocess.run
        self.transport = HTTP('etm', {'etm_proxy': 'socks5h://127.0.0.1:10929'})
        self.local_base = f'http://127.0.0.1:{self.server.server_port}'
        self.base_patch = patch.dict(BASES, etm=self.local_base)
        self.run_patch = patch('automation_integrations.api_read.subprocess.run', side_effect=self.run_local_curl)
        self.base_patch.start()
        self.addCleanup(self.base_patch.stop)
        self.run_patch.start()
        self.addCleanup(self.run_patch.stop)

    def run_local_curl(self, args, **kwargs):
        # Keep the adapter's config bytes untouched: only replace production
        # routing with the loopback fixture so the real curl parser is tested.
        self.calls.append((list(args), kwargs))
        lines = kwargs['input'].decode('utf-8').splitlines()
        url = json.loads(next(line.removeprefix('url = ') for line in lines if line.startswith('url = ')))
        parsed = urlsplit(url)
        self.assertEqual(parsed.hostname, '127.0.0.1')
        self.assertEqual(parsed.port, self.server.server_port)
        self.assertEqual(args[args.index('--proxy') + 1], 'socks5h://127.0.0.1:10929')
        self.assertEqual(args[args.index('--proto') + 1], '=https')
        self.assertEqual(args[-2:], ['--config', '-'])
        self.assertEqual(args[1], '-q')
        self.assertNotIn('--location', args)
        local_args = list(args)
        local_args[local_args.index('--proxy') + 1] = ''
        local_args[local_args.index('--proto') + 1] = '=http'
        return self.real_run(local_args, **kwargs)

    def test_utf8_body_quotes_backslashes_and_controls_survive_real_curl(self):
        body = {
            'Remarks': 'Самовывоз: Волгоград, Университетский проспект, 85. 👷',
            'escaped': 'Кавычки "да"; слеш \\; буквальный \\u0410; строка\nтаб\tвозврат\r\b\f',
            'Order-Lines': [{'ItemDescription': 'ПуГВ 1×0,75 мм², белый', 'OrderedQuantity': 100}],
        }
        result = self.transport.call('POST', '/invoice/create', body=body,
                                     headers={'X-Fixture-Label': 'Проверка кодировки'})
        self.assertTrue(result['data']['received'])
        request = self.server.requests[-1]
        self.assertEqual(request['method'], 'POST')
        self.assertEqual(request['body'], json.dumps(body, ensure_ascii=False).encode('utf-8'))
        self.assertEqual(json.loads(request['body']), body)
        self.assertEqual(request['headers']['Content-Type'], 'application/json; charset=utf-8')
        self.assertEqual(request['headers']['X-Fixture-Label'].encode('latin1').decode('utf-8'), 'Проверка кодировки')
        self.assertIn(b'data-binary = ', self.calls[-1][1]['input'])

    def test_credentials_stay_on_stdin_and_query_round_trips(self):
        secrets = {'log': 'fixture-user', 'pwd': 'Пароль "сложный" \\ +&?#', 'session-id': 'fixture-session'}
        token = 'fixture-header-secret'
        self.transport.call('POST', '/user/login', query=secrets,
                            headers={'Authorization': 'Bearer ' + token})
        sent = self.server.requests[-1]
        self.assertEqual(parse_qs(urlsplit(sent['path']).query), {k: [v] for k, v in secrets.items()})
        self.assertEqual(sent['body'], b'')
        self.assertEqual(sent['headers']['Authorization'], 'Bearer ' + token)
        args, kwargs = self.calls[-1]
        for secret in (*secrets.values(), token):
            self.assertNotIn(secret, '\n'.join(args))
        self.assertIn(token.encode('utf-8'), kwargs['input'])
        self.assertTrue(kwargs['capture_output'])

    def test_redirect_is_rejected_without_following_it(self):
        with self.assertRaises(Failure) as raised:
            self.transport.call('GET', '/redirect')
        self.assertEqual(raised.exception.code, 'provider_http_error')
        self.assertEqual(raised.exception.status, 302)
        self.assertEqual([r['path'] for r in self.server.requests], ['/redirect'])

    def test_unconfigured_proxy_fails_before_curl(self):
        with self.assertRaisesRegex(Failure, '^etm_proxy_unconfigured$'):
            HTTP('etm', {}).call('GET', '/catalog')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.server.requests, [])

    def test_curl_diagnostics_never_escape_failure(self):
        failure = subprocess.CompletedProcess([], 7, b'', b'fixture-secret https://private.invalid/?pwd=secret')
        with patch('automation_integrations.api_read.subprocess.run', return_value=failure):
            with self.assertRaisesRegex(Failure, '^etm_proxy_request_failed$') as raised:
                self.transport.call('GET', '/catalog')
        self.assertNotIn('fixture-secret', str(raised.exception))
        self.assertNotIn('private.invalid', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
