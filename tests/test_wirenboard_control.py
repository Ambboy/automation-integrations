"""Offline safety and readback tests for confirmed cloud management."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import unittest

from automation_integrations import wirenboard_control as workflow
from automation_integrations.api_read import Failure
from automation_integrations.wirenboard_shell import ShellFailure


SERIAL = 'TEST123'
ORG = '00000000-0000-4000-8000-000000000001'
ACCESS = 'wb-private-access-token'
REFRESH = 'wb-private-refresh-token'
TUNNEL_KEY = 'wb-private-tunnel-key'
TUNNEL_URL = 'https://test123.ssh.wirenboard.cloud/redirect?key=' + TUNNEL_KEY


class FakeVault:
    def __init__(self):
        self.calls = []
        self.sensitive = []

    def get(self, service):
        self.calls.append(service)
        return {'WBCLOUD_ACCESS_TOKEN': ACCESS, 'WBCLOUD_REFRESH_TOKEN': REFRESH}


class FakeCloud:
    """Authoritative GET state is separate from mutation response claims."""
    def __init__(self):
        self.calls = []
        self.owner = 'owner-id'
        self.controller = {'id': '00000000-0000-4000-8000-000000000002', 'serialNumber': SERIAL, 'description': 'Before',
                           'organization': {'id': ORG}, 'group': None,
                           'metricsEnabled': True, 'metricsSendIntervalSeconds': 60,
                           'agentStatus': 'online', 'lastSeenAt': '2026-10-01T00:00:00Z'}
        self.services = [{'port': 8080, 'name': 'Dashboard'}]
        self.diagnostic = {'requestedAt': '2026-10-01T00:00:00Z', 'status': 'ready'}
        self.apply_mutations = True
        self.mutation_error = None
        self.readback_error = None
        self.on_mutation = None

    @property
    def mutations(self):
        return [call for call in self.calls if call[0] != 'GET']

    def call(self, method, path, **kwargs):
        self.calls.append((method, path, deepcopy(kwargs)))
        if method == 'GET':
            if path == '/users/me/':
                return {'id': self.owner}
            if self.readback_error is not None and self.mutations:
                raise self.readback_error
            if path == '/controllers/' + SERIAL + '/':
                if self.controller is None:
                    raise Failure('resource_not_found', 404)
                return deepcopy(self.controller)
            if path == '/controllers/' + SERIAL + '/services/':
                return deepcopy(self.services)
            if path == '/controllers/' + SERIAL + '/diagnostic/':
                return deepcopy(self.diagnostic)
            raise AssertionError('Unexpected read route: ' + path)
        if self.on_mutation:
            self.on_mutation(method, path, kwargs)
        if self.mutation_error is not None:
            raise self.mutation_error
        body = kwargs.get('body')
        if (method, path) == ('PATCH', '/controllers/' + SERIAL + '/'):
            claimed = {**deepcopy(self.controller), **deepcopy(body)}
            if self.apply_mutations:
                self.controller.update(deepcopy(body))
            return claimed
        if (method, path) == ('DELETE', '/controllers/' + SERIAL + '/'):
            if self.apply_mutations:
                self.controller = None
            return None
        if (method, path) == ('POST', '/controllers/' + SERIAL + '/request-diagnostic/'):
            return None
        if (method, path) == ('POST', '/controllers/' + SERIAL + '/tcp-tunnels/ssh/'):
            return {'tunnelRedirectUrl': TUNNEL_URL, 'tunnelKey': TUNNEL_KEY}
        if (method, path) == ('POST', '/controllers/' + SERIAL + '/services/'):
            if self.apply_mutations:
                self.services.append(deepcopy(body))
            return deepcopy(body)
        if method == 'DELETE' and path == '/controllers/' + SERIAL + '/services/8080/':
            if self.apply_mutations:
                self.services = [row for row in self.services if row['port'] != 8080]
            return None
        raise AssertionError('Unexpected mutation route: ' + path)


class FakeShell:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.result = result if result is not None else {'stdout': 'hello', 'exit_code': 0}
        self.error = error

    def call(self, serial, url, command, *, credentials=None, timeout=30):
        self.calls.append((serial, url, deepcopy(command), credentials, timeout))
        if self.error:
            raise self.error
        return deepcopy(self.result)


class WirenboardControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.config = {'state_dir': str(self.state), 'wirenboard_transport': 'ssh:example-hermes',
                       'item_ids': {'wirenboard': 'wb-credential-item'}}
        self.context = {'scope': ['owner', 'owner', 'session-key', 'thread'], 'message_id': 'm1'}
        self.vault = FakeVault()
        self.http = FakeCloud()
        self.request = {'action': 'prepare', 'service': 'wirenboard', 'operation': 'controller_update',
                        'params': {'serial_number': SERIAL, 'fields': {'description': 'After'}}}

    def action(self, request, *, message='m1', now=1000, context=None, http=None, shell=None):
        return workflow.process(request, context or {**self.context, 'message_id': message}, self.config,
                                http=http or self.http, vault=self.vault, clock=lambda: now, shell=shell)

    def prepare(self, request=None):
        return self.action(request or self.request)['draft_id']

    def confirm(self, ident, *, message='m2', now=1000):
        return self.action({'action': 'confirm', 'confirmation_text': 'ПОДТВЕРЖДАЮ ' + ident},
                           message=message, now=now)

    def execute(self, ident, **kwargs):
        return self.action({'action': 'execute', 'draft_id': ident}, **kwargs)

    def status(self, ident, **kwargs):
        return self.action({'action': 'status', 'draft_id': ident}, **kwargs)

    def draft_path(self, ident):
        return self.state / 'wirenboard-writes' / (ident + '.json')

    def test_invalid_requests_and_unauthenticated_scope_fail_before_credentials(self):
        invalid = [
            {**self.request, 'operation': 'arbitrary_command'},
            {**self.request, 'params': {'serial_number': '../OTHER', 'fields': {'description': 'After'}}},
            {**self.request, 'params': {'serial_number': SERIAL, 'fields': {'admin': True}}},
            {**self.request, 'params': {'serial_number': SERIAL, 'fields': {}}},
            {**self.request, 'params': {'serial_number': SERIAL, 'fields': {'metricsEnabled': 'yes'}}},
            {**self.request, 'confirmed': True},
            {'action': 'execute', 'draft_id': '../private'},
        ]
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(Failure):
                self.action(request)
        with self.assertRaises(Failure):
            self.action(self.request, context={'scope': ['attacker', 'owner', 'session-key', 'thread'], 'message_id': 'm1'})
        self.assertEqual(self.vault.calls, [])
        self.assertEqual(self.http.calls, [])

    def test_prepare_reads_actual_object_and_records_private_preview_without_mutation(self):
        result = self.action(self.request)
        self.assertEqual(result['status'], 'prepared')
        self.assertEqual(result['confirmation_command'], 'ПОДТВЕРЖДАЮ ' + result['draft_id'])
        self.assertEqual(result['expires_at'], 1600)
        self.assertEqual(self.http.mutations, [])
        self.assertIn(('GET', '/controllers/' + SERIAL + '/'), [call[:2] for call in self.http.calls])
        preview = json.dumps(result['preview'], ensure_ascii=False)
        for value in (SERIAL, 'After', 'Before'):
            self.assertIn(value, preview)
        path = self.draft_path(result['draft_id'])
        row = json.loads(path.read_text())
        self.assertIn('before', row)
        self.assertIn('intent_hash', row)
        self.assertIn('target_hash', row)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        for secret in (ACCESS, REFRESH):
            self.assertNotIn(secret, json.dumps(result))

    def test_confirmation_requires_exact_text_in_a_new_native_owner_message(self):
        ident = self.prepare()
        calls_before = len(self.http.calls)
        with self.assertRaisesRegex(Failure, 'owner_confirmation_required'):
            self.execute(ident)
        with self.assertRaisesRegex(Failure, 'new_owner_message_required'):
            self.confirm(ident, message='m1')
        for text in ('yes', 'quoted ПОДТВЕРЖДАЮ ' + ident, 'ПОДТВЕРЖДАЮ ' + ident + '\n'):
            with self.subTest(text=text), self.assertRaises(Failure):
                self.action({'action': 'confirm', 'confirmation_text': text}, message='m2')
        with self.assertRaises(Failure):
            self.action({'action': 'execute', 'draft_id': ident, 'confirmed': True}, message='m2')
        self.assertEqual(self.confirm(ident)['status'], 'confirmed')
        self.assertEqual(len(self.http.calls), calls_before)
        self.assertEqual(self.http.mutations, [])

    def test_scope_is_bound_to_owner_session_and_thread(self):
        ident = self.prepare()
        for scope in (['other', 'other', 'session-key', 'thread'],
                      ['owner', 'owner', 'different-session', 'thread'],
                      ['owner', 'owner', 'session-key', 'different-thread']):
            context = {'scope': scope, 'message_id': 'm2'}
            with self.subTest(scope=scope), self.assertRaisesRegex(Failure, 'draft_scope_mismatch'):
                self.action({'action': 'confirm', 'confirmation_text': 'ПОДТВЕРЖДАЮ ' + ident}, context=context)
            with self.assertRaisesRegex(Failure, 'draft_scope_mismatch'):
                self.status(ident, context=context)
        self.assertEqual(self.http.mutations, [])

    def test_expired_preparation_and_confirmation_cannot_mutate(self):
        ident = self.prepare()
        with self.assertRaises(Failure):
            self.confirm(ident, now=1601)
        self.confirm(ident, now=1001)
        with self.assertRaises(Failure):
            self.execute(ident, now=1601)
        self.assertEqual(self.http.mutations, [])

    def test_controller_update_requires_authoritative_readback_and_cannot_repeat(self):
        ident = self.prepare()
        self.confirm(ident)
        result = self.execute(ident)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(self.http.controller['description'], 'After')
        self.assertEqual(len(self.http.mutations), 1)
        self.execute(ident, now=9000)
        self.status(ident, now=9000)
        self.assertEqual(len(self.http.mutations), 1)

    def test_mutation_response_claim_is_insufficient_without_matching_readback(self):
        ident = self.prepare()
        self.confirm(ident)
        self.http.apply_mutations = False
        result = self.execute(ident)
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertEqual(self.http.controller['description'], 'Before')
        self.assertEqual(len(self.http.mutations), 1)
        self.status(ident)
        self.assertEqual(len(self.http.mutations), 1)

    def test_stale_affected_fields_reject_before_mutation(self):
        ident = self.prepare()
        self.confirm(ident)
        self.http.controller['description'] = 'Someone else changed this'
        with self.assertRaisesRegex(Failure, 'target_changed_prepare_again'):
            self.execute(ident)
        result = self.status(ident)
        self.assertEqual(result['status'], 'rejected')
        self.assertEqual(result['last_error'], 'target_changed_prepare_again')
        self.assertEqual(self.http.mutations, [])

    def test_volatile_controller_health_does_not_invalidate_approved_edit(self):
        ident = self.prepare()
        self.confirm(ident)
        self.http.controller.update(agentStatus='offline', lastSeenAt='2026-10-02T00:00:00Z')
        self.assertEqual(self.execute(ident)['status'], 'verified')
        self.assertEqual(len(self.http.mutations), 1)

    def test_changed_credential_target_cannot_execute_existing_confirmation(self):
        ident = self.prepare()
        self.confirm(ident)
        self.config['item_ids']['wirenboard'] = 'different-credential-item'
        with self.assertRaises(Failure):
            self.execute(ident)
        self.assertEqual(self.http.mutations, [])

    def test_changed_account_identity_rejects_before_mutation(self):
        ident = self.prepare()
        self.confirm(ident)
        self.http.owner = 'different-account'
        with self.assertRaisesRegex(Failure, 'cloud_account_changed'):
            self.execute(ident)
        self.assertEqual(self.http.mutations, [])

    def test_status_cannot_verify_readback_from_a_changed_cloud_account(self):
        ident = self.prepare()
        self.confirm(ident)
        self.http.mutation_error = Failure('request_timeout')
        self.assertEqual(self.execute(ident)['status'], 'outcome_unknown')
        self.http.owner = 'different-account'
        self.http.controller['description'] = 'After'
        calls_before = len(self.http.calls)
        result = self.status(ident)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(result['last_error'], 'cloud_account_changed')
        self.assertTrue(all(path == '/users/me/' for method, path, kwargs in self.http.calls[calls_before:]))

    def test_draft_payload_tampering_is_detected_before_network(self):
        ident = self.prepare()
        self.confirm(ident)
        path = self.draft_path(ident)
        row = json.loads(path.read_text())
        row['params']['fields']['description'] = 'Unapproved change'
        path.write_text(json.dumps(row))
        calls_before = len(self.http.calls)
        for action in (self.status, self.execute):
            with self.assertRaisesRegex(Failure, 'draft_integrity_failed'):
                action(ident)
        self.assertEqual(len(self.http.calls), calls_before)
        self.assertEqual(self.http.mutations, [])

    def test_tampered_before_snapshot_cannot_change_approved_preconditions(self):
        ident = self.prepare()
        path = self.draft_path(ident)
        row = json.loads(path.read_text())
        row['before']['controller']['data']['description'] = 'Invented prior state'
        path.write_text(json.dumps(row))
        with self.assertRaisesRegex(Failure, 'draft_integrity_failed'):
            self.confirm(ident)
        self.assertEqual(self.http.mutations, [])

    def test_submission_marker_is_durable_before_mutation_and_private(self):
        ident = self.prepare()
        self.confirm(ident)
        path = self.draft_path(ident)
        def inspect(method, route, kwargs):
            row = json.loads(path.read_text())
            self.assertEqual(row['status'], 'submitting')
            self.assertIn('submitted_at', row)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.http.on_mutation = inspect
        self.assertEqual(self.execute(ident)['status'], 'verified')

    def test_unknown_submission_never_retries_and_duplicate_prepare_stays_blocked_after_expiry(self):
        ident = self.prepare()
        self.confirm(ident)
        self.http.mutation_error = Failure('request_timeout')
        self.assertEqual(self.execute(ident)['status'], 'outcome_unknown')
        self.execute(ident, now=9000)
        duplicate = self.action(self.request, now=9000)
        self.assertEqual(duplicate['error'], 'existing_unresolved_draft')
        self.assertEqual(duplicate['draft_id'], ident)
        self.assertEqual(len(self.http.mutations), 1)
        self.assertEqual(len(list((self.state / 'wirenboard-writes').glob('*.json'))), 1)

    def test_status_reconciles_uncertain_outcome_only_by_reading(self):
        ident = self.prepare()
        self.confirm(ident)
        self.http.mutation_error = Failure('request_timeout')
        self.assertEqual(self.execute(ident)['status'], 'outcome_unknown')
        self.http.controller['description'] = 'After'
        calls_before = len(self.http.calls)
        self.assertEqual(self.status(ident, now=9000)['status'], 'verified')
        self.assertTrue(all(method == 'GET' for method, path, kwargs in self.http.calls[calls_before:]))
        self.assertEqual(len(self.http.mutations), 1)

    def test_mutation_401_is_rejected_without_refresh_or_replay(self):
        ident = self.prepare()
        self.confirm(ident)
        self.http.mutation_error = Failure('authentication_failed', 401)
        self.assertEqual(self.execute(ident)['status'], 'rejected')
        self.execute(ident)
        self.assertEqual(len(self.http.mutations), 1)
        self.assertFalse(any(path == '/auth/token/refresh/' for method, path, kwargs in self.http.calls))

    def test_readback_error_never_erases_acceptance_or_replays_mutation(self):
        ident = self.prepare()
        self.confirm(ident)
        self.http.readback_error = Failure('access_denied', 403)
        self.assertEqual(self.execute(ident)['status'], 'accepted_unverified')
        self.execute(ident)
        self.status(ident)
        self.assertEqual(len(self.http.mutations), 1)

    def test_unexpected_exception_details_and_tokens_never_escape(self):
        ident = self.prepare()
        self.confirm(ident)
        self.http.mutation_error = RuntimeError('server echoed ' + ACCESS + ' ' + REFRESH)
        result = self.execute(ident)
        self.assertEqual(result['status'], 'outcome_unknown')
        for secret in (ACCESS, REFRESH):
            self.assertNotIn(secret, json.dumps(result))
            self.assertNotIn(secret, self.draft_path(ident).read_text())

    def test_concurrent_execute_submits_exactly_once(self):
        ident = self.prepare()
        self.confirm(ident)
        entered, release = threading.Event(), threading.Event()
        def hold(method, path, kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test synchronization timed out')
        self.http.on_mutation = hold
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.execute, ident)
            try:
                self.assertTrue(entered.wait(5))
                second = pool.submit(self.execute, ident)
            finally:
                release.set()
            self.assertEqual(first.result(5)['status'], 'verified')
            self.assertEqual(second.result(5)['status'], 'verified')
        self.assertEqual(len(self.http.mutations), 1)

    def test_controller_delete_verifies_absence_with_same_account(self):
        ident = self.prepare({**self.request, 'operation': 'controller_delete', 'params': {'serial_number': SERIAL}})
        self.confirm(ident)
        self.assertEqual(self.execute(ident)['status'], 'verified')
        self.assertIsNone(self.http.controller)
        self.assertEqual(len(self.http.mutations), 1)

    def test_service_delete_verifies_collection_without_undocumented_detail_get(self):
        ident = self.prepare({**self.request, 'operation': 'service_delete',
                              'params': {'serial_number': SERIAL, 'port': 8080}})
        self.confirm(ident)
        self.assertEqual(self.execute(ident)['status'], 'verified')
        self.assertEqual(self.http.services, [])
        self.assertFalse(any(method == 'GET' and path.endswith('/services/8080/')
                             for method, path, kwargs in self.http.calls))

    def test_diagnostic_acceptance_does_not_claim_diagnostic_completion(self):
        ident = self.prepare({**self.request, 'operation': 'request_diagnostic', 'params': {'serial_number': SERIAL}})
        self.confirm(ident)
        self.assertEqual(self.execute(ident)['status'], 'accepted_unverified')
        self.assertEqual(len(self.http.mutations), 1)

    def shell_request(self, **params):
        return {**self.request, 'operation': 'controller_exec',
                'params': {'serial_number': SERIAL, 'command': ['printf', 'hello'], **params}}

    def test_invalid_command_requests_never_read_credentials_or_open_tunnels(self):
        invalid = [self.shell_request(command=value) for value in
                   ('printf hello', [], [''], ['printf', '\0'], ['arg'] * 65, [True])]
        invalid += [self.shell_request(timeout=value) for value in (0, 31, True, '30')]
        invalid += [{**self.shell_request(), 'operation': 'controller_reboot'}]
        shell = FakeShell()
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(Failure):
                self.action(request, shell=shell)
        self.assertEqual(self.vault.calls, [])
        self.assertEqual(self.http.calls, [])
        self.assertEqual(shell.calls, [])

    def test_command_prepare_reads_identity_and_tunnel_opens_only_after_confirmation(self):
        shell = FakeShell()
        result = self.action(self.shell_request(timeout=12), shell=shell)
        ident = result['draft_id']
        self.assertEqual(self.http.mutations, [])
        self.assertEqual(shell.calls, [])
        self.assertEqual(result['preview']['parameters']['command'], ['printf', 'hello'])
        with self.assertRaisesRegex(Failure, 'owner_confirmation_required'):
            self.execute(ident, shell=shell)
        self.assertEqual(self.http.mutations, [])
        self.confirm(ident)
        def submitting(method, path, kwargs):
            self.assertEqual(json.loads(self.draft_path(ident).read_text())['status'], 'submitting')
        self.http.on_mutation = submitting
        self.assertEqual(self.execute(ident, shell=shell)['status'], 'verified')
        self.assertEqual([call[:2] for call in self.http.mutations],
                         [('POST', '/controllers/' + SERIAL + '/tcp-tunnels/ssh/')])
        self.assertEqual(shell.calls, [(SERIAL, TUNNEL_URL, ['printf', 'hello'], None, 12)])
        self.execute(ident, shell=shell)
        self.status(ident, shell=shell)
        self.assertEqual(len(self.http.mutations), 1)
        self.assertEqual(len(shell.calls), 1)

    def test_command_output_never_returns_or_persists_cloud_tokens_or_tunnel_secrets(self):
        shell = FakeShell({'stdout': ' '.join((ACCESS, REFRESH, TUNNEL_KEY, TUNNEL_URL)), 'exit_code': 0})
        ident = self.prepare(self.shell_request())
        self.confirm(ident)
        result = self.execute(ident, shell=shell)
        self.assertEqual(result['status'], 'verified')
        for secret in (ACCESS, REFRESH, TUNNEL_KEY, TUNNEL_URL):
            self.assertNotIn(secret, json.dumps(result))
            self.assertNotIn(secret, self.draft_path(ident).read_text())

    def test_uncertain_command_is_never_reexecuted_or_replaced_even_after_expiry(self):
        shell = FakeShell(error=RuntimeError('terminal disconnected ' + TUNNEL_KEY))
        request = self.shell_request()
        ident = self.prepare(request)
        self.confirm(ident)
        result = self.execute(ident, shell=shell)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertNotIn(TUNNEL_KEY, json.dumps(result))
        self.execute(ident, shell=shell, now=9000)
        self.status(ident, shell=shell, now=9000)
        duplicate = self.action(request, shell=shell, now=9000)
        self.assertEqual(duplicate['error'], 'existing_unresolved_draft')
        self.assertEqual(duplicate['draft_id'], ident)
        self.assertEqual(len(self.http.mutations), 1)
        self.assertEqual(len(shell.calls), 1)

    def test_nonzero_command_exit_does_not_claim_success(self):
        shell = FakeShell({'stdout': 'operation failed', 'exit_code': 2})
        ident = self.prepare(self.shell_request())
        self.confirm(ident)
        result = self.execute(ident, shell=shell)
        self.assertEqual(result['status'], 'accepted_unverified')
        self.assertFalse(result['mutation_verified'])
        self.assertEqual(result['verification']['exit_code'], 2)

    def test_definitive_precommand_rejections_allow_new_confirmation_after_repair(self):
        for code in ('ssh_authentication_failed', 'terminal_session_rejected',
                     'shell_connection_failed', 'untrusted_tunnel_origin'):
            with self.subTest(code=code):
                request = self.shell_request(command=['printf', code])
                ident = self.prepare(request)
                self.confirm(ident)
                shell = FakeShell(error=ShellFailure(code))
                result = self.execute(ident, shell=shell)
                self.assertEqual(result['status'], 'rejected')
                self.assertEqual(result['last_error'], code)
                self.execute(ident, shell=shell)
                self.assertEqual(len(shell.calls), 1)
                replacement = self.action(request, now=9000)
                self.assertEqual(replacement['status'], 'prepared')
                self.assertNotEqual(replacement['draft_id'], ident)

    def test_ambiguous_shell_failures_still_block_replacement_and_replay(self):
        for code in ('shell_outcome_unknown', 'shell_timeout_outcome_unknown',
                     'shell_transport_failed_outcome_unknown', 'invalid_terminal_response',
                     'invalid_shell_response', 'shell_transport_failed'):
            with self.subTest(code=code):
                request = self.shell_request(command=['printf', code])
                ident = self.prepare(request)
                self.confirm(ident)
                shell = FakeShell(error=ShellFailure(code))
                self.assertEqual(self.execute(ident, shell=shell)['status'], 'outcome_unknown')
                self.execute(ident, shell=shell)
                self.assertEqual(len(shell.calls), 1)
                self.assertEqual(self.action(request, now=9000)['error'], 'existing_unresolved_draft')

    def test_public_shell_result_bounds_json_escaping_and_keeps_full_private_output(self):
        output = '\0' * 20000
        ident = self.prepare(self.shell_request())
        self.confirm(ident)
        result = self.execute(ident, shell=FakeShell({'stdout': output, 'exit_code': 0}))
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['result']['exit_code'], 0)
        self.assertTrue(result['result']['stdout_truncated'])
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), workflow.MAX_PUBLIC_RESULT)
        self.assertLess(len(result['result']['stdout']), len(output))
        stored = json.loads(self.draft_path(ident).read_text())
        self.assertEqual(stored['result']['stdout'], output)
        status = self.status(ident)
        self.assertTrue(status['result']['stdout_truncated'])
        self.assertLessEqual(len(json.dumps(status, ensure_ascii=False)), workflow.MAX_PUBLIC_RESULT)

    def test_small_public_shell_result_explicitly_reports_complete_stdout(self):
        ident = self.prepare(self.shell_request())
        self.confirm(ident)
        result = self.execute(ident, shell=FakeShell({'stdout': 'complete\n', 'exit_code': 0}))
        self.assertEqual(result['result'], {'stdout': 'complete\n', 'exit_code': 0, 'stdout_truncated': False})

    def test_shell_requires_valid_controller_and_organization_uuids(self):
        original = deepcopy(self.http.controller)
        for fields in ({'id': None}, {'id': 'not-a-uuid'}, {'organization': None},
                       {'organization': {}}, {'organization': {'id': 'not-a-uuid'}}):
            with self.subTest(fields=fields):
                self.http.controller = {**deepcopy(original), **fields}
                with self.assertRaisesRegex(Failure, 'controller_identity_not_verified'):
                    self.prepare(self.shell_request())
        self.assertEqual(self.http.mutations, [])
        self.http.controller = original
        ident = self.prepare(self.shell_request())
        self.confirm(ident)
        self.http.controller['organization'] = None
        shell = FakeShell()
        with self.assertRaisesRegex(Failure, 'controller_identity_not_verified'):
            self.execute(ident, shell=shell)
        self.assertEqual(self.http.mutations, [])
        self.assertEqual(shell.calls, [])

    def test_preview_exposes_previous_values_and_named_group_deletion_scope(self):
        prepared = self.action(self.request)
        self.assertEqual(prepared['preview']['previous_values'], {'description': 'Before'})
        child = {'id': '00000000-0000-4000-8000-000000000005', 'name': 'Child',
                 'organization': {'id': ORG}, 'subgroups': []}
        group = {'id': '00000000-0000-4000-8000-000000000004', 'name': 'Plant room',
                 'organization': {'id': ORG}, 'subgroups': [child]}
        preview = workflow.preview('group_delete', {'id': group['id']},
                                   {'group': {'http_status': 200, 'data': group}}, {})
        self.assertTrue(preview['destructive'])
        self.assertEqual(preview['targets'][0]['name'], 'Plant room')
        self.assertEqual({row['id'] for row in preview['affected_groups']}, {group['id'], child['id']})
        self.assertEqual(self.http.mutations, [])

    def test_prepare_cannot_replace_a_submission_in_progress_after_expiry(self):
        ident = self.prepare()
        self.confirm(ident)
        entered, release, preparing = threading.Event(), threading.Event(), threading.Event()
        def hold(method, path, kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test synchronization timed out')
        def duplicate():
            preparing.set()
            return self.action(self.request, now=9000)
        self.http.on_mutation = hold
        self.http.mutation_error = Failure('request_timeout')
        with ThreadPoolExecutor(max_workers=2) as pool:
            submission = pool.submit(self.execute, ident)
            try:
                self.assertTrue(entered.wait(5))
                replacement = pool.submit(duplicate)
                self.assertTrue(preparing.wait(5))
            finally:
                release.set()
            self.assertEqual(submission.result(5)['status'], 'outcome_unknown')
            self.assertEqual(replacement.result(5)['error'], 'existing_unresolved_draft')
        self.assertEqual(len(self.http.mutations), 1)
        self.assertEqual(len(list((self.state / 'wirenboard-writes').glob('*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
