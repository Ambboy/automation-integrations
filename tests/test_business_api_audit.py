"""Regressions found against the official Yandex, Saby and Tochka contracts."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from automation_integrations import confirmed_write, extended_api
from automation_integrations.api_read import Failure
from tests.test_api_catalog import FakeHTTP, FakeVault


class BusinessAPIAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {'state_dir': self.tmp.name, 'yandex_client_id': 'company'}
        self.vault = FakeVault()
        self.cache = Path(self.tmp.name, 'saby-session.json')

    def saby(self, http, *, operation='version_info', params=None, write=False):
        return extended_api.call('saby', operation, params or {'body': {'Параметр': {}}},
                                 self.config, write=write, vault=self.vault, http=http)[0]

    def test_corrupted_wrong_type_and_old_credential_caches_reauthenticate(self):
        stale = {'token': 'OLD_PRIVATE_TOKEN', 'credential_fingerprint': 'another-account'}
        for cached in ('{broken', '[]', 'null', '{"token":42}', json.dumps(stale)):
            with self.subTest(cached=cached):
                self.cache.write_text(cached)
                http = FakeHTTP({'token': 'NEW_PRIVATE_TOKEN'}, {'result': {'version': '1'}})
                self.assertEqual(self.saby(http), {'version': '1'})
                self.assertEqual(http.calls[0][0][1], '/oauth/service/')
                self.assertEqual(http.calls[1][1]['headers']['X-SBISAccessToken'], 'NEW_PRIVATE_TOKEN')
                self.assertEqual(self.cache.stat().st_mode & 0o777, 0o600)

    def test_credential_rotation_invalidates_cache_before_any_rpc(self):
        self.saby(FakeHTTP({'token': 'OLD_TOKEN'}, {'result': {}}))
        old = json.loads(self.cache.read_text())['credential_fingerprint']
        get = self.vault.get
        def rotated(service):
            values = get(service)
            values['SABY_SECRET_KEY'] = 'ROTATED_PRIVATE_SECRET'
            return values
        self.vault.get = rotated
        http = FakeHTTP({'token': 'ROTATED_TOKEN'}, {'result': {}})
        self.saby(http)
        self.assertEqual(http.calls[0][0][1], '/oauth/service/')
        self.assertNotEqual(old, json.loads(self.cache.read_text())['credential_fingerprint'])

    def test_working_legacy_cache_stays_unbound_until_explicit_401(self):
        self.cache.write_text(json.dumps({'token': 'LEGACY_TOKEN'}))
        http = FakeHTTP({'result': {'version': '1'}})
        self.assertEqual(self.saby(http), {'version': '1'})
        self.assertEqual(len(http.calls), 1)
        self.assertEqual(http.calls[0][0][1], '/service/?srv=1')
        self.assertNotIn('credential_fingerprint', json.loads(self.cache.read_text()))
        http = FakeHTTP(Failure('authorization_failed', 401), {'token': 'NEW_TOKEN'}, {'result': {}})
        self.saby(http)
        self.assertEqual(len(http.calls), 3)
        self.assertIn('credential_fingerprint', json.loads(self.cache.read_text()))

    def test_malformed_or_failed_auth_cannot_supply_a_usable_token(self):
        for response in ([], None, {'token': 1}, {'token': 'bad\ntoken'},
                         {'token': 'looks-valid', 'error': {}},
                         {'token': 'looks-valid', 'error': {'code': -32000}}):
            with self.subTest(response=response):
                self.cache.unlink(missing_ok=True)
                http = FakeHTTP(response)
                with self.assertRaisesRegex(Failure, '^saby_authentication_failed$'):
                    self.saby(http)
                self.assertEqual(len(http.calls), 1)
                self.assertFalse(self.cache.exists())

    def test_rpc_business_error_preserves_code_without_private_message(self):
        http = FakeHTTP({'token': 'TOKEN'}, {'result': {}, 'error': {
            'code': -32000, 'message': 'PRIVATE_ACCOUNT_DATA'}})
        with self.assertRaises(Failure) as caught:
            self.saby(http)
        self.assertEqual(caught.exception.code, 'saby_api_error')
        self.assertEqual(caught.exception.provider_code, '-32000')
        self.assertNotIn('PRIVATE_ACCOUNT_DATA', str(caught.exception))
        self.assertEqual(len(http.calls), 2)
        code = '00000000-0000-0000-0000-1FA000001002'
        http = FakeHTTP({'error': {'code': -32000, 'data': {'error_code': code,
                        'details': 'PRIVATE_ACCOUNT_DATA'}}})
        with self.assertRaises(Failure) as caught:
            self.saby(http)
        self.assertEqual(caught.exception.provider_code, code)

    def test_invalid_rpc_envelopes_fail_with_controlled_error(self):
        for response in ([], {'unrelated': []}, {'jsonrpc': '1.0', 'result': {}},
                         {'id': 999, 'result': {}}):
            with self.subTest(response=response):
                self.cache.unlink(missing_ok=True)
                with self.assertRaisesRegex(Failure, '^invalid_provider_json$'):
                    self.saby(FakeHTTP({'token': 'TOKEN'}, response))

    def test_read_401_recovery_is_bounded_and_final_bad_cache_removed(self):
        http = FakeHTTP({'token': 'FIRST'}, Failure('authorization_failed', 401),
                        {'token': 'SECOND'}, Failure('authorization_failed', 401))
        with self.assertRaises(Failure):
            self.saby(http)
        self.assertEqual(len(http.calls), 4)
        self.assertFalse(self.cache.exists())

    def test_write_is_never_replayed_after_auth_failure_or_timeout(self):
        for failure in (Failure('authorization_failed', 401), Failure('request_timeout')):
            with self.subTest(failure=failure):
                self.cache.unlink(missing_ok=True)
                http = FakeHTTP({'token': 'TOKEN'}, failure)
                with self.assertRaises(Failure):
                    self.saby(http, operation='document_delete',
                              params={'body': {'Документ': {'Идентификатор': 'doc'}}}, write=True)
                self.assertEqual(len(http.calls), 2)

    def yandex_bodies(self):
        vehicle = {'license_plate': 'A123BC', 'model': 'Car', 'limit_id': 'limit', 'access_type': 'anyone'}
        return {
            'vehicles_bulk_create': {'vehicles': [vehicle]},
            'vehicles_bulk_update': {'vehicles': [{**vehicle, 'vehicle_id': 'vehicle'}]},
            'vehicles_bulk_archive': {'vehicle_ids': ['vehicle']},
            'promocodes_create': {'value': 100, 'count': 5, 'active_until':
                (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=1)).isoformat()}}

    def test_all_documented_idempotency_headers_are_durable_draft_ids(self):
        context = {'scope': ['owner', 'owner', 'session', 'topic'], 'message_id': 'prepare'}
        for operation, body in self.yandex_bodies().items():
            with self.subTest(operation=operation):
                row = confirmed_write.process({'action': 'prepare', 'service': 'yandex_go',
                    'operation': operation, 'params': {'body': body}}, context, self.config,
                    vault=self.vault, http=FakeHTTP())
                ident = row['draft_id']
                confirmed_write.process({'action': 'confirm', 'confirmation_text': 'ПОДТВЕРЖДАЮ ' + ident},
                    {**context, 'message_id': 'confirm'}, self.config, vault=self.vault)
                http = FakeHTTP(Failure('request_timeout'))
                row = confirmed_write.process({'action': 'execute', 'draft_id': ident}, context,
                    self.config, vault=self.vault, http=http)
                self.assertEqual(http.calls[0][1]['headers']['X-Idempotency-Token'], ident)
                self.assertEqual(row['status'], 'outcome_unknown')
                confirmed_write.process({'action': 'execute', 'draft_id': ident}, context,
                    self.config, vault=self.vault, http=http)
                self.assertEqual(len(http.calls), 1)
                self.assertEqual(json.loads(Path(self.tmp.name, 'contract-writes', ident + '.json').read_text())['draft_id'], ident)

    def test_required_idempotency_is_checked_before_credentials(self):
        for key in (None, '', 'not-a-uuid', 'x\nheader:value'):
            with self.subTest(key=key), self.assertRaisesRegex(Failure, '^idempotency_key_required$'):
                extended_api.call('yandex_go', 'vehicles_bulk_archive', {'body': {'vehicle_ids': ['one']}},
                    self.config, write=True, vault=self.vault, http=FakeHTTP(), idempotency_key=key)
        self.assertEqual(self.vault.calls, [])

    def test_error_envelopes_in_http_success_are_not_accepted(self):
        cases = [('tochka', 'open_banking_get_accounts_list',
                  {'code': '400', 'id': 'audit', 'message': 'PRIVATE_BANK_DATA', 'Errors': []}, '400'),
                 ('yandex_go', 'user_list', {'code': 'INVALID_REQUEST', 'message': 'PRIVATE_USER_DATA'}, 'INVALID_REQUEST')]
        for service, operation, response, code in cases:
            with self.subTest(service=service), self.assertRaises(Failure) as caught:
                extended_api.execute(service, operation, {}, self.config, vault=self.vault, http=FakeHTTP(response))
            self.assertEqual(caught.exception.provider_code, code)
            self.assertNotIn('PRIVATE_', str(caught.exception))

    def test_provider_pagination_is_preserved(self):
        response = {'items': [], 'cursor': 'next-cursor', 'limit': 1}
        result = extended_api.execute('yandex_go', 'user_list', {'query': {'limit': 1, 'cursor': 'previous'}},
            self.config, vault=self.vault, http=FakeHTTP(response))
        self.assertEqual(result['data'], response)
        response = {'Документ': [], 'Навигация': {'ЕстьЕще': 'Да'}}
        self.assertEqual(self.saby(FakeHTTP({'token': 'TOKEN'}, {'result': response})), response)


if __name__ == '__main__':
    unittest.main()
