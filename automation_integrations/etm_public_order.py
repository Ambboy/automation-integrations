"""Explicit public-document checkout when the portal cannot offer an office.

Creating a document is already a business mutation. Its identifiers are recorded
before any readback, and reservation requires a fresh, verifiable document
preflight. A failed or interrupted execution is reconciled by reads, never replayed.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import re

try:
    from .api_read import Failure, HTTP
    from . import etm_order, extended_api
except ImportError:
    from api_read import Failure, HTTP
    import etm_order
    import extended_api


ACCEPTED = {'05', '5', '15', '151', '152', '153', '20', '24', '25', '26',
            '27', '40', '45', '451', '452', '455'}
DOCUMENT_ID = re.compile(r'[0-9]+-[0-9]+\Z')


class PublicCheckout:
    def __init__(self, web_client, portal_checkout, *, http=None):
        self.client = web_client
        self.portal = portal_checkout
        self.http = http or HTTP('etm', web_client.config)
        self.session = None
        self.submitted = False

    def __repr__(self):
        return 'PublicCheckout(authenticated=' + str(bool(self.session)) + ')'

    def _authenticate(self):
        if not self.session:
            secret = self.client.vault.get('etm')
            auth = self.http.call('POST', '/user/login', query={
                'log': secret['ETM_LOGIN'], 'pwd': secret['ETM_PASSWORD']})
            self.session = extended_api.etm_session(auth)
            self.client.vault.sensitive.append(self.session)

    def _public(self, path, *, query=None, body=None):
        result = self.http.call('POST', path,
            query={**(query or {}), 'session-id': self.session}, body=body)
        return extended_api.validate_etm_response(result)

    def _destination(self, params):
        city = self.client.call('GET', '/info/city/' + params['region'])
        rows = city.get('rows')
        if not isinstance(rows, list):
            raise Failure('etm_pickup_office_unverified')
        matches = [r for r in rows if isinstance(r, dict)
                   and str(r.get('id')) == params['pickup_store']]
        if (len(matches) != 1 or matches[0].get('available_pick') is not True
                or not isinstance(matches[0].get('address'), str) or not matches[0]['address']):
            raise Failure('etm_pickup_office_unverified')
        row = matches[0]
        return {'code': params['pickup_store'], 'name': row.get('name') or row['address'],
                'address': row['address'], 'time': row.get('time')}

    def prepare(self, params, identity, contract, fields, basket):
        params = deepcopy(params)
        reference = params.get('customer_order_number')
        if not isinstance(reference, str) or not re.fullmatch(r'[0-9A-ZБ-ЯЁ./-]{1,100}', reference):
            raise Failure('etm_customer_order_number_required')
        if (not isinstance(contract.get('name'), str) or not contract['name'].strip()
                or str(contract.get('id')) != params.get('contract_id')):
            raise Failure('etm_contract_unavailable')
        profile = self.client.call('GET', '/user/profile')
        contracts = profile.get('contracts')
        if not isinstance(contracts, list):
            raise Failure('etm_public_contract_unverified')
        matches = [r for r in contracts if isinstance(r, dict)
                   and str(r.get('id')) == contract['id'] and r.get('num') == contract['name']]
        if len(matches) != 1:
            raise Failure('etm_public_contract_unverified')
        try:
            contract_date = datetime.strptime(matches[0]['from'], '%d.%m.%Y').date().isoformat()
        except (KeyError, TypeError, ValueError):
            raise Failure('etm_public_contract_unverified') from None
        store = self._destination(params)
        items, lines, estimate = [], [], Decimal(0)
        for index, row in enumerate(params['items'], 1):
            query = {'type': 'etm', 'city': params['region'], 'skl': params['pickup_store']}
            card = self.client.call('GET', '/goods/' + row['code'], query=query)
            self.portal.sleeper(1)
            prices = self.client.call('GET', '/goods/' + row['code'] + '/price', query=query)
            matches = [x for x in prices.get('rows', []) if str(x.get('gdscode')) == row['code']]
            if str(card.get('gdsCode')) != row['code'] or len(matches) != 1:
                raise Failure('etm_product_verification_failed')
            price = etm_order._decimal(matches[0].get('pricewnds'))
            packs = self.client.call('GET', '/goods/' + row['code'] + '/packs',
                                    query={'city': params['region'], 'skl': params['pickup_store']})
            amount = price * etm_order._decimal(row['quantity'])
            estimate += amount
            items.append({**row, 'name': card.get('gdsNameTitle'), 'unit': card.get('gdsUnitName'),
                'unit_price_vat': etm_order._money(price), 'line_estimate_vat': etm_order._money(amount),
                'pack': card.get('gdsInfoPacks'),
                'packaging_rules_as_returned': packs.get('packRestrictShipRate', {}),
                'availability_as_returned': card.get('gdsCommonAvail'),
                'availability_is_allocation': False, 'pickup_date_as_returned': card.get('gdsPickup')})
            lines.append({'LineNumber': index, 'SupplierItemCode': row['code'],
                'ItemDescription': card.get('gdsNameTitle') or row['code'],
                'OrderedQuantity': row['quantity'], 'OrderedUnitGrossPrice': format(price, 'f'),
                'GrossAmount': etm_order._money(amount)})
        total = etm_order._money(estimate)
        params['max_total'] = params.get('max_total', total)
        if etm_order._decimal(params['max_total']) < etm_order._decimal(total):
            raise Failure('etm_quote_exceeds_max_total')
        payment = self.portal._payment(params, total, contract['id'])
        blockers = []
        if (params['payment_method'], params['pay_type']) != ('bill', 'bill'):
            blockers.append('public_api_requires_verified_contract_bill_payment')
        note = params.get('note', '')
        if not params.get('allow_supplier_order'):
            note = '\n'.join(filter(None, [note,
                'Только из складского наличия. Закупка товара у поставщика не согласована.']))
        if params.get('continuous_cut'):
            note = '\n'.join([note] + ['Код ' + r['code'] + ': требуется один непрерывный отрезок ' +
                r['quantity'] + ' ' + (r.get('unit') or '') + '; не делить на несколько отрезков.'
                for r in items]).strip()
        remarks = '\n'.join(filter(None, [note, 'Самовывоз: ' + store['address'] +
            '; код склада ЭТМ ' + params['pickup_store'] + '.',
            'Оплата по договору ' + contract['name'] + '.']))
        body = {'OrderNumber': reference, 'DocumentFunctionCode': 'P',
                'ContractNumber': contract['name'], 'ContractDate': contract_date, 'Currency': 'RUB',
                'Seller': {'ILN': '4660011519999'}, 'Remarks': remarks,
                'Order-Lines': lines, 'TotalLines': len(lines), 'TotalGrossAmount': total}
        # Use the same locally compiled documented contract as the public tool.
        extended_api.validate('etm', 'invoice_create', {'body': body}, write=True)
        preview = {'items': items, 'estimated_total_vat': total,
            'maximum_total_vat': params['max_total'], 'currency': 'RUB', 'pickup': store,
            'contract': deepcopy(contract), 'payment': payment, 'legal_entity': deepcopy(identity),
            'note': params.get('note', ''), 'continuous_cut': params.get('continuous_cut', False),
            'allow_supplier_order': params.get('allow_supplier_order', False),
            'order_route': 'ETM public API: create a document, verify its terms, then reserve for the requested office',
            'customer_order_number': reference,
            'customer_order_number_kind': 'Customer system reference; not an ETM assigned document number',
            'availability': 'Requested-office stock and allocation are unverified. Reservation requires document preflight.',
            'payment_conditions': 'Contract invoice only. The public API does not select a new payment method or make a payment.',
            'ordering_blockers': blockers, 'can_submit': not blockers,
            'creation_may_require_review': True,
            'instruction': 'Document creation is a business action. If its destination, contract or allocation cannot be '
                           'verified, report the created document and stop without reservation or retry.'}
        return {'route': 'public_api', 'params': params, 'preview': preview,
                'checkout_fields': deepcopy(fields), 'create_body': body, 'order_note': note,
                'basket_was_empty': not bool(basket.get('rows'))}

    @staticmethod
    def _ids(response):
        data = response.get('data', {})
        if not isinstance(data, dict):
            return [], False
        values, valid = [], True
        if 'id' in data:
            values.append(data['id'])
        if 'ids' in data:
            rows = data['ids']
            if not isinstance(rows, list):
                valid = False
            else:
                values.extend(r.get('docid') if isinstance(r, dict) else None for r in rows)
        if 'createdDoc' in data:
            rows = data['createdDoc']
            if not isinstance(rows, list):
                valid = False
            else:
                values.extend(r.get('invnum') if isinstance(r, dict) else None for r in rows)
        ids = []
        for value in values:
            if not isinstance(value, str) or not DOCUMENT_ID.fullmatch(value):
                valid = False
            elif value not in ids:
                ids.append(value)
        return ids, valid and bool(values) and len(ids) <= 100

    @staticmethod
    def _contract_bound(data, contract):
        value = data.get('i_dogovor')
        return value is not None and str(value) in (str(contract['id']), contract['name'])

    def _inspect(self, prepared, receipt, *, final):
        params = prepared['params']
        entity, contract = prepared['preview']['legal_entity'], prepared['preview']['contract']
        documents, problems, actual, total, cut_rows = [], [], {}, Decimal(0), {}
        if not receipt.get('all_returned_ids_valid') or not receipt.get('document_ids'):
            problems.append('final_document_ids_incomplete')
        for ident in receipt.get('document_ids', []):
            if not isinstance(ident, str) or not DOCUMENT_ID.fullmatch(ident):
                raise Failure('invalid_etm_document_id')
            body = self.client.call('GET', '/invoice/' + ident + '/body',
                                    query={'detail': 'buyer,seller,delivery,price'})
            number = body.get('invnum')
            if not isinstance(number, str) or not number:
                raise Failure('etm_document_number_unverified')
            listing = self.client.call('GET', '/invoice', query={'usr-inv-num': number, 'rows': 100, 'page': 1})
            matches = [r for r in listing.get('rows', []) if str(r.get('id')) == ident]
            listed = matches[0] if len(matches) == 1 else {}
            errors = []
            if body.get('invnetnum') != ident or len(matches) != 1:
                errors.append('document_id_not_verified')
            buyer = body.get('buyer') or {}
            if (str(body.get('cli_code')) != entity['clicode'] or str(buyer.get('inn')) != entity['inn_org']
                    or str(buyer.get('kpp')) != entity['kpp_org']):
                errors.append('legal_entity_mismatch')
            rows = body.get('rows')
            if not isinstance(rows, list):
                raise Failure('etm_document_rows_unverified')
            quantities = self.portal._contents(rows)
            for row in rows:
                code = str(row.get('gdscode'))
                cut_rows[code] = cut_rows.get(code, 0) + 1
            if body.get('records') != len(rows):
                errors.append('document_rows_incomplete')
            for code, quantity in quantities.items():
                actual[code] = actual.get(code, Decimal(0)) + quantity
            amount = etm_order._decimal(body.get('invsum'), allow_zero=True)
            total += amount
            for data in (body, listed):
                if data.get('i_dogovor') is not None and not self._contract_bound(data, contract):
                    errors.append('contract_mismatch')
            status = str(listed.get('status_code') or '')
            pay_title = listed.get('pay_title')
            payment_bound = (isinstance(pay_title, str)
                and etm_order._note_matches(contract['name'], pay_title) and bool(listed.get('pay_date')))
            contract_bound = payment_bound or any(self._contract_bound(data, contract) for data in (body, listed))
            if final or status in ACCEPTED:
                if (status in ACCEPTED and (not params['allow_supplier_order'] or params['continuous_cut'])
                        and ident not in receipt.get('allocation_verified_document_ids', [])):
                    errors.append('physical_allocation_unverified_for_created_order')
                if str(listed.get('st_dest')) != params['pickup_store']:
                    errors.append('pickup_store_mismatch')
                if not payment_bound:
                    errors.append('contract_payment_terms_unverified')
                if status not in ACCEPTED or body.get('invStatus') in ('Спецификация', 'Расторгнутый счет'):
                    errors.append('document_not_accepted_order')
                if receipt.get('note'):
                    comments = self.client.call('GET', '/invoice/' + ident + '/ps').get('comments', [])
                    if not etm_order._note_matches(receipt['note'], [body.get('ps', ''), comments]):
                        errors.append('order_note_unverified')
            documents.append({'id': ident, 'number': number, 'status': body.get('invStatus'),
                'status_code': status, 'total_vat': etm_order._money(amount), 'currency': 'RUB',
                'pickup_store': listed.get('st_dest'), 'current_store': body.get('store'),
                'payment_title': listed.get('pay_title'), 'payment_date': listed.get('pay_date'),
                'contract_bound': contract_bound,
                'items': [{'code': r.get('gdscode'), 'quantity': r.get('cnt'), 'name': r.get('gdsname'),
                           'shipping_date_as_returned': r.get('dateotgr')} for r in rows],
                'verification_problems': errors})
            problems.extend(ident + ':' + error for error in errors)
        if actual != self.portal._expected(params):
            problems.append('final_quantities_mismatch')
        if params.get('continuous_cut') and any(cut_rows.get(r['code']) != 1 for r in params['items']):
            problems.append('continuous_cut_split_across_document_rows')
        if total > etm_order._decimal(params['max_total']):
            problems.append('final_total_exceeds_approved_maximum')
        if total != etm_order._decimal(receipt['expected_total_vat']):
            problems.append('final_total_differs_from_quote')
        return documents, problems, total

    def _preflight(self, prepared, documents):
        params, contract = prepared['params'], prepared['preview']['contract']
        problems, allocations = [], {}
        for document in documents:
            ident = document['id']
            if document['status_code'] not in ('01', '1') or document['status'] != 'Спецификация':
                problems.append(ident + ':document_reservation_state_unverified')
                continue
            check = self.client.call('GET', '/invoice/' + ident + '/order',
                                     query={'skl': params['pickup_store']})
            errors = []
            # The portal's offered stores/qop cannot veto the public method's
            # documented skl selector. Verify the directory now and st_dest after
            # reservation. Preflight is used for contract/allocation evidence only.
            if check.get('i_dogovor') not in (None, ''):
                if not self._contract_bound(check, contract):
                    errors.append('contract_mismatch_in_preflight')
            elif not document['contract_bound']:
                errors.append('contract_not_bound')
            if check.get('qpay') != 'bill':
                errors.append('contract_bill_payment_unverified')
            if (check.get('cpr', {}).get('zapretgo') or check.get('zapretgo') or check.get('zapret_invoice')
                    or check.get('for_own_use', {}).get('available')):
                errors.append('document_reservation_restricted')
            good = check.get('can-reserve', {}).get('rows')
            bad = check.get('not-reserve', {}).get('rows')
            if not isinstance(good, list) or not isinstance(bad, list) or bad:
                errors.append('document_allocation_unverified')
                good = []
            expected = self.portal._contents([{'gdscode': row['code'], 'cnt': row['quantity']}
                                             for row in document['items']])
            if self.portal._contents(good) != expected:
                errors.append('document_allocation_quantity_mismatch')
            try:
                if etm_order._money(check.get('invStoreSum')) != document['total_vat']:
                    errors.append('document_price_changed_in_preflight')
            except Failure:
                errors.append('document_preflight_total_unverified')
            for row in good:
                code = str(row.get('gdscode'))
                allocations[code] = allocations.get(code, 0) + 1
                physical = True
                try:
                    etm_order._decimal(row.get('g-net'))
                    etm_order._decimal(row.get('g-num'))
                except Failure:
                    physical = False
                if not physical and (not params['allow_supplier_order'] or params['continuous_cut']):
                    errors.append('document_physical_allocation_unverified')
                if not physical:
                    pack = next((r.get('packaging_rules_as_returned', {})
                        for r in prepared['preview']['items'] if r['code'] == str(row.get('gdscode'))), {})
                    minimum = pack.get('packMinPartSuppl')
                    if minimum not in (None, '') and etm_order._decimal(row['cnt']) < etm_order._decimal(minimum, allow_zero=True):
                        errors.append('supplier_minimum_not_met')
            if params['continuous_cut'] and len(good) != len(expected):
                errors.append('continuous_cut_allocation_unverified')
            problems.extend(ident + ':' + error for error in errors)
        if params['continuous_cut']:
            expected_codes = {item['code'] for document in documents for item in document['items']}
            if any(allocations.get(code) != 1 for code in expected_codes):
                problems.append('continuous_cut_split_across_allocations')
        return problems

    @staticmethod
    def _result(prepared, receipt, documents, problems, total):
        return {'status': 'accepted_unverified' if problems else 'verified',
                'mutation_verified': not problems, 'documents': documents,
                'document_created': bool(receipt.get('created_document_ids')),
                'reservation_request_sent': bool(receipt.get('order_attempted_ids')),
                'final_order_verified': not problems,
                'total_vat': etm_order._money(total), 'currency': 'RUB',
                'verification_problems': problems, 'expected_items': prepared['params']['items'],
                'pickup': prepared['preview']['pickup'], 'receipt': deepcopy(receipt),
                'ready_for_pickup': False, 'order_route': 'public_api',
                'instruction': 'A created specification is not a verified placed order. '
                               'Report every created document and its verification problems. '
                               'Do not repeat creation or reservation to resolve an uncertain result.'}

    def execute(self, prepared, *, on_stage):
        if self.submitted:
            raise Failure('etm_public_checkout_already_submitted')
        params = prepared['params']
        if prepared['preview'].get('can_submit') is not True:
            raise Failure('etm_checkout_has_ordering_blockers')
        identity = self.client.login(params['region'])
        if identity != prepared['preview']['legal_entity']:
            raise Failure('etm_legal_entity_changed')
        contract, fields = self.portal._features(params)
        fresh = self.prepare(params, identity, contract, fields, {'rows': []})
        if any(fresh[key] != prepared[key] for key in ('create_body', 'checkout_fields')):
            raise Failure('etm_checkout_terms_changed')
        if fresh['preview']['pickup'] != prepared['preview']['pickup']:
            raise Failure('etm_pickup_changed_since_prepare')
        if fresh['preview']['payment'] != prepared['preview']['payment']:
            raise Failure('etm_payment_changed_since_prepare')
        self._authenticate()
        on_stage('checkout_submitting', {'route': 'public_api', 'action': 'invoice_create',
            'customer_order_number': params['customer_order_number'],
            'total_vat': prepared['preview']['estimated_total_vat'], 'currency': 'RUB'})
        self.submitted = True
        response = self._public('/invoice/create', body=prepared['create_body'])
        ids, valid = self._ids(response)
        receipt = {'route': 'public_api', 'document_ids': ids, 'created_document_ids': list(ids),
            'ordered_document_ids': [], 'order_attempted_ids': [], 'all_returned_ids_valid': valid,
            'allocation_verified_document_ids': [],
            'customer_order_number': params['customer_order_number'],
            'expected_total_vat': prepared['preview']['estimated_total_vat'],
            'note': prepared.get('order_note', '')}
        on_stage('checkout_accepted', deepcopy(receipt))
        documents, problems, total = self._inspect(prepared, receipt, final=False)
        if not problems:
            problems.extend(self._preflight(prepared,
                [document for document in documents if document['status_code'] not in ACCEPTED]))
        if problems:
            return self._result(prepared, receipt, documents, problems, total)
        # Preflight all split documents before reserving the first one.
        for document in documents:
            ident = document['id']
            if document['status_code'] in ACCEPTED:
                # Creation can itself return an accepted order. Never reserve it twice.
                if str(document['pickup_store']) != params['pickup_store']:
                    return self._result(prepared, receipt, documents,
                        [ident + ':accepted_document_destination_mismatch'], total)
                continue
            if document['status_code'] not in ('01', '1') or document['status'] != 'Спецификация':
                return self._result(prepared, receipt, documents,
                    [ident + ':document_reservation_state_unverified'], total)
            # Terms/allocation can change while other split documents are being
            # reserved. Recheck this document immediately before its own POST.
            problems = self._preflight(prepared, [document])
            if problems:
                result = self.reconcile(prepared, receipt)
                result.update(status='accepted_unverified', mutation_verified=False, final_order_verified=False)
                result['verification_problems'].extend(problems)
                return result
            receipt['allocation_verified_document_ids'].append(ident)
            receipt['order_attempted_ids'].append(ident)
            on_stage('checkout_accepted', deepcopy(receipt))
            on_stage('checkout_submitting', {'route': 'public_api', 'action': 'invoice_order', 'document_id': ident})
            response = self._public('/invoice/' + ident + '/order',
                query={'skl': params['pickup_store'], 'tovzak': prepared['create_body']['Remarks']})
            receipt['ordered_document_ids'].append(ident)
            returned, returned_valid = self._ids(response)
            data = response.get('data')
            if isinstance(data, dict) and any(k in data for k in ('id', 'ids', 'createdDoc')):
                receipt['all_returned_ids_valid'] = receipt['all_returned_ids_valid'] and returned_valid
                retained = ([value for value in receipt['document_ids'] if value != ident]
                            if returned_valid else receipt['document_ids'])
                receipt['document_ids'] = list(dict.fromkeys(retained + returned))
                if returned_valid and ident in receipt['allocation_verified_document_ids']:
                    receipt['allocation_verified_document_ids'] = list(dict.fromkeys(
                        receipt['allocation_verified_document_ids'] + returned))
            on_stage('checkout_accepted', deepcopy(receipt))
            if not receipt['all_returned_ids_valid']:
                return self.reconcile(prepared, receipt)
        return self.reconcile(prepared, receipt)

    def reconcile(self, prepared, receipt):
        if self.client.login(prepared['params']['region']) != prepared['preview']['legal_entity']:
            raise Failure('etm_legal_entity_changed')
        documents, problems, total = self._inspect(prepared, receipt, final=True)
        return self._result(prepared, receipt, documents, problems, total)
