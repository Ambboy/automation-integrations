"""Fixed cloud-management contracts from docs/WIRENBOARD_OPENAPI.yaml.

This module only validates and builds requests. Authorization, confirmation,
execution and verification belong to the control workflow. Port, serial and
batch bounds below are local restrictions within the public API contract.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
import re
import uuid


SOURCE = 'https://wirenboard.cloud/api/v1/docs/schema/'
CONTROLLER_FIELDS = ('description', 'latitude', 'longitude', 'userDefinedData',
                     'metricsEnabled', 'metricsSendIntervalSeconds')
MAX_CONTROLLERS = 20


def _metadata(method, path, params, required, policy, *, destructive=False):
    return {'method': method, 'path': path, 'params': params, 'required': required,
            'effect': 'write', 'confirmation_required': True,
            'destructive': destructive, 'verification': policy, 'source': SOURCE}


OPERATIONS = {
    'controller_update': _metadata('PATCH', '/controllers/{serial_number}/',
        ('serial_number', 'fields'), ('serial_number', 'fields'), 'controller_fields'),
    'request_diagnostic': _metadata('POST', '/controllers/{serial_number}/request-diagnostic/',
        ('serial_number',), ('serial_number',), 'diagnostic_requested'),
    'service_add': _metadata('POST', '/controllers/{serial_number}/services/',
        ('serial_number', 'port', 'name'), ('serial_number', 'port'), 'service_present'),
    'service_update': _metadata('PATCH', '/controllers/{serial_number}/services/{port}/',
        ('serial_number', 'port', 'fields'), ('serial_number', 'port', 'fields'), 'service_fields'),
    'service_delete': _metadata('DELETE', '/controllers/{serial_number}/services/{port}/',
        ('serial_number', 'port'), ('serial_number', 'port'), 'service_absent', destructive=True),
    'group_create': _metadata('POST', '/groups/', ('organization_id', 'name', 'parent'),
        ('organization_id', 'name'), 'new_group_in_tree'),
    'group_update': _metadata('PATCH', '/groups/{id}/', ('id', 'fields'),
        ('id', 'fields'), 'group_fields_in_tree'),
    'group_delete': _metadata('DELETE', '/groups/{id}/', ('id',), ('id',), 'resource_absent', destructive=True),
    'group_attach': _metadata('POST', '/groups/{id}/attach-controllers/', ('id', 'controllers'),
        ('id', 'controllers'), 'controllers_group'),
    'group_detach': _metadata('POST', '/groups-detach-from-controllers/', ('controllers',),
        ('controllers',), 'controllers_ungrouped'),
    'controller_delete': _metadata('DELETE', '/controllers/{serial_number}/',
        ('serial_number',), ('serial_number',), 'resource_absent', destructive=True),
}


def _object(value, allowed, required=(), *, nonempty=False):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError('invalid_parameters')
    if not set(required) <= set(value):
        raise ValueError('missing_parameter')
    if nonempty and not value:
        raise ValueError('empty_update')


def _text(value, maximum, *, blank=False, nullable=False):
    if value is None and nullable:
        return None
    if (not isinstance(value, str) or len(value) > maximum
            or not blank and not value.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('invalid_string')
    return value


def _serial(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,36}', value):
        raise ValueError('invalid_serial_number')
    return value.upper()


def _uuid(value, *, nullable=False):
    if value is None and nullable:
        return None
    try:
        if not isinstance(value, str):
            raise ValueError()
        parsed = uuid.UUID(value)
        if str(parsed) != value.lower():
            raise ValueError()
        return str(parsed)
    except (ValueError, AttributeError):
        raise ValueError('invalid_identifier') from None


def _integer(value, minimum, maximum, error):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(error)
    return value


def _coordinate(value, key):
    if value is None:
        return None
    if type(value) in (int, float):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('invalid_coordinate')
        value = format(Decimal(str(value)), 'f')
    if not isinstance(value, str) or not re.fullmatch(r'-?\d{1,3}(?:\.\d{1,7})?', value):
        raise ValueError('invalid_coordinate')
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError('invalid_coordinate') from None
    bound = 90 if key == 'latitude' else 180
    if not -bound <= number <= bound:
        raise ValueError('invalid_coordinate')
    return format(number, 'f')


def _custom_data(value):
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError('invalid_custom_metadata')
    result = []
    for row in value:
        _object(row, ('label', 'value'), ('label', 'value'))
        result.append({'label': _text(row['label'], 255), 'value': _text(row['value'], 1024)})
    return result


def _controller_fields(fields):
    _object(fields, CONTROLLER_FIELDS, nonempty=True)
    result = {}
    for key, value in fields.items():
        if key == 'description':
            result[key] = _text(value, 255, blank=True, nullable=True)
        elif key in ('latitude', 'longitude'):
            result[key] = _coordinate(value, key)
        elif key == 'userDefinedData':
            result[key] = _custom_data(value)
        elif key == 'metricsEnabled':
            if type(value) is not bool:
                raise ValueError('invalid_boolean')
            result[key] = value
        else:
            result[key] = _integer(value, 60, 240, 'invalid_metrics_interval')
    return result


def validate(operation, params):
    """Return an independent normalized value; never mutate caller input."""
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise ValueError('unknown_operation')
    metadata = OPERATIONS[operation]
    _object(params, metadata['params'], metadata['required'])
    result = dict(params)
    if 'serial_number' in params:
        result['serial_number'] = _serial(params['serial_number'])
    for key in ('id', 'organization_id'):
        if key in params:
            result[key] = _uuid(params[key])
    if 'port' in params:
        result['port'] = _integer(params['port'], 1, 65535, 'invalid_port')
    if 'name' in params:
        result['name'] = _text(params['name'], 64 if operation == 'service_add' else 255,
                               blank=operation == 'service_add')
    if 'parent' in params:
        result['parent'] = _uuid(params['parent'], nullable=True)
    if 'controllers' in params:
        values = params['controllers']
        if not isinstance(values, list) or not 1 <= len(values) <= MAX_CONTROLLERS:
            raise ValueError('invalid_controller_batch')
        result['controllers'] = [_serial(value) for value in values]
        if len(set(result['controllers'])) != len(result['controllers']):
            raise ValueError('duplicate_controller')
    if operation == 'controller_update':
        result['fields'] = _controller_fields(params['fields'])
    elif operation == 'service_update':
        fields = params['fields']
        # Changing a service port also changes its resource identity. Keep this
        # local operation to label updates; add/delete handles other ports.
        _object(fields, ('name',), nonempty=True)
        result['fields'] = {}
        if 'name' in fields:
            result['fields']['name'] = _text(fields['name'], 64, blank=True)
    elif operation == 'group_update':
        fields = params['fields']
        _object(fields, ('name', 'parent'), nonempty=True)
        result['fields'] = {}
        if 'name' in fields:
            result['fields']['name'] = _text(fields['name'], 255)
        if 'parent' in fields:
            result['fields']['parent'] = _uuid(fields['parent'], nullable=True)
            if result['fields']['parent'] == result['id']:
                raise ValueError('group_cannot_parent_itself')
    return result


def build(operation, params):
    """Build one documented mutation; bodyless endpoints use None."""
    p = validate(operation, params)
    metadata = OPERATIONS[operation]
    body = None
    if operation in ('controller_update', 'service_update', 'group_update'):
        body = p['fields']
    elif operation == 'service_add':
        body = {key: p[key] for key in ('port', 'name') if key in p}
    elif operation == 'group_create':
        body = {'organization': p['organization_id'], 'name': p['name']}
        if 'parent' in p:
            body['parent'] = p['parent']
    elif operation in ('group_attach', 'group_detach'):
        body = {'controllers': p['controllers']}
    return {'method': metadata['method'], 'path': metadata['path'].format(**p), 'body': body}


def _read(key, path, query=None):
    result = {'key': key, 'method': 'GET', 'path': path}
    if query is not None:
        result['query'] = query
    return result


def _data(snapshots, key):
    """Snapshots are {key: {http_status: int, data: decoded_body}}."""
    snapshot = (snapshots or {}).get(key)
    if not isinstance(snapshot, dict) or snapshot.get('http_status') != 200 or 'data' not in snapshot:
        raise ValueError('verification_snapshot_missing')
    return snapshot['data']


def _organization(value):
    if not isinstance(value, dict) or not isinstance(value.get('organization'), dict):
        raise ValueError('invalid_verification_response')
    return _uuid(value['organization'].get('id'))


def _controller_identity(value, serial):
    if not isinstance(value, dict) or _serial(value.get('serialNumber')) != serial:
        raise ValueError('controller_identity_mismatch')
    return {'id': _uuid(value.get('id')), 'serial_number': serial, 'organization_id': _organization(value)}


def _group_identity(value, identifier):
    if not isinstance(value, dict) or _uuid(value.get('id')) != identifier:
        raise ValueError('group_identity_mismatch')
    return {'id': identifier, 'organization_id': _organization(value)}


def verification_plan(operation, params, response=None, before=None):
    """Return fixed GETs tagged for snapshots; repeat after new reads are added.

    Group updates first read `group`, then obtain its organization from that
    snapshot and add `groups`. Creation uses the tree before/after because the
    documented creation response has no id. No mutation response authorizes an
    arbitrary URL, path or follow-up operation.
    """
    p = validate(operation, params)
    if operation in ('controller_update', 'controller_delete'):
        return [_read('controller', '/controllers/' + p['serial_number'] + '/')]
    if operation == 'request_diagnostic':
        return [_read('diagnostic', '/controllers/' + p['serial_number'] + '/diagnostic/')]
    if operation.startswith('service_'):
        return [_read('services', '/controllers/' + p['serial_number'] + '/services/')]
    if operation == 'group_create':
        return [_read('groups', '/groups/', {'organization_id': p['organization_id']})]
    if operation in ('group_update', 'group_delete'):
        reads = [_read('group', '/groups/' + p['id'] + '/')]
        if operation == 'group_update' and before and 'group' in before:
            identity = _group_identity(_data(before, 'group'), p['id'])
            reads.append(_read('groups', '/groups/', {'organization_id': identity['organization_id']}))
        return reads
    reads = [_read('controller:' + serial, '/controllers/' + serial + '/') for serial in p['controllers']]
    if operation == 'group_attach':
        reads.insert(0, _read('group', '/groups/' + p['id'] + '/'))
    return reads


def _tree(value):
    if not isinstance(value, list):
        raise ValueError('invalid_verification_response')
    nodes = {}

    def visit(rows, parent=None, depth=0):
        if depth > 64 or not isinstance(rows, list):
            raise ValueError('invalid_verification_response')
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('name'), str):
                raise ValueError('invalid_verification_response')
            identifier = _uuid(row.get('id'))
            if identifier in nodes or len(nodes) >= 10000:
                raise ValueError('invalid_verification_response')
            nodes[identifier] = {'id': identifier, 'name': row['name'], 'parent': parent,
                                 'organization_id': _organization(row)}
            visit(row.get('subgroups'), identifier, depth + 1)

    visit(value)
    return nodes


def _group_id(controller):
    if not isinstance(controller, dict) or 'group' not in controller:
        raise ValueError('invalid_verification_response')
    group = controller['group']
    if group is None:
        return None
    if not isinstance(group, dict):
        raise ValueError('invalid_verification_response')
    return _uuid(group.get('id'))


def _selected(value, keys):
    if not isinstance(value, dict):
        raise ValueError('invalid_verification_response')
    return {key: {'present': key in value, 'value': value.get(key)} for key in keys}


def _services(value):
    if not isinstance(value, list):
        raise ValueError('invalid_verification_response')
    result = {}
    for row in value:
        if not isinstance(row, dict):
            raise ValueError('invalid_verification_response')
        port = _integer(row.get('port'), 1, 65535, 'invalid_verification_response')
        if port in result:
            raise ValueError('invalid_verification_response')
        result[port] = row
    return result


def _parent(tree, parent, organization, target=None):
    if parent is None:
        return None
    if parent not in tree or tree[parent]['organization_id'] != organization:
        raise ValueError('group_parent_not_in_organization')
    ancestor = parent
    while ancestor is not None:
        if ancestor == target:
            raise ValueError('group_parent_cycle')
        ancestor = tree[ancestor]['parent']
    return tree[parent]


def precondition(operation, params, before):
    """Stable fields to compare between preview and the moment of submission.

    Validate target existence and select only relevant current state. Agent
    pings, metrics timestamps and unrelated controller fields are excluded.
    A mismatch means the existing preview must be rebuilt and confirmed again.
    """
    p = validate(operation, params)
    if 'serial_number' in p:
        _controller_identity(_data(before, 'controller'), p['serial_number'])
    if operation in ('controller_update', 'controller_delete'):
        controller = _data(before, 'controller')
        keys = ('id', 'serialNumber', 'organization') + (tuple(p['fields']) if operation == 'controller_update'
                                                        else CONTROLLER_FIELDS + ('group',))
        return _selected(controller, keys)
    if operation == 'request_diagnostic':
        return _selected(_data(before, 'diagnostic'), ('status', 'id', 'created'))
    if operation.startswith('service_'):
        services = _services(_data(before, 'services'))
        current = services.get(p['port'])
        if operation == 'service_add':
            if current is not None:
                raise ValueError('service_already_exists')
            return {'port': p['port'], 'exists': False}
        if current is None:
            raise ValueError('service_not_found')
        return _selected(current, ('id', 'port', 'name'))
    if operation in ('group_create', 'group_update'):
        tree = _tree(_data(before, 'groups'))
        if operation == 'group_create':
            parent = p.get('parent')
            return {'organization_id': p['organization_id'],
                    'parent': _parent(tree, parent, p['organization_id']),
                    'matching_ids': sorted(key for key, node in tree.items()
                                           if node['name'] == p['name'] and node['parent'] == parent)}
        if p['id'] not in tree:
            raise ValueError('group_not_found')
        identity = _group_identity(_data(before, 'group'), p['id'])
        target = tree[p['id']]
        if target['organization_id'] != identity['organization_id']:
            raise ValueError('group_identity_mismatch')
        result = _selected(target, ('id', 'organization_id') + tuple(p['fields']))
        if 'parent' in p['fields']:
            result['target_parent'] = _parent(tree, p['fields']['parent'], target['organization_id'], p['id'])
        return result
    if operation == 'group_delete':
        group = _data(before, 'group')
        _group_identity(group, p['id'])
        # Descendants are relevant when deleting an entire group hierarchy.
        return _tree([group])
    result = {}
    organization = None
    if operation == 'group_attach':
        group = _data(before, 'group')
        organization = _group_identity(group, p['id'])['organization_id']
        result['group'] = _selected(group, ('id', 'name', 'organization'))
    for serial in p['controllers']:
        controller = _data(before, 'controller:' + serial)
        _controller_identity(controller, serial)
        if organization is not None and _organization(controller) != organization:
            raise ValueError('controller_not_in_group_organization')
        result[serial] = {'identity': _selected(controller, ('id', 'serialNumber', 'organization')),
                          'group_id': _group_id(controller)}
    return result


def _equal_field(key, expected, actual):
    if key in ('latitude', 'longitude') and expected is not None and actual is not None:
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except InvalidOperation:
            return False
    # JSON booleans and integers must not compare equal (True == 1 in Python).
    return type(expected) is type(actual) and expected == actual


def _matches(actual, expected):
    return isinstance(actual, dict) and all(key in actual and _equal_field(key, value, actual[key])
                                          for key, value in expected.items())


def verify(operation, params, before, after, response=None):
    """Evaluate fresh GET snapshots; write-response content is not evidence."""
    p = validate(operation, params)
    result = {'verified': False, 'reason': 'expected_state_not_observed'}
    try:
        if 'serial_number' in p:
            identity = _controller_identity(_data(before, 'controller'), p['serial_number'])
            if operation != 'controller_delete':
                if _controller_identity(_data(after, 'controller'), p['serial_number']) != identity:
                    return {'verified': False, 'reason': 'controller_identity_mismatch'}
        if operation in ('group_update', 'group_delete', 'group_attach'):
            identity = _group_identity(_data(before, 'group'), p['id'])
            if operation != 'group_delete' and _group_identity(_data(after, 'group'), p['id']) != identity:
                return {'verified': False, 'reason': 'group_identity_mismatch'}
        if operation in ('controller_delete', 'group_delete'):
            key = 'controller' if operation == 'controller_delete' else 'group'
            _data(before, key)
            if isinstance(after.get(key), dict) and after[key].get('http_status') == 404:
                return {'verified': True, 'reason': 'resource_no_longer_visible_to_same_account'}
            return result
        if operation == 'controller_update':
            result['verified'] = _matches(_data(after, 'controller'), p['fields'])
        elif operation == 'request_diagnostic':
            previous = _data(before, 'diagnostic')
            current = _data(after, 'diagnostic')
            if (not isinstance(current, dict) or not isinstance(current.get('status'), str)
                    or not isinstance(previous, dict)):
                raise ValueError('invalid_verification_response')
            changed = any(current.get(key) != previous.get(key) for key in ('status', 'id', 'created'))
            if current['status'] != 'not_requested' and changed:
                return {'verified': True, 'reason': 'diagnostic_request_observed', 'archive_complete': False}
            return {'verified': False, 'reason': 'diagnostic_request_not_observable_yet', 'status': 'pending'}
        elif operation.startswith('service_'):
            services = _services(_data(after, 'services'))
            if operation == 'service_delete':
                result['verified'] = p['port'] not in services
            else:
                expected = ({key: p[key] for key in ('port', 'name') if key in p} if operation == 'service_add'
                            else {'port': p['port'], **p['fields']})
                result['verified'] = _matches(services.get(p['port']), expected)
        elif operation in ('group_create', 'group_update'):
            tree = _tree(_data(after, 'groups'))
            if operation == 'group_create':
                old_tree = _tree(_data(before, 'groups'))
                candidates = [node for key, node in tree.items() if key not in old_tree
                              and node['name'] == p['name'] and node['parent'] == p.get('parent')
                              and node['organization_id'] == p['organization_id']]
                if len(candidates) == 1:
                    return {'verified': True, 'reason': 'new_group_observed', 'resource_id': candidates[0]['id']}
                result['reason'] = 'new_group_not_uniquely_observed'
                return result
            if p['id'] not in tree or tree[p['id']]['organization_id'] != identity['organization_id']:
                return {'verified': False, 'reason': 'group_identity_mismatch'}
            result['verified'] = _matches(tree.get(p['id']), p['fields'])
        elif operation in ('group_attach', 'group_detach'):
            for serial in p['controllers']:
                old_identity = _controller_identity(_data(before, 'controller:' + serial), serial)
                if _controller_identity(_data(after, 'controller:' + serial), serial) != old_identity:
                    return {'verified': False, 'reason': 'controller_identity_mismatch'}
            result['verified'] = all(_group_id(_data(after, 'controller:' + serial)) == p.get('id')
                                     for serial in p['controllers'])
    except (ValueError, TypeError, KeyError, AttributeError):
        return {'verified': False, 'reason': 'verification_read_unavailable_or_invalid'}
    if result['verified']:
        result['reason'] = 'expected_state_observed'
    return result
