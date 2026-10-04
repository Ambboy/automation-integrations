"""ETM business rejection, ambiguous response and authentication regressions."""
from copy import deepcopy
import tempfile
import unittest

from automation_integrations import confirmed_write, extended_api
from automation_integrations.api_read import Failure, execute
from tests.test_api_catalog import FakeHTTP, FakeVault


AUTH = {'status': {'code': 200}, 'data': {'session': 'ETM_SESSION_SECRET'}}
ORDER = {'path': {'id': '1-2065278809'}, 'query': {'skl': 1000}}


class EtmApiTests(unittest.TestCase):
    def call_order(self, response, *, auth=None):
        http = FakeHTTP(deepcopy(AUTH if auth is None else auth), response)
        result = extended_api.call('etm', 'invoice_order', ORDER, {}, write=True,
                                   http=http, vault=FakeVault())
        return result, http

    def test_both_documented_status_envelopes_require_explicit_success(self):
        for response in ({'code': 200, 'message': ''},
                         {'status': {'code': '200', 'message': ''}}):
            with self.subTest(response=response):
                (result, secrets), http = self.call_order(response)
                self.assertEqual(result, response)
                self.assertEqual(http.calls[-1][0], ('POST', '/invoice/1-2065278809/order'))
                self.assertEqual(http.calls[-1][1]['query'],
                                 {'skl': '1000', 'session-id': 'ETM_SESSION_SECRET'})
                self.assertIn('ETM_SESSION_SECRET', secrets)

    def test_business_errors_keep_numeric_code_without_provider_message(self):
        for code in (400, '403', 404, 422, 429, 500):
            for wrapped in (False, True):
                status = {'code': code, 'message': 'sensitive account information'}
                response = {'status': status} if wrapped else status
                with self.subTest(code=code, wrapped=wrapped):
                    with self.assertRaises(Failure) as caught:
                        self.call_order(response)
                    self.assertEqual(caught.exception.code, 'etm_api_error')
                    self.assertEqual(caught.exception.status, int(code))
                    self.assertEqual(caught.exception.provider_code, str(code))
                    self.assertNotIn('sensitive', str(caught.exception))

    def test_empty_and_malformed_status_are_never_success(self):
        responses = [None, [], {}, '', {'data': {}}, {'code': True}, {'code': 200.0},
                     {'code': ' 200'}, {'code': '0200'}, {'code': '۲۰۰'},
                     {'status': None}, {'status': []}, {'status': '200'},
                     {'status': {}, 'code': 200}, {'status': {'message': ''}}]
        for response in responses:
            with self.subTest(response=response), self.assertRaisesRegex(Failure, '^invalid_provider_json$'):
                self.call_order(response)

    def test_failed_authentication_never_reaches_business_endpoint(self):
        responses = [None, {}, [], {'status': {'code': 403}, 'data': {'session': 'stale'}},
                     {'status': {'code': 200}}, {'status': {'code': 200}, 'data': []},
                     {'status': {'code': 200}, 'data': {'session': ''}},
                     {'status': {'code': 200}, 'data': {'session': 123}},
                     {'status': {'code': 200}, 'data': {'session': 'bad\ntoken'}}]
        for auth in responses:
            http, vault = FakeHTTP(auth), FakeVault()
            with self.subTest(auth=auth), self.assertRaises(Failure):
                extended_api.call('etm', 'invoice_order', ORDER, {}, write=True,
                                  http=http, vault=vault)
            self.assertEqual(len(http.calls), 1)
            self.assertEqual(http.calls[0][0], ('POST', '/user/login'))
            self.assertNotIn('stale', vault.sensitive)

    def test_pdf_success_and_json_error_share_print_endpoint(self):
        params = {'path': {'id': ORDER['path']['id'], 'proc': 'bill'}}
        pdf = b'%PDF-1.7\nfixture\n'
        result, _ = extended_api.call('etm', 'invoice_print', params, {}, write=True,
                                     http=FakeHTTP(AUTH, pdf), vault=FakeVault())
        self.assertEqual(result, pdf)
        with self.assertRaises(Failure) as caught:
            extended_api.call('etm', 'invoice_print', params, {}, write=True,
                             http=FakeHTTP(AUTH, {'status': {'code': 400}}), vault=FakeVault())
        self.assertEqual(caught.exception.status, 400)
        for response in (pdf, b'<html>error</html>'):
            with self.assertRaisesRegex(Failure, '^invalid_provider_json$'):
                self.call_order(response)

    def test_legacy_reads_use_same_status_and_authentication_checks(self):
        goods = {'service': 'etm', 'operation': 'goods', 'params': {'id': '2655564'}}
        for response in ({}, {'status': {'code': 400}}, {'code': 403}):
            with self.subTest(response=response), self.assertRaises(Failure):
                execute(goods, {}, FakeVault(), FakeHTTP(AUTH, response))
        login = {'service': 'etm', 'operation': 'login_check'}
        bad_auth = {'status': {'code': 403}, 'data': {'session': 'stale'}}
        http = FakeHTTP(bad_auth)
        with self.assertRaises(Failure) as caught:
            execute(login, {}, FakeVault(), http)
        self.assertEqual(caught.exception.provider_code, '403')
        self.assertEqual(len(http.calls), 1)
        success = execute(login, {}, FakeVault(), FakeHTTP(AUTH))
        self.assertEqual(success['data'], {'authenticated': True})

    def test_durable_workflow_distinguishes_rejection_from_unknown_and_never_retries(self):
        for response, expected in (({'code': 400}, 'rejected'),
                                   ({'status': {'code': 403}}, 'rejected'),
                                   ({}, 'outcome_unknown'),
                                   ({'code': 500}, 'outcome_unknown'),
                                   ({'code': 200}, 'accepted_unverified')):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as state:
                config = {'state_dir': state}
                context = {'scope': ['owner', 'owner', 'session', 'topic'], 'message_id': '1'}
                vault, http = FakeVault(), FakeHTTP(AUTH, response)
                def action(request, message='1'):
                    return confirmed_write.process(request, {**context, 'message_id': message},
                                                   config, http=http, vault=vault, clock=lambda: 1000)
                draft = action({'action': 'prepare', 'service': 'etm',
                                'operation': 'invoice_order', 'params': ORDER})
                self.assertEqual(http.calls, [])
                action({'action': 'confirm', 'confirmation_text': draft['confirmation_command']}, '2')
                request = {'action': 'execute', 'draft_id': draft['draft_id']}
                result = action(request)
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['provider_accepted'], expected == 'accepted_unverified')
                if expected == 'rejected':
                    code = response.get('status', response)['code']
                    self.assertEqual(result['provider_code'], str(code))
                self.assertEqual(action(request), result)
                self.assertEqual(len(http.calls), 2)


if __name__ == '__main__':
    unittest.main()
