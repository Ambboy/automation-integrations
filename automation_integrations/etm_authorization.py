"""Apply the owner's configured ETM purchasing policy to a native message.

The Hermes bridge creates ``owner_message`` from the authenticated inbound
message, outside model tool arguments. Its digest is audit provenance, not a
signature or a replacement for the bridge's owner/private-chat checks.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import re


OWNER_COMMAND_OPERATIONS = frozenset({
    'order_checkout', 'invoice_order', 'invoice_delivery',
    'delivery_point_create', 'invoice_print', 'catalog_job_create',
    'invoice_approval_update',
})
_MESSAGE_FIELDS = {'source', 'message_id', 'scope', 'text_sha256'}
_EMPTY_TEXT_HASH = hashlib.sha256(b'').hexdigest()
PROCUREMENT_OPERATIONS = frozenset({
    'order_checkout', 'invoice_create', 'invoice_order', 'invoice_delivery',
    'delivery_point_create', 'invoice_approval_update',
})


def is_procurement(service, operation):
    return service == 'etm' and isinstance(operation, str) and operation in PROCUREMENT_OPERATIONS


def account_hash(config):
    """Use the same identity for website and public-API durable records."""
    value = {'item': config.get('item_ids', {}).get('etm')}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode()).hexdigest()


@contextmanager
def procurement_lock(config, *, enabled=True):
    """Acquire before either workflow's existing locks, including state reads."""
    if not enabled:
        yield
        return
    root = Path(config['state_dir'])
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (root / 'etm-procurement.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def procurement_effect(operation, params, *, row=None):
    """Describe business resources without trusting a model-supplied bypass flag.

    Item codes deliberately ignore quantity, region and notes: changing those
    cannot disguise a replacement for an uncertain creation. Known document
    IDs distinguish independent existing documents even when products overlap.
    """
    params = params if isinstance(params, dict) else {}
    body = params.get('body') or {}
    effect = {'order_checkout': 'create', 'invoice_order': 'reserve',
              'invoice_delivery': 'delivery', 'invoice_approval_update': 'approval',
              'delivery_point_create': 'delivery_point'}.get(operation, 'unknown')
    if operation == 'invoice_create':
        effect = {'P': 'create', 'A': 'confirm', 'C': 'replace', 'D': 'cancel'}.get(
            body.get('DocumentFunctionCode'), 'unknown')
    query = params.get('query') or {}
    if (operation == 'invoice_approval_update' and isinstance(query.get('text'), str)
            and not any(key in query for key in ('sg', 'docStatus'))):
        effect = 'comment'
    documents, references, items = set(), set(), set()
    if effect == 'delivery_point':
        references.add(hashlib.sha256(json.dumps(params, sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode()).hexdigest())
    path = params.get('path') or {}
    if isinstance(path.get('id'), str) and path['id']:
        documents.add(path['id'])
    reference = body.get('OrderNumber') or params.get('customer_order_number')
    if isinstance(reference, str) and reference:
        references.add(reference)
    for item in params.get('items', []) + body.get('Order-Lines', []):
        if isinstance(item, dict):
            code = item.get('code') or item.get('SupplierItemCode')
            if code is not None:
                items.add(str(code))
    if isinstance(row, dict):
        receipt = row.get('receipt') or {}
        lifecycle = row.get('lifecycle') or {}
        for name in ('document_ids', 'created_document_ids', 'ordered_document_ids',
                     'order_attempted_ids', 'ids'):
            values = receipt.get(name, [])
            if isinstance(values, list):
                documents.update(value for value in values if isinstance(value, str) and value)
        values = lifecycle.get('target_ids', [])
        if isinstance(values, list):
            documents.update(value for value in values if isinstance(value, str) and value)
        result = row.get('result') or {}
        if isinstance(result, dict):
            data = result.get('data') or {}
            if isinstance(data, dict):
                if isinstance(data.get('id'), str) and data['id']:
                    documents.add(data['id'])
                for key, field in (('ids', 'docid'), ('createdDoc', 'invnum')):
                    values = data.get(key, [])
                    if isinstance(values, list):
                        documents.update(value[field] for value in values if isinstance(value, dict)
                            and isinstance(value.get(field), str) and value[field])
            values = result.get('documents', [])
            if isinstance(values, list):
                for value in values:
                    if not isinstance(value, dict):
                        continue
                    if isinstance(value.get('id'), str) and value['id']:
                        documents.add(value['id'])
                    reference = value.get('customer_order_number')
                    if isinstance(reference, str) and reference:
                        references.add(reference)
                    content = value.get('items', [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                code = item.get('gdscode') or item.get('code')
                                if code is not None:
                                    items.add(str(code))
            evidence = result.get('reconciliation') or {}
            if isinstance(evidence, dict) and isinstance(evidence.get('document_ids'), list):
                documents.update(value for value in evidence['document_ids']
                    if isinstance(value, str) and value)
        for value in (receipt.get('customer_order_number'), lifecycle.get('order_number')):
            if isinstance(value, str) and value:
                references.add(value)
    return {'kind': effect, 'documents': documents, 'references': references, 'items': items,
            'comment_text': query.get('text') if effect == 'comment' else None,
            'known_specification': bool(isinstance(row, dict) and row.get('status') == 'specification'
                and not (row.get('receipt') or {}).get('order_attempted_ids')),
            'preflight_specification': bool(isinstance(row, dict)
                and (row.get('lifecycle') or {}).get('all_targets_specifications') is True)}


def effects_conflict(current, previous):
    """Block overlapping uncertain effects, while keeping recovery possible."""
    # Cancellation is an independent compensating operation. Its live preflight
    # verifies the target; it must remain available after failed creation/order.
    # A second uncertain cancellation must never be sent for the same target.
    if current['kind'] == 'cancel' and previous['kind'] != 'cancel':
        return False
    # Comments are individually authorized messages, not another purchasing
    # attempt. Preserve no-replay only for the same uncertain message/target.
    if current['kind'] == 'comment' or previous['kind'] == 'comment':
        return (current['kind'] == previous['kind']
                and current.get('comment_text') == previous.get('comment_text')
                and bool(current['documents'] & previous['documents']))
    if (previous['kind'] in ('create', 'confirm')
            and current['kind'] in ('reserve', 'confirm', 'replace', 'approval')
            and current['kind'] != previous['kind']
            and (previous.get('known_specification') or current.get('preflight_specification'))):
        return False
    if current['kind'] == 'delivery_point' or previous['kind'] == 'delivery_point':
        return (current['kind'] == previous['kind']
                and bool(current['references'] & previous['references']))
    if current['documents'] and previous['documents']:
        return bool(current['documents'] & previous['documents'])
    if current['references'] & previous['references']:
        return True
    if (current['kind'] != 'create' and current['references'] and previous['references']):
        # A/C/D act on a preflight-verified existing customer reference. The
        # same product in another reference does not make that action a replay.
        return False
    if current['items'] and previous['items']:
        return bool(current['items'] & previous['items'])
    # Known, distinct customer references are sufficient for unrelated recovery
    # or document actions. For new purchases product identity takes precedence.
    if current['references'] and previous['references']:
        return False
    # An old interrupted mutation with no target evidence cannot be assumed
    # unrelated to another creation or document action.
    return True


def unresolved_procurement(config, scope, *, exclude=None, operation=None, params=None, row=None):
    """Return only an overlapping unresolved effect; callers hold the account lock.

    Preparation is read-only and never calls this guard. Execution retains
    durable same-effect deduplication while permitting independent documents and
    exact-target recovery. Legacy rows lacking enough evidence remain guarded.
    """
    account = account_hash(config)
    root = Path(config['state_dir'])
    current = procurement_effect(operation, params, row=row) if operation else None
    for store in ('etm-writes', 'contract-writes'):
        for path in sorted((root / store).glob('*.json')):
            old = json.loads(path.read_text())
            if exclude == (store, old.get('draft_id')):
                continue
            if old.get('account_hash', account) != account:
                continue
            if store == 'contract-writes':
                if not is_procurement(old.get('service'), old.get('operation')):
                    continue
                old_operation, old_params = old.get('operation'), old.get('params')
                function = (old_params or {}).get('body', {}).get('DocumentFunctionCode')
                unresolved = (old.get('status') in ('submitting', 'outcome_unknown')
                    or (old_operation == 'invoice_create' and function in ('P', 'A', 'C', 'D')
                        and old.get('status') in ('accepted_unverified', 'specification'))
                    or (old.get('status') == 'accepted_unverified'
                        and old_operation in ('invoice_order', 'invoice_delivery', 'invoice_approval_update')))
            else:
                unresolved = old.get('status') in ('submitting', 'outcome_unknown',
                                                   'accepted_unverified', 'specification')
                old_operation, old_params = 'order_checkout', old.get('prepared', {}).get('params')
            if not unresolved:
                continue
            previous = procurement_effect(old_operation, old_params, row=old)
            if current is not None and not effects_conflict(current, previous):
                continue
            if old.get('scope') != scope:
                return {'ok': False, 'error': 'other_unresolved_checkout',
                        'instruction': 'An earlier ETM operation affecting this target is unresolved. '
                                       'Read its provider state; unrelated documents and cancellation recovery remain available.'}
            return {'ok': False, 'error': 'existing_unresolved_draft',
                    'draft_id': old['draft_id'], 'status': old['status'],
                    'instruction': 'Reconcile this exact ETM effect before repeating or replacing it. '
                                   'Cancellation recovery and independent documents remain available.'}
    return None


def owner_command(context, config, service, operation, params):
    """Return current native-message evidence for documented ETM write actions.

    Configuration records standing permission; message provenance binds its
    use to the current owner turn. No wording heuristic or model-supplied
    confirmation boolean can grant this permission. Cancellation and replacement
    follow the same explicit owner command; other providers retain their policy.
    """
    if (not isinstance(context, dict) or not isinstance(config, dict)
            or config.get('etm_order_authorization') != 'owner_command'
            or service != 'etm' or not isinstance(operation, str)
            or not isinstance(params, dict)):
        return None
    if operation == 'invoice_create':
        body = params.get('body')
        if not isinstance(body, dict) or body.get('DocumentFunctionCode') not in ('P', 'A', 'C', 'D'):
            return None
    elif operation not in OWNER_COMMAND_OPERATIONS:
        return None

    scope, message = context.get('scope'), context.get('message_id')
    if (not isinstance(scope, list) or len(scope) != 4
            or not all(isinstance(value, str) for value in scope)
            or not scope[0] or scope[0] != scope[1] or not scope[2]
            or not isinstance(message, str) or not message.strip()):
        return None
    native = context.get('owner_message')
    if (not isinstance(native, dict) or set(native) != _MESSAGE_FIELDS
            or native.get('source') != 'native_owner_telegram'
            or native.get('message_id') != message
            or not isinstance(native.get('scope'), list)
            or native['scope'] != scope):
        return None
    text_hash = native.get('text_sha256')
    if (not isinstance(text_hash, str)
            or not re.fullmatch(r'[a-f0-9]{64}', text_hash)
            or text_hash == _EMPTY_TEXT_HASH):
        return None
    return {'policy': 'owner_command', 'message_id': message, 'text_sha256': text_hash}
