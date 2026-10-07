"""Regressions for the 2026-10-07 contract/transport audit; no live effects."""
import ast
import copy
from datetime import datetime, timezone
import http.client
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from automation_integrations import abcp_api as abcp, abcp_write
from automation_integrations import wirenboard as wb, wirenboard_http as wb_http
from ops import abcp_audit_release as release
from ops import abcp_build_release as builder


ROOT = Path(__file__).resolve().parents[1]


class Response(io.BytesIO):
    def __init__(self, body, content_type='application/json'):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode())
        self.status = 200
        self.headers = {'Content-Type': content_type}


class AbcpAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        credential = self.root / 'credentials.env'
        credential.write_text('ABCP_API_HOST=test.public.api.abcp.ru\nABCP_API_LOGIN=fixture\n'
                              'ABCP_API_PASSWORD_MD5=fixture-private\n')
        credential.chmod(0o600)
        self.config = {'state_dir': str(self.root / 'state'), 'credentials_file': str(credential)}

    def test_mixed_basket_items_block_duplicate_workflow_submission(self):
        request = {'action': 'prepare', 'service': 'abcp', 'operation': 'abcp_client_post_basket_add',
                   'params': {'positions': [{'code': 'part-A', 'quantity': 1},
                                             {'code': 'part-B', 'quantity': 1}]}}
        context = {'scope': ['owner', 'owner', 'session', 'topic'], 'message_id': '1'}
        opener = MagicMock()
        opener.open.return_value = Response({'status': 0, 'positions': [
            {'status': 1, 'code': 'part-A'}, {'status': 0, 'code': 'part-B', 'errorMessage': 'unavailable'}]})
        draft = abcp_write.process(request, context, self.config, clock=lambda: 100)
        identifier = draft['draft_id']
        abcp_write.process({'action': 'confirm', 'confirmation_text': 'ПОДТВЕРЖДАЮ ' + identifier},
                           {**context, 'message_id': '2'}, self.config, clock=lambda: 101)
        execute = {'action': 'execute', 'draft_id': identifier}
        with patch.object(abcp.urllib.request, 'build_opener', return_value=opener):
            result = abcp_write.process(execute, context, self.config, clock=lambda: 102)
            self.assertEqual(result['status'], 'partial')
            self.assertTrue(result['partial_success'])
            self.assertEqual(result['result']['data']['positions'][0]['code'], 'part-A')
            self.assertEqual(abcp_write.process(execute, context, self.config)['status'], 'partial')
            replacement = abcp_write.process(request, context, self.config, clock=lambda: 103)
            self.assertEqual(replacement['error'], 'existing_unresolved_draft')
        self.assertEqual(opener.open.call_count, 1)

    def test_nonfinite_response_is_structured_failure_without_retry(self):
        for number in (b'NaN', b'Infinity', b'-Infinity', b'1e999'):
            for write, operation, params in (
                (False, 'abcp_client_get_orders_version', {}),
                (True, 'abcp_client_post_basket_add', {'positions': []}),
            ):
                with self.subTest(number=number, write=write):
                    opener = MagicMock()
                    opener.open.return_value = Response(b'{"value":' + number + b'}')
                    expected = 'invalid_provider_json_outcome_unknown' if write else 'invalid_provider_json'
                    with self.assertRaisesRegex(abcp.AbcpError, '^' + expected + '$'):
                        abcp.execute(self.config, operation, params, write=write, opener=opener)
                    self.assertEqual(opener.open.call_count, 1)

    def test_incomplete_http_body_is_not_an_unstructured_runner_failure(self):
        for write, operation, params in (
            (False, 'abcp_client_get_orders_version', {}),
            (True, 'abcp_client_post_basket_add', {'positions': []}),
        ):
            opener = MagicMock()
            response = MagicMock()
            response.__enter__.return_value = response
            response.read.side_effect = http.client.IncompleteRead(b'{"sta', 5)
            opener.open.return_value = response
            error = 'transport_outcome_unknown' if write else 'transport_unavailable'
            with self.assertRaisesRegex(abcp.AbcpError, '^' + error + '$'):
                abcp.execute(self.config, operation, params, write=write, opener=opener)
            self.assertEqual(opener.open.call_count, 1)

    def test_malformed_json_export_is_not_saved_as_successful_binary(self):
        metadata = copy.deepcopy(abcp.operation('abcp_client_get_orders_version'))
        metadata['response_kind'] = 'binary_or_json'
        opener = MagicMock()
        opener.open.return_value = Response(b'{"error":')
        with patch.object(abcp, 'operation', return_value=metadata):
            with self.assertRaisesRegex(abcp.AbcpError, '^invalid_provider_json$'):
                abcp.execute(self.config, 'fixture', {}, opener=opener)
        self.assertFalse((self.root / 'state' / 'results').exists())

    def test_documented_batch_maximum_is_checked_before_credentials(self):
        with patch.object(abcp, 'credentials') as credentials:
            with self.assertRaisesRegex(abcp.AbcpError, '^invalid_array_length$'):
                abcp.execute(self.config, 'abcp_client_post_search_batch', {'search': [
                    {'brand': 'A', 'number': '1'}] * 101})
        credentials.assert_not_called()
        abcp.validate('abcp_client_post_search_batch', {'search': [{'brand': 'A', 'number': '1'}] * 100})

    def test_documented_page_bounds_unsigned_ids_and_lengths(self):
        cases = [
            ('abcp_client_get_orders', {'limit': 0}),
            ('abcp_client_get_orders', {'limit': 1001}),
            ('abcp1_admin_get_cp_users_profiles', {'limit': 101}),
            ('ts_admin_get_cp_ts_good_receipts_get', {'limit': 1001}),
            ('ts_admin_get_cp_ts_legal_persons_list', {'limit': 51}),
            ('ts_admin_get_cp_ts_legal_persons_list', {'skip': -1}),
            ('ts_admin_post_cp_ts_supplier_orders_orders_list', {'supplierIds': [-1]}),
            ('abcp1_admin_get_cp_users', {'organizationName': 'abc'}),
        ]
        for operation, params in cases:
            with self.subTest(operation=operation, params=params), self.assertRaises(abcp.AbcpError):
                abcp.validate(operation, params)
        abcp.validate('ts_admin_get_cp_ts_legal_persons_list', {'limit': 50, 'skip': 0})

    def test_schema_generator_bounds_and_capability_schemas_agree(self):
        # Extract this pure helper without importing the build-only bs4 dependency
        # or running the generator's file writes during a unit test.
        path = ROOT / 'docs/abcp-api-research/build_contract.py'
        node = next(node for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'apply_reviewed_bounds')
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
        contract = abcp._contract()['operations']
        capabilities = json.loads((ROOT / 'registry/capabilities/abcp.json').read_text())['capabilities']
        for row in capabilities:
            operation = copy.deepcopy(contract[row['id']])
            namespace['apply_reviewed_bounds'](operation)
            self.assertEqual(operation, contract[row['id']])
            self.assertEqual(row['parameters'], operation['parameters'])
            self.assertEqual(row['executable_contracts'][row['id']]['params_schema'], operation['parameters'])

    def test_business_requirement_flags_are_optional_and_ts2_does_not_require_ts1_status(self):
        abcp.validate('ts_admin_get_cp_ts_legal_persons_list', {})
        abcp.validate('ts_admin_post_cp_ts_delivery_update', {'id': 1, 'trackNumber': 'sample'}, write=True)
        abcp.validate('ts_admin_post_cp_ts_order_pickings_change_status',
                      {'id': 1, 'operationStatusId': 3}, write=True)
        with self.assertRaisesRegex(abcp.AbcpError, '^missing_required_parameter$'):
            abcp.validate('ts_admin_post_cp_ts_order_pickings_change_status', {'id': 1}, write=True)
        path = ROOT / 'docs/abcp-api-research/build_contract.py'
        node = next(node for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'req')
        namespace = {'re': re}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
        required = namespace['req']
        for description in ('признак обязательности веса', 'Признак обязательности договора',
                            'для заказов 1.0 обязательный при смене статуса операции с 5 на 3'):
            self.assertFalse(required({'name': 'field', 'description': description, 'required_text': ''}))
        self.assertTrue(required({'name': 'field', 'description': '[обязательный] ID', 'required_text': ''}))

    def test_status_navigation_is_discoverable_in_both_generated_catalog_fields(self):
        destination = self.root / 'bundle'
        builder.build(destination)
        catalog = json.loads((destination / 'registry/catalog.json').read_text())
        self.assertIn(builder.STATUS_NAVIGATION, catalog['instructions'])
        self.assertEqual(catalog['instructions'], catalog['services'][0]['instructions'])
        for operation in ('abcp_client_get_orders_version', 'ts_admin_get_cp_ts_positions_list',
                          'ts_admin_get_cp_ts_positions_get'):
            self.assertIn(operation, catalog['instructions'])


class WirenBoardAuditTests(unittest.TestCase):
    def test_optional_pagination_links_fall_back_to_count(self):
        first = {'count': 3, 'results': [{'serialNumber': 'A'}, {'serialNumber': 'B'}]}
        wb._validate_response('controllers', first)
        self.assertEqual(wb.pagination(first, {'page_size': 2})['next_page'], 2)
        last = {'count': 3, 'results': [{'serialNumber': 'C'}]}
        self.assertFalse(wb.pagination(last, {'page_size': 2, 'page': 2})['has_more'])
        with self.assertRaisesRegex(Exception, '^invalid_provider_response$'):
            wb._validate_response('controllers', {**first, 'next': False})

    def test_nonfinite_numbers_rejected_for_direct_and_ssh_envelopes(self):
        for number in (b'NaN', b'1e999'):
            with self.subTest(number=number):
                opener = MagicMock()
                opener.open.return_value = Response(b'{"value":' + number + b'}')
                with patch('urllib.request.build_opener', return_value=opener):
                    with self.assertRaisesRegex(wb_http.TransportFailure, '^invalid_json$'):
                        wb_http.call('GET', '/users/me/', config={'wirenboard_transport': 'direct'})
                remote = subprocess.CompletedProcess([], 0, stdout=(
                    b'{"ok":true,"status":200,"data":{"value":' + number + b'}}'))
                with patch('subprocess.run', return_value=remote) as run:
                    with self.assertRaisesRegex(wb_http.TransportFailure, '^wirenboard_ssh_request_failed$'):
                        wb_http.call('GET', '/users/me/', config={'wirenboard_transport': 'ssh:example-hermes'})
                    self.assertEqual(run.call_count, 1)


class AbcpReleaseAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.home, self.root, self.source, self.backup = (base / name for name in ('home', 'root', 'source', 'backup'))
        for path in (self.home, self.root, self.source):
            path.mkdir()
        self.state = {'active_agents': 0, 'active_work': None, 'restart_requested': False,
                      'gateway_state': 'running', 'updated_at': datetime.now(timezone.utc).isoformat(),
                      'pid': 123, 'code_sha': 'fixture'}
        (self.home / 'gateway_state.json').write_text(json.dumps(self.state))
        self.expected, self.before, self.after = {}, {}, {}
        for rel in release.FILES:
            old, new = (b'value = 1\n', b'value = 2\n') if rel.endswith('.py') else (b'{"value":1}', b'{"value":2}')
            for base_path, data in ((self.root / 'release', old), (self.source, new)):
                path = base_path / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            self.expected[rel] = release.sha(old)
            self.before[rel], self.after[rel] = old, new
        for path in (self.home / 'config.yaml', self.root / 'config.json', self.root / 'credentials.env',
                     self.root / 'release/registry/catalog.json', self.root / 'release/automation_integrations/abcp_write.py'):
            path.write_text('protected fixture')
        (self.source / 'expected.json').write_text(json.dumps(self.expected))
        release.prepare(self.source, self.backup, self.home, self.root)

    def assert_targets(self, expected):
        self.assertEqual({rel: (self.root / 'release' / rel).read_bytes() for rel in release.FILES}, expected)

    def test_exact_three_file_update_and_guarded_rollback(self):
        protected = release.protected(self.home, self.root)
        self.assertTrue(release.transition(self.backup, self.home, self.root)['applied'])
        self.assert_targets(self.after)
        self.assertTrue(release.transition(self.backup, self.home, self.root, rollback=True)['rolled_back'])
        self.assert_targets(self.before)
        self.assertEqual(protected, release.protected(self.home, self.root))

    def test_active_agent_prevents_every_replacement(self):
        (self.home / 'gateway_state.json').write_text(json.dumps({**self.state, 'active_agents': 1}))
        with self.assertRaisesRegex(release.GuardError, '^gateway_not_idle$'):
            release.transition(self.backup, self.home, self.root)
        self.assert_targets(self.before)

    def test_concurrent_target_change_rejected_before_first_replacement(self):
        changed = self.root / 'release' / release.FILES[-1]
        changed.write_bytes(b'concurrent update')
        with self.assertRaisesRegex(release.GuardError, '^cas_or_artifact_mismatch$'):
            release.transition(self.backup, self.home, self.root)
        self.assert_targets({**self.before, release.FILES[-1]: b'concurrent update'})

    def test_failure_after_replacement_restores_entire_preimage(self):
        real = release.atomic
        def fail_after_replace(path, data, mode=0o600):
            real(path, data, mode)
            if path == self.root / 'release' / release.FILES[1] and data == self.after[release.FILES[1]]:
                raise OSError('simulated directory fsync failure')
        with patch.object(release, 'atomic', side_effect=fail_after_replace):
            with self.assertRaises(OSError):
                release.transition(self.backup, self.home, self.root)
        self.assert_targets(self.before)

    def test_navigation_release_updates_only_two_instruction_fields_and_rolls_back(self):
        before = {'instructions': 'Original.', 'services': [
            {'id': 'abcp', 'instructions': 'Original.', 'operations': {'fixture': {}}}]}
        after = copy.deepcopy(before)
        after['instructions'] += ' ' + builder.STATUS_NAVIGATION
        after['services'][0]['instructions'] = after['instructions']
        catalog = self.root / 'release/registry/catalog.json'
        catalog.write_bytes(release.encoded(before))
        source = self.source / 'registry/catalog.json'
        source.write_bytes(release.encoded(after))
        (self.source / 'expected.json').write_text(json.dumps({'registry/catalog.json': release.sha(catalog.read_bytes())}))
        backup = self.backup.with_name('navigation-backup')
        with patch.object(release, 'FILES', release.CATALOG_FILES):
            release.prepare(self.source, backup, self.home, self.root)
            result = release.transition(backup, self.home, self.root)
            self.assertEqual(result['targets'], 1)
            self.assertEqual(json.loads(catalog.read_text()), after)
            self.assertEqual({rel: (self.root / 'release' / rel).read_bytes()
                              for rel in release.ADAPTER_FILES}, self.before)
            release.transition(backup, self.home, self.root, rollback=True)
        self.assertEqual(json.loads(catalog.read_text()), before)

    def test_navigation_guard_rejects_operation_changes(self):
        before = {'instructions': 'Original.', 'services': [
            {'id': 'abcp', 'instructions': 'Original.', 'operations': {'fixture': {}}}]}
        after = copy.deepcopy(before)
        after['instructions'] += ' Add navigation.'
        after['services'][0]['instructions'] = after['instructions']
        after['services'][0]['operations']['new_permission'] = {}
        with self.assertRaisesRegex(release.GuardError, '^catalog_change_outside_instructions$'):
            release.validate_navigation(release.encoded(before), release.encoded(after))


if __name__ == '__main__':
    unittest.main()
