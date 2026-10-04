import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation_integrations.api_read import execute, Failure, validate, sanitize, OPERATIONS
from automation_integrations.catalog import Catalog

ROOT = Path(__file__).resolve().parents[1]


class FakeVault:
    def __init__(self):
        self.sensitive = ['TOP_SECRET']; self.calls = []

    def get(self, service):
        from automation_integrations.api_read import FIELDS
        self.calls.append(service)
        return dict.fromkeys(FIELDS[service], 'TOP_SECRET')


class FakeHTTP:
    def __init__(self, *responses):
        self.responses = list(responses); self.calls = []

    def call(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class CatalogTests(unittest.TestCase):
    def test_discovery_without_brand_and_after_context_loss(self):
        catalog = Catalog(ROOT / 'registry/catalog.json')
        for query, service in [('закрывающие', 'saby'), ('остатки кабеля', 'etm'),
                               ('поступление оплаты', 'tochka'), ('поездка', 'yandex_go')]:
            with self.subTest(query=query):
                self.assertEqual(catalog.find(query)['services'][0]['id'], service)
        first = catalog.context()
        self.assertEqual(Catalog(catalog.path).context(), first)
        self.assertLess(len(first), 2200)

    def test_registry_and_executor_agree(self):
        for item in Catalog(ROOT / 'registry/catalog.json').load()['services']:
            self.assertEqual(set(item['operations']), set(OPERATIONS[item['id']]))
            for name, operation in item['operations'].items():
                self.assertEqual(set(operation['params']), set(OPERATIONS[item['id']][name]))

    def test_fresh_receipt_does_not_claim_other_operations(self):
        with tempfile.TemporaryDirectory() as state:
            c = Catalog(ROOT / 'registry/catalog.json', state)
            Path(state, 'etm.login_check.json').write_text(json.dumps({'ok': False, 'error': 'network_unavailable'}))
            card = c.find(service='etm')['services'][0]
            self.assertFalse(card['operations']['login_check']['last_check']['ok'])
            self.assertNotIn('last_check', card['operations']['price'])

    def test_unknown_and_malformed_operations_never_read_secrets(self):
        vault = FakeVault()
        requests = [{'service': 'tochka', 'operation': 'payment'},
                    {'service': 'saby', 'operation': 'documents', 'params': {'method': 'СБИС.ПодписатьДокумент'}},
                    {'service': 'etm', 'operation': 'search', 'params': {'query': '\nprivate'}},
                    {'service': 'yandex_go', 'operation': 'users', 'params': {'limit': True}},
                    {'service': 'etm', 'operation': 'goods', 'params': {}},
                    {'service': 'saby', 'operation': 'documents', 'params': {'type': 'Договор'}}]
        for request in requests:
            with self.subTest(request=request), self.assertRaises(Failure):
                execute(request, {}, vault, FakeHTTP())
        self.assertEqual(vault.calls, [])

    def test_yandex_company_header_required_except_discovery(self):
        for operation in ('auth_list', 'users'):
            http = FakeHTTP({'users': []})
            execute({'service': 'yandex_go', 'operation': operation}, {'yandex_client_id': 'company'}, FakeVault(), http)
            self.assertEqual('X-YaTaxi-Selected-Corp-Client-Id' in http.calls[0][1]['headers'], operation != 'auth_list')

    def test_etm_session_and_credentials_never_returned(self):
        http = FakeHTTP({'status': {'code': 200}, 'data': {'session': 'SESSION_SECRET'}},
                        {'status': {'code': 200}, 'data': {'id': 42, 'session': 'SESSION_SECRET',
                         'text': 'TOP_SECRET SESSION_SECRET https://example.test/signed?q=secret'}})
        result = execute({'service': 'etm', 'operation': 'goods', 'params': {'id': '42'}}, {}, FakeVault(), http)
        rendered = json.dumps(result)
        for secret in ('TOP_SECRET', 'SESSION_SECRET', 'https://'):
            self.assertNotIn(secret, rendered)
        self.assertEqual(result['data']['data']['id'], 42)
        self.assertEqual(http.calls[1][0], ('GET', '/goods/42'))

    def test_saby_reuses_cache_renews_once_and_only_reads(self):
        with tempfile.TemporaryDirectory() as state:
            config = {'state_dir': state, 'saby_org': {'ИНН': 'test'}}
            Path(state, 'saby-session.json').write_text('{"token":"old"}')
            http = FakeHTTP(Failure('authorization_failed', 401), {'token': 'new'}, {'result': {'Документ': []}})
            request = {'service': 'saby', 'operation': 'documents', 'params': {'page_size': 2}}
            result = execute(request, config, FakeVault(), http)
            self.assertTrue(result['ok'])
            self.assertEqual(len(http.calls), 3)
            self.assertEqual(http.calls[0][1]['body']['method'], 'СБИС.СписокДокументов')
            self.assertEqual(json.loads(Path(state, 'saby-session.json').read_text())['token'], 'new')
            self.assertEqual(Path(state, 'saby-session.json').stat().st_mode & 0o777, 0o600)
            second = FakeHTTP({'result': {'Документ': []}})
            execute(request, config, FakeVault(), second)
            self.assertEqual(len(second.calls), 1)

    def test_saby_renewal_is_bounded(self):
        with tempfile.TemporaryDirectory() as state:
            http = FakeHTTP({'token': 'first'}, Failure('authorization_failed', 401),
                            {'token': 'second'}, Failure('authorization_failed', 401))
            with self.assertRaises(Failure):
                execute({'service': 'saby', 'operation': 'documents'},
                        {'state_dir': state, 'saby_org': {}}, FakeVault(), http)
            self.assertEqual(len(http.calls), 4)

    def test_tochka_empty_statements_is_not_empty_transactions_claim(self):
        http = FakeHTTP({'Data': {'Statement': []}})
        result = execute({'service': 'tochka', 'operation': 'statements'}, {}, FakeVault(), http)
        self.assertEqual(http.calls[0][0], ('GET', '/open-banking/v1.0/statements'))
        self.assertEqual(result['data'], {'Data': {'Statement': []}})
        card = Catalog(ROOT / 'registry/catalog.json').find(service='tochka')['services'][0]
        self.assertIn('пустой список не означает', card['instructions'])

    def test_nested_signed_urls_and_sensitive_values(self):
        data = {'Вложение': [{'Файл': {'Ссылка': 'https://signed/?secret=one'}}],
                'note': 'one', 'secret_key': 'hidden', 'amount': 12}
        result = sanitize(data, ['one'])
        self.assertNotIn('one', json.dumps(result)); self.assertEqual(result['amount'], 12)

    def test_redirect_and_bad_bank_ca_fail_closed(self):
        from automation_integrations.api_read import NoRedirect, HTTP
        with self.assertRaises(Failure):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'https://untrusted.test')
        with tempfile.TemporaryDirectory() as tmp:
            ca = Path(tmp) / 'ca.pem'; ca.write_text('invalid')
            with patch('urllib.request.build_opener') as opener, self.assertRaises(ValueError):
                HTTP('tochka', {'tochka_ca': str(ca)}).call('GET', '/accounts')
            opener.assert_not_called()

    def test_deploy_preserves_speech_and_topics_and_other_settings(self):
        try:
            from ops.greif_catalog_config import render
            import yaml
        except ImportError:
            self.skipTest('deployment requires system PyYAML')
        original = {'tts': {'provider': 'automation-speech'}, 'plugins': {'enabled': ['automation-topic-style'],
            'entries': {'automation-topic-style': {'settings': {'enabled': True}}}},
            'platform_toolsets': {'telegram': ['hermes-telegram'], 'cli': ['hermes-cli']},
            'platforms': {'telegram': {'extra': {'disable_topic_auto_rename': True}}}}
        after = yaml.safe_load(render(yaml.safe_dump(original).encode(), Path('/test')))
        self.assertEqual(after['tts'], original['tts'])
        self.assertEqual(after['platforms'], original['platforms'])
        self.assertEqual(after['plugins']['entries']['automation-topic-style'], original['plugins']['entries']['automation-topic-style'])
        self.assertEqual(after['platform_toolsets']['cli'], ['hermes-cli'])
        self.assertEqual(after['platform_toolsets']['telegram'], ['hermes-telegram', 'automation-api'])

    def test_install_and_guarded_rollback_on_isolated_home(self):
        try:
            from ops import greif_catalog_config as deploy
        except ImportError:
            self.skipTest('deployment requires system PyYAML')
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'home'; home.mkdir()
            state = Path(tmp) / 'state'; state.mkdir()
            original = b'plugins:\n  enabled: []\nplatform_toolsets:\n  telegram: [hermes-telegram]\n'
            (home / 'config.yaml').write_bytes(original)
            (state / 'private.json').write_text('{}')
            (state / 'validation.json').write_text('{"passed":true}')
            with patch.multiple(deploy, HOME=home, ROOT=state, PROJECT=ROOT):
                with patch('sys.argv', ['deploy', 'apply']):
                    deploy.main()
                applied = (home / 'config.yaml').read_bytes()
                (home / 'config.yaml').write_bytes(applied + b'other: preserve\n')
                with patch('sys.argv', ['deploy', 'rollback']), self.assertRaises(AssertionError):
                    deploy.main()
                self.assertIn(b'other: preserve', (home / 'config.yaml').read_bytes())
                (home / 'config.yaml').write_bytes(applied)
                with patch('sys.argv', ['deploy', 'rollback']):
                    deploy.main()
                self.assertEqual((home / 'config.yaml').read_bytes(), original)
                self.assertFalse((home / 'plugins/automation-api-catalog').exists())
                self.assertTrue((state / 'disabled-plugin').exists())


if __name__ == '__main__':
    unittest.main()
