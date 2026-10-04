import copy
import json
from pathlib import Path
import unittest

from automation_integrations import wirenboard_control_contract as control


ORG = '00000000-0000-4000-8000-000000000001'
GROUP = '00000000-0000-4000-8000-000000000002'
PARENT = '00000000-0000-4000-8000-000000000003'
NEW = '00000000-0000-4000-8000-000000000004'
OTHER_ORG = '00000000-0000-4000-8000-000000000005'


def snapshot(key, data, status=200):
    result = {key: {'http_status': status, 'data': data}}
    if key in ('services', 'diagnostic'):
        result['controller'] = {'http_status': 200, 'data': controller()}
    if key == 'groups' or key.startswith('controller:'):
        result['group'] = {'http_status': 200, 'data': group()}
    return result


def group(identifier=GROUP, name='Room', children=None, organization=ORG):
    return {'id': identifier, 'name': name, 'organization': {'id': organization, 'name': 'Org'},
            'level': 0, 'subgroups': children or []}


def controller(serial='ABC', **fields):
    return {'id': NEW, 'serialNumber': serial, 'organization': {'id': ORG},
            'description': 'Before', 'group': {'id': GROUP, 'name': 'Room'}, **fields}


class ControlContractTests(unittest.TestCase):
    def test_fixed_operations_build_exact_schema_bodies(self):
        cases = [
            ('controller_update', {'serial_number': 'abc', 'fields': {'metricsEnabled': True, 'metricsSendIntervalSeconds': 60}},
             'PATCH', '/controllers/ABC/', {'metricsEnabled': True, 'metricsSendIntervalSeconds': 60}),
            ('request_diagnostic', {'serial_number': 'abc'}, 'POST', '/controllers/ABC/request-diagnostic/', None),
            ('service_add', {'serial_number': 'abc', 'port': 1883, 'name': 'MQTT'}, 'POST', '/controllers/ABC/services/', {'port': 1883, 'name': 'MQTT'}),
            ('service_update', {'serial_number': 'abc', 'port': 1883, 'fields': {'name': 'Broker'}},
             'PATCH', '/controllers/ABC/services/1883/', {'name': 'Broker'}),
            ('service_delete', {'serial_number': 'abc', 'port': 1883}, 'DELETE', '/controllers/ABC/services/1883/', None),
            ('group_create', {'organization_id': ORG, 'name': 'Room', 'parent': PARENT}, 'POST', '/groups/', {'organization': ORG, 'name': 'Room', 'parent': PARENT}),
            ('group_update', {'id': GROUP, 'fields': {'parent': None, 'name': 'Moved'}}, 'PATCH', '/groups/' + GROUP + '/', {'parent': None, 'name': 'Moved'}),
            ('group_delete', {'id': GROUP}, 'DELETE', '/groups/' + GROUP + '/', None),
            ('group_attach', {'id': GROUP, 'controllers': ['abc', 'def']}, 'POST', '/groups/' + GROUP + '/attach-controllers/', {'controllers': ['ABC', 'DEF']}),
            ('group_detach', {'controllers': ['abc']}, 'POST', '/groups-detach-from-controllers/', {'controllers': ['ABC']}),
            ('controller_delete', {'serial_number': 'abc'}, 'DELETE', '/controllers/ABC/', None),
        ]
        self.assertEqual({case[0] for case in cases}, set(control.OPERATIONS))
        for operation, params, method, path, body in cases:
            with self.subTest(operation=operation):
                self.assertEqual(control.build(operation, params), {'method': method, 'path': path, 'body': body})
                self.assertTrue(control.OPERATIONS[operation]['confirmation_required'])

    def test_unknown_endpoints_paths_and_readonly_fields_rejected(self):
        cases = [
            ('reboot', {'serial_number': 'abc'}), ('raw', {'method': 'DELETE', 'url': 'https://untrusted.test'}),
            ('controller_delete', {'serial_number': '../users/me'}), ('controller_delete', {'serial_number': 'A' * 37}),
            ('group_delete', {'id': GROUP + '/controllers/'}), ('group_delete', {'id': GROUP.replace('-', '')}),
            ('request_diagnostic', {'serial_number': 'abc', 'body': {'command': 'reboot'}}),
            ('controller_update', {'serial_number': 'abc', 'fields': {}}),
            ('controller_update', {'serial_number': 'abc', 'fields': {'firmwareVersion': 'fake'}}),
            ('controller_update', {'serial_number': 'abc', 'fields': {'serialNumber': 'new'}}),
            ('controller_update', {'serial_number': 'abc', 'fields': {'organization': OTHER_ORG}}),
            ('controller_update', {'serial_number': 'abc', 'fields': {'group': GROUP}}),
            ('controller_update', {'serial_number': 'abc', 'fields': {'isAgentOk': True}}),
            ('service_update', {'serial_number': 'abc', 'port': 1883, 'fields': {'port': 1884}}),
            ('service_add', {'serial_number': 'abc', 'port': 1883, 'displayName': 'Readonly'}),
            ('group_update', {'id': GROUP, 'fields': {'organization': OTHER_ORG}}),
            ('group_update', {'id': GROUP, 'fields': {'subgroups': []}}),
            ('group_create', {'organization_id': ORG, 'name': 'New', 'id': GROUP}),
        ]
        for operation, params in cases:
            with self.subTest(operation=operation, params=params), self.assertRaises(ValueError):
                control.build(operation, params)

    def test_boolean_integer_string_bounds_and_missing_values(self):
        cases = [
            ('service_add', {'serial_number': 'abc', 'port': True}),
            ('service_add', {'serial_number': 'abc', 'port': '1883'}),
            ('service_add', {'serial_number': 'abc', 'port': 0}),
            ('service_add', {'serial_number': 'abc', 'port': 65536}),
            ('service_add', {'serial_number': 'abc', 'port': 1, 'name': 'a' * 65}),
            ('controller_update', {'serial_number': 'abc', 'fields': {'metricsEnabled': 1}}),
            ('controller_update', {'serial_number': 'abc', 'fields': {'metricsSendIntervalSeconds': True}}),
            ('controller_update', {'serial_number': 'abc', 'fields': {'metricsSendIntervalSeconds': 59}}),
            ('controller_update', {'serial_number': 'abc', 'fields': {'metricsSendIntervalSeconds': 241}}),
            ('controller_update', {'serial_number': 'abc', 'fields': {'description': 'x' * 256}}),
            ('group_create', {'organization_id': ORG, 'name': ' '}),
            ('group_create', {'organization_id': ORG, 'name': 'x' * 256}),
            ('group_update', {'id': GROUP, 'fields': {'parent': GROUP}}),
            ('group_update', {'id': GROUP, 'fields': {}}),
            ('group_attach', {'id': GROUP, 'controllers': []}),
            ('group_attach', {'id': GROUP, 'controllers': ['a', 'A']}),
            ('group_attach', {'id': GROUP, 'controllers': ['A' + str(i) for i in range(21)]}),
            ('group_detach', {'controllers': 'ABC'}), ('controller_update', {'fields': {'description': 'New'}}),
        ]
        for operation, params in cases:
            with self.subTest(operation=operation, params=params), self.assertRaises(ValueError):
                control.validate(operation, params)
        self.assertEqual(control.build('service_add', {'serial_number': 'abc', 'port': 65535, 'name': ''})['body'], {'port': 65535, 'name': ''})

    def test_coordinates_match_decimal_contract_and_geographic_bounds(self):
        valid = {'description': None, 'latitude': 52.1234567, 'longitude': '-180.0000000',
                 'metricsEnabled': False, 'metricsSendIntervalSeconds': 240}
        p = {'serial_number': 'abc', 'fields': valid}
        expected = {**valid, 'latitude': '52.1234567'}
        self.assertEqual(control.build('controller_update', p)['body'], expected)
        for key, value in [('latitude', 90.0000001), ('longitude', -180.1), ('latitude', True),
                           ('longitude', float('nan')), ('latitude', float('inf')), ('latitude', '1e2'),
                           ('latitude', '12.12345678'), ('longitude', 'http://untrusted.test')]:
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, 'invalid_coordinate'):
                control.validate('controller_update', {'serial_number': 'abc', 'fields': {key: value}})
        cleared = {'serial_number': 'abc', 'fields': {'latitude': None, 'longitude': None, 'description': ''}}
        self.assertEqual(control.build('controller_update', cleared)['body'], cleared['fields'])

    def test_metadata_schema_strict_and_normalization_does_not_alias(self):
        params = {'serial_number': 'abc', 'fields': {'userDefinedData': [{'label': 'Room', 'value': 'Lab'}]}}
        original = copy.deepcopy(params)
        result = control.validate('controller_update', params)
        result['fields']['userDefinedData'][0]['value'] = 'Changed'
        self.assertEqual(params, original)
        for metadata in ([{'key': 'Room', 'value': 'Lab'}], [{'label': '', 'value': 'Lab'}],
                         [{'label': 'Room', 'value': ''}], [{'label': 'Room', 'value': 'x' * 1025}],
                         [{'label': 'Room', 'value': 'Lab', 'readonly': True}],
                         [{'label': 'Room', 'value': 'Lab'}] * 101, {'Room': 'Lab'}):
            with self.subTest(metadata_type=type(metadata).__name__), self.assertRaises(ValueError):
                control.validate('controller_update', {'serial_number': 'abc', 'fields': {'userDefinedData': metadata}})
        for metadata in (None, []):
            self.assertEqual(control.build('controller_update', {'serial_number': 'abc', 'fields': {'userDefinedData': metadata}})['body'], {'userDefinedData': metadata})

    def test_plan_never_uses_mutation_response_urls_and_services_use_collection(self):
        plan = control.verification_plan('service_update', {'serial_number': 'abc', 'port': 1883, 'fields': {'name': 'Broker'}},
                                         response={'url': 'https://untrusted.test', 'port': 22})
        self.assertEqual(plan, [{'key': 'services', 'method': 'GET', 'path': '/controllers/ABC/services/'}])
        self.assertEqual(control.verification_plan('controller_update', {'serial_number': 'abc', 'fields': {'description': 'New'}}),
                         [{'key': 'controller', 'method': 'GET', 'path': '/controllers/ABC/'}])

    def test_group_plan_expands_after_authoritative_group_read(self):
        params = {'id': GROUP, 'fields': {'parent': PARENT}}
        initial = control.verification_plan('group_update', params)
        self.assertEqual(initial, [{'key': 'group', 'method': 'GET', 'path': '/groups/' + GROUP + '/'}])
        second = control.verification_plan('group_update', params, before=snapshot('group', group()))
        self.assertEqual(second[0], initial[0])
        self.assertEqual(second[1], {'key': 'groups', 'method': 'GET', 'path': '/groups/', 'query': {'organization_id': ORG}})
        self.assertEqual(control.verification_plan('group_create', {'organization_id': ORG, 'name': 'Room'}), [second[1]])

    def test_precondition_ignores_volatile_and_unrelated_controller_fields(self):
        params = {'serial_number': 'abc', 'fields': {'description': 'New'}}
        before = snapshot('controller', controller(lastAgentPingAt='old', metricsEnabled=True))
        latest = copy.deepcopy(before)
        latest['controller']['data'].update(lastAgentPingAt='new', metricsEnabled=False)
        self.assertEqual(control.precondition('controller_update', params, before), control.precondition('controller_update', params, latest))
        latest['controller']['data']['description'] = 'Another edit'
        self.assertNotEqual(control.precondition('controller_update', params, before), control.precondition('controller_update', params, latest))

    def test_update_verification_uses_readback_and_decimal_equivalence(self):
        params = {'serial_number': 'abc', 'fields': {'description': 'New', 'latitude': '52.10', 'metricsEnabled': True}}
        before = snapshot('controller', controller(latitude='0', metricsEnabled=False))
        after = snapshot('controller', controller(description='New', latitude='52.1000000', metricsEnabled=True))
        self.assertTrue(control.verify('controller_update', params, before, after)['verified'])
        self.assertFalse(control.verify('controller_update', params, before, before, response=params['fields'])['verified'])
        after['controller']['data']['metricsEnabled'] = 1
        self.assertFalse(control.verify('controller_update', params, before, after)['verified'])

    def test_service_precondition_and_verification_are_port_scoped(self):
        params = {'serial_number': 'abc', 'port': 1883, 'fields': {'name': 'Broker'}}
        before = snapshot('services', [{'id': 'service-a', 'port': 1883, 'name': 'Old'}, {'port': 8080, 'name': 'Web'}])
        unrelated = copy.deepcopy(before)
        unrelated['services']['data'][1]['name'] = 'Changed'
        self.assertEqual(control.precondition('service_update', params, before), control.precondition('service_update', params, unrelated))
        after = snapshot('services', [{'id': 'service-a', 'port': 1883, 'name': 'Broker'}])
        self.assertTrue(control.verify('service_update', params, before, after)['verified'])
        self.assertFalse(control.verify('service_delete', {'serial_number': 'abc', 'port': 1883}, before, after)['verified'])
        self.assertTrue(control.verify('service_delete', {'serial_number': 'abc', 'port': 1883}, before, snapshot('services', []))['verified'])
        with self.assertRaisesRegex(ValueError, 'service_already_exists'):
            control.precondition('service_add', {'serial_number': 'abc', 'port': 1883}, before)
        with self.assertRaisesRegex(ValueError, 'service_not_found'):
            control.precondition('service_update', params, snapshot('services', []))

    def test_group_create_verified_by_unique_new_tree_node_not_write_response(self):
        params = {'organization_id': ORG, 'name': 'New room', 'parent': PARENT}
        before = snapshot('groups', [group(PARENT, children=[group(GROUP, 'New room')])])
        after = snapshot('groups', [group(PARENT, children=[group(GROUP, 'New room'), group(NEW, 'New room')])])
        result = control.verify('group_create', params, before, after, response={'name': 'New room', 'organization': ORG, 'parent': PARENT})
        self.assertEqual(result, {'verified': True, 'reason': 'new_group_observed', 'resource_id': NEW})
        self.assertFalse(control.verify('group_create', params, before, before, response={'id': NEW})['verified'])
        after['groups']['data'][0]['subgroups'].append(group(OTHER_ORG, 'New room'))
        self.assertFalse(control.verify('group_create', params, before, after)['verified'])

    def test_group_move_verifies_parent_in_tree_and_rejects_cycles(self):
        params = {'id': GROUP, 'fields': {'parent': PARENT, 'name': 'Moved'}}
        before = {**snapshot('group', group()), **snapshot('groups', [group(), group(PARENT, 'Parent')])}
        after = snapshot('groups', [group(PARENT, 'Parent', [group(GROUP, 'Moved')])])
        control.precondition('group_update', params, before)
        self.assertTrue(control.verify('group_update', params, before, after)['verified'])
        wrong_parent = snapshot('groups', [group(GROUP, 'Moved'), group(PARENT, 'Parent')])
        self.assertFalse(control.verify('group_update', params, before, wrong_parent)['verified'])
        cyclic = {**snapshot('group', group()), **snapshot('groups', [group(GROUP, children=[group(PARENT)])])}
        with self.assertRaisesRegex(ValueError, 'group_parent_cycle'):
            control.precondition('group_update', params, cyclic)
        foreign = {**snapshot('group', group()), **snapshot('groups', [group(), group(PARENT, organization=OTHER_ORG)])}
        with self.assertRaisesRegex(ValueError, 'group_parent_not_in_organization'):
            control.precondition('group_update', params, foreign)

    def test_group_attach_and_detach_check_every_target_controller(self):
        params = {'id': GROUP, 'controllers': ['abc', 'def']}
        before = {**snapshot('group', group()), **snapshot('controller:ABC', controller(group=None)),
                  **snapshot('controller:DEF', controller('DEF', group=None))}
        control.precondition('group_attach', params, before)
        partial = {**snapshot('controller:ABC', controller()), **snapshot('controller:DEF', controller('DEF', group=None))}
        self.assertFalse(control.verify('group_attach', params, before, partial)['verified'])
        full = {**snapshot('controller:ABC', controller()), **snapshot('controller:DEF', controller('DEF'))}
        self.assertTrue(control.verify('group_attach', params, before, full)['verified'])
        self.assertTrue(control.verify('group_detach', {'controllers': ['abc', 'def']}, full, before)['verified'])
        foreign = copy.deepcopy(before)
        foreign['controller:DEF']['data']['organization']['id'] = OTHER_ORG
        with self.assertRaisesRegex(ValueError, 'controller_not_in_group_organization'):
            control.precondition('group_attach', params, foreign)

    def test_diagnostic_async_request_is_not_archive_completion(self):
        params = {'serial_number': 'abc'}
        before = snapshot('diagnostic', {'id': None, 'created': None, 'status': 'not_requested'})
        pending = control.verify('request_diagnostic', params, before, before)
        self.assertFalse(pending['verified'])
        self.assertEqual(pending['status'], 'pending')
        after = snapshot('diagnostic', {'id': NEW, 'created': '2026-10-04T10:00:00Z', 'status': 'requested'})
        verified = control.verify('request_diagnostic', params, before, after)
        self.assertTrue(verified['verified'])
        self.assertFalse(verified['archive_complete'])

    def test_delete_only_verifies_fresh_404_not_auth_or_network_failure(self):
        for operation, params, key, data in [('controller_delete', {'serial_number': 'abc'}, 'controller', controller()),
                                            ('group_delete', {'id': GROUP}, 'group', group())]:
            with self.subTest(operation=operation):
                before = snapshot(key, data)
                self.assertTrue(control.verify(operation, params, before, snapshot(key, None, 404))['verified'])
                for status in (200, 401, 403, 500):
                    self.assertFalse(control.verify(operation, params, before, snapshot(key, data, status))['verified'])
                self.assertFalse(control.verify(operation, params, before, {})['verified'])

    def test_failed_or_invalid_read_never_verifies_success(self):
        cases = [
            ('controller_update', {'serial_number': 'abc', 'fields': {'description': 'New'}}, 'controller'),
            ('service_add', {'serial_number': 'abc', 'port': 1883}, 'services'),
            ('group_create', {'organization_id': ORG, 'name': 'New'}, 'groups'),
            ('group_attach', {'id': GROUP, 'controllers': ['abc']}, 'controller:ABC'),
        ]
        for operation, params, key in cases:
            for after in ({}, snapshot(key, None), snapshot(key, {}, 403)):
                with self.subTest(operation=operation, after=after):
                    self.assertFalse(control.verify(operation, params, {}, after)['verified'])

    def test_wrong_controller_identity_never_prepares_or_verifies(self):
        params = {'serial_number': 'abc', 'fields': {'description': 'New'}}
        before = snapshot('controller', controller())
        for changes in ({'serialNumber': 'OTHER'}, {'id': GROUP}, {'organization': {'id': OTHER_ORG}}):
            after = snapshot('controller', controller(description='New', **changes))
            with self.subTest(changes=changes):
                self.assertFalse(control.verify('controller_update', params, before, after)['verified'])
        for value in (controller('OTHER'), controller(id='not-uuid'), controller(organization={'id': 'bad'})):
            with self.subTest(value=value), self.assertRaises(ValueError):
                control.precondition('controller_update', params, snapshot('controller', value))

    def test_wrong_group_and_batch_controller_identity_never_verify(self):
        params = {'id': GROUP, 'controllers': ['abc']}
        before = {**snapshot('group', group()), **snapshot('controller:ABC', controller(group=None))}
        for changes in ({'serialNumber': 'OTHER'}, {'id': GROUP}, {'organization': {'id': OTHER_ORG}}):
            after = snapshot('controller:ABC', controller(**changes))
            with self.subTest(changes=changes):
                self.assertFalse(control.verify('group_attach', params, before, after)['verified'])
        wrong = {**before, **snapshot('group', group(PARENT))}
        with self.assertRaisesRegex(ValueError, 'group_identity_mismatch'):
            control.precondition('group_attach', params, wrong)
        update = {'id': GROUP, 'fields': {'name': 'New'}}
        with self.assertRaisesRegex(ValueError, 'group_identity_mismatch'):
            control.verification_plan('group_update', update, before=snapshot('group', group(PARENT)))
        self.assertFalse(control.verify('group_delete', {'id': GROUP}, snapshot('group', group(PARENT)), snapshot('group', None, 404))['verified'])

    def test_implemented_body_fields_remain_subset_of_documented_schema(self):
        try:
            import yaml
        except ImportError:
            self.skipTest('schema snapshot verification requires PyYAML')
        path = Path(__file__).resolve().parents[1] / 'docs/WIRENBOARD_OPENAPI.yaml'
        schemas = yaml.safe_load(path.read_text())['components']['schemas']
        fields = schemas['PatchedUpdateControllerRequest']['properties']
        self.assertTrue(set(control.CONTROLLER_FIELDS) < set(fields))
        self.assertEqual(fields['metricsSendIntervalSeconds']['minimum'], 60)
        self.assertEqual(fields['metricsSendIntervalSeconds']['maximum'], 240)
        self.assertEqual(fields['userDefinedData']['maxItems'], 100)
        self.assertEqual(set(schemas['UserDefinedDataRequest']['properties']), {'label', 'value'})
        self.assertEqual(set(schemas['PatchedControllerServiceRequest']['properties']), {'port', 'name'})
        self.assertEqual(set(schemas['CreateGroupRequest']['required']), {'name', 'organization'})
        self.assertEqual(set(schemas['PatchedUpdateGroupRequest']['properties']), {'name', 'parent'})
        self.assertEqual(set(schemas['ControllerGroupSetterRequest']['required']), {'controllers'})

    def test_catalog_and_generator_expose_exact_confirmed_contracts(self):
        try:
            from ops.build_wirenboard_capabilities import write_operations
        except ImportError:
            self.skipTest('capability generator requires PyYAML')
        root = Path(__file__).resolve().parents[1]
        registry = json.loads((root / 'registry/catalog.json').read_text())
        card = next(row for row in registry['services'] if row['id'] == 'wirenboard')
        generated = write_operations()
        self.assertEqual(set(card['write_operations']), set(control.OPERATIONS) | {'controller_exec'})
        for operation, metadata in control.OPERATIONS.items():
            with self.subTest(operation=operation):
                published = card['write_operations'][operation]
                self.assertEqual(set(published['params']), set(metadata['params']))
                self.assertEqual(set(published['schema']['required']), set(metadata['required']))
                self.assertEqual(published['schema'], generated[operation]['schema'])
                self.assertTrue(published['confirmation_required'])
                self.assertEqual(published['account_access'], 'not_live_tested')
        self.assertEqual(len(card['operations']), 10)
        self.assertEqual(card['write_operations']['controller_exec']['adapter_kind'], 'composite')

    def test_regeneration_preserves_read_receipts_without_claiming_write_access(self):
        try:
            from ops.build_wirenboard_capabilities import build, ADAPTERS, WRITE_ADAPTERS, COMPOSITE_ADAPTERS
        except ImportError:
            self.skipTest('capability generator requires PyYAML')
        root = Path(__file__).resolve().parents[1]
        receipt = {'ok': True, 'checked_at': '2026-10-04T07:00:00Z'}
        previous = {'capabilities': [{'id': 'GET /api/v1/users/me/', 'adapter': 'me',
                                     'access': 'observed_success', 'live_check': receipt}]}
        result = build(root / 'docs/WIRENBOARD_OPENAPI.yaml', '2026-10-04', previous)
        self.assertEqual(result['total'], 72)
        self.assertEqual(len(result['capabilities']), 72)
        self.assertEqual((len(ADAPTERS), len(WRITE_ADAPTERS), len(COMPOSITE_ADAPTERS)), (10, 11, 1))
        for row in result['capabilities']:
            if row['adapter'] == 'me':
                self.assertEqual(row['access'], 'observed_success')
                self.assertEqual(row['live_check'], receipt)
            if row['id'] in WRITE_ADAPTERS or row['id'] in COMPOSITE_ADAPTERS:
                self.assertEqual(row['execution'], 'integration_write')
                self.assertEqual(row['access'], 'unverified')
                self.assertEqual(row['live_check']['status'], 'not_tested')
            if row['id'] == 'POST /api/v1/auth/logout/':
                self.assertEqual(row['execution'], 'not_implemented')


if __name__ == '__main__':
    unittest.main()
