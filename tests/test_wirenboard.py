import concurrent.futures
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from automation_integrations import api_read, wirenboard as wb
from automation_integrations.api_read import Failure, sanitize


ORG = '00000000-0000-4000-8000-000000000001'
METRICS = {'serial_number': 'abc123', 'name': 'load15',
           'start': '2026-10-01T00:00:00Z', 'stop': '2026-10-02T00:00:00Z'}


class Vault:
    def __init__(self, access='seed-access', refresh='seed-refresh'):
        self.values = {'WBCLOUD_ACCESS_TOKEN': access, 'WBCLOUD_REFRESH_TOKEN': refresh}
        self.sensitive = []
        self.calls = []

    def get(self, service):
        self.calls.append(service)
        return self.values


class HTTP:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def call(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class WirenboardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name)
        self.config = {'state_dir': str(self.state)}
        self.cache = self.state / 'wirenboard-session.json'

    def execute(self, http, vault=None, operation='me', params=None):
        return wb.execute(operation, params or {}, self.config, vault or Vault(), http)

    def test_access_reused_and_private_atomic_cache(self):
        first = HTTP({'id': 'user'})
        self.assertEqual(self.execute(first), {'id': 'user'})
        second = HTTP([])
        self.assertEqual(self.execute(second, operation='organizations'), [])
        self.assertEqual([call[:2] for call in first.calls + second.calls],
                         [('GET', '/users/me/'), ('GET', '/organizations/')])
        self.assertEqual(second.calls[0][2]['headers'], {'Authorization': 'Bearer seed-access'})
        self.assertEqual(self.cache.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.state / 'wirenboard.lock').stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.state.glob('*.tmp')), [])

    def test_rotation_cached_instead_of_reusing_vault_seed(self):
        vault = Vault()
        first = HTTP(Failure('authorization_failed', 401),
                     {'access': 'rotated-access', 'refresh': 'rotated-refresh'}, {'id': 'u'})
        self.execute(first, vault)
        self.assertEqual([call[:2] for call in first.calls],
                         [('GET', '/users/me/'), ('POST', '/auth/token/refresh/'), ('GET', '/users/me/')])
        self.assertEqual(first.calls[1][2], {'body': {'refresh': 'seed-refresh'}})
        self.assertEqual(first.calls[2][2]['headers']['Authorization'], 'Bearer rotated-access')
        second = HTTP({'id': 'u'})
        self.execute(second, vault)
        self.assertEqual(len(second.calls), 1)
        self.assertEqual(second.calls[0][2]['headers']['Authorization'], 'Bearer rotated-access')
        third = HTTP(Failure('authorization_failed', 401),
                     {'access': 'access-again', 'refresh': 'refresh-again'}, {'id': 'u'})
        self.execute(third, vault)
        self.assertEqual(third.calls[1][2]['body']['refresh'], 'rotated-refresh')
        self.assertEqual(json.loads(self.cache.read_text())['refresh'], 'refresh-again')
        cleaned = json.dumps(sanitize({'note': 'seed-access seed-refresh rotated-access rotated-refresh access-again refresh-again'}, vault.sensitive))
        for secret in vault.sensitive:
            self.assertNotIn(secret, cleaned)

    def test_refresh_only_seed_and_nonrotating_response(self):
        http = HTTP({'access': 'fresh-access'}, {'id': 'u'})
        self.execute(http, Vault(access=None))
        self.assertEqual(http.calls[0][:2], ('POST', '/auth/token/refresh/'))
        self.assertEqual(json.loads(self.cache.read_text())['refresh'], 'seed-refresh')

    def test_refresh_is_pending_before_network(self):
        cache = self.cache

        class InspectHTTP(HTTP):
            def call(self, method, path, **kwargs):
                if path == '/auth/token/refresh/':
                    row = json.loads(cache.read_text())
                    assert row['status'] == 'refresh_pending'
                    assert row['access'] is None
                return super().call(method, path, **kwargs)

        self.execute(InspectHTTP({'access': 'a', 'refresh': 'r'}, {}), Vault(access=None))

    def test_uncertain_refresh_never_retries_old_token(self):
        for response in (Failure('request_timeout'), Failure('authorization_failed', 401),
                         Failure('invalid_provider_json'), ['invalid'], {'access': 'a', 'refresh': None}):
            with self.subTest(response=type(response).__name__):
                self.cache.unlink(missing_ok=True)
                http = HTTP(response)
                vault = Vault(access=None)
                expected = ('refresh_outcome_unknown' if isinstance(response, Failure)
                            and response.status not in (401, 403) else 'reauthentication_required')
                with self.assertRaisesRegex(Failure, '^' + expected + '$'):
                    self.execute(http, vault)
                second = HTTP()
                with self.assertRaisesRegex(Failure, '^reauthentication_required$'):
                    self.execute(second, vault)
                self.assertEqual(second.calls, [])
                self.assertEqual(len(http.calls), 1)

    def test_invalid_refresh_response_preserves_rotated_token(self):
        with self.assertRaisesRegex(Failure, '^reauthentication_required$'):
            self.execute(HTTP({'access': None, 'refresh': 'rotated-do-not-lose'}), Vault(access=None))
        row = json.loads(self.cache.read_text())
        self.assertEqual(row['refresh'], 'rotated-do-not-lose')
        self.assertEqual(row['status'], 'reauthentication_required')

    def test_failed_rotated_token_persistence_does_not_retry(self):
        real_write = wb._write_cache

        def failing_write(path, row):
            if row.get('access') == 'rotated-access':
                raise Failure('session_cache_write_failed')
            real_write(path, row)

        http = HTTP({'access': 'rotated-access', 'refresh': 'rotated-refresh'})
        with patch.object(wb, '_write_cache', side_effect=failing_write):
            with self.assertRaisesRegex(Failure, '^session_cache_write_failed$'):
                self.execute(http, Vault(access=None))
        self.assertEqual(json.loads(self.cache.read_text())['status'], 'refresh_pending')
        second = HTTP()
        with self.assertRaisesRegex(Failure, '^reauthentication_required$'):
            self.execute(second, Vault(access=None))
        self.assertEqual(second.calls, [])

    def test_cache_failure_before_refresh_prevents_network(self):
        http = HTTP()
        with patch.object(wb, '_write_cache', side_effect=Failure('session_cache_write_failed')):
            with self.assertRaisesRegex(Failure, '^session_cache_write_failed$'):
                self.execute(http, Vault(access=None))
        self.assertEqual(http.calls, [])

    def test_cache_corruption_does_not_fall_back_to_vault_seed(self):
        self.cache.write_text('{partial')
        http = HTTP()
        with self.assertRaisesRegex(Failure, 'session_cache_invalid_reauthentication_required'):
            self.execute(http)
        self.assertEqual(http.calls, [])

    def test_changed_credentials_recover_pending_state(self):
        with self.assertRaises(Failure):
            self.execute(HTTP(Failure('request_timeout')), Vault(access=None))
        http = HTTP({'id': 'new-session'})
        self.assertEqual(self.execute(http, Vault('new-seed-access', 'new-seed-refresh'))['id'], 'new-session')
        self.assertEqual(http.calls[0][2]['headers']['Authorization'], 'Bearer new-seed-access')

    def test_no_refresh_on_403_or_non_auth_failures(self):
        for failure in (Failure('authorization_failed', 403), Failure('network_unavailable'), Failure('provider_http_error', 500)):
            with self.subTest(code=failure.code):
                http = HTTP(failure)
                with self.assertRaises(Failure) as caught:
                    self.execute(http)
                self.assertIs(caught.exception, failure)
                self.assertEqual(len(http.calls), 1)

    def test_missing_refresh_and_second_401_require_reauthentication(self):
        for vault, responses, expected_calls in (
            (Vault(refresh=None), [Failure('authorization_failed', 401)], 1),
            (Vault(), [Failure('authorization_failed', 401), {'access': 'new', 'refresh': 'new-r'}, Failure('authorization_failed', 401)], 3),
            (Vault(access=None), [{'access': 'new', 'refresh': 'new-r'}, Failure('authorization_failed', 401)], 2),
        ):
            with self.subTest(expected_calls=expected_calls):
                self.cache.unlink(missing_ok=True)
                http = HTTP(*responses)
                with self.assertRaisesRegex(Failure, '^reauthentication_required$'):
                    self.execute(http, vault)
                self.assertEqual(len(http.calls), expected_calls)
                second = HTTP()
                with self.assertRaises(Failure):
                    self.execute(second, vault)
                self.assertEqual(second.calls, [])

    def test_concurrent_requests_refresh_once_and_serialize_reads(self):
        counts = {'active': 0, 'max_active': 0, 'refreshes': 0, 'reads': 0}
        guard = threading.Lock()

        class ConcurrentHTTP:
            def call(self, method, path, **kwargs):
                with guard:
                    counts['active'] += 1
                    counts['max_active'] = max(counts['max_active'], counts['active'])
                try:
                    time.sleep(0.01)
                    if path == '/auth/token/refresh/':
                        counts['refreshes'] += 1
                        return {'access': 'shared-access', 'refresh': 'shared-refresh'}
                    assert kwargs['headers']['Authorization'] == 'Bearer shared-access'
                    counts['reads'] += 1
                    return {'id': 'u'}
                finally:
                    with guard:
                        counts['active'] -= 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(self.execute, ConcurrentHTTP(), Vault(access=None)) for _ in range(6)]
            for future in futures:
                self.assertEqual(future.result(timeout=5), {'id': 'u'})
        self.assertEqual(counts, {'active': 0, 'max_active': 1, 'refreshes': 1, 'reads': 6})

    def test_fixed_routes_and_post_metrics_are_read_only(self):
        operations = [
            ('me', {}, 'GET', '/users/me/', {}),
            ('organizations', {}, 'GET', '/organizations/', []),
            ('controllers', {'organization_id': ORG, 'page': 2, 'page_size': 7}, 'GET', '/controllers/',
             {'count': 0, 'results': [], 'next': None, 'previous': None}),
            ('counters', {}, 'GET', '/controllers-count/', {'count': 3, 'countAgentNotOk': 1}),
            ('controller', {'serial_number': 'abc_1-2'}, 'GET', '/controllers/ABC_1-2/', {}),
            ('diagnostic', {'serial_number': 'abc123'}, 'GET', '/controllers/ABC123/diagnostic/', {}),
            ('metrics', METRICS, 'POST', '/controllers/ABC123/system-metrics/', []),
            ('groups', {'organization_id': ORG}, 'GET', '/groups/', []),
            ('group', {'id': ORG}, 'GET', '/groups/' + ORG + '/', {}),
            ('last_metrics_time', {'serial_number': 'abc123'}, 'GET', '/controllers/ABC123/last-metrics-time/', {}),
        ]
        for operation, params, method, path, response in operations:
            with self.subTest(operation=operation):
                http = HTTP(response)
                self.execute(http, operation=operation, params=params)
                self.assertEqual(http.calls[0][:2], (method, path))
                if operation == 'metrics':
                    self.assertEqual(http.calls[0][2]['body'], {key: METRICS[key] for key in ('name', 'start', 'stop')})

    def test_strict_validation_before_vault_and_network(self):
        requests = [
            ('reboot', {}), ('raw', {'url': 'https://example.test'}), ('diagnostic_download', {'serial_number': '123'}),
            ('controller', {}), ('controller', {'serial_number': '../../users/me'}),
            ('controller', {'serial_number': 'https://example.test'}), ('controller', {'serial_number': 'x' * 37}),
            ('me', {'method': 'DELETE'}), ('me', []), ('controllers', {'page': 0}),
            ('controllers', {'page': True}), ('controllers', {'page': 10001}),
            ('controllers', {'page_size': 101}), ('controllers', {'page_size': 0}),
            ('controllers', {'organization_id': 'not-uuid'}), ('groups', {}),
            ('group', {'id': ORG + '/controllers/'}), ('controllers', {'search': 'a\nsecret'}),
            ('metrics', {**METRICS, 'name': 'exec'}), ('metrics', {**METRICS, 'stop': '2026-10-02T00:00:01Z'}),
            ('metrics', {**METRICS, 'stop': METRICS['start']}), ('metrics', {**METRICS, 'start': '2026-10-01T00:00:00'}),
            ('metrics', {**METRICS, 'stop': '2026-10-02'}), ('metrics', {**METRICS, 'body': {'cmd': 'reboot'}}),
        ]
        vault, http = Vault(), HTTP()
        for operation, params in requests:
            with self.subTest(operation=operation, params=params), self.assertRaises(Failure):
                wb.execute(operation, params, self.config, vault, http)
        self.assertEqual(vault.calls, [])
        self.assertEqual(http.calls, [])
        self.assertFalse(self.cache.exists())

    def test_datetime_range_uses_offsets_and_allows_24_hours(self):
        result = wb.validate('metrics', {**METRICS, 'start': '2026-10-01T02:00:00+02:00', 'stop': '2026-10-02T00:00:00Z'})
        self.assertEqual(result['serial_number'], 'ABC123')

    def test_pagination_never_follows_provider_urls(self):
        response = {'count': 22, 'results': [{'serialNumber': '1'}],
                    'next': 'https://untrusted.test/?page=999&token=private', 'previous': None}
        http = HTTP(response)
        result = self.execute(http, operation='controllers')
        self.assertEqual(http.calls[0][2]['query'], {'page': 1, 'page_size': 20})
        self.assertEqual(len(http.calls), 1)
        self.assertEqual(wb.pagination(result, {}), {'page': 1, 'page_size': 20, 'count': 22,
                                                   'returned': 1, 'has_more': True, 'next_page': 2})
        self.assertNotIn('http', json.dumps(wb.pagination(result, {})))

    def test_invalid_response_shape_and_empty_results(self):
        for operation, response in (('controllers', []), ('controllers', {'count': True, 'results': [], 'next': None, 'previous': None}),
                                    ('organizations', {}), ('counters', {'count': -1, 'countAgentNotOk': 0}), ('me', [])):
            with self.subTest(operation=operation), self.assertRaisesRegex(Failure, '^invalid_provider_response$'):
                self.execute(HTTP(response), operation=operation)
        self.assertEqual(wb.result_state('controllers', {'results': []}), 'empty')
        self.assertEqual(wb.result_state('organizations', []), 'empty')
        self.assertEqual(wb.result_state('controller', {}), 'data')

    def test_runner_validates_before_secrets_or_network(self):
        vault, http = Vault(), HTTP()
        requests = [
            {'service': 'wirenboard', 'operation': 'controller', 'params': {'serial_number': '../me'}},
            {'service': 'wirenboard', 'operation': 'reboot', 'params': {'serial_number': '123'}},
            {'service': 'wirenboard', 'operation': 'controllers', 'params': {'url': 'https://untrusted.test'}},
            {'service': 'wirenboard', 'operation': 'metrics', 'params': {**METRICS, 'name': 'exec'}},
        ]
        for request in requests:
            with self.subTest(request=request), self.assertRaises(Failure):
                api_read.execute(request, self.config, vault, http)
        self.assertEqual(vault.calls, [])
        self.assertEqual(http.calls, [])
        self.assertFalse(self.cache.exists())

    def test_runner_sanitizes_provider_data_and_retains_numeric_pagination(self):
        response = {'count': 22, 'next': 'https://untrusted.test/?page=999&token=private',
                    'previous': None, 'results': [{'serialNumber': 'A1', 'access_token': 'leak',
                                                  'description': 'seed-access seed-refresh'}]}
        http, vault = HTTP(response), Vault()
        result = api_read.execute({'service': 'wirenboard', 'operation': 'controllers'}, self.config, vault, http)
        self.assertEqual(vault.calls, ['wirenboard'])
        self.assertEqual(len(http.calls), 1)
        self.assertTrue(result['ok'])
        self.assertEqual(result['result_state'], 'data')
        self.assertEqual(result['pagination']['next_page'], 2)
        self.assertTrue(result['pagination']['has_more'])
        self.assertEqual(result['data']['next'], '[url withheld]')
        self.assertEqual(result['data']['results'][0]['access_token'], '[redacted]')
        rendered = json.dumps(result)
        for secret in ('seed-access', 'seed-refresh', 'private', 'leak', 'https://'):
            self.assertNotIn(secret, rendered)
        empty = api_read.execute({'service': 'wirenboard', 'operation': 'organizations'}, self.config, vault, HTTP([]))
        self.assertEqual(empty['result_state'], 'empty')

    def test_real_vault_accepts_single_token_and_reads_only_expected_fields(self):
        vault = api_read.Vault({'item_ids': {'wirenboard': 'record-id'}})
        record = {'login': {'username': 'ignored', 'password': 'never-read'},
                  'fields': [{'name': 'WBCLOUD_REFRESH_TOKEN', 'value': 'refresh-only'},
                             {'name': 'UNRELATED_SECRET', 'value': 'unrelated'}]}
        with patch.object(vault, 'item', return_value=record) as item:
            result = vault.get('wirenboard')
        item.assert_called_once_with('record-id')
        self.assertEqual(result, {'WBCLOUD_ACCESS_TOKEN': '', 'WBCLOUD_REFRESH_TOKEN': 'refresh-only'})
        self.assertEqual(vault.sensitive, ['refresh-only'])


if __name__ == '__main__':
    unittest.main()
