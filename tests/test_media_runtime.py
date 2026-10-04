import concurrent.futures
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch

from automation_integrations import media_runtime as media


class Response(io.BytesIO):
    def __init__(self, data=b'{}', status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}

    def getheader(self, name, default=None):
        return self.headers.get(name, default)


class TransportTests(unittest.TestCase):
    def test_auth_only_to_fixed_https_hosts_no_redirect_or_retry(self):
        transport = media.MediaHTTP()
        for url in ('http://api.fal.ai/run', 'https://api.fal.ai.attacker.test/run',
                    'https://api.fal.ai@attacker.test/run', 'https://api.fal.ai:444/run',
                    'https://api.fal.ai./run', 'https://api.fal.ai/run#fragment'):
            with patch.object(media, '_open_response') as opened:
                with self.assertRaises(media.MediaError):
                    transport.request('POST', url, headers={'Authorization': 'Key SECRET'})
                opened.assert_not_called()
        connection = Mock()
        with patch.object(media, '_open_response', return_value=(Response(status=302), connection)) as opened:
            with self.assertRaisesRegex(media.MediaError, 'redirect_refused'):
                transport.request('POST', 'https://api.fal.ai/run', body={'prompt': 'x'})
            self.assertEqual(opened.call_count, 1)
            connection.close.assert_called_once()

    def test_user_agent_query_bytes_text_and_safe_errors(self):
        connection = Mock()
        with patch.object(media, '_open_response', return_value=(Response(b'ok'), connection)) as opened:
            out = media.MediaHTTP().request('PUT', 'https://storage.googleapis.com/object?signature=one',
                query={'tag': ['a', 'b']}, body=b'\x00file', response_kind='text')
            self.assertEqual(out, 'ok')
            args = opened.call_args.args
            self.assertEqual(args[2]['User-Agent'], media.USER_AGENT)
            self.assertEqual(args[3], b'\x00file')
            self.assertIn('signature=one&tag=a&tag=b', args[1])
            self.assertNotIn('Authorization', args[2])
        with self.assertRaisesRegex(media.MediaError, 'credential_forwarding_refused'):
            media.MediaHTTP().request('PUT', 'https://storage.googleapis.com/object',
                                     headers={'Authorization': 'Key SECRET'}, body=b'x')
        with patch.object(media, '_open_response', side_effect=OSError('URL SECRET')) as opened:
            with self.assertRaises(media.MediaError) as error:
                media.MediaHTTP().request('POST', 'https://api.inference.sh/run')
            self.assertEqual(str(error.exception), 'network_unavailable')
            self.assertEqual(opened.call_count, 1)

    def test_observed_r2_upload_is_allowed_but_cdn_credentials_are_always_denied(self):
        r2 = '3d0ae9f8488861468c48977d2886dac7.r2.cloudflarestorage.com'
        with patch.object(media, '_open_response', return_value=(Response(b''), Mock())) as opened:
            self.assertEqual(media.MediaHTTP().request('PUT', 'https://' + r2 + '/file?X-Amz-Signature=SIGNED',
                                                      body=b'file', response_kind='text'), '')
            self.assertEqual(opened.call_args.args[0], 'PUT')
            self.assertNotIn('Authorization', opened.call_args.args[2])
        for host in (r2, 'storage.googleapis.com', 'v3.fal.media', 'cloud.inference.sh', 'fal.ai'):
            for header in ('Authorization', 'Cookie', 'X-API-Key', 'aUtHoRiZaTiOn'):
                with self.subTest(host=host, header=header), patch.object(media, '_open_response') as opened:
                    with self.assertRaisesRegex(media.MediaError, 'credential_forwarding_refused'):
                        media.MediaHTTP(allowed_hosts={host}).request('PUT', 'https://' + host + '/file',
                                                                   body=b'file', headers={header: 'SECRET'})
                    opened.assert_not_called()
        # Merely adding a host to the transport allowlist cannot grant it
        # access to provider credentials.
        with patch.object(media, '_open_response') as opened:
            with self.assertRaisesRegex(media.MediaError, 'credential_forwarding_refused'):
                media.MediaHTTP(allowed_hosts={'example.test'}).request('GET', 'https://example.test/file',
                                                                      headers={'Authorization': 'SECRET'})
            opened.assert_not_called()

    def test_bounded_response_retry_after_and_invalid_json(self):
        for response, expected in ((Response(b'12345'), 'response_too_large'),
                (Response(b'x', headers={'Content-Length': '1000'}), 'response_too_large'),
                (Response(b'no'), 'invalid_provider_response'),
                (Response(status=402), 'insufficient_credits')):
            with patch.object(media, '_open_response', return_value=(response, Mock())):
                with self.assertRaisesRegex(media.MediaError, expected):
                    media.MediaHTTP(max_json_bytes=4).request('GET', 'https://api.fal.ai/x')
        with patch.object(media, '_open_response', return_value=(Response(status=429, headers={'Retry-After': '7'}), Mock())):
            with self.assertRaises(media.MediaError) as error:
                media.MediaHTTP().request('GET', 'https://api.fal.ai/x')
            self.assertEqual(error.exception.retry_after, 7)

    def test_fal_exhausted_balance_403_is_classified_without_exposing_body(self):
        cases = (
            (403, b'{"detail":"User is locked. Reason: Exhausted balance. Top up your balance at fal.ai/dashboard/billing. SECRET"}', 'insufficient_credits'),
            (403, b'{"detail":"Insufficient credits for this operation. SECRET"}', 'insufficient_credits'),
            (403, b'{"detail":"Access denied: credits permission required. SECRET"}', 'access_denied'),
            (403, b'{"detail":"Unknown account permission problem SECRET"}', 'access_denied'),
            (402, b'{"detail":"SECRET"}', 'insufficient_credits'),
        )
        for status, body, expected in cases:
            response = Response(body, status=status)
            with self.subTest(status=status, expected=expected), \
                    patch.object(response, 'read', wraps=response.read) as read, \
                    patch.object(media, '_open_response', return_value=(response, Mock())):
                with self.assertRaises(media.MediaError) as raised:
                    media.MediaHTTP().request('POST', 'https://queue.fal.run/fal-ai/model', body={})
                self.assertEqual(raised.exception.code, expected)
                self.assertEqual(raised.exception.http_status, status)
                self.assertNotIn('SECRET', str(raised.exception))
                self.assertNotIn('fal.ai/dashboard', str(raised.exception))
                if status == 403:
                    read.assert_called_once_with(4096)
                else:
                    read.assert_not_called()
        # An unbounded provider body must not be searched past the private cap.
        response = Response(b'x' * 4096 + b' insufficient credits SECRET', status=403)
        with patch.object(media, '_open_response', return_value=(response, Mock())):
            with self.assertRaisesRegex(media.MediaError, '^access_denied$'):
                media.MediaHTTP().request('POST', 'https://queue.fal.run/fal-ai/model', body={})

    def test_sse_has_wall_clock_deadline_and_requests_are_bounded(self):
        with patch.object(media, '_open_response', return_value=(Response(b'data: x\n\n'), Mock())), \
                patch.object(media.time, 'monotonic', side_effect=[0, 2]):
            with self.assertRaisesRegex(media.MediaError, 'request_timeout'):
                media.MediaHTTP().request('POST', 'https://fal.run/model', timeout=1, response_kind='sse')
        with patch.object(media, '_open_response') as opened:
            with self.assertRaisesRegex(media.MediaError, 'request_too_large'):
                media.MediaHTTP(max_binary_bytes=4).request('PUT', 'https://storage.googleapis.com/x', body=b'12345')
            opened.assert_not_called()

    def test_dns_all_answers_are_public_and_connection_is_pinned(self):
        def answer(ip):
            return (socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))
        for address in ('127.0.0.1', '10.1.2.3', '169.254.169.254', '::1', '100.64.0.1'):
            with patch.object(socket, 'getaddrinfo', return_value=[answer('8.8.8.8'), answer(address)]):
                with self.assertRaisesRegex(media.MediaError, 'nonpublic_address_refused'):
                    media._public_addresses('cloud.inference.sh')
        with patch.object(media, '_public_addresses', return_value=['8.8.8.8']), \
                patch.object(media, '_PinnedHTTPSConnection') as factory:
            media._open_response('GET', 'https://api.fal.ai/a?q=1', {}, None, 4)
            factory.assert_called_once_with('api.fal.ai', '8.8.8.8', 4)
            factory.return_value.request.assert_called_once_with('GET', '/a?q=1', body=None, headers={})

    def test_precise_sanitization_preserves_pagination_and_usage(self):
        value = {'session_id': 's1', 'next_page_token': 'next', 'total_tokens': 32,
                 'url': 'https://fal.media/x?signature=SIGNED', 'api_key': 'new-secret',
                 'nested': ['KNOWN', {'key': 'provider-secret'}]}
        cleaned = media.sanitize(value, ['KNOWN'], redact_keys=['key'])
        self.assertEqual(cleaned['session_id'], 's1')
        self.assertEqual(cleaned['next_page_token'], 'next')
        self.assertEqual(cleaned['total_tokens'], 32)
        self.assertEqual(cleaned['api_key'], '[redacted]')
        self.assertEqual(cleaned['nested'], ['[redacted]', {'key': '[redacted]'}])
        self.assertIn('https://', cleaned['url'])


class DurableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_lookup_does_not_create_and_jobs_bind_account_request_identity(self):
        absent = Path(self.tmp.name) / 'absent'
        self.assertFalse(media.job_exists(absent, 'invalid'))
        self.assertFalse(absent.exists())
        store = media.JobStore(self.tmp.name)
        request = {'service': 'fal', 'operation': 'run', 'params': {'prompt': 'x'}}
        row, created = store.prepare('owner-message', request, account='one', provider='fal', scope=['owner'])
        self.assertTrue(created)
        self.assertEqual(len(row['id']), 36)
        self.assertEqual(row['job_id'], row['id'])
        self.assertTrue(media.job_exists(self.tmp.name, row['id']))
        self.assertFalse(store.prepare('owner-message', request, account='one', provider='fal', scope=['owner'])[1])
        with self.assertRaisesRegex(media.MediaError, 'job_identity_conflict'):
            store.prepare('owner-message', {}, account='one', provider='fal', scope=['owner'])
        other, created = store.prepare('owner-message', request, account='two', provider='fal', scope=['owner'])
        self.assertTrue(created)
        self.assertNotEqual(row['id'], other['id'])
        with self.assertRaisesRegex(media.MediaError, 'job_account_mismatch'):
            store.get(row['id'], account='two')

    def test_uncertain_submission_cannot_restart_across_messages_or_processes(self):
        store = media.JobStore(self.tmp.name)
        row, _ = store.prepare('first', {'prompt': 'x'}, account='a', provider='fal')
        store.mark_submitting(row['id'])
        with self.assertRaisesRegex(media.MediaError, 'job_already_submitted'):
            store.mark_submitting(row['id'])
        recovered = media.JobStore(self.tmp.name)
        self.assertEqual(recovered.recover(), [row['id']])
        replacement, created = recovered.prepare('second', {'prompt': 'x'}, account='a', provider='fal')
        self.assertFalse(created)
        self.assertEqual(replacement['id'], row['id'])
        self.assertEqual(replacement['state'], 'outcome_unknown')
        recovered.submitted(row['id'], 'provider-123', result={'url': 'https://fal.media/private'})
        self.assertEqual(recovered.find_provider_job('fal', 'provider-123', account='a')['id'], row['id'])
        self.assertEqual(recovered.list(account='a', statuses=['submitted'])[0]['id'], row['id'])
        recovered.save_result(row['id'], {'done': True}, state='completed')
        with self.assertRaisesRegex(media.MediaError, 'invalid_job_transition'):
            recovered.update(row['id'], state='prepared')
        self.assertEqual(os.stat(recovered.path).st_mode & 0o777, 0o600)

    def test_only_one_concurrent_submit_transition(self):
        store = media.JobStore(self.tmp.name)
        row, _ = store.prepare('one', {}, account='a')
        def submit(_):
            try:
                return store.mark_submitting(row['id'])['state']
            except media.MediaError as exc:
                return exc.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(submit, range(8)))
        self.assertEqual(results.count('submitting'), 1)
        self.assertEqual(results.count('job_already_submitted'), 7)

    def test_budget_reservation_is_atomic_and_reconciled_cost_replaces_estimate(self):
        ledger = media.BudgetLedger(self.tmp.name)
        def reserve(index):
            try:
                ledger.reserve(str(index), 'fal', '0.60', account='one', limits={'day': '1.00'})
                return 'reserved'
            except media.MediaError as exc:
                return exc.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve, range(8)))
        self.assertEqual(results.count('reserved'), 1)
        self.assertEqual(results.count('daily_budget_exceeded'), 7)
        row = ledger.snapshot('fal', account='one')['reservations'][0]
        ledger.reconcile(row['job_id'], '0.20', account='one')
        ledger.reconcile(row['job_id'], '0.20', account='one')
        ledger.reserve('next', 'fal', '0.80', account='one', limits={'day': '1.00'})
        with self.assertRaisesRegex(media.MediaError, 'daily_budget_exceeded'):
            ledger.reserve('over', 'fal', '0.000000001', account='one', limits={'day': '1.00'})
        ledger.reserve('other-account', 'fal', '1', account='two', limits={'day': '1'})

    def test_unknown_cost_without_caps_is_allowed_and_unknown_outcomes_hold_reserve(self):
        ledger = media.BudgetLedger(self.tmp.name)
        ledger.reserve('unpriced', 'inf', None, account='a')
        self.assertEqual(ledger.snapshot('inf', account='a')['unbounded_count'], 1)
        with self.assertRaisesRegex(media.MediaError, 'cost_bound_required_for_budget'):
            ledger.reserve('capped', 'inf', None, account='a', limits={'per_task': '5'})
        with self.assertRaisesRegex(media.MediaError, 'unbounded_previous_spend'):
            ledger.reserve('capped-known', 'inf', '1', account='a', limits={'month': '5'})
        ledger.reserve('known', 'fal', '1', account='a', limits={'day': '1'})
        ledger.mark_unknown('known')
        with self.assertRaisesRegex(media.MediaError, 'daily_budget_exceeded'):
            ledger.reserve('replacement', 'fal', '1', account='a', limits={'day': '1'})
        with self.assertRaisesRegex(media.MediaError, 'budget_account_mismatch'):
            ledger.reconcile('known', '1', account='other')
        ledger.release('known')  # Caller has explicitly established no charge.
        ledger.reserve('after-rejection', 'fal', '1', account='a', limits={'day': '1'})

    def test_actual_overrun_is_recorded_and_blocks_more_spend(self):
        ledger = media.BudgetLedger(self.tmp.name)
        ledger.reserve('one', 'fal', '.5', account='a', limits={'day': '1'})
        result = ledger.reconcile('one', '1.2')
        self.assertEqual(result['actual_cost'], '1.2')
        with self.assertRaisesRegex(media.MediaError, 'daily_budget_exceeded'):
            ledger.reserve('two', 'fal', '.1', account='a', limits={'day': '1'})

    def test_invalid_money_and_symlinked_state_are_rejected(self):
        ledger = media.BudgetLedger(self.tmp.name)
        for amount in (True, 'NaN', 'Infinity', '-1', float('nan')):
            with self.assertRaisesRegex(media.MediaError, 'invalid_money_amount'):
                ledger.reserve('invalid', 'fal', amount, account='a')
        linked = Path(self.tmp.name) / 'link'
        linked.symlink_to(self.tmp.name, target_is_directory=True)
        with self.assertRaisesRegex(media.MediaError, 'private_state_required'):
            media.JobStore(linked)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = media.ArtifactStore(self.tmp.name)

    def test_registration_hides_urls_download_is_bound_private_and_cached(self):
        url = 'https://v3.fal.media/files/image?signature=SECRET'
        row = self.store.register(url, 'job-one')
        self.assertEqual(row['status'], 'remote')
        self.assertNotIn('SECRET', json.dumps(row))
        self.assertNotIn('https', json.dumps(self.store.get(row['id'])))
        self.assertNotEqual(row['id'], self.store.register(url, 'job-two')['id'])
        transport = Mock()
        transport.request.return_value = b'\x89PNG\r\n\x1a\nfixture'
        with patch.object(media, '_public_addresses', return_value=['8.8.8.8']):
            saved = self.store.download_registered(row['id'], transport=transport)
            again = self.store.download_registered(row['id'], transport=transport)
        self.assertEqual(saved, again)
        transport.request.assert_called_once_with('GET', url, headers={}, timeout=60, response_kind='binary')
        self.assertEqual(saved['mime_type'], 'image/png')
        self.assertEqual(Path(saved['path']).stat().st_mode & 0o777, 0o600)
        self.assertNotIn('SECRET', json.dumps(saved))

    def test_artifact_download_rejects_untrusted_hosts_private_dns_html_and_oversize(self):
        for url in ('https://attacker.test/file', 'http://fal.media/file',
                    'https://fal.media.attacker.test/file', 'https://user:secret@fal.media/file'):
            with self.assertRaises(media.MediaError):
                self.store.register(url, 'job')
        row = self.store.register('https://cloud.inference.sh/output', 'job')
        transport = Mock()
        with patch.object(media, '_public_addresses', side_effect=media.MediaError('nonpublic_address_refused')):
            with self.assertRaisesRegex(media.MediaError, 'nonpublic_address_refused'):
                self.store.download_registered(row['id'], transport=transport)
            transport.request.assert_not_called()
        with patch.object(media, '_public_addresses', return_value=['8.8.8.8']):
            for raw, code in ((b'<html>error', 'unexpected_artifact_content'),
                              (b'12345', 'artifact_too_large')):
                transport.request.return_value = raw
                with self.assertRaisesRegex(media.MediaError, code):
                    self.store.download_registered(row['id'], transport=transport,
                                                   max_bytes=4 if raw == b'12345' else 100)

    def test_provider_r2_artifact_registration_and_no_lookalike_domains(self):
        row = self.store.register('https://bucket.r2.cloudflarestorage.com/output?X-Amz-Signature=SIGNED', 'job')
        self.assertEqual(row['status'], 'remote')
        self.assertNotIn('SIGNED', json.dumps(row))
        for host in ('bucket.r2.cloudflarestorage.com.attacker.test', 'attackercloudflarestorage.com',
                     'r2.cloudflarestorage.com.attacker.test'):
            with self.assertRaisesRegex(media.MediaError, 'artifact_host_not_allowed'):
                self.store.register('https://' + host + '/output', 'job')

    def test_concurrent_downloads_do_not_repeat_and_tampering_is_detected(self):
        row = self.store.register('https://fal.media/file', 'job')
        transport = Mock()
        transport.request.return_value = b'\x89PNG\r\n\x1a\nfixture'
        with patch.object(media, '_public_addresses', return_value=['8.8.8.8']), \
                concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            outputs = list(pool.map(lambda _: self.store.download_registered(row['id'], transport=transport), range(4)))
        self.assertEqual(transport.request.call_count, 1)
        self.assertTrue(all(value == outputs[0] for value in outputs))
        Path(outputs[0]['path']).write_bytes(b'\x89PNG\r\n\x1a\nchanged')
        with self.assertRaisesRegex(media.MediaError, 'artifact_integrity_failed'):
            self.store.get(row['id'])


if __name__ == '__main__':
    unittest.main()
