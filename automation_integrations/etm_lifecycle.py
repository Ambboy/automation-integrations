"""Read-backed ETM document transitions; never send or replay a business request.

The caller holds the account procurement lock. Cancellation/replacement target
the customer's exact OrderNumber, so resolve and retain every affected ETM ID.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
import re
import time
import uuid

try:
    from .api_read import Failure, HTTP, Vault
    from .api_write import save
    from .etm_authorization import account_hash
    from . import extended_api
except ImportError:
    from api_read import Failure, HTTP, Vault
    from api_write import save
    from etm_authorization import account_hash
    import extended_api

ID = re.compile(r'[0-9]+-[0-9]+\Z')


class Reader:
    def __init__(self, config, *, http=None, vault=None):
        self.http = http or HTTP('etm', config)
        self.vault = vault or Vault(config)
        secret = self.vault.get('etm')
        auth = self.http.call('POST', '/user/login', query={
            'log': secret['ETM_LOGIN'], 'pwd': secret['ETM_PASSWORD']})
        self.session = extended_api.etm_session(auth)
        self.vault.sensitive.append(self.session)

    def read(self, path, query=None):
        response = self.http.call('GET', path, query={
            **(query or {}), 'session-id': self.session})
        extended_api.validate_etm_response(response)
        data = response.get('data')
        if not isinstance(data, dict):
            raise Failure('etm_lifecycle_invalid_response')
        return data


def canceled(document):
    # Use explicit provider status labels; numeric cancellation codes are not
    # specified by the public manual. A missing document is never cancellation.
    # The body is fetched after the listing. Never let a stale list status
    # override an explicit current body status.
    name = str(document.get('status') or document.get('invStatus')
               or document.get('status_name') or '').strip().casefold()
    return (name.startswith(('расторгнут', 'отменён', 'отменен', 'аннулирован'))
            or name in ('отказ', 'отказ от заказа'))


def specification(document):
    return (str(document.get('status_code')) in ('01', '1')
            and document.get('status') == 'Спецификация')


def _document(reader, ident, listed=None):
    if not isinstance(ident, str) or not ID.fullmatch(ident):
        raise Failure('invalid_etm_document_id')
    body = reader.read('/invoice/' + ident + '/body', {'detail': 'buyer,delivery,price'})
    if body.get('invnetnum') != ident or not body.get('cli_code') or not body.get('invnum'):
        raise Failure('etm_lifecycle_document_unverified')
    listed = listed or {}
    if (listed and (listed.get('id') != ident
            or listed.get('cli_code') is not None and str(listed['cli_code']) != str(body['cli_code']))):
        raise Failure('etm_lifecycle_document_identity_mismatch')
    return {'id': ident, 'number': str(body['invnum']),
            'customer_order_number': str(listed.get('usr_inv_num') or body['invnum']),
            'client_code': str(body['cli_code']), 'status': body.get('invStatus'),
            'status_name': listed.get('status_name'), 'status_code': listed.get('status_code'),
            'pickup_store': listed.get('st_dest'), 'current_store': body.get('store'),
            'total_vat': body.get('invsum'), 'paid_as_returned': listed.get('pay', body.get('paysum')),
            'body_paid_as_returned': body.get('paysum'),
            'operations': deepcopy(listed.get('operations') or {}),
            'items': [{k: row.get(k) for k in ('gdscode', 'cnt')} for row in body.get('rows', [])]}


def _listed(reader, reference):
    rows, page, count = [], 1, None
    while True:
        data = reader.read('/invoice', {'usr-inv-num': reference, 'rows': 100, 'page': page})
        batch = data.get('rows')
        if not isinstance(batch, list) or any(not isinstance(row, dict) for row in batch):
            raise Failure('etm_lifecycle_listing_unverified')
        try:
            current = int(data['records'])
        except (KeyError, ValueError, TypeError):
            raise Failure('etm_lifecycle_listing_incomplete') from None
        if current < 0 or current > 1000 or count is not None and current != count:
            raise Failure('etm_lifecycle_listing_incomplete')
        count = current
        rows.extend(batch)
        if len(rows) == count:
            break
        if not batch or len(rows) > count or page >= 10:
            raise Failure('etm_lifecycle_listing_incomplete')
        page += 1
    exact = [row for row in rows if str(row.get('usr_inv_num') or '') == reference]
    if len({row.get('id') for row in exact}) != len(exact):
        raise Failure('etm_lifecycle_duplicate_document_id')
    return exact


def _source_rows(config, reference):
    root = Path(config['state_dir']) / 'etm-writes'
    for path in sorted(root.glob('*.json')):
        row = json.loads(path.read_text())
        if row.get('account_hash', account_hash(config)) != account_hash(config):
            continue
        receipt = row.get('receipt') or {}
        prepared = row.get('prepared') or {}
        if (receipt.get('customer_order_number') == reference
                or prepared.get('params', {}).get('customer_order_number') == reference):
            yield path, row


def _ids(result):
    try:
        from .etm_public_order import PublicCheckout
    except ImportError:
        from etm_public_order import PublicCheckout
    return PublicCheckout._ids(result or {})


def _generic_source_rows(config, reference):
    """Yield only complete provider receipts for operations D/C can resolve."""
    for path in sorted((Path(config['state_dir']) / 'contract-writes').glob('*.json')):
        row = json.loads(path.read_text())
        if (row.get('service') != 'etm'
                or row.get('account_hash', account_hash(config)) != account_hash(config)):
            continue
        operation = row.get('operation')
        body = row.get('params', {}).get('body', {})
        if operation == 'invoice_create':
            if body.get('DocumentFunctionCode') not in ('P', 'A') or body.get('OrderNumber') != reference:
                continue
        elif operation != 'invoice_order':
            continue
        original, valid = _ids(row.get('result'))
        if not valid:
            # A known path ID or a partial returned list cannot prove all the
            # documents potentially created by a lost/split response.
            continue
        if operation == 'invoice_create' and body.get('DocumentFunctionCode') == 'A':
            original = list(set(original + list((row.get('lifecycle') or {}).get('target_ids') or [])))
        if not original or any(not isinstance(ident, str) or not ID.fullmatch(ident) for ident in original):
            continue
        yield path, row, original


def _current_generic_ids(row, original):
    recovery = row.get('recovery') or {}
    replacement = recovery.get('replacement_document_ids') or []
    if replacement:
        current = replacement
    elif row.get('status') == 'canceled' and recovery.get('canceled_document_ids'):
        current = recovery['canceled_document_ids']
    else:
        current = original
    if not isinstance(current, list) or any(not isinstance(ident, str) or not ID.fullmatch(ident) for ident in current):
        return set()
    return set(current)


def _lineage(config, reference):
    current, historical = set(), set()
    for _, row in _source_rows(config, reference):
        receipt = row.get('receipt') or {}
        recovery = row.get('recovery') or {}
        replacement = recovery.get('replacement_document_ids') or []
        if replacement:
            historical.update(receipt.get('document_ids') or [])
            current.update(replacement)
        else:
            current.update(receipt.get('document_ids') or [])
    for _, row, original in _generic_source_rows(config, reference):
        if row.get('operation') != 'invoice_create':
            continue
        active = _current_generic_ids(row, original)
        current.update(active)
        historical.update(set(original) - active)
        for recovery in [row.get('recovery') or {}, *row.get('recovery_history', [])]:
            historical.update(set(recovery.get('canceled_document_ids') or []) - active)
    replacements = []
    for path in (Path(config['state_dir']) / 'contract-writes').glob('*.json'):
        row = json.loads(path.read_text())
        body = row.get('params', {}).get('body', {})
        if (row.get('account_hash', account_hash(config)) == account_hash(config)
                and row.get('service') == 'etm' and row.get('operation') == 'invoice_create'
                and row.get('status') == 'replaced' and body.get('OrderNumber') == reference):
            replacements.append(row)
    for row in sorted(replacements, key=lambda r: r.get('created_at', 0)):
        old = set((row.get('lifecycle') or {}).get('target_ids') or [])
        new, valid = _ids(row.get('result'))
        if valid:
            historical.update(old)
            current.difference_update(old)
            current.update(set(new) - old)
    current.difference_update(historical)
    return current, historical


def _discover_managed_cancel_targets(config, reference, known, found, historical, reader, listed):
    """Recover one extra specification under our unique generated reference.

    Neither ID supersedes the other: retain and later verify cancellation of
    both. Manual references, splits, reservations and uncertain receipts do not
    qualify for this narrowly evidenced discovery.
    """
    if len(known) != 1 or len(found) != 1 or known == found or historical:
        return None
    sources = list(_source_rows(config, reference))
    if len(sources) != 1:
        return None
    _, source = sources[0]
    receipt = source.get('receipt') or {}
    try:
        draft = source['draft_id']
        if str(uuid.UUID(draft)) != draft or reference != 'AI-' + uuid.UUID(draft).hex.upper():
            return None
    except (KeyError, ValueError, TypeError, AttributeError):
        return None
    if (receipt.get('all_returned_ids_valid') is not True
            or receipt.get('order_attempted_ids') != []
            or receipt.get('document_ids') != sorted(known)
            or receipt.get('customer_order_number') != reference
            or source.get('recovery') or source.get('recovery_history')):
        return None
    documents = [_document(reader, ident, next((row for row in listed if row.get('id') == ident), None))
                 for ident in sorted(known | found)]
    if (len({doc['client_code'] for doc in documents}) != 1
            or any(doc['customer_order_number'] != reference or doc['number'] != reference
                   or not (doc['status'] == 'Спецификация' or canceled(doc))
                   or doc['operations'].get('cancel') is False for doc in documents)):
        return None
    try:
        signatures = []
        for doc in documents:
            paid = Decimal(str(doc['body_paid_as_returned']))
            if not paid.is_finite() or paid != 0 or not doc['items']:
                return None
            items = []
            for item in doc['items']:
                code, quantity = str(item['gdscode']), Decimal(str(item['cnt']))
                if not code.isdecimal() or not quantity.is_finite() or quantity <= 0:
                    return None
                items.append((code, quantity))
            signatures.append(sorted(items))
    except (InvalidOperation, ValueError, TypeError, KeyError):
        return None
    if signatures[0] != signatures[1]:
        return None
    return documents


def preflight(operation, params, config, *, http=None, vault=None):
    if operation != 'invoice_create' or params.get('body', {}).get('DocumentFunctionCode') not in ('A', 'C', 'D'):
        return None
    body = params['body']
    reference, function = body['OrderNumber'], body['DocumentFunctionCode']
    reader = Reader(config, http=http, vault=vault)
    listed = _listed(reader, reference)
    known, historical = _lineage(config, reference)
    found = {str(row.get('id')) for row in listed}
    discovered = None
    if known and found - known - historical:
        if function == 'D':
            discovered = _discover_managed_cancel_targets(
                config, reference, known, found, historical, reader, listed)
        if discovered is None:
            raise Failure('etm_customer_order_number_ambiguous')
    if not known and len(found) != 1:
        raise Failure('etm_customer_order_number_ambiguous' if found else 'etm_original_order_not_found')
    target_ids = sorted(known | found) if discovered else sorted(known or found)
    documents = discovered or [_document(reader, ident, next((r for r in listed if r.get('id') == ident), None))
                              for ident in target_ids]
    if (not documents or len({d['client_code'] for d in documents}) != 1
            or any(d['customer_order_number'] != reference for d in documents)):
        raise Failure('etm_original_order_identity_mismatch')
    for document in documents:
        if canceled(document):
            if function != 'D':
                raise Failure('etm_original_order_already_canceled')
            continue
        if function == 'D' and document['operations'].get('cancel') is False:
            raise Failure('etm_provider_cancellation_unavailable')
        if function == 'C' and not (specification(document) or document['status'] == 'Счёт на оплату'
                                   or document['status'] == 'Счет на оплату'):
            raise Failure('etm_document_not_replaceable')
    return {'function': function, 'order_number': reference, 'target_ids': target_ids,
            'client_code': documents[0]['client_code'], 'documents': documents,
            'all_targets_specifications': (all(d['status'] == 'Спецификация' for d in documents)
                                          if discovered else all(specification(d) for d in documents)),
            **({'discovered_document_ids': sorted(found - known),
                'identity_resolution': 'Both unpaid documents have the exact managed UUID customer reference, '
                                       'client and item quantities. Cancel and verify both IDs; neither is assumed superseded.'}
               if discovered else {}),
            'already_complete': function == 'D' and all(canceled(d) for d in documents)}


def assert_same_target(previous, current):
    keys = ('function', 'order_number', 'target_ids', 'client_code')
    if not isinstance(previous, dict) or not isinstance(current, dict) or any(
            previous.get(k) != current.get(k) for k in keys):
        raise Failure('etm_lifecycle_target_changed')


def _resolve_sources(config, reference, documents, *, replacement_ids=None):
    canceled_ids = {d['id'] for d in documents if canceled(d)}
    for path, source in _source_rows(config, reference):
        receipt = source.get('receipt') or {}
        if receipt.get('all_returned_ids_valid') is not True:
            continue
        ids = set((source.get('recovery') or {}).get('replacement_document_ids')
                  or receipt.get('document_ids', []))
        if not ids or not ids <= canceled_ids:
            continue
        if source.get('status') == 'canceled':
            continue
        status = 'replaced' if replacement_ids else 'canceled'
        if source.get('recovery'):
            source.setdefault('recovery_history', []).append(deepcopy(source['recovery']))
        source['recovery'] = {'previous_status': source.get('status'), 'verified_at': time.time(),
                              'order_number': reference, 'canceled_document_ids': sorted(ids),
                              'replacement_document_ids': replacement_ids or [],
                              'evidence': deepcopy(documents)}
        source['status'] = status
        source['result'] = {**(source.get('result') or {}), 'status': status,
                            'document_cancellation_verified': True, 'final_order_verified': False,
                            'mutation_verified': False, 'ready_for_pickup': False,
                            'documents': deepcopy(documents),
                            'instruction': 'Previous documents are canceled. Preserve this receipt; do not replay the old checkout.'}
        save(path, source)
    for path, source, original in _generic_source_rows(config, reference):
        ids = _current_generic_ids(source, original)
        if not ids or not ids <= canceled_ids or source.get('status') == 'canceled':
            continue
        status = 'replaced' if replacement_ids else 'canceled'
        if source.get('recovery'):
            source.setdefault('recovery_history', []).append(deepcopy(source['recovery']))
        raw_result = deepcopy(source.get('result') or {})
        source['recovery'] = {
            'previous_status': source.get('status'), 'verified_at': time.time(),
            'order_number': reference, 'canceled_document_ids': sorted(ids),
            'replacement_document_ids': replacement_ids or [], 'evidence': deepcopy(documents),
            'previous_reconciliation': deepcopy(raw_result.get('reconciliation')),
            'original_operation_completion_verified': False}
        source['status'] = status
        # Preserve the raw provider status/data and all receipt fields. This
        # establishes cancellation of their exact documents, not success of an
        # earlier uncertain reservation or confirmation request.
        raw_result['reconciliation'] = {
            'status': status, 'verified': True, 'read_only': True,
            'effect': 'cancellation_of_linked_documents',
            'document_cancellation_verified': True,
            'original_operation_completion_verified': False,
            'order_number': reference, 'documents': deepcopy(documents)}
        source['result'] = raw_result
        save(path, source)


def reconcile(row, config, *, http=None, vault=None):
    if row.get('service') != 'etm':
        return None
    if row.get('operation') != 'invoice_create':
        try:
            from . import etm_lifecycle_actions
        except ImportError:
            import etm_lifecycle_actions
        return etm_lifecycle_actions.reconcile(row, config, http=http, vault=vault)
    params = row['params']; body = params['body']; function = body['DocumentFunctionCode']
    lifecycle = row.get('lifecycle') or {}
    ids = list(lifecycle.get('target_ids') or [])
    returned, valid = _ids(row.get('result'))
    if function == 'P':
        if not valid:
            return None
        ids = sorted(_current_generic_ids(row, returned))
    elif not ids:
        return None
    reader = Reader(config, http=http, vault=vault)
    listed = _listed(reader, body['OrderNumber'])
    # A recovered P/A may now represent a later replacement generation. Its
    # preserved original response must not redirect status to canceled ancestors.
    replacement_generation = (row.get('recovery') or {}).get('replacement_document_ids')
    if function == 'A' and replacement_generation:
        ids = sorted(_current_generic_ids(row, list(set(ids + returned))))
    all_ids = sorted(set(ids if function in ('P', 'A') and replacement_generation else ids + returned))
    documents = [_document(reader, ident, next((r for r in listed if r.get('id') == ident), None))
                 for ident in all_ids]
    if any(d['customer_order_number'] != body['OrderNumber'] for d in documents):
        raise Failure('etm_lifecycle_document_reference_mismatch')
    if lifecycle.get('client_code') and any(d['client_code'] != lifecycle['client_code'] for d in documents):
        raise Failure('etm_lifecycle_client_mismatch')
    old = [d for d in documents if d['id'] in ids]
    new = [d for d in documents if d['id'] not in ids]
    status = row.get('status', 'accepted_unverified')
    verified = False
    if function == 'D' and all(canceled(d) for d in old):
        status, verified = 'canceled', True
        _resolve_sources(config, body['OrderNumber'], old)
    elif function == 'C' and valid and new and all(canceled(d) for d in old):
        # Later cancellation of the replacement does not undo the completed C
        # transition. This also recovers a crash after saving the source lineage
        # but before saving this operation's verification.
        status, verified = 'replaced', True
        _resolve_sources(config, body['OrderNumber'], old, replacement_ids=[d['id'] for d in new])
    elif function in ('P', 'A') and documents:
        if valid and all(canceled(d) for d in documents):
            status, verified = 'canceled', True
            _resolve_sources(config, body['OrderNumber'], documents)
        elif all(specification(d) for d in documents):
            status = 'specification'
    result = {**(row.get('result') or {}), 'documents': documents,
              'reconciliation': {'function': function, 'verified': verified, 'status': status,
                                  'read_only': True, 'order_number': body['OrderNumber']}}
    updates = {'status': status, 'result': result, 'lifecycle': {**lifecycle, 'target_ids': ids}}
    if function in ('P', 'A') and status == 'canceled':
        result['reconciliation'].update(document_cancellation_verified=True,
                                        original_operation_completion_verified=False)
        # The wrapper persists its in-memory row after this helper returns.
        # Keep the recovery audit written above when that row is itself one
        # of the linked sources, rather than overwriting it with stale metadata.
        if row.get('draft_id'):
            for _, saved, _ in _generic_source_rows(config, body['OrderNumber']):
                if saved.get('draft_id') == row['draft_id'] and saved.get('status') == 'canceled':
                    for key in ('recovery', 'recovery_history'):
                        if key in saved:
                            updates[key] = deepcopy(saved[key])
    return updates


def reconcile_checkout(row, config, *, checkout=None):
    receipt = row.get('receipt') or {}
    ids = receipt.get('document_ids')
    reference = receipt.get('customer_order_number')
    if (not ids or not reference or receipt.get('all_returned_ids_valid') is not True
            or not hasattr(checkout, 'client')):
        return None
    client = checkout.client
    identity = client.login(row['prepared']['params']['region'])

    class WebReader:
        def read(self, path, query=None):
            return client.call('GET', path, query=query)

    reader = WebReader()
    listed = _listed(reader, reference)
    # An observed sibling with the same reference must not be left active while
    # the original receipt is declared canceled. Reads never alter that receipt.
    all_ids = sorted(set(ids + [str(r.get('id')) for r in listed]))
    documents = [_document(reader, ident, next((r for r in listed if r.get('id') == ident), None)) for ident in all_ids]
    if any(d['client_code'] != identity['clicode'] or d['customer_order_number'] != reference for d in documents):
        raise Failure('etm_lifecycle_document_identity_mismatch')
    if all(canceled(d) for d in documents):
        status = 'canceled'
    elif (not receipt.get('order_attempted_ids') and receipt.get('all_returned_ids_valid')
          and all(specification(d) for d in documents)):
        status = 'specification'
    else:
        return None
    return {**(row.get('result') or {}), 'status': status, 'documents': documents,
            'document_created': True, 'final_order_verified': False, 'mutation_verified': False,
            'document_cancellation_verified': status == 'canceled', 'ready_for_pickup': False,
            'next_actions': [] if status == 'canceled' else ['invoice_create:A', 'invoice_create:C', 'invoice_create:D', 'invoice_order'],
            'instruction': 'Known document state. Use its exact identifiers for the next authorized action; do not repeat creation.'}
