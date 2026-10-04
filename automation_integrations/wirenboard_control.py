"""Confirmed controller management with exact targets and durable outcomes."""
from __future__ import annotations

import fcntl
import json
from pathlib import Path
import re
import time
import uuid

try:
    from .api_read import Failure, HTTP, Vault, sanitize
    from .api_write import digest, save
    from . import wirenboard, wirenboard_control_contract as contract
except ImportError:
    from api_read import Failure, HTTP, Vault, sanitize
    from api_write import digest, save
    import wirenboard
    import wirenboard_control_contract as contract


TERMINAL = {'verified', 'rejected'}
SHELL_OPERATION = 'controller_exec'
# These failures establish that the requested command was never sent. Transport
# loss, malformed responses after execution, and timeout outcomes stay unknown.
SHELL_PRECOMMAND_REJECTIONS = {
    'unsupported_shell_egress', 'invalid_shell_request', 'invalid_serial_number',
    'invalid_tunnel_url', 'untrusted_tunnel_origin', 'invalid_shell_command',
    'shell_command_too_large', 'invalid_shell_timeout', 'invalid_ssh_credentials',
    'tunnel_redirect_invalid', 'tunnel_unavailable', 'tunnel_redirect_limit',
    'ssh_authentication_failed', 'terminal_session_rejected', 'invalid_terminal_cookie',
    'shell_connection_timeout', 'shell_connection_failed', 'cloud_terminal_unavailable',
}
MAX_PUBLIC_RESULT = 60000
LABELS = {
    'controller_update': 'Изменить настройки контроллера в облаке',
    'request_diagnostic': 'Запустить сбор диагностики контроллера',
    'service_add': 'Добавить сервис контроллера',
    'service_update': 'Переименовать сервис контроллера',
    'service_delete': 'Удалить сервис контроллера из облака',
    'group_create': 'Создать группу', 'group_update': 'Изменить группу',
    'group_delete': 'Удалить группу', 'group_attach': 'Перенести контроллеры в группу',
    'group_detach': 'Убрать контроллеры из групп',
    'controller_delete': 'Удалить контроллер из облака',
    'controller_exec': 'Выполнить команду на контроллере',
}


def validate(operation, params):
    if operation != SHELL_OPERATION:
        try:
            return contract.validate(operation, params)
        except ValueError as exc:
            raise Failure(str(exc)) from None
    if not isinstance(params, dict) or set(params) - {'serial_number', 'command', 'timeout'}:
        raise Failure('invalid_parameters')
    if not {'serial_number', 'command'} <= set(params):
        raise Failure('missing_parameter')
    try:
        serial = wirenboard.validate('controller', {'serial_number': params['serial_number']})['serial_number']
    except ValueError as exc:
        raise Failure(str(exc)) from None
    command = params['command']
    if (not isinstance(command, list) or not 1 <= len(command) <= 64
            or any(not isinstance(arg, str) or '\0' in arg or len(arg) > 16000 for arg in command)
            or not command[0] or len(json.dumps(command)) > 20000):
        raise Failure('invalid_controller_command')
    timeout = params.get('timeout', 30)
    if type(timeout) is not int or not 1 <= timeout <= 30:
        raise Failure('invalid_command_timeout')
    return {'serial_number': serial, 'command': command, 'timeout': timeout}


def target(config):
    return digest({'origin': 'https://wirenboard.cloud/api/v1',
                   'credential_item': config.get('item_ids', {}).get('wirenboard'),
                   'transport': config.get('wirenboard_transport'),
                   'ssh_credential_item': config.get('wirenboard_ssh_item')})


def request_spec(operation, params):
    if operation == SHELL_OPERATION:
        return {'method': 'CONTROLLER_EXEC', 'serial_number': params['serial_number'],
                'command': params['command'], 'timeout': params['timeout']}
    try:
        return contract.build(operation, params)
    except ValueError as exc:
        raise Failure(str(exc)) from None


def snapshot(operation, params, call, *, before=None, response=None):
    result = {}
    # Group verification resolves its organization from the first bounded read.
    for _ in range(3):
        if operation == SHELL_OPERATION:
            plan = [{'key': 'controller', 'method': 'GET',
                     'path': '/controllers/' + params['serial_number'] + '/'}]
        else:
            try:
                plan = contract.verification_plan(operation, params, response=response,
                                                  before={**(before or {}), **result})
            except ValueError as exc:
                raise Failure(str(exc)) from None
            if 'serial_number' in params and not any(read['key'] == 'controller' for read in plan):
                plan = [{'key': 'controller', 'method': 'GET',
                         'path': '/controllers/' + params['serial_number'] + '/'}] + plan
        pending = [read for read in plan if read['key'] not in result]
        if not pending:
            break
        for read in pending:
            if read['method'] != 'GET':
                raise Failure('invalid_verification_plan')
            try:
                data = call('GET', read['path'], query=read.get('query'))
                result[read['key']] = {'http_status': 200, 'data': data}
            except Failure as exc:
                if exc.status != 404:
                    raise
                result[read['key']] = {'http_status': 404, 'data': None}
    return result


def precondition(operation, params, snapshots):
    if operation != SHELL_OPERATION:
        try:
            stable = contract.precondition(operation, params, snapshots)
        except ValueError as exc:
            raise Failure(str(exc)) from None
        if 'serial_number' in params:
            row = snapshots.get('controller', {})
            obj = row.get('data') or {}
            if row.get('http_status') != 200 or obj.get('serialNumber') != params['serial_number']:
                raise Failure('controller_identity_not_verified')
            stable = {'operation': stable, 'controller': {key: obj.get(key)
                       for key in ('id', 'serialNumber', 'organization')}}
        return stable
    row = snapshots.get('controller', {})
    obj = row.get('data') or {}
    if row.get('http_status') != 200 or obj.get('serialNumber') != params['serial_number']:
        raise Failure('controller_identity_not_verified')
    try:
        return contract._controller_identity(obj, params['serial_number'])
    except (ValueError, TypeError, KeyError, AttributeError):
        raise Failure('controller_identity_not_verified') from None


def preview(operation, params, snapshots, spec):
    targets = []
    for key, row in snapshots.items():
        obj = row.get('data')
        if (key == 'controller' or key.startswith('controller:')) and isinstance(obj, dict):
            targets.append({'kind': 'controller', **{k: obj.get(k) for k in
                            ('id', 'serialNumber', 'description', 'organization', 'group')}})
        elif key == 'group' and isinstance(obj, dict):
            targets.append({'kind': 'group', **{k: obj.get(k) for k in ('id', 'name', 'organization')}})
    result = {'service': 'wirenboard', 'operation': operation, 'action': LABELS[operation],
              'targets': targets, 'parameters': params,
              'destructive': operation in ('controller_delete', 'group_delete', 'service_delete'),
              'effect': 'Выполнение точной команды на контроллере' if operation == SHELL_OPERATION
              else 'Изменение объектов Wiren Board Cloud; результат сверяется чтением'}
    if operation == 'controller_update':
        current = snapshots['controller']['data']
        result['previous_values'] = {key: current.get(key) for key in params['fields']}
    elif operation in ('service_update', 'service_delete'):
        current = next(row for row in snapshots['services']['data'] if row['port'] == params['port'])
        result['previous_values'] = {key: current.get(key) for key in ('port', 'name')}
    elif operation == 'group_update':
        current = contract._tree(snapshots['groups']['data'])[params['id']]
        result['previous_values'] = {key: current.get(key) for key in params['fields']}
    elif operation == 'group_delete':
        result['affected_groups'] = list(contract._tree([snapshots['group']['data']]).values())
    elif operation == 'group_create':
        result['targets'] = [{'kind': 'organization', 'id': params['organization_id']}]
        if params.get('parent'):
            result['targets'].append({'kind': 'parent_group',
                                      **contract._tree(snapshots['groups']['data'])[params['parent']]})
    if operation == SHELL_OPERATION:
        result['verification'] = 'Exit code confirms command completion; equipment effects require task-specific checks.'
    return result


def _shell_credentials(vault, config):
    ident = config.get('wirenboard_ssh_item')
    if not ident:
        return None
    item = vault.item(ident)
    fields = {entry['name']: entry.get('value') for entry in item.get('fields') or []}
    mapping = {'WB_SSH_USERNAME': 'username', 'WB_SSH_PASSWORD': 'password',
               'WB_SSH_PRIVATEKEY': 'privatekey', 'WB_SSH_PASSPHRASE': 'passphrase'}
    result = {dst: fields[src] for src, dst in mapping.items() if fields.get(src)}
    if not result or any(not isinstance(value, str) for value in result.values()):
        raise Failure('ssh_credential_field_missing')
    vault.sensitive.extend(value for key, value in result.items() if key != 'username')
    return result


def process(request, context, config, *, http=None, vault=None, clock=time.time, shell=None):
    if not isinstance(request, dict) or not isinstance(context, dict):
        raise Failure('invalid_write_request')
    scope, message = context.get('scope'), context.get('message_id')
    if (not isinstance(scope, list) or len(scope) != 4 or not all(isinstance(v, str) for v in scope)
            or not scope[0] or scope[0] != scope[1] or not scope[2]
            or not isinstance(message, str) or not message):
        raise Failure('invalid_write_context')
    action = request.get('action')
    allowed = {'prepare': {'action', 'service', 'operation', 'params'},
               'confirm': {'action', 'confirmation_text'},
               'execute': {'action', 'draft_id'}, 'status': {'action', 'draft_id'}}
    if action not in allowed or set(request) - allowed[action]:
        raise Failure('invalid_write_request')
    if action == 'prepare':
        if request.get('service') != 'wirenboard':
            raise Failure('invalid_write_request')
        operation = request.get('operation')
        params = validate(operation, request.get('params', {}))
        ident = str(uuid.uuid4())
    else:
        ident = request.get('draft_id')
        if action == 'confirm':
            text = request.get('confirmation_text')
            if not isinstance(text, str) or not re.fullmatch(r'ПОДТВЕРЖДАЮ [a-f0-9-]{36}', text):
                raise Failure('exact_confirmation_required')
            ident = text.split(' ')[1]
        try:
            if str(uuid.UUID(ident)) != ident:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise Failure('invalid_draft_id') from None
    root = Path(config['state_dir']) / 'wirenboard-writes'
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / (ident + '.json')
    vault = vault or Vault(config)
    http = http or HTTP('wirenboard', config)

    def view(row):
        out = {key: row.get(key) for key in ('draft_id', 'service', 'operation', 'status',
                'expires_at', 'preview', 'last_error', 'http_status', 'verification', 'result')}
        out.update(ok=True, mutation_verified=row['status'] == 'verified')
        if row['status'] == 'prepared':
            out.update(confirmation_command='ПОДТВЕРЖДАЮ ' + ident,
                instruction='Show the exact targets and complete parameters. Only a new authenticated owner message confirms this draft.')
        if row['status'] == 'outcome_unknown':
            out['instruction'] = 'Inspect status/readback. Never repeat the mutation or create a replacement draft automatically.'
        if row['operation'] == SHELL_OPERATION and isinstance(out.get('result'), dict):
            result = dict(out['result'])
            out['result'] = result
            stdout = result.get('stdout')
            if isinstance(stdout, str):
                result['stdout_truncated'] = False
                if len(json.dumps(out, ensure_ascii=False)) > MAX_PUBLIC_RESULT:
                    result['stdout_truncated'] = True
                    low, high = 0, len(stdout)
                    # Bound the serialized envelope, including escaped control
                    # characters and the preview. Keep full sanitized output in
                    # the private durable receipt and retain exit metadata here.
                    while low < high:
                        middle = (low + high + 1) // 2
                        result['stdout'] = stdout[:middle]
                        if len(json.dumps(out, ensure_ascii=False)) <= MAX_PUBLIC_RESULT:
                            low = middle
                        else:
                            high = middle - 1
                    result['stdout'] = stdout[:low]
        return out

    with (root / ('prepare.lock' if action == 'prepare' else ident + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action == 'prepare':
            intent = digest({'operation': operation, 'params': params, 'target': target(config)})
            for candidate in root.glob('*.json'):
                with (root / (candidate.stem + '.lock')).open('a') as other:
                    fcntl.flock(other, fcntl.LOCK_EX)
                    old = json.loads(candidate.read_text())
                    if old.get('scope') != scope or old.get('intent_hash') != intent or old.get('status') in TERMINAL:
                        continue
                    if old.get('expires_at', 0) < clock() and 'submitted_at' not in old:
                        continue
                    return {'ok': False, 'error': 'existing_unresolved_draft', 'draft_id': old['draft_id'], 'status': old['status']}
            spec = request_spec(operation, params)
            with wirenboard.authorized_session(config, vault, http) as call:
                before = snapshot(operation, params, call)
                account_id = call.user_id
            stable = precondition(operation, params, before)
            summary = preview(operation, params, before, spec)
            if len(json.dumps(summary, ensure_ascii=False)) > 22000:
                raise Failure('write_preview_too_large')
            row = {'draft_id': ident, 'service': 'wirenboard', 'operation': operation, 'params': params,
                   'payload_hash': digest(params), 'request_hash': digest(spec), 'intent_hash': intent,
                   'target_hash': target(config), 'scope': scope, 'created_message': message,
                   'account_id': account_id,
                   'created_at': clock(), 'expires_at': clock() + 600, 'status': 'prepared',
                   'preview': sanitize(summary, vault.sensitive), 'before': before,
                   'before_hash': digest(before), 'precondition_hash': digest(stable)}
            save(path, row)
            return view(row)
        if not path.exists():
            raise Failure('draft_not_found')
        row = json.loads(path.read_text())
        if row['scope'] != scope:
            raise Failure('draft_scope_mismatch')
        if row['payload_hash'] != digest(row['params']) or row['before_hash'] != digest(row['before']):
            raise Failure('draft_integrity_failed')
        if row['status'] == 'submitting':
            row.update(status='outcome_unknown', last_error='interrupted_submission')
            save(path, row)
        if action == 'confirm':
            if row['status'] != 'prepared':
                raise Failure('draft_not_confirmable')
            if message == row['created_message']:
                raise Failure('new_owner_message_required')
            if row['expires_at'] < clock():
                raise Failure('draft_expired_prepare_again')
            row.update(status='confirmed', approved_hash=row['payload_hash'], confirmed_message=message)
            save(path, row)
            return view(row)
        operation, params = row['operation'], row['params']
        if row['target_hash'] != target(config) or row['request_hash'] != digest(request_spec(operation, validate(operation, params))):
            raise Failure('draft_contract_or_target_changed')
        if action == 'status':
            if row['status'] in ('outcome_unknown', 'accepted_unverified') and operation != SHELL_OPERATION:
                try:
                    with wirenboard.authorized_session(config, vault, http) as call:
                        if call.user_id != row['account_id']:
                            raise Failure('cloud_account_changed')
                        after = snapshot(operation, params, call, before=row['before'], response=row.get('response'))
                    check = contract.verify(operation, params, row['before'], after, response=row.get('response'))
                    row['verification'] = check
                    if check['verified']:
                        row.update(status='verified', last_error=None)
                except Failure as exc:
                    row.update(last_error=exc.code, http_status=exc.status)
                save(path, row)
            return view(row)
        if row['status'] in TERMINAL or row['status'] in ('outcome_unknown', 'accepted_unverified'):
            return view(row)
        if row['status'] != 'confirmed' or row.get('approved_hash') != row['payload_hash']:
            raise Failure('owner_confirmation_required')
        if row['expires_at'] < clock():
            raise Failure('confirmation_expired')
        with wirenboard.authorized_session(config, vault, http) as call:
            if call.user_id != row['account_id']:
                raise Failure('cloud_account_changed')
            current = snapshot(operation, params, call, before=row['before'])
            if digest(precondition(operation, params, current)) != row['precondition_hash']:
                row.update(status='rejected', last_error='target_changed_prepare_again')
                save(path, row)
                raise Failure('target_changed_prepare_again')
            credentials = _shell_credentials(vault, config) if operation == SHELL_OPERATION else None
            row.update(status='submitting', submitted_at=clock())
            save(path, row)
            try:
                if operation == SHELL_OPERATION:
                    tunnel = call('POST', '/controllers/' + params['serial_number'] + '/tcp-tunnels/ssh/')
                    url = tunnel.get('tunnelRedirectUrl') if isinstance(tunnel, dict) else None
                    if not isinstance(url, str) or not url:
                        raise Failure('cloud_terminal_unavailable')
                    vault.sensitive.extend([url] + [v for k, v in tunnel.items() if k == 'tunnelKey' and isinstance(v, str)])
                    if shell is None:
                        try:
                            from .wirenboard_shell import ShellTransport
                        except ImportError:
                            from wirenboard_shell import ShellTransport
                        shell = ShellTransport()
                    result = shell.call(params['serial_number'], url, params['command'],
                                        credentials=credentials, timeout=params['timeout'])
                    row['result'] = sanitize(result, vault.sensitive)
                    row['verification'] = {'kind': 'command_exit', 'exit_code': result.get('exit_code'),
                                           'equipment_effects': 'Inspect command output and task-specific readback.'}
                    row.update(status='verified' if result.get('exit_code') == 0 else 'accepted_unverified', last_error=None)
                else:
                    spec = request_spec(operation, params)
                    result = call(spec['method'], spec['path'], query=spec.get('query'), body=spec.get('body'))
                    row.update(status='accepted_unverified', response=sanitize(result, vault.sensitive), last_error=None)
                    save(path, row)
                    after = snapshot(operation, params, call, before=row['before'], response=result)
                    check = contract.verify(operation, params, row['before'], after, response=result)
                    row['verification'] = check
                    if check['verified']:
                        row['status'] = 'verified'
            except Failure as exc:
                if row['status'] == 'submitting':
                    before_command = operation == SHELL_OPERATION and exc.code in SHELL_PRECOMMAND_REJECTIONS
                    row['status'] = 'rejected' if before_command or exc.status in (400, 401, 403, 404, 405, 422, 429) else 'outcome_unknown'
                row.update(last_error=exc.code, http_status=exc.status)
            except Exception as exc:
                code = getattr(exc, 'code', '')
                safe = code if isinstance(code, str) and re.fullmatch(r'[a-z][a-z0-9_]{1,100}', code) else 'controller_execution_failed'
                row.update(last_error=safe)
                if row['status'] == 'submitting':
                    row['status'] = ('rejected' if operation == SHELL_OPERATION and safe in SHELL_PRECOMMAND_REJECTIONS
                                     else 'outcome_unknown')
            save(path, row)
        return view(row)
