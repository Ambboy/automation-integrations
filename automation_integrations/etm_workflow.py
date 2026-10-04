"""Durable owner-authorized ETM checkout; an uncertain POST is never replayed."""
import fcntl
import json
from pathlib import Path
import re
import time
import uuid

try:
    from .api_read import Failure, sanitize
    from .api_write import digest, save
    from .etm_authorization import account_hash, owner_command, procurement_lock, unresolved_procurement
    from . import etm_order
except ImportError:
    from api_read import Failure, sanitize
    from api_write import digest, save
    from etm_authorization import account_hash, owner_command, procurement_lock, unresolved_procurement
    import etm_order


VERSION = 1


def checkout_started(row):
    """Older durable records used only stage names; never downgrade their POST."""
    return bool(row.get('checkout_started') or row.get('receipt') or
                str(row.get('stage', '')).startswith(('checkout_', 'document_note_')))


def record_failure(row, reason):
    """Basket acceptance cannot imply an attempted final order submission."""
    if row.get('receipt'):
        row['status'] = 'accepted_unverified'
    elif not checkout_started(row) and row.get('stage') in ('basket_add_accepted', 'basket_select_accepted'):
        row.update(status='blocked', result={
            'order_submitted': False, 'basket_changed': True, 'reason': reason,
            'instruction': 'The basket change was accepted, but order checkout was not submitted. '
                           'Prepare a new preview from the current basket; do not repeat the old execute.'})
    else:
        row['status'] = 'outcome_unknown' if 'submitted_at' in row else 'rejected'
    row['last_error'] = reason


def process(request, context, config, *, checkout=None, clock=time.time):
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
    target = digest({'item': config.get('item_ids', {}).get('etm'),
                     'proxy': config.get('etm_proxy'), 'version': VERSION})
    account = account_hash(config)
    if action == 'prepare':
        if request.get('service') != 'etm' or request.get('operation') != 'order_checkout':
            raise Failure('unsupported_write_operation')
        params = etm_order.validate_params(request.get('params', {}))
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
    root = Path(config['state_dir']) / 'etm-writes'
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / (ident + '.json')

    def client():
        nonlocal checkout
        if checkout is None:
            checkout = etm_order.Checkout(etm_order.WebsiteClient(config))
        return checkout

    def view(row):
        out = {k: row.get(k) for k in ('draft_id', 'status', 'expires_at', 'preview',
                                      'stage', 'checkout_started', 'last_error', 'http_status', 'provider_code', 'result')}
        out.update(ok=True, service='etm', operation='order_checkout',
                   mutation_verified=row['status'] == 'verified',
                   verification='Final document checks establish placement only. '
                                'Payment and pickup readiness require their own provider status.')
        if row['status'] == 'prepared':
            direct = owner_command(context, config, 'etm', 'order_checkout', row['prepared']['params'])
            out['confirmation_required'] = direct is None
            if direct:
                out.update(authorization_policy='owner_command',
                           instruction='For the owner request to place this order, check the exact items, '
                                       'quantity, price ceiling, pickup and payment against the request, then '
                                       'call execute immediately. No extra user message or UUID confirmation is needed. '
                                       'For a quote/status-only request, stop after this read-only preview.')
            else:
                out.update(confirmation_command='ПОДТВЕРЖДАЮ ' + row['draft_id'],
                           instruction='Show the exact items, quantity, total ceiling, pickup office, '
                                       'payment method and agreement. This draft requires a new owner message.')
        return out

    def unresolved_checkout(exclude=None):
        return unresolved_procurement(config, scope,
            exclude=('etm-writes', exclude) if exclude else None)

    # One account checkout at a time, including reads that establish its basket
    # preconditions. Generic reads cannot mutate this basket.
    with procurement_lock(config), (root / 'checkout.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action == 'prepare':
            blocker = unresolved_checkout()
            if blocker:
                return blocker
            intent = digest({'params': params, 'target': target})
            for old_path in root.glob('*.json'):
                old = json.loads(old_path.read_text())
                if old.get('scope') != scope or old.get('intent_hash') != intent:
                    continue
                if old['status'] in ('rejected', 'blocked'):
                    continue
                if old['status'] == 'verified' and old['created_message'] != message:
                    continue
                if old['expires_at'] < clock() and 'submitted_at' not in old:
                    continue
                return {'ok': False, 'error': 'existing_unresolved_draft',
                        'draft_id': old['draft_id'], 'status': old['status'],
                        'instruction': 'Inspect this exact draft; never replace an uncertain checkout.'}
            prepared = client().prepare(params)
            preview = json.loads(json.dumps(prepared['preview'], ensure_ascii=False, allow_nan=False))
            if len(json.dumps(preview, ensure_ascii=False)) > 18000:
                raise Failure('write_preview_too_large')
            row = {'draft_id': ident, 'scope': scope, 'created_message': message,
                   'created_at': clock(), 'expires_at': clock() + 600,
                   'status': 'blocked' if preview.get('can_submit') is False else 'prepared',
                   'checkout_started': False,
                   'prepared': prepared, 'preview': preview,
                   'prepared_hash': digest(prepared), 'intent_hash': intent, 'target_hash': target,
                   'account_hash': account}
            save(path, row)
            return view(row)
        if not path.exists():
            raise Failure('draft_not_found')
        row = json.loads(path.read_text())
        if row['scope'] != scope:
            raise Failure('draft_scope_mismatch')
        if row['prepared_hash'] != digest(row['prepared']):
            raise Failure('draft_integrity_failed')
        if row['status'] == 'submitting':
            record_failure(row, 'interrupted_submission')
            save(path, row)
        elif (row['status'] == 'outcome_unknown' and not checkout_started(row)
                  and row.get('stage') in ('basket_add_accepted', 'basket_select_accepted')):
            # Recover basket-only records left unknown by the earlier wrapper.
            record_failure(row, row.get('last_error') or 'interrupted_submission')
            save(path, row)
        if action == 'confirm':
            if row['status'] != 'prepared':
                raise Failure('draft_not_confirmable')
            if message == row['created_message']:
                raise Failure('new_owner_message_required')
            if row['expires_at'] < clock():
                raise Failure('draft_expired_prepare_again')
            row.update(status='confirmed', confirmed_message=message, approved_hash=row['prepared_hash'])
            save(path, row)
            return view(row)
        if action == 'status':
            if row['status'] in ('accepted_unverified', 'outcome_unknown') and row.get('receipt'):
                if row['target_hash'] != target:
                    raise Failure('draft_contract_or_target_changed')
                try:
                    result = client().reconcile(row['prepared'], row['receipt'])
                    if result.get('status') not in ('verified', 'accepted_unverified'):
                        raise Failure('invalid_checkout_result')
                    row.update(result=result, status=result['status'], last_error=None)
                except Failure as exc:
                    row.update(last_error=exc.code, http_status=exc.status, provider_code=exc.provider_code)
                save(path, row)
            elif (row['status'] == 'outcome_unknown' and not checkout_started(row)
                  and row.get('stage') in ('basket_add_submitting', 'basket_select_submitting')):
                if row['target_hash'] != target:
                    raise Failure('draft_contract_or_target_changed')
                try:
                    result = client().reconcile_basket(row['prepared'])
                    if (not isinstance(result, dict) or result.get('order_submitted') is not False
                            or not isinstance(result.get('items'), list)
                            or type(result.get('matches_expected')) is not bool
                            or result.get('status') != ('blocked' if result['matches_expected'] else 'outcome_unknown')):
                        raise Failure('invalid_basket_reconciliation_result')
                    row.update(result=result, status=result['status'], last_error=None)
                except Failure as exc:
                    row.update(last_error=exc.code, http_status=exc.status, provider_code=exc.provider_code)
                save(path, row)
            return view(row)
        if row['status'] in ('verified', 'accepted_unverified', 'outcome_unknown', 'rejected', 'blocked'):
            return view(row)
        direct = owner_command(context, config, 'etm', 'order_checkout', row['prepared']['params'])
        if row['status'] == 'prepared' and direct:
            row.update(status='confirmed', approved_hash=row['prepared_hash'],
                       confirmed_message=message, authorization=direct)
        if row['status'] != 'confirmed' or row.get('approved_hash') != row['prepared_hash']:
            raise Failure('owner_confirmation_required')
        if row['expires_at'] < clock():
            raise Failure('confirmation_expired')
        if row['target_hash'] != target:
            raise Failure('draft_contract_or_target_changed')
        blocker = unresolved_checkout(exclude=ident)
        if blocker:
            return blocker

        def stage(name, details=None):
            row.update(status='submitting', stage=name, submitted_at=row.get('submitted_at', clock()))
            if name == 'checkout_submitting':
                row['checkout_started'] = True
            if name == 'checkout_accepted':
                row.update(status='accepted_unverified', receipt=details)
            save(path, row)  # durable state BEFORE each possible provider mutation

        try:
            result = client().execute(row['prepared'], on_stage=stage)
            if result.get('status') not in ('verified', 'accepted_unverified'):
                raise Failure('invalid_checkout_result')
            row.update(status=result['status'], result=result, last_error=None)
        except Failure as exc:
            record_failure(row, exc.code)
            row.update(http_status=exc.status, provider_code=exc.provider_code)
        except Exception:
            record_failure(row, 'unexpected_checkout_error')
        save(path, row)
        return view(row)
