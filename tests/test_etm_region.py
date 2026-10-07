"""Portal city selection must be confirmed by ETM before checkout discovery."""
from copy import deepcopy
import json
import unittest

from automation_integrations.api_read import Failure
from automation_integrations.etm_order import Checkout, WebsiteClient


ENTITY = {'clicode': '123', 'cliName': 'Fixture LLC',
          'inn_org': '1234567890', 'kpp_org': '123456789'}
CITY = {'name': 'Ростов-на-Дону', 'class17': 'ЮГРСТ', 'st': '35', 'rows': []}
SECRETS = {'ETM_LOGIN': 'region-fixture-login', 'ETM_PASSWORD': 'region-fixture-password'}
SESSION = 'region-fixture-session'


class RegionVault:
    def __init__(self):
        self.sensitive = list(SECRETS.values())

    def get(self, service):
        if service != 'etm':
            raise AssertionError(service)
        return deepcopy(SECRETS)


class RegionPortal:
    """Ignores the requested city cookie until the real region-setting call."""
    def __init__(self, *, city='34', region='ЮГВЛГ'):
        self.city = city
        self.region = region
        self.calls = []
        self.descriptor = deepcopy(CITY)
        self.ignore_switch = False
        self.switch_attempted = False
        self.switch_rejection = None
        self.after_switch_session = None

    @staticmethod
    def success(data):
        return {'status': {'code': 200}, 'data': deepcopy(data)}

    def __call__(self, method, path, *, headers=None, query=None, form=None):
        self.calls.append({'method': method, 'path': path, 'headers': deepcopy(headers),
                           'query': deepcopy(query), 'form': deepcopy(form)})
        if (method, path) == ('POST', '/user/login'):
            return self.success({**ENTITY, 'session': SESSION,
                                 'city': self.city, 'rg': self.region})
        if (method, path) == ('GET', '/info/city/61'):
            return self.success(self.descriptor)
        if (method, path) == ('POST', '/user/set'):
            self.switch_attempted = True
            if self.switch_rejection is not None:
                return deepcopy(self.switch_rejection)
            if form not in ({'param': 'region', 'val': 'ЮГРСТ'},
                            {'param': 'region', 'val': 'ЮГВЛГ'}):
                raise AssertionError('Region switch must use the vendor city descriptor')
            if not self.ignore_switch:
                self.city, self.region = ('61', 'ЮГРСТ') if form['val'] == 'ЮГРСТ' else ('34', 'ЮГВЛГ')
            # The live endpoint confirms success without a data object.
            return {'status': {'code': 200, 'message': ''}}
        if (method, path) == ('GET', '/user/session/get'):
            data = ({**ENTITY, 'city': self.city, 'rg': self.region}
                    if not self.switch_attempted or self.after_switch_session is None
                    else self.after_switch_session)
            return self.success(data)
        if (method, path) == ('GET', '/basket/functionality'):
            return self.success({'contract': {'defaultValue': '555', 'value': []}})
        if (method, path) == ('GET', '/basket/order'):
            return self.success({'records': 0, 'rows': [], 'stores': []})
        raise AssertionError(('Unexpected portal request', method, path))

    def requests(self, method, path):
        return [c for c in self.calls if (c['method'], c['path']) == (method, path)]


class ETMRegionTests(unittest.TestCase):
    def setUp(self):
        self.portal = RegionPortal()
        self.vault = RegionVault()
        self.client = WebsiteClient({}, vault=self.vault, transport=self.portal)

    def assert_no_checkout(self):
        self.assertFalse(any(c['path'].startswith(('/basket/', '/payment/', '/invoice/'))
                             for c in self.portal.calls))

    def assert_no_business_writes(self):
        self.assertFalse(any(c['method'] != 'GET' and c['path'] not in
                             ('/user/login', '/user/set') for c in self.portal.calls))

    def test_switches_server_region_and_reads_it_back_before_checkout(self):
        result = Checkout(self.client).options({'region': '61'})
        self.assertEqual(result['region'], '61')
        self.assertEqual(result['legal_entity'], ENTITY)
        switches = self.portal.requests('POST', '/user/set')
        self.assertEqual(len(switches), 1)
        self.assertEqual(switches[0]['form'], {'param': 'region', 'val': 'ЮГРСТ'})
        self.assertEqual(len(self.portal.requests('GET', '/info/city/61')), 1)
        paths = [(c['method'], c['path']) for c in self.portal.calls]
        switch_index = paths.index(('POST', '/user/set'))
        readback_index = paths.index(('GET', '/user/session/get'), switch_index + 1)
        self.assertLess(readback_index, paths.index(('GET', '/basket/functionality')))
        self.assert_no_business_writes()

    def test_already_selected_region_needs_no_switch(self):
        self.portal.city, self.portal.region = '61', 'ЮГРСТ'
        result = Checkout(self.client).options({'region': '61'})
        self.assertEqual(result['region'], '61')
        self.assertFalse(self.portal.requests('POST', '/user/set'))
        self.assertTrue(self.portal.requests('GET', '/user/session/get'))
        self.assert_no_business_writes()

    def test_successful_set_without_actual_region_change_fails_closed(self):
        self.portal.ignore_switch = True
        with self.assertRaisesRegex(Failure, '^etm_region_unverified$'):
            Checkout(self.client).options({'region': '61'})
        self.assertEqual(len(self.portal.requests('POST', '/user/set')), 1)
        self.assert_no_checkout()
        self.assert_no_business_writes()

    def test_incomplete_or_inconsistent_session_confirmation_fails_closed(self):
        for session in ({}, {'city': '61'}, {'rg': 'ЮГРСТ'},
                        {'city': '61', 'rg': 'ЮГВЛГ'},
                        {'city': '34', 'rg': 'ЮГРСТ'}):
            with self.subTest(session=session):
                self.setUp()
                self.portal.after_switch_session = deepcopy(session)
                with self.assertRaisesRegex(Failure, '^etm_region_unverified$'):
                    Checkout(self.client).options({'region': '61'})
                self.assert_no_checkout()
                self.assert_no_business_writes()

    def test_invalid_city_descriptor_does_not_attempt_region_change(self):
        for descriptor in ({}, {'name': 'Ростов-на-Дону'},
                           {**CITY, 'class17': ''}, {**CITY, 'class17': None},
                           {**CITY, 'class17': ['ЮГРСТ']},
                           {**CITY, 'class17': 'ЮГРСТ\r\nX: injected'}):
            with self.subTest(descriptor=descriptor):
                self.setUp()
                self.portal.descriptor = deepcopy(descriptor)
                with self.assertRaisesRegex(Failure, '^etm_region_descriptor_invalid$'):
                    self.client.login('61')
                self.assertFalse(self.portal.requests('POST', '/user/set'))
                self.assert_no_checkout()

    def test_switch_rejection_is_not_retried_and_does_not_expose_provider_message(self):
        self.portal.switch_rejection = {
            'status': {'code': 403, 'message': ' '.join((*SECRETS.values(), SESSION))}}
        with self.assertRaises(Failure) as raised:
            Checkout(self.client).options({'region': '61'})
        self.assertEqual(len(self.portal.requests('POST', '/user/set')), 1)
        for secret in (*SECRETS.values(), SESSION):
            self.assertNotIn(secret, str(raised.exception))
            self.assertNotIn(secret, repr(self.client))
        self.assert_no_checkout()

    def test_status_only_success_remains_invalid_for_checkout_reads(self):
        self.client.transport = lambda *_args, **_kwargs: {'status': {'code': 200}}
        with self.assertRaisesRegex(Failure, '^etm_portal_invalid_response$'):
            self.client.call('GET', '/basket/functionality')

    def test_failed_confirmation_cannot_be_bypassed_by_reusing_logged_in_client(self):
        self.portal.ignore_switch = True
        for _ in range(2):
            with self.assertRaises(Failure):
                Checkout(self.client).options({'region': '61'})
        self.assert_no_checkout()

    def test_existing_client_cannot_silently_change_requested_region(self):
        self.client.login('61')
        calls = len(self.portal.calls)
        with self.assertRaisesRegex(Failure, '^etm_portal_region_changed$'):
            self.client.login('34')
        self.assertEqual(len(self.portal.calls), calls)
        self.assert_no_business_writes()

    def test_discovery_and_representation_do_not_leak_credentials_or_session(self):
        result = Checkout(self.client).options({'region': '61'})
        visible = json.dumps(result, ensure_ascii=False) + repr(self.client)
        for secret in (*SECRETS.values(), SESSION):
            self.assertNotIn(secret, visible)
        self.assertIn(SESSION, self.vault.sensitive)
        self.assert_no_business_writes()

    def test_close_restores_original_region_and_is_idempotent(self):
        self.client.login('61')
        self.client.close()
        self.assertEqual((self.portal.city, self.portal.region), ('34', 'ЮГВЛГ'))
        calls = len(self.portal.calls)
        self.client.close()
        self.assertEqual(len(self.portal.calls), calls)
        self.assert_no_business_writes()

    def test_close_does_not_overwrite_an_external_region_change(self):
        self.client.login('61')
        self.portal.city, self.portal.region = '77', 'МОСКВА'
        with self.assertRaisesRegex(Failure, '^etm_region_restore_conflict$'):
            self.client.close()
        self.assertEqual(len(self.portal.requests('POST', '/user/set')), 1)
        self.assertEqual(self.portal.city, '77')

    def test_close_never_claims_an_ignored_restore_succeeded(self):
        self.client.login('61')
        self.portal.ignore_switch = True
        with self.assertRaisesRegex(Failure, '^etm_region_restore_unverified$'):
            self.client.close()
        self.assertEqual(self.portal.city, '61')

    def test_close_restores_after_failed_switch_verification(self):
        self.portal.after_switch_session = {'city': '0', 'rg': 'UNKNOWN'}
        with self.assertRaisesRegex(Failure, '^etm_region_unverified$'):
            self.client.login('61')
        self.assertIsNone(self.client.verified_region)
        self.portal.after_switch_session = None
        self.client.close()
        self.assertEqual((self.portal.city, self.portal.region), ('34', 'ЮГВЛГ'))

    def test_failed_switch_verification_does_not_allow_overwriting_external_region(self):
        self.portal.after_switch_session = {'city': '77', 'rg': 'МОСКВА'}
        with self.assertRaisesRegex(Failure, '^etm_region_unverified$'):
            self.client.login('61')
        with self.assertRaisesRegex(Failure, '^etm_region_restore_conflict$'):
            self.client.close()
        self.assertEqual(len(self.portal.requests('POST', '/user/set')), 1)

    def test_reused_client_rechecks_region_before_business_operation(self):
        self.client.login('61')
        self.portal.city, self.portal.region = '34', 'ЮГВЛГ'
        with self.assertRaisesRegex(Failure, '^etm_region_changed_during_operation$'):
            Checkout(self.client).options({'region': '61'})
        self.assert_no_checkout()


if __name__ == '__main__':
    unittest.main()
