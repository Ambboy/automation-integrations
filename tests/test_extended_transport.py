import http.server
import http.client
import json
import shutil
import subprocess
import threading
import unittest
from unittest.mock import patch

from automation_integrations.api_read import HTTP, Failure, provider_environment


class TransportTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('curl'), 'curl required for real config parser roundtrip')
    def test_etm_curl_json_preserves_utf8_and_escaping(self):
        bodies = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                bodies.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        real_run = subprocess.run
        def local_curl(args, **kwargs):
            # Run the real curl config parser. Only replace the remote transport
            # with the isolated local fixture; production still enforces HTTPS.
            args = list(args)
            index = args.index('--proxy'); del args[index:index + 2]
            args[args.index('--proto') + 1] = '=http'
            lines = kwargs['input'].decode().splitlines()
            lines[0] = 'url = "http://127.0.0.1:' + str(server.server_port) + '/test"'
            kwargs['input'] = '\n'.join(lines).encode()
            return real_run(args, **kwargs)
        body = {'purpose': 'Проверка счёта «Тест»', 'address': 'Воронеж', 'note': 'line1\nline2 "quote" \\path'}
        try:
            with patch('subprocess.run', side_effect=local_curl):
                result = HTTP('etm', {'etm_proxy': 'socks5h://127.0.0.1:10929'}).call('POST', '/invoice/test', body=body)
            self.assertEqual(result, {})
            self.assertEqual(bodies, [body])
        finally:
            server.shutdown(); server.server_close(); thread.join(2)

    def test_only_supported_sandbox_can_select_nonproduction(self):
        self.assertEqual(provider_environment('tochka', {'tochka_environment': 'sandbox'}), 'sandbox')
        for service in ('saby', 'yandex_go', 'etm', 'wirenboard'):
            with self.assertRaisesRegex(Failure, 'unsupported_provider_environment'):
                provider_environment(service, {service + '_environment': 'sandbox'})

    def test_interrupted_provider_response_is_not_a_local_runner_error(self):
        for error in (http.client.RemoteDisconnected('private provider text'),
                      http.client.IncompleteRead(b'private body'), ConnectionResetError('private URL')):
            with patch('urllib.request.build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaisesRegex(Failure, '^provider_connection_interrupted$'):
                    HTTP('saby', {}).call('POST', '/service/', body={})


if __name__ == '__main__':
    unittest.main()
