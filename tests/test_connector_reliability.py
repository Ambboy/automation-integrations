"""Failures that previously disabled discovery or hid provider diagnostics."""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import email.utils
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

from automation_integrations.api_read import HTTP, Failure, atomic, retry_after_seconds
from automation_integrations.catalog import Catalog
from ops import connector_reliability_release as release
from ops import connector_audit, connector_live_smoke


ROOT = Path(__file__).resolve().parents[1]


class ReliabilityTests(unittest.TestCase):
    def test_parallel_receipts_are_complete_and_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'receipt.json'
            def write(i):
                atomic(path, {'n': i, 'rows': list(range(100))})
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(write, range(50)))
            self.assertIn(json.loads(path.read_text())['n'], range(50))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(tmp).glob('*.tmp')), [])

    def test_corrupt_or_cross_operation_receipt_does_not_break_catalog(self):
        bad = ['{', '[]', '{"ok":"true"}', '{"ok":true,"service":"saby"}']
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'etm.goods.json'
            catalog = Catalog(ROOT / 'registry/catalog.json', tmp)
            for raw in bad:
                path.write_text(raw)
                result = catalog.find(service='etm')['services'][0]['operations']['goods']['last_check']
                self.assertFalse(result['ok'])
                self.assertEqual(result['error'], 'verification_receipt_invalid')
                self.assertGreater(len(catalog.find()['services']), 1)

    def test_http_errors_keep_machine_codes_and_retry_after_without_response_text(self):
        for service, payload, expected in [
            ('saby', {'error': {'code': -32000, 'message': 'PRIVATE'}}, '-32000'),
            ('saby', {'error': {'code': 1, 'data': {'error_code': 403}}}, '403'),
            ('tochka', {'Errors': [{'errorCode': 'UK.OBIE.Field.Invalid'}]}, 'UK.OBIE.Field.Invalid'),
            ('yandex_go', {'code': 'TOO_MANY_REQUESTS', 'message': 'PRIVATE'}, 'TOO_MANY_REQUESTS'),
        ]:
            with self.subTest(service=service), tempfile.TemporaryDirectory() as tmp:
                error = urllib.error.HTTPError('https://provider.test/PRIVATE', 429, 'PRIVATE',
                    {'Retry-After': '37'}, io.BytesIO(json.dumps(payload).encode()))
                # Bank CA is unrelated to response handling; exercise the same
                # HTTP implementation using the Saby base then restore identity.
                client = HTTP(service, {'state_dir': tmp})
                with patch('ssl.PEM_cert_to_DER_cert', return_value=b'fixture'), \
                     patch('pathlib.Path.read_text', return_value='fixture'), \
                     patch('hashlib.sha256') as digest, \
                     patch('ssl.create_default_context') as ssl_context, \
                     patch('urllib.request.build_opener') as opener:
                    client.config['tochka_ca'] = '/fixture/root.pem'
                    digest.return_value.hexdigest.return_value = 'd26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31'
                    opener.return_value.open.side_effect = error
                    with patch.object(client, 'rate_gate'), self.assertRaises(Failure) as caught:
                        client.call('GET', '/read')
                self.assertEqual(caught.exception.code, 'rate_limited')
                self.assertEqual(caught.exception.provider_code, expected)
                self.assertEqual(caught.exception.retry_after, 37)
                self.assertNotIn('PRIVATE', str(caught.exception))

    def test_truncated_success_response_never_becomes_success(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{}'
        response.headers = {'Content-Length': '100'}
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(Failure, '^provider_connection_interrupted$'):
                HTTP('saby', {}).call('POST', '/service/', body={})

    def test_etm_malformed_json_is_a_provider_error(self):
        with patch('subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b'<html>PRIVATE</html>\n200'
            with self.assertRaisesRegex(Failure, '^invalid_provider_json$'):
                HTTP('etm', {'etm_proxy': 'socks5h://127.0.0.1:10929'}).call('GET', '/goods/1')

    def test_retry_after_accepts_dates_and_clamps_untrusted_values(self):
        future = email.utils.format_datetime(dt.datetime.fromtimestamp(1120, dt.timezone.utc))
        with patch('time.time', return_value=1000):
            self.assertEqual(retry_after_seconds(future), 120)
        self.assertEqual(retry_after_seconds('999999999999999'), 86400)
        self.assertEqual(retry_after_seconds('invalid'), 60)

    def test_bank_read_recovers_once_but_writes_and_authorization_never_replay(self):
        from automation_integrations import extended_api
        from automation_integrations.api_read import execute
        from tests.test_api_catalog import FakeVault, FakeHTTP
        from tests.test_openapi_contract import PAYMENT
        for operation in ('accounts', 'open_banking_get_accounts_list'):
            http = FakeHTTP(Failure('request_timeout'), {'Data': {'Account': []}})
            result = execute({'service': 'tochka', 'operation': operation}, {}, FakeVault(), http)
            self.assertTrue(result['ok'])
            self.assertEqual(len(http.calls), 2)
            self.assertEqual(http.calls[0], http.calls[1])
            failed = FakeHTTP(Failure('request_timeout'), Failure('request_timeout'))
            with self.assertRaisesRegex(Failure, '^request_timeout$'):
                execute({'service': 'tochka', 'operation': operation}, {}, FakeVault(), failed)
            self.assertEqual(len(failed.calls), 2)
        for failure in (Failure('authorization_failed', 401), Failure('rate_limited', 429),
                        Failure('invalid_provider_json'), Failure('provider_http_error', 400)):
            http = FakeHTTP(failure)
            with self.assertRaises(Failure):
                execute({'service': 'tochka', 'operation': 'accounts'}, {}, FakeVault(), http)
            self.assertEqual(len(http.calls), 1)
        http = FakeHTTP(Failure('request_timeout'))
        with self.assertRaisesRegex(Failure, '^request_timeout$'):
            extended_api.call('tochka', 'payment_create_payment_for_sign', PAYMENT, {},
                              write=True, vault=FakeVault(), http=http)
        self.assertEqual(len(http.calls), 1)

    def test_corrupt_rate_state_is_explicit_and_not_bypassed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'yandex-rate.json'
            for value in ('{', '[]', '{"blocked_until":"tomorrow"}', '{"next_at":NaN}'):
                path.write_text(value)
                with self.assertRaisesRegex(Failure, '^rate_limit_state_invalid$'):
                    HTTP('yandex_go', {'state_dir': tmp}).rate_gate()
                self.assertEqual(path.read_text(), value)

    def test_inventory_matches_runtime_and_live_probes_are_validated_reads(self):
        report = connector_audit.inventory()
        self.assertTrue(report['passed'], report['problems'])
        self.assertEqual(set(report['services']), {'etm', 'yandex_go', 'saby', 'tochka',
                                                  'wirenboard', 'fal', 'inference', 'abcp'})
        from automation_integrations.api_read import validate
        for service, operation, params in connector_live_smoke.PROBES:
            validate({'service': service, 'operation': operation, 'params': params})

    def test_parameter_index_preserves_full_fal_body_schema_and_operation_metadata(self):
        report = connector_audit.inventory()
        contract = json.loads((ROOT / 'registry/contracts/fal.json').read_text())['operations']
        source = contract['create_asset_collection']
        entry = report['services']['fal']['executable']['create_asset_collection']
        self.assertEqual(entry['parameters'], source['schema'])
        self.assertIn('body', entry['parameters']['required'])
        self.assertEqual(entry['parameters']['properties']['body'], source['schema']['properties']['body'])
        for parameter in source['parameters']:
            self.assertEqual(entry['parameters']['properties'][parameter['name']], parameter['schema'])
        for field in ('effect', 'method', 'path', 'source'):
            self.assertEqual(entry[field], source[field])
        self.assertEqual(entry['tool'], 'integration_write')
        self.assertTrue(entry['available_in_catalog'])
        self.assertEqual(entry['schema_coverage'], 'schema_present_documentation_may_be_partial')
        # Existing object-valued `parameters` contracts retain their complete
        # validation schema through the same generic inventory loop.
        inference = json.loads((ROOT / 'registry/contracts/inference.json').read_text())['operations']['app_run']
        self.assertEqual(report['services']['inference']['executable']['app_run']['parameters'],
                         inference['parameters'])

    def test_release_preserves_other_modules_and_refuses_later_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            layout = release.Layout(source=base/'source', home=base/'home', root=base/'installed', backup=base/'backup')
            layout.home.mkdir()
            layout.config.write_text('original config')
            layout.gateway.write_text('{"active_agents":0}')
            layout.root.mkdir()
            (layout.root/'private.json').write_text('private unchanged')
            for source, target in layout.targets():
                source.parent.mkdir(parents=True, exist_ok=True)
                target.parent.mkdir(parents=True, exist_ok=True)
                source.write_text('new ' + source.name)
                target.write_text('old ' + source.name)
            untouched = layout.root/'release/untouched.py'
            untouched.write_text('unchanged')
            release.prepare(layout)
            # A concurrent file already equal to our candidate is still not
            # ours to roll back when preflight refuses the transaction.
            first_source, first_target = layout.targets()[0]
            original = first_target.read_bytes()
            first_target.write_bytes(first_source.read_bytes())
            with self.assertRaisesRegex(release.guarded.ReleaseError, 'Concurrent'):
                release.apply(layout)
            self.assertEqual(first_target.read_bytes(), first_source.read_bytes())
            first_target.write_bytes(original)
            release.apply(layout)
            with self.assertRaisesRegex(release.guarded.ReleaseError, 'already'):
                release.apply(layout)
            self.assertTrue((layout.backup/'applied.json').exists())
            self.assertFalse((layout.backup/'failed-apply.json').exists())
            for source, target in layout.targets():
                self.assertEqual(source.read_bytes(), target.read_bytes())
            self.assertEqual(untouched.read_text(), 'unchanged')
            self.assertEqual(layout.config.read_text(), 'original config')
            target = layout.targets()[0][1]
            installed = target.read_bytes()
            target.write_text('later user edit')
            with self.assertRaisesRegex(release.guarded.ReleaseError, 'Concurrent'):
                release.rollback(layout)
            self.assertEqual(target.read_text(), 'later user edit')
            target.write_bytes(installed)
            release.rollback(layout)
            for source, target in layout.targets():
                self.assertEqual(target.read_text(), 'old ' + source.name)

    def test_failed_partial_release_restores_original_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            layout = release.Layout(source=base/'source', home=base/'home', root=base/'installed', backup=base/'backup')
            layout.home.mkdir(); layout.root.mkdir()
            layout.config.write_text('config'); layout.gateway.write_text('{"active_agents":0}')
            (layout.root/'private.json').write_text('private')
            for source, target in layout.targets():
                source.parent.mkdir(parents=True, exist_ok=True); target.parent.mkdir(parents=True, exist_ok=True)
                source.write_text('new'); target.write_text('old')
            release.prepare(layout)
            original = release.guarded.atomic
            target = layout.targets()[1][1]
            failed = []
            def interrupted(path, data, *args):
                if Path(path) == target and data == b'new' and not failed:
                    failed.append(True)
                    raise OSError('simulated disk failure')
                return original(path, data, *args)
            with patch.object(release.guarded, 'atomic', side_effect=interrupted):
                with self.assertRaisesRegex(release.guarded.ReleaseError, 'restored'):
                    release.apply(layout)
            self.assertTrue((layout.backup/'failed-apply.json').exists())
            self.assertTrue(all(target.read_text() == 'old' for _, target in layout.targets()))


if __name__ == '__main__':
    unittest.main()
