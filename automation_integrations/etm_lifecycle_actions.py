"""Read back existing ETM document actions without retrying business requests.

The published delivery read schema does not expose the requested point/date/time
binding. Preserve that uncertainty instead of treating a delivery ID as proof.
"""
from copy import deepcopy

try:
    from .api_read import Failure
except ImportError:
    from api_read import Failure


OPERATIONS = frozenset({'invoice_order', 'invoice_delivery', 'invoice_approval_update'})


def _helpers():
    # Imported lazily because etm_lifecycle delegates these operations here.
    try:
        from .etm_lifecycle import Reader, _document, _listed, _ids, canceled
        from .etm_public_order import ACCEPTED
    except ImportError:
        from etm_lifecycle import Reader, _document, _listed, _ids, canceled
        from etm_public_order import ACCEPTED
    return Reader, _document, _listed, _ids, canceled, ACCEPTED


class _CachedReader:
    """Reuse one body snapshot when joining its exact list row."""
    def __init__(self, reader):
        self.reader = reader
        self.bodies = {}

    def read(self, path, query=None):
        if path.endswith('/body'):
            if path not in self.bodies:
                value = self.reader.read(path, query)
                rows = value.get('rows', [])
                if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                    raise Failure('etm_lifecycle_document_rows_unverified')
                self.bodies[path] = value
            return deepcopy(self.bodies[path])
        return self.reader.read(path, query)


def _read_document(reader, ident, document, listed):
    initial = document(reader, ident)
    rows = listed(reader, initial['number'])
    matches = [row for row in rows if row.get('id') == ident]
    if len(matches) != 1:
        return initial, {}, ['document_list_identity_unverified'], []
    return document(reader, ident, matches[0]), matches[0], [], [row.get('id') for row in rows]


def _outcome(row, documents, problems, *, details=None):
    verified = not problems
    status = 'verified' if verified else row.get('status', 'accepted_unverified')
    if not verified and status not in ('accepted_unverified', 'outcome_unknown'):
        status = 'accepted_unverified'
    raw = row.get('result')
    result = deepcopy(raw) if isinstance(raw, dict) else {}
    result.update(documents=documents, reconciliation={
        'operation': row['operation'], 'verified': verified, 'status': status,
        'read_only': True, 'problems': list(dict.fromkeys(problems)), **(details or {})})
    # Generic actions do not carry the quantity, contract or physical-allocation
    # baseline checked by order_checkout. Verify only the requested action state.
    result['ready_for_pickup'] = False
    return {'status': status, 'result': result}


def reconcile(row, config, *, http=None, vault=None):
    if row.get('service') != 'etm' or row.get('operation') not in OPERATIONS:
        return None
    operation = row['operation']
    params = row.get('params') or {}
    ident = (params.get('path') or {}).get('id')
    query = params.get('query') or {}
    Reader, document, listed, ids_from_response, canceled, accepted = _helpers()
    reader = _CachedReader(Reader(config, http=http, vault=vault))
    ids = [ident]
    problems = []
    target_source = 'request_path'
    if operation == 'invoice_order':
        raw = row.get('result')
        raw = raw if isinstance(raw, dict) else {}
        data = raw.get('data')
        explicit_ids = isinstance(data, dict) and any(key in data for key in ('id', 'ids', 'createdDoc'))
        returned, valid = ids_from_response(raw)
        if explicit_ids:
            # Read every usable returned ID for evidence even if another ID is
            # malformed; never downgrade a partial response to single-ID success.
            ids = returned or [ident]
            target_source = 'provider_response'
            if not valid:
                problems.append('returned_document_ids_incomplete')
        elif data is not None and not isinstance(data, dict):
            problems.append('returned_document_ids_unverified')

    documents, list_rows, related_ids = [], [], []
    for current in ids:
        found, list_row, issues, siblings = _read_document(reader, current, document, listed)
        documents.append(found)
        list_rows.append(list_row)
        problems.extend(current + ':' + issue for issue in issues)
        related_ids.extend(value for value in siblings if value != current)
    if len({doc['client_code'] for doc in documents}) != 1:
        problems.append('document_clients_differ')

    if operation == 'invoice_order':
        if target_source == 'request_path' and related_ids:
            # A lost/no-ID response may have split the original document. The
            # original's accepted state cannot prove the outcome of siblings.
            # A common reference alone is insufficient to claim their lineage.
            problems.append('unreturned_related_documents_unverified')
        desired = query.get('skl')
        if desired is None:
            problems.append('requested_destination_not_explicit')
        for found in documents:
            prefix = found['id'] + ':'
            if (str(found.get('status_code') or '') not in accepted
                    or not found.get('status') or found['status'] == 'Спецификация'
                    or canceled(found)):
                problems.append(prefix + 'order_acceptance_unverified')
            if desired is None or str(found.get('pickup_store')) != str(desired):
                problems.append(prefix + 'destination_unverified')
            note = query.get('tovzak')
            if isinstance(note, str) and note:
                body = reader.bodies.get('/invoice/' + found['id'] + '/body') or {}
                if body.get('ps') != note:
                    annotations = reader.read('/invoice/' + found['id'] + '/ps')
                    comments = annotations.get('comments')
                    if (not isinstance(comments, list) or not any(
                            isinstance(comment, dict) and comment.get('text') == note for comment in comments)):
                        problems.append(prefix + 'order_note_unverified')
        return _outcome(row, documents, problems, details={
            'target_source': target_source, 'document_ids': ids,
            'related_document_ids_as_returned': related_ids,
            'quantity_baseline_available': False, 'physical_allocation_verified': False,
            'delivery_requested': str(desired) == '1000'})

    if operation == 'invoice_delivery':
        for found, list_row in zip(documents, list_rows):
            found['delivery_as_returned'] = {key: deepcopy(list_row.get(key)) for key in
                                            ('delivery', 'delivery_status', 'delivery_name')}
        # These are the only published delivery fields in invoice list/body.
        # They cannot prove adr/date/time/time_po/phone from the write request.
        problems.append('delivery_point_date_window_binding_unverified')
        return _outcome(row, documents, problems, details={
            'target_source': target_source, 'delivery_read_schema_has_binding_fields': False})

    comments = reader.read('/invoice/' + ident + '/ps')
    entries = comments.get('comments')
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise Failure('etm_lifecycle_comments_unverified')
    expected_text = query.get('text')
    sg = query.get('sg')
    matched = [entry for entry in entries if expected_text is None or entry.get('text') == expected_text]
    if expected_text is not None and not matched:
        problems.append('comment_text_unverified')
    if sg is not None:
        if (str(sg) not in ('1', '2')
                or str(list_rows[0].get('agreed') or '') != str(sg)):
            problems.append('current_approval_unverified')
        if expected_text is not None and not any(str(entry.get('agreed') or '') == str(sg) for entry in matched):
            problems.append('comment_approval_unverified')
    if query.get('docStatus') is not None:
        # /ps documents history and permission, not a current docStatus field.
        problems.append('final_approval_status_unverified')
    if query.get('service_message') == 'true':
        problems.append('internal_message_visibility_unverified')
    if expected_text is None and sg is None and query.get('docStatus') is None:
        problems.append('requested_comment_action_not_explicit')
    return _outcome(row, documents, problems, details={
        'target_source': target_source, 'matching_comments': len(matched) if expected_text is not None else None,
        'current_agreed_as_returned': list_rows[0].get('agreed')})
