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
    'delivery_point_create', 'invoice_print',
})
_MESSAGE_FIELDS = {'source', 'message_id', 'scope', 'text_sha256'}
_EMPTY_TEXT_HASH = hashlib.sha256(b'').hexdigest()
PROCUREMENT_OPERATIONS = frozenset({
    'order_checkout', 'invoice_create', 'invoice_order', 'invoice_delivery',
    'delivery_point_create',
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


def unresolved_procurement(config, scope, *, exclude=None):
    """Block new ETM effects until uncertain writes in either route resolve.

    Callers hold ``procurement_lock`` throughout this check and submission.
    Generic accepted responses are terminal for this guard; website checkout
    also needs its final document readback, so its accepted state still blocks.
    Legacy records without account hashes belong conservatively to this state
    directory's configured account.
    """
    account = account_hash(config)
    root = Path(config['state_dir'])
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
                unresolved = old.get('status') in ('submitting', 'outcome_unknown')
            else:
                unresolved = old.get('status') in ('submitting', 'outcome_unknown', 'accepted_unverified')
            if not unresolved:
                continue
            if old.get('scope') != scope:
                return {'ok': False, 'error': 'other_unresolved_checkout',
                        'instruction': 'An earlier ETM procurement operation for this account is unresolved. '
                                       'Inspect the original conversation before placing another order or shipment.'}
            return {'ok': False, 'error': 'existing_unresolved_draft',
                    'draft_id': old['draft_id'], 'status': old['status'],
                    'instruction': 'Inspect this exact ETM draft; never replace an uncertain order or shipment '
                                   'by changing parameters or switching between the public API and website checkout.'}
    return None


def owner_command(context, config, service, operation, params):
    """Return current native-message evidence for allowed ETM purchases only.

    Configuration records standing permission; message provenance binds its
    use to the current owner turn. No wording heuristic or model-supplied
    confirmation boolean can grant this permission. Cancellation/replacement
    and writes to other providers keep their existing confirmation policy.
    """
    if (not isinstance(context, dict) or not isinstance(config, dict)
            or config.get('etm_order_authorization') != 'owner_command'
            or service != 'etm' or not isinstance(operation, str)
            or not isinstance(params, dict)):
        return None
    if operation == 'invoice_create':
        body = params.get('body')
        if not isinstance(body, dict) or body.get('DocumentFunctionCode') not in ('P', 'A'):
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
