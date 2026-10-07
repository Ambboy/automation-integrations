"""Durable native-owner confirmation for compiled, documented business operations.

There are no automatic mutation retries. A successful HTTP/RPC result records
provider acceptance, never pretends to establish settlement/signature/delivery.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

try:
    from .api_read import Failure, provider_environment
    from .api_write import digest, save
    from .etm_authorization import (account_hash, is_procurement, owner_command,
                                    procurement_lock, unresolved_procurement)
    from . import extended_api
except ImportError:
    from api_read import Failure, provider_environment
    from api_write import digest, save
    from etm_authorization import (account_hash, is_procurement, owner_command,
                                   procurement_lock, unresolved_procurement)
    import extended_api


def target(config, service):
    return digest({'service': service, 'environment': provider_environment(service, config),
                   'client_id': config.get('yandex_client_id') if service == 'yandex_go' else None,
                   'credential_item': config.get('item_ids', {}).get(service)})


def process(request, context, config, *, http=None, vault=None, clock=time.time):
    if not isinstance(request, dict) or not isinstance(context, dict):
        raise Failure('invalid_write_request')
    scope, message = context.get('scope'), context.get('message_id')
    if (not isinstance(scope, list) or len(scope) != 4 or not all(isinstance(x, str) for x in scope)
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
        service, operation = request.get('service'), request.get('operation')
        if not isinstance(service, str) or not isinstance(operation, str):
            raise Failure('invalid_write_request')
        params = extended_api.validate(service, operation, request.get('params', {}), write=True)
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
    root = Path(config['state_dir']) / 'contract-writes'
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / (ident + '.json')
    if action == 'prepare':
        procurement = is_procurement(service, operation)
    else:
        # Service/operation are immutable draft metadata. Read them only to
        # choose the outer lock; reread the complete record under both locks.
        metadata = json.loads(path.read_text()) if path.exists() else {}
        procurement = is_procurement(metadata.get('service'), metadata.get('operation'))

    def lifecycle_module():
        try:
            from . import etm_lifecycle
        except ImportError:
            import etm_lifecycle
        return etm_lifecycle

    def reconcile(row):
        if row.get('service') != 'etm' or row['status'] not in ('accepted_unverified', 'outcome_unknown', 'specification'):
            return
        if row.get('target_hash') != target(config, row['service']):
            raise Failure('draft_contract_or_target_changed')
        try:
            updates = lifecycle_module().reconcile(row, config, http=http, vault=vault)
            if updates:
                row.update(updates)
        except Failure as exc:
            row.update(last_error=exc.code, http_status=exc.status, provider_code=exc.provider_code)
        save(path, row)

    def view(row):
        out = {k: row.get(k) for k in ('draft_id', 'service', 'operation', 'status', 'expires_at',
                                      'preview', 'source', 'last_error', 'http_status', 'provider_code', 'lifecycle', 'result')}
        out.update(ok=True, provider_accepted=row['status'] in ('accepted_unverified', 'verified', 'canceled', 'replaced'),
                   mutation_verified=row['status'] in ('verified', 'canceled', 'replaced'),
                   verification='Inspect the provider result and use the documented read/status operation for the returned ID. '
                                'HTTP/RPC acceptance does not prove business completion. No automatic retry.')
        if row['status'] == 'prepared':
            direct = owner_command(context, config, row['service'], row['operation'], row['params'])
            out['confirmation_required'] = direct is None
            if direct:
                out.update(authorization_policy='owner_command', instruction=
                    'For the owner request to perform this ETM procurement operation, check these exact '
                    'parameters against the request and call execute immediately. No extra user message '
                    'or UUID confirmation is needed. A quote/status-only request does not authorize execution.')
            else:
                out['confirmation_command'] = 'ПОДТВЕРЖДАЮ ' + ident
                out['instruction'] = 'Show the complete service, operation, environment and parameters below. '
                out['instruction'] += 'Only that exact command in a new authenticated owner message confirms this draft.'
        return out

    with procurement_lock(config, enabled=procurement), (root / (
            'prepare.lock' if action == 'prepare' else ident + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action == 'prepare':
            built = extended_api.contract(service).build(service, operation, params)
            intent = digest({'service': service, 'operation': operation, 'params': params, 'target': target(config, service)})
            for candidate in root.glob('*.json'):
                # Serialize expiry replacement with the exact draft's execute
                # transition: it may have checked expiry just before this scan.
                with (root / (candidate.stem + '.lock')).open('a') as candidate_lock:
                    fcntl.flock(candidate_lock, fcntl.LOCK_EX)
                    old = json.loads(candidate.read_text())
                    if old.get('scope') != scope or old.get('intent_hash') != intent or old.get('status') in ('rejected', 'canceled'):
                        continue
                    if old.get('expires_at', 0) < clock() and 'submitted_at' not in old:
                        continue
                    return {'ok': False, 'error': 'existing_unresolved_draft', 'draft_id': old['draft_id'],
                            'status': old['status'], 'instruction': 'Inspect the exact existing draft and provider object; do not replace it.'}
            lifecycle = None
            if (service == 'etm' and operation == 'invoice_create'
                    and params.get('body', {}).get('DocumentFunctionCode') in ('A', 'C', 'D')):
                lifecycle = lifecycle_module().preflight(operation, params, config, http=http, vault=vault)
            metadata = extended_api.operations(service)[operation]
            preview = {'service': service, 'operation': operation,
                       'environment': provider_environment(service, config),
                       'effect': metadata['effect'], 'method': built['method'], 'path': built['path'],
                       'parameters': json.loads(json.dumps(params, ensure_ascii=False, allow_nan=False)),
                       'completion': 'One provider request. Its business completion requires subsequent verification.'}
            if service == 'etm' and operation == 'invoice_create':
                try:
                    from .etm_document import preview_details
                except ImportError:
                    from etm_document import preview_details
                preview.update(preview_details(params['body']))
            if lifecycle:
                preview['lifecycle'] = lifecycle
            # A native hook/tool must be able to show the entire preview. Never
            # persist a draft whose approval details would be silently truncated.
            if len(json.dumps(preview, ensure_ascii=False)) > 18000:
                raise Failure('write_preview_too_large')
            row = {'draft_id': ident, 'service': service, 'operation': operation, 'params': params,
                   'intent_hash': intent, 'payload_hash': digest(params), 'request_hash': digest(built),
                   'target_hash': target(config, service), 'scope': scope,
                   'created_message': message, 'created_at': clock(), 'expires_at': clock() + 600,
                   'status': 'prepared', 'preview': preview, 'source': metadata.get('source')}
            if procurement:
                row['account_hash'] = account_hash(config)
            if lifecycle:
                row['lifecycle'] = lifecycle
            save(path, row)
            return view(row)
        if not path.exists():
            raise Failure('draft_not_found')
        row = json.loads(path.read_text())
        if row['scope'] != scope:
            raise Failure('draft_scope_mismatch')
        if row['payload_hash'] != digest(row['params']):
            raise Failure('draft_integrity_failed')
        if row['status'] == 'submitting':
            row.update(status='outcome_unknown', last_error='interrupted_submission')
            save(path, row)
        if action == 'status':
            reconcile(row)
            return view(row)
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
        if row['status'] in ('accepted_unverified', 'outcome_unknown', 'rejected', 'verified', 'canceled', 'replaced', 'specification'):
            return view(row)
        direct = owner_command(context, config, row['service'], row['operation'], row['params'])
        if row['status'] == 'prepared' and direct:
            row.update(status='confirmed', approved_hash=row['payload_hash'],
                       confirmed_message=message, authorization=direct)
        if row['status'] != 'confirmed' or row.get('approved_hash') != row['payload_hash']:
            raise Failure('owner_confirmation_required')
        if row['expires_at'] < clock():
            raise Failure('confirmation_expired')
        service, operation, params = row['service'], row['operation'], row['params']
        normalized = extended_api.validate(service, operation, params, write=True)
        built = extended_api.contract(service).build(service, operation, normalized)
        if row['request_hash'] != digest(built) or row['target_hash'] != target(config, service):
            raise Failure('draft_contract_or_target_changed')
        if procurement:
            blocker = unresolved_procurement(config, scope, exclude=('contract-writes', ident),
                operation=operation, params=params, row=row)
            if blocker:
                return blocker
        if (service == 'etm' and operation == 'invoice_create'
                and params.get('body', {}).get('DocumentFunctionCode') in ('A', 'C', 'D')):
            fresh = lifecycle_module().preflight(operation, params, config, http=http, vault=vault)
            lifecycle_module().assert_same_target(row.get('lifecycle'), fresh)
            row['lifecycle'] = fresh
            if fresh and fresh.get('already_complete'):
                updates = lifecycle_module().reconcile(row, config, http=http, vault=vault)
                if not updates or updates.get('status') not in ('verified', 'canceled', 'replaced'):
                    raise Failure('etm_lifecycle_completion_unverified')
                row.update(updates)
                save(path, row)
                return view(row)
        row.update(status='submitting', submitted_at=clock())
        save(path, row)  # fsync file AND directory before any possible business effect
        try:
            result, secrets = extended_api.call(service, operation, params, config, write=True, vault=vault, http=http)
            row.update(status='accepted_unverified', last_error=None)
            save(path, row)  # preserve acceptance even if output conversion fails
            row['result'] = extended_api.output(result, secrets, config)
        except Failure as exc:
            if row['status'] == 'submitting':
                row['status'] = 'rejected' if exc.status in (400, 401, 403, 404, 405, 406, 422, 429) else 'outcome_unknown'
            row.update(last_error=exc.code, http_status=exc.status, provider_code=exc.provider_code)
        except Exception:
            if row['status'] == 'submitting':
                row['status'] = 'outcome_unknown'
            row['last_error'] = 'unexpected_execution_error'
        save(path, row)
        reconcile(row)
        return view(row)
