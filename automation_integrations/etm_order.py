"""ETM portal checkout. Public API reads remain in api_read.

Portal contracts were recovered from the live ETM frontend (2026-10-04).
This module never pays, clears a basket, generates document numbers, or retries
mutations. Its caller owns authorization, account-wide serialization and durable
stage recording. prepare is read-only; execute requires that recorded approval.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import urllib.parse
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

try:
    from .api_read import Failure, Vault
except ImportError:
    from api_read import Failure, Vault

SOURCE = 'https://www.etm.ru/ipro3/cart'
BASE = 'https://www.etm.ru/api/ipro'
PROXY = 'socks5h://127.0.0.1:10929'


def _decimal(value, *, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise Failure('invalid_etm_number')
    try:
        result = Decimal(str(value).replace(',', '.'))
    except InvalidOperation:
        raise Failure('invalid_etm_number') from None
    if not result.is_finite() or result < 0 or (not allow_zero and result == 0) or result > 10**10:
        raise Failure('invalid_etm_number')
    return result


def _number(value):
    return format(_decimal(value), 'f')


def _money(value):
    return format(_decimal(value, allow_zero=True).quantize(Decimal('.01'), rounding=ROUND_HALF_UP), 'f')


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,20}', value):
        raise Failure('invalid_etm_identifier')
    return value


def _row_selected(row):
    """Parse an explicit provider selection flag; absence is not deselection."""
    value = row.get('selected')
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value in ('0', '1', 'false', 'true'):
        return value in ('1', 'true')
    raise Failure('etm_basket_selection_unverified')


def validate_params(params):
    """Offline canonicalization, before fetching credentials or making requests."""
    allowed = {'items', 'region', 'pickup_store', 'contract_id', 'payment_method', 'pay_type',
               'max_total', 'note', 'continuous_cut', 'allow_supplier_order', 'currency'}
    if not isinstance(params, dict) or set(params) - allowed:
        raise Failure('invalid_etm_checkout_parameters')
    rows = params.get('items')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise Failure('invalid_etm_checkout_items')
    normalized, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'code', 'quantity'}:
            raise Failure('invalid_etm_checkout_item')
        code = _identifier(row['code'])
        if code in seen:
            raise Failure('duplicate_etm_checkout_item')
        seen.add(code)
        normalized.append({'code': code, 'quantity': _number(row['quantity'])})
    result = {'items': normalized, 'region': _identifier(params.get('region')),
              'pickup_store': _identifier(params.get('pickup_store')),
              'payment_method': params.get('payment_method', 'bill'),
              'pay_type': params.get('pay_type', 'bill'), 'currency': params.get('currency', 'RUB'),
              'note': params.get('note', ''), 'continuous_cut': params.get('continuous_cut', False),
              'allow_supplier_order': params.get('allow_supplier_order', False)}
    # These create an invoice/request. Online payment/card capture is a separate operation.
    if (result['payment_method'], result['pay_type']) not in (('bill', 'bill'), ('agree_m', 'agree_m')):
        raise Failure('unsupported_etm_checkout_payment')
    if result['currency'] != 'RUB':
        raise Failure('unsupported_etm_currency')
    if (not isinstance(result['note'], str) or len(result['note']) > 2000
            or any(ord(c) < 32 and c not in '\n\t' for c in result['note'])):
        raise Failure('invalid_etm_note')
    for flag in ('continuous_cut', 'allow_supplier_order'):
        if type(result[flag]) is not bool:
            raise Failure('invalid_etm_checkout_flag')
    if 'contract_id' in params:
        result['contract_id'] = _identifier(params['contract_id'])
    if 'max_total' in params:
        result['max_total'] = _money(_decimal(params['max_total']))
    return result


def validate_options(params):
    if not isinstance(params, dict) or set(params) - {'region', 'pickup_store'}:
        raise Failure('invalid_etm_checkout_options')
    result = {'region': _identifier(params.get('region'))}
    if 'pickup_store' in params:
        result['pickup_store'] = _identifier(params['pickup_store'])
    return result


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def _note_matches(expected, comments):
    def normalized(value):
        return ' ' + ' '.join(re.findall(r'\w+', value.casefold(), re.UNICODE)) + ' '
    wanted = normalized(expected)
    def values(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for child in value:
                yield from values(child)
        elif isinstance(value, dict):
            for child in value.values():
                yield from values(child)
    return any(wanted in normalized(value) for value in values(comments))


def _multipart(form):
    boundary = 'etm_' + uuid.uuid4().hex
    parts = []
    for key, value in form.items():
        if not re.fullmatch(r'[A-Za-z0-9_-]+', key):
            raise Failure('invalid_etm_form_field')
        parts.extend(['--' + boundary,
                      'Content-Disposition: form-data; name="' + key + '"', '', str(value)])
    return '\r\n'.join(parts + ['--' + boundary + '--', '']), boundary


class WebsiteClient:
    """Secrets/session only in memory; fixed ETM origin and proxy; no retries."""
    def __init__(self, config, *, vault=None, transport=None):
        if config.get('etm_environment', 'production') != 'production':
            raise Failure('unsupported_provider_environment')
        self.config = config
        self.vault = vault or Vault(config)
        self.transport = transport or self._transport
        self.session = None
        self.region = None
        self.identity = {}

    def __repr__(self):
        return f'WebsiteClient(authenticated={bool(self.session)})'

    def _transport(self, method, path, *, headers=None, query=None, form=None):
        if self.config.get('etm_proxy') != PROXY:
            raise Failure('etm_proxy_unconfigured')
        if not path.startswith('/') or '?' in path or '#' in path or '..' in path:
            raise Failure('invalid_etm_portal_path')
        url = BASE + path
        if query:
            url += '?' + urllib.parse.urlencode(query)
        headers = {'Accept': 'application/json', **(headers or {})}
        lines = ['url = ' + json.dumps(url, ensure_ascii=False), 'request = ' + json.dumps(method)]
        if form is not None:
            body, boundary = _multipart(form)
            headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
            lines.append('data-binary = ' + json.dumps(body, ensure_ascii=False))
        lines += ['header = ' + json.dumps(k + ': ' + v, ensure_ascii=False) for k, v in headers.items()]
        try:
            response = subprocess.run(['/usr/bin/curl', '-q', '--silent', '--proxy', PROXY,
                '--noproxy', '', '--proto', '=https', '--max-time', '40', '--max-filesize',
                str(4 * 1024 * 1024), '--write-out', '\n%{http_code}', '--config', '-'],
                input='\n'.join(lines).encode(), capture_output=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired):
            raise Failure('etm_portal_transport_unknown') from None
        if response.returncode:
            raise Failure('etm_portal_transport_unknown')
        body, separator, status = response.stdout.rpartition(b'\n')
        if not separator or not status.isdigit():
            raise Failure('etm_portal_transport_unknown')
        if not 200 <= int(status) < 300:
            raise Failure('etm_portal_http_error', int(status))
        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise Failure('etm_portal_invalid_response') from None

    def call(self, method, path, *, query=None, form=None):
        headers = {}
        if self.session:
            headers['session-id'] = self.session
        if self.region:
            headers['Cookie'] = 'city=' + self.region
        payload = self.transport(method, path, headers=headers, query=query, form=form)
        if not isinstance(payload, dict) or not isinstance(payload.get('status'), dict):
            raise Failure('etm_portal_invalid_response')
        code = payload['status'].get('code')
        if str(code) != '200':
            raise Failure('etm_portal_rejected', provider_code=str(code))
        data = payload.get('data')
        if not isinstance(data, dict):
            raise Failure('etm_portal_invalid_response')
        return data

    def login(self, region):
        region = _identifier(region)
        if self.session:
            if region != self.region:
                raise Failure('etm_portal_region_changed')
            if not self.identity.get('clicode') or not self.identity.get('inn_org'):
                raise Failure('etm_legal_entity_unverified')
            return self.identity
        self.region = region
        secrets = self.vault.get('etm')
        data = self.call('POST', '/user/login', form={'log': secrets['ETM_LOGIN'],
            'pwd': secrets['ETM_PASSWORD'], 'city': region, 'user-id': str(uuid.uuid4())})
        session = data.get('session')
        if not isinstance(session, str) or not session:
            raise Failure('etm_portal_login_failed')
        self.session = session
        self.vault.sensitive.append(session)
        self.identity = {k: str(data.get(k) or '') for k in ('clicode', 'cliName', 'inn_org', 'kpp_org')}
        # The API login can omit the legal-party INN/KPP. Verify against a real
        # account document, as the established ETM workflow does; never invent it.
        if self.identity['clicode'] and not self.identity['inn_org']:
            listing = self.call('GET', '/invoice', query={'rows': 1, 'page': 1})
            rows = [r for r in listing.get('rows', [])
                    if str(r.get('cli_code')) == self.identity['clicode']]
            if rows:
                ident = str(rows[0].get('id', ''))
                if re.fullmatch(r'[0-9]+-[0-9]+', ident):
                    body = self.call('GET', '/invoice/' + ident + '/body', query={'detail': 'buyer'})
                    if body.get('invnetnum') == ident and str(body.get('cli_code')) == self.identity['clicode']:
                        buyer = body.get('buyer', {})
                        self.identity.update(inn_org=str(buyer.get('inn') or ''),
                                             kpp_org=str(buyer.get('kpp') or ''))
        if not self.identity['clicode'] or not self.identity['inn_org']:
            raise Failure('etm_legal_entity_unverified')
        return self.identity


class Checkout:
    def __init__(self, client, *, sleeper=time.sleep):
        self.client = client
        self.sleeper = sleeper

    def options(self, params):
        """Safe discovery; no basket rows, session, or documents cross this boundary."""
        params = validate_options(params)
        entity = self.client.login(params['region'])
        features = self.client.call('GET', '/basket/functionality')
        query = {'rows': 1, 'group': 1, 'page': 1}
        if params.get('pickup_store'):
            query['skl'] = params['pickup_store']
        basket = self.client.call('GET', '/basket/order', query=query)
        stores = [{k: s.get(k) for k in ('code', 'name', 'address', 'time', 'selected',
                  'pickupAvailable')} for s in basket.get('stores', [])]
        chosen = params.get('pickup_store') or next((str(s['code']) for s in stores
            if str(s.get('selected')) in ('1', 'true', 'True')), None)
        contract = features.get('contract', {})
        payment_rows = []
        if chosen:
            payment = self.client.call('GET', '/payment/methods', query={
                'region': params['region'], 'store': chosen, 'to_pay': '0.00',
                'i_dogovor': contract.get('defaultValue', '')})
            payment_rows = [{k: p.get(k) for k in ('payment_method_code', 'payment_method_name',
                'payment_method_status', 'payment_method_text', 'paytype')}
                for row in payment.get('rows', []) for p in row.get('pay_meth', [])]
        return {'region': params['region'], 'pickup_stores': stores,
            'default_contract_id': contract.get('defaultValue'),
            'contracts': [{'id': str(c.get('code')), 'name': c.get('name')}
                          for c in contract.get('value', [])],
            'payment_methods': payment_rows, 'legal_entity': entity,
            'source': SOURCE, 'portal_internal_api': True,
            'instruction': 'Choose the office by its returned address. These are checkout-offered '
                'offices, not an exhaustive city directory. Payment availability is rechecked '
                'for the exact total during prepare and execute.'}

    def _basket(self, params, contract_id=None):
        # group=1 matches the live frontend; fetch every page before deciding emptiness.
        query = {'rows': 100, 'group': 1, 'skl': params['pickup_store'], 'page': 1}
        if contract_id:
            query['i_dogovor'] = contract_id
        first = self.client.call('GET', '/basket/order', query=query)
        if not isinstance(first.get('rows'), list) or 'records' not in first:
            raise Failure('etm_basket_schema_changed')
        rows = list(first['rows'])
        if any(not isinstance(row, dict) for row in rows):
            raise Failure('etm_basket_schema_changed')
        count = first['records']
        if isinstance(count, bool):
            raise Failure('etm_basket_schema_changed')
        try:
            count = int(count)
        except (TypeError, ValueError):
            raise Failure('etm_basket_schema_changed') from None
        if count < len(rows) or count > 5000:
            raise Failure('etm_basket_pagination_incomplete')
        while len(rows) < count:
            query['page'] += 1
            page = self.client.call('GET', '/basket/order', query=query)
            batch = page.get('rows', [])
            if not batch or page.get('records', count) != count or query['page'] > 500:
                raise Failure('etm_basket_pagination_incomplete')
            if page.get('cartVersion') != first.get('cartVersion'):
                raise Failure('etm_basket_changed_during_read')
            rows.extend(batch)
        if len(rows) != count or len({str(r.get('nn')) for r in rows}) != len(rows):
            raise Failure('etm_basket_pagination_incomplete')
        # Legacy group-only emptiness must be checked, never silently treated as empty.
        for key in ('can-reserve', 'not-reserve', 'can-reserve-long'):
            if first.get(key, {}).get('rows') and not rows:
                raise Failure('etm_basket_schema_changed')
        if first.get('edit_mode') or first.get('edit_doc'):
            raise Failure('etm_basket_in_document_edit_mode')
        first['rows'] = rows
        return first

    @staticmethod
    def _contents(rows):
        result = {}
        for row in rows:
            code = str(row.get('gdscode', ''))
            _identifier(code)
            qty = _decimal(row.get('cnt'))
            result[code] = result.get(code, Decimal(0)) + qty
        return result

    @staticmethod
    def _expected(params):
        return {r['code']: _decimal(r['quantity']) for r in params['items']}

    @staticmethod
    def _basket_signature(basket):
        return _fingerprint([{k: r.get(k) for k in ('nn', 'gdscode', 'cnt', 'selected', 'row_id')}
                             for r in basket['rows']])

    @staticmethod
    def _store(basket, store_id):
        stores = [s for s in basket.get('stores', []) if str(s.get('code')) == store_id]
        if len(stores) != 1 or str(stores[0].get('selected')) not in ('1', 'True', 'true'):
            raise Failure('etm_pickup_store_not_selected')
        store = stores[0]
        if store.get('pickupAvailable', {}).get('availability') is not True:
            raise Failure('etm_pickup_unavailable')
        if not store.get('address'):
            raise Failure('etm_pickup_address_unverified')
        return {k: store.get(k) for k in ('code', 'name', 'address', 'time')}

    def _features(self, params):
        features = self.client.call('GET', '/basket/functionality')
        contract = features.get('contract', {})
        if not contract.get('available') or contract.get('sendKey') != 'i_dogovor':
            raise Failure('etm_contract_unavailable')
        code = params.get('contract_id') or contract.get('defaultValue')
        matches = [r for r in contract.get('value', []) if str(r.get('code')) == str(code)]
        if len(matches) != 1 or not matches[0].get('name'):
            raise Failure('etm_contract_unavailable')
        fields = {'i_dogovor': str(code)}
        for key, feature in features.items():
            if not isinstance(feature, dict) or not feature.get('available') or key == 'contract':
                continue
            # Any newly required feature needs an explicit supported mapping, not a guess.
            if feature.get('required') and key != 'ps':
                raise Failure('etm_additional_checkout_field_required')
        if params['note']:
            if not features.get('ps', {}).get('available') or features['ps'].get('sendKey') != 'tovzak':
                raise Failure('etm_order_note_unavailable')
            fields['tovzak'] = params['note']
        if features.get('for_own_use', {}).get('available'):
            # This is a business choice, so expose a blocker instead of inferring it.
            raise Failure('etm_marked_goods_purpose_required')
        return {'id': str(code), 'name': matches[0]['name']}, fields

    def _payment(self, params, total, contract_id):
        data = self.client.call('GET', '/payment/methods', query={'region': params['region'],
            'store': params['pickup_store'], 'to_pay': _money(total), 'i_dogovor': contract_id})
        methods = [m for row in data.get('rows', []) for m in row.get('pay_meth', [])]
        chosen = [m for m in methods if m.get('payment_method_code') == params['payment_method']
                  and m.get('paytype') == params['pay_type'] and m.get('payment_method_status') is True]
        if len(chosen) != 1:
            raise Failure('etm_requested_payment_unavailable')
        return {k: chosen[0].get(k) for k in ('payment_method_code', 'paytype',
                                            'payment_method_name', 'payment_method_text')}

    def prepare(self, params):
        params = validate_params(params)
        identity = self.client.login(params['region'])
        contract, fields = self._features(params)
        params['contract_id'] = contract['id']
        basket = self._basket(params, contract['id'])
        contents = self._contents(basket['rows'])
        if contents and contents != self._expected(params):
            raise Failure('etm_basket_contains_other_items')
        store = self._store(basket, params['pickup_store'])
        items, estimate, blockers = [], Decimal(0), []
        for row in params['items']:
            query = {'type': 'etm', 'city': params['region'], 'skl': params['pickup_store']}
            card = self.client.call('GET', '/goods/' + row['code'], query=query)
            self.sleeper(1)
            prices = self.client.call('GET', '/goods/' + row['code'] + '/price', query=query)
            matches = [x for x in prices.get('rows', []) if str(x.get('gdscode')) == row['code']]
            if str(card.get('gdsCode')) != row['code'] or len(matches) != 1:
                raise Failure('etm_product_verification_failed')
            price = _decimal(matches[0].get('pricewnds'))
            packs = self.client.call('GET', '/goods/' + row['code'] + '/packs',
                                     query={'city': params['region'], 'skl': params['pickup_store']})
            amount = price * _decimal(row['quantity'])
            estimate += amount
            items.append({**row, 'name': card.get('gdsNameTitle'), 'unit': card.get('gdsUnitName'),
                'pack': card.get('gdsInfoPacks'), 'unit_price_vat': _money(price),
                'line_estimate_vat': _money(amount), 'availability_as_returned': card.get('gdsCommonAvail'),
                'pickup_date_as_returned': card.get('gdsPickup'), 'availability_is_allocation': False,
                'packaging_rules_as_returned': packs.get('packRestrictShipRate', {}),
                'packaging_warning': 'Supplier minimum applies to supplier sourcing; factory pack size '
                    'does not establish the supplier minimum or warehouse availability.'})
        if contents:
            estimate = _decimal(basket.get('sum'))
            # ETM adds rows unselected. Selecting these exact requested rows is
            # part of execution, so read-only preparation must allow that state.
            self._check_orderable(basket, params, require_selected=False)
        total = _money(estimate)
        maximum = params.get('max_total', total)
        if _decimal(maximum) < estimate:
            raise Failure('etm_quote_exceeds_max_total')
        params['max_total'] = maximum
        payment = self._payment(params, estimate, contract['id'])
        preview = {'items': items, 'estimated_total_vat': total, 'maximum_total_vat': maximum,
            'currency': 'RUB', 'pickup': store, 'contract': contract, 'payment': payment,
            'legal_entity': identity, 'note': params['note'], 'continuous_cut': params['continuous_cut'],
            'allow_supplier_order': params['allow_supplier_order'],
            'availability': 'Final allocation and delivery dates are checked after the authorized basket add.',
            'order_route': 'ETM website checkout with native ETM document numbers',
            'ordering_blockers': blockers, 'can_submit': not blockers,
            'production_write_verification': 'not_executed_by_deployment'}
        if params['continuous_cut']:
            preview['continuous_cut_verification'] = {
                'requested': True,
                'single_allocation_verified': bool(contents),
                'physical_cut_verified': False,
                'instruction': 'The supplier receives the one-continuous-cut requirement in the order note. '
                               'One stock allocation does not confirm physical cut continuity.'}
        return {'params': params, 'preview': preview, 'checkout_fields': fields,
                'basket_fingerprint': self._basket_signature(basket),
                'basket_was_empty': not contents}

    def _check_orderable(self, basket, params, *, require_selected=True):
        self._store(basket, params['pickup_store'])
        if basket.get('zapretgo') or basket.get('zapret_invoice') or basket.get('cpr', {}).get('zapretgo'):
            raise Failure('etm_checkout_restricted')
        if self._contents(basket['rows']) != self._expected(params):
            raise Failure('etm_basket_quantity_mismatch')
        selected = [_row_selected(row) for row in basket['rows']]
        if require_selected and not all(selected):
            raise Failure('etm_basket_selection_mismatch')
        for row in basket['rows']:
            parts = row.get('delivery_parts', [])
            if not parts or sum((_decimal(p.get('cnt')) for p in parts), Decimal(0)) != _decimal(row['cnt']):
                raise Failure('etm_allocation_unverified')
            if params['continuous_cut'] and len(parts) != 1:
                raise Failure('etm_continuous_cut_unavailable')
            def physical(part):
                try:
                    return _decimal(part.get('g-net')) > 0 and _decimal(part.get('g-num')) > 0
                except Failure:
                    return False
            if not params['allow_supplier_order'] and not all(physical(p) for p in parts):
                raise Failure('etm_supplier_order_not_authorized')
            # The portal uses PartNum as optional display text, not as a stock
            # identity or proof of a continuous cut. Require one physical source;
            # submit the cut requirement as a note and keep fulfillment unverified.
            if params['continuous_cut'] and not all(physical(p) for p in parts):
                raise Failure('etm_continuous_cut_unverified')
        if params['continuous_cut'] and len(basket['rows']) != len(params['items']):
            raise Failure('etm_continuous_cut_unavailable')
        if params.get('max_total') and _decimal(basket.get('sum')) > _decimal(params['max_total']):
            raise Failure('etm_checkout_exceeds_approved_total')

    def _select_basket(self, basket, params, contract_id, *, on_stage):
        """Select only verified requested rows using the ETM frontend contract."""
        self._check_orderable(basket, params, require_selected=False)
        lines = []
        for row in basket['rows']:
            if not _row_selected(row):
                line = str(row.get('nn', ''))
                if not re.fullmatch(r'[1-9][0-9]{0,19}', line):
                    raise Failure('etm_basket_selection_unverified')
                lines.append((line, str(row['gdscode'])))
        # frontend-module-55451 (Am/j -> N) sends selected=true to this row route.
        # No select-all request: a concurrently added unrelated line must never
        # become part of the user's order. Durable stages precede every mutation.
        for line, code in lines:
            on_stage('basket_select_submitting', {'line': line, 'code': code})
            self.client.call('POST', '/basket/' + line + '/edit', form={'selected': 'true'})
            on_stage('basket_select_accepted', {'line': line, 'code': code})
        if lines:
            basket = self._basket(params, contract_id)
        self._check_orderable(basket, params)
        return basket

    @staticmethod
    def _allocation_signature(basket):
        return _fingerprint({'rows': [{k: row.get(k) for k in ('nn', 'gdscode', 'cnt', 'selected',
            'sum', 'delivery_parts')} for row in basket['rows']], 'sum': basket.get('sum'),
            'contract': basket.get('i_dogovor'), 'stores': [{k: s.get(k) for k in ('code', 'selected',
            'pickupAvailable')} for s in basket.get('stores', [])]})

    @staticmethod
    def _receipt(data):
        rows = data.get('createdDoc', [])
        list_valid = isinstance(rows, list)
        rows = rows if list_valid else []
        ids = []
        for row in rows if isinstance(rows, list) else []:
            ident = row.get('invnum') if isinstance(row, dict) else None
            if isinstance(ident, (int, str)) and re.fullmatch(r'[0-9]+-[0-9]+', str(ident)):
                ids.append(str(ident))
        return {'document_ids': list(dict.fromkeys(ids)), 'i_dogovor': data.get('i_dogovor'),
                'pay_sum': data.get('pay_sum'), 'invUsrInvNum': data.get('invUsrInvNum'),
                'all_returned_ids_valid': list_valid and bool(rows) and len(set(ids)) == len(rows)}

    def execute(self, prepared, *, on_stage):
        """Caller must durably authorize this exact prepared object and serialize account."""
        params = validate_params(prepared['params'])
        if prepared['preview'].get('can_submit') is False:
            raise Failure('etm_checkout_has_ordering_blockers')
        if self.client.login(params['region']) != prepared['preview']['legal_entity']:
            raise Failure('etm_legal_entity_changed')
        contract, fields = self._features(params)
        if contract != prepared['preview']['contract'] or fields != prepared['checkout_fields']:
            raise Failure('etm_checkout_terms_changed')
        basket = self._basket(params, contract['id'])
        if self._basket_signature(basket) != prepared['basket_fingerprint']:
            raise Failure('etm_basket_changed_since_prepare')
        if prepared['basket_was_empty']:
            for row in params['items']:
                on_stage('basket_add_submitting', {'code': row['code'], 'quantity': row['quantity']})
                self.client.call('POST', '/basket/add', form={'gds': row['code'],
                    'val': row['quantity'], 'city': params['region']})
                on_stage('basket_add_accepted', {'code': row['code']})
            basket = self._basket(params, contract['id'])
        basket = self._select_basket(basket, params, contract['id'], on_stage=on_stage)
        if self._store(basket, params['pickup_store']) != prepared['preview']['pickup']:
            raise Failure('etm_pickup_changed_since_prepare')
        payment = self._payment(params, basket['sum'], contract['id'])
        if payment != prepared['preview']['payment']:
            raise Failure('etm_payment_changed_since_prepare')
        # Re-read allocation directly before the irreversible checkout.
        final = self._basket(params, contract['id'])
        self._check_orderable(final, params)
        if self._allocation_signature(final) != self._allocation_signature(basket):
            raise Failure('etm_allocation_changed_before_submit')
        # Supplier minimum is conditional. Enforce it only once the selected
        # checkout allocation actually routes a line to supplier/future supply.
        packaging = {r['code']: r.get('packaging_rules_as_returned', {})
                     for r in prepared['preview']['items']}
        for row in final['rows']:
            unallocated = False
            for part in row.get('delivery_parts', []):
                try:
                    _decimal(part.get('g-net'))
                    _decimal(part.get('g-num'))
                except Failure:
                    unallocated = True
            minimum = packaging.get(str(row['gdscode']), {}).get('packMinPartSuppl')
            if unallocated and minimum not in (None, ''):
                if _decimal(row['cnt']) < _decimal(minimum, allow_zero=True):
                    raise Failure('etm_supplier_minimum_not_met')
        form = {**fields, 'skl': params['pickup_store'], 'payment_method_code': params['payment_method'],
                'pay-type': params['pay_type'], 'application': 'ipro3'}
        if params['continuous_cut']:
            units = {item['code']: item.get('unit') or '' for item in prepared['preview']['items']}
            allocation_notes = ['Код ' + str(r['gdscode']) + ': требуется один непрерывный отрезок ' +
                str(r['cnt']) + ' ' + units.get(str(r['gdscode']), '') +
                '; не делить на несколько отрезков.' for r in final['rows']]
            form['tovzak'] = '\n'.join([form.get('tovzak', '')] + allocation_notes).strip()
        on_stage('checkout_submitting', {'total_vat': _money(final['sum']), 'currency': 'RUB'})
        data = self.client.call('POST', '/basket/order', form=form)
        receipt = self._receipt(data)
        receipt['expected_total_vat'] = _money(final['sum'])
        receipt['note'] = form.get('tovzak', '')
        on_stage('checkout_accepted', receipt)
        if receipt['note']:
            for ident in receipt['document_ids']:
                on_stage('document_note_submitting', {'document_id': ident})
                self.client.call('POST', '/invoice/' + ident + '/ps',
                                 form={'text': receipt['note'], 'service_message': 'false'})
                on_stage('document_note_accepted', {'document_id': ident})
        return self.reconcile(prepared, receipt)

    def reconcile(self, prepared, receipt):
        """Read every returned final document; never re-submit an uncertain checkout."""
        params = validate_params(prepared['params'])
        if self.client.login(params['region']) != prepared['preview']['legal_entity']:
            raise Failure('etm_legal_entity_changed')
        problems, documents, actual = [], [], {}
        if not receipt.get('all_returned_ids_valid'):
            problems.append('final_document_ids_incomplete')
        if str(receipt.get('i_dogovor') or '') != params['contract_id']:
            problems.append('contract_not_bound')
        total = Decimal(0)
        for ident in receipt.get('document_ids', []):
            if not isinstance(ident, str) or not re.fullmatch(r'[0-9]+-[0-9]+', ident):
                raise Failure('invalid_etm_document_id')
            body = self.client.call('GET', '/invoice/' + ident + '/body',
                                    query={'detail': 'buyer,seller,delivery,price'})
            number = body.get('invnum')
            listing = self.client.call('GET', '/invoice', query={'usr-inv-num': number,
                'rows': 100, 'page': 1})
            matches = [r for r in listing.get('rows', []) if str(r.get('id')) == ident]
            listing_row = matches[0] if len(matches) == 1 else {}
            doc_problems = []
            if body.get('invnetnum') != ident or len(matches) != 1:
                doc_problems.append('document_id_not_verified')
            expected_entity = prepared['preview']['legal_entity']
            if (str(body.get('cli_code')) != expected_entity['clicode']
                    or str(body.get('buyer', {}).get('inn')) != expected_entity['inn_org']
                    or str(body.get('buyer', {}).get('kpp')) != expected_entity['kpp_org']):
                doc_problems.append('legal_entity_mismatch')
            # st_code/body.store describe the current/source warehouse. st_dest is
            # the receiving warehouse and is required to verify a transfer's destination.
            if str(listing_row.get('st_dest')) != params['pickup_store']:
                doc_problems.append('pickup_store_mismatch')
            pay_title = listing_row.get('pay_title', '')
            if (prepared['preview']['contract']['name'] not in pay_title
                    or not listing_row.get('pay_date')):
                doc_problems.append('contract_payment_terms_unverified')
            status = str(listing_row.get('status_code') or '')
            if status in ('01', '1', '10', '101') or body.get('invStatus') in ('Спецификация', 'Расторгнутый счет'):
                doc_problems.append('document_not_accepted_order')
            elif status not in ('05', '5', '15', '151', '152', '153', '20', '24', '25', '26',
                                 '27', '40', '45', '451', '452', '455'):
                doc_problems.append('document_status_unverified')
            quantities = self._contents(body.get('rows', []))
            if body.get('records') != len(body.get('rows', [])):
                doc_problems.append('document_rows_incomplete')
            for code, quantity in quantities.items():
                actual[code] = actual.get(code, Decimal(0)) + quantity
            amount = _decimal(body.get('invsum'), allow_zero=True)
            total += amount
            if receipt.get('note'):
                comments = self.client.call('GET', '/invoice/' + ident + '/ps').get('comments', [])
                if not _note_matches(receipt['note'], comments):
                    doc_problems.append('order_note_unverified')
            document = {'id': ident, 'number': number, 'status': body.get('invStatus'),
                'status_code': status, 'total_vat': _money(amount), 'currency': 'RUB',
                'pickup_store': listing_row.get('st_dest'), 'current_store': body.get('store'),
                'payment_title': pay_title,
                'payment_date': listing_row.get('pay_date'), 'items': [
                    {'code': r.get('gdscode'), 'quantity': r.get('cnt'), 'name': r.get('gdsname'),
                     'shipping_date_as_returned': r.get('dateotgr')} for r in body.get('rows', [])],
                'verification_problems': doc_problems}
            documents.append(document)
            problems.extend(ident + ':' + p for p in doc_problems)
        if actual != self._expected(params):
            problems.append('final_quantities_mismatch')
        if total > _decimal(params['max_total']):
            problems.append('final_total_exceeds_approved_maximum')
        if receipt.get('expected_total_vat') and total != _decimal(receipt['expected_total_vat']):
            problems.append('final_total_differs_from_checkout')
        result = {'status': 'accepted_unverified' if problems else 'verified',
                'mutation_verified': not problems, 'documents': documents, 'total_vat': _money(total),
                'currency': 'RUB', 'verification_problems': problems,
                'expected_items': params['items'], 'pickup': prepared['preview']['pickup'],
                'receipt': receipt, 'ready_for_pickup': False,
                'instruction': 'Report each document status and calculated shipping date; acceptance is not pickup readiness.'}
        if params['continuous_cut']:
            result['continuous_cut_verification'] = {
                'requested': True,
                'physical_cut_verified': False,
                'instruction': 'The order requests one continuous cut; actual physical fulfillment is not yet verified.'}
        return result

    def reconcile_basket(self, prepared):
        """Only for a caller-recorded uncertain add BEFORE any checkout was attempted."""
        params = validate_params(prepared['params'])
        if self.client.login(params['region']) != prepared['preview']['legal_entity']:
            raise Failure('etm_legal_entity_changed')
        basket = self._basket(params, params['contract_id'])
        contents = self._contents(basket['rows'])
        matches = contents == self._expected(params)
        return {'status': 'blocked' if matches else 'outcome_unknown',
                'order_submitted': False, 'basket_changed': True,
                'reason': 'etm_basket_add_reconciled' if matches else 'etm_basket_add_unresolved',
                'items': [{'code': code, 'quantity': _number(quantity)} for code, quantity in contents.items()],
                'matches_expected': matches,
                'instruction': 'Reconcile the current basket. No item was added or removed by this check.'}
