"""Exercise fixed Tochka contracts against the provider's public sandbox only.

Requires --execute. No production configuration is loaded, no vault item is read,
no arbitrary URL override exists, and no email/webhook-send operation is exercised.
Sandbox mutations use the real durable prepare/confirm/execute state machine with
an explicitly synthetic local context. This does not test Telegram identity.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from automation_integrations import confirmed_write, extended_api
from automation_integrations.api_read import Failure, Vault

ACCOUNT = '12345810901234567890/044525104'
CUSTOMER = '1234567ab'
SOURCE = 'https://developers.tochka.com/docs/tochka-api/pesochnica'


def shape(value, depth=0):
    if isinstance(value, dict):
        if depth > 1:
            return {'type': 'object', 'keys': sorted(value)[:30]}
        return {key: shape(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return {'type': 'array', 'count': len(value), 'item_shape': shape(value[0], depth + 1) if value else None}
    if value is None:
        return 'null'
    return type(value).__name__


def first(value, key):
    if isinstance(value, dict):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
        for item in value.values():
            candidate = first(item, key)
            if candidate:
                return candidate
    if isinstance(value, list):
        for item in value:
            candidate = first(item, key)
            if candidate:
                return candidate
    return None


def run(ca, output, profile="full"):
    private_root = Path.home() / '.local/share/automation-integrations/tochka-sandbox-audits'
    private_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    state = Path(tempfile.mkdtemp(prefix='audit-', dir=private_root))
    config = {'state_dir': str(state), 'tochka_environment': 'sandbox', 'tochka_ca': str(ca)}
    vault = Vault(config)
    rows, raw = [], {}
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'environment': 'sandbox',
        'base_url': 'https://enter.tochka.com/sandbox/v2', 'source': SOURCE,
        'credential': 'public provider sandbox fixture; no production credentials accessed',
        'confirmation_context': 'synthetic local sandbox identity; not Telegram identity verification',
        'limitations': ['Sandbox responses may be static examples; production permissions and settlement are not established.',
                       'No email or webhook-send endpoints called. No retry of a submitted mutation.',
                       'Unexercised routes remain offline-schema-only.'], 'checks': rows}

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        raw_path = state / 'responses.json'
        fd = os.open(raw_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(raw, handle, ensure_ascii=False, indent=2)

    def check(operation, params=None, write=False):
        params = params or {}
        row = {'operation': operation, 'effect': extended_api.operations('tochka')[operation]['effect'],
               'mode': 'durable_prepare_confirm_execute' if write else 'read'}
        rows.append(row)
        try:
            if write:
                context = {'scope': ['sandbox-audit', 'sandbox-audit', 'local-synthetic', ''],
                           'message_id': 'prepare-' + str(uuid.uuid4())}
                preview = confirmed_write.process({'action': 'prepare', 'service': 'tochka',
                    'operation': operation, 'params': params}, context, config, vault=vault)
                if not preview.get('ok') or preview.get('status') != 'prepared':
                    raise Failure('sandbox_prepare_failed')
                row['preview_environment'] = preview['preview']['environment']
                if row['preview_environment'] != 'sandbox':
                    raise Failure('sandbox_environment_required')
                context['message_id'] = 'confirm-' + str(uuid.uuid4())
                confirmation = confirmed_write.process({'action': 'confirm',
                    'confirmation_text': preview['confirmation_command']}, context, config, vault=vault)
                if confirmation['status'] != 'confirmed':
                    raise Failure('sandbox_confirmation_failed')
                result = confirmed_write.process({'action': 'execute', 'draft_id': preview['draft_id']},
                                                 context, config, vault=vault)
                row.update(status=result['status'], error=result.get('last_error'),
                           http_status=result.get('http_status'), mutation_verified=False)
                data = result.get('result')
            else:
                result = extended_api.execute('tochka', operation, params, config, vault=vault)
                data = result['data']
                row.update(status='ok', error=None, http_status=200)
            raw[operation] = result
            row['response_shape'] = shape(data)
            if isinstance(data, dict) and isinstance(data.get('artifact'), dict):
                artifact = data['artifact']
                artifact_path = Path(artifact['path'])
                if artifact_path.parent != state / 'artifacts':
                    raise Failure('unexpected_artifact_location')
                content = artifact_path.read_bytes()
                if (not content.startswith(b'%PDF-') or len(content) != artifact['bytes']
                        or hashlib.sha256(content).hexdigest() != artifact['sha256']
                        or artifact_path.stat().st_mode & 0o777 != 0o600):
                    raise Failure('artifact_integrity_failed')
                row['artifact_integrity_verified'] = True
                row['artifact_bytes'] = len(content)
            save()
            print(json.dumps({key: row.get(key) for key in ('operation', 'status', 'error', 'http_status')}, ensure_ascii=False), flush=True)
            return data
        except Failure as exc:
            row.update(status='failed', error=exc.code, http_status=exc.status)
            save()
            print(json.dumps(row, ensure_ascii=False), flush=True)
            return None

    initial = [
        ('open_banking_get_accounts_list', {}),
        ('open_banking_get_account_info', {'path': {'accountId': ACCOUNT}}),
        ('open_banking_get_balances_list', {}),
        ('open_banking_get_balance_info', {'path': {'accountId': ACCOUNT}}),
        ('open_banking_get_customers_list', {}),
        ('open_banking_get_customer_info', {'path': {'customerCode': CUSTOMER}}),
        ('open_banking_get_authorized_card_transactions', {'path': {'accountId': ACCOUNT}}),
        ('open_banking_get_statements_list', {'query': {'limit': 5}}),
        ('consent_get_all_consents_list', {'headers': {'customer-code': CUSTOMER}}),
        ('acquiring_get_retailers', {'query': {'customerCode': CUSTOMER}}),
        ('acquiring_get_payment_operation_list', {'query': {'customerCode': CUSTOMER, 'page': 1, 'perPage': 5}}),
        ('acquiring_get_subscription_list', {'query': {'customerCode': CUSTOMER, 'page': 1, 'perPage': 5, 'recurring': False}}),
        ('payment_get_payment_for_sign_list', {'query': {'customerCode': CUSTOMER}}),
        ('sbp_get_payments', {'query': {'customerCode': CUSTOMER, 'page': 1, 'perPage': 5}}),
        ('sbp_get_customer_info', {'path': {'customerCode': CUSTOMER, 'bankCode': '044525104'}}),
    ]
    results = {name: check(name, params) for name, params in initial} if profile == 'full' else {}
    if profile == 'full':
        legal_id = first(results['sbp_get_customer_info'], 'legalId')
        if legal_id:
            check('sbp_get_legal_entity', {'path': {'legalId': legal_id}})
            check('sbp_get_accounts_list', {'path': {'legalId': legal_id}})
            check('sbp_get_merchants_list', {'path': {'legalId': legal_id}})
            check('sbp_get_qr_codes_list', {'path': {'legalId': legal_id}})
        consent_id = first(results['consent_get_all_consents_list'], 'consentId')
        if consent_id:
            check('consent_get_consent_info', {'path': {'consentId': consent_id}, 'headers': {'customer-code': CUSTOMER}})
        statement = check('open_banking_init_statement', {'body': {'Data': {'Statement': {
            'accountId': ACCOUNT, 'startDateTime': '2026-10-01', 'endDateTime': '2026-10-03'}}}}, write=True)
        statement_id = first(statement, 'statementId')
        if statement_id:
            check('open_banking_get_statement', {'path': {'accountId': ACCOUNT, 'statementId': statement_id}})
        payment = check('payment_create_payment_for_sign', {'body': {'Data': {
            'accountCode': ACCOUNT.split('/')[0], 'bankCode': '044525104',
            'counterpartyBankBic': '044525104', 'counterpartyAccountNumber': '40702810840020002504',
            'counterpartyName': 'Проверка официальной песочницы', 'paymentAmount': 100,
            'paymentDate': '2026-10-04', 'paymentPurpose': 'Тест API песочницы. Без НДС'}}}, write=True)
        request_id = first(payment, 'requestId')
        if request_id:
            check('payment_get_payment_status', {'path': {'requestId': request_id}})
        acquiring = check('acquiring_create_payment_operation', {'body': {'Data': {
            'customerCode': CUSTOMER, 'amount': 100, 'purpose': 'Тест API песочницы',
            'paymentMode': ['sbp', 'card']}}}, write=True)
        operation_id = first(acquiring, 'operationId')
        if operation_id:
            check('acquiring_get_payment_operation_info', {'path': {'operationId': operation_id}})
    invoice = check('invoice_create_invoice', {'body': {'Data': {
        'accountId': ACCOUNT, 'customerCode': CUSTOMER,
        'SecondSide': {'taxCode': '660000000000', 'type': 'ip'},
        'Content': {'Invoice': {'Positions': [{'positionName': 'Тест песочницы',
            'unitCode': 'шт.', 'ndsKind': 'without_nds', 'price': 100,
            'quantity': 1, 'totalAmount': 100}], 'totalAmount': 100, 'number': 'sandbox-api-audit'}}
        }}}, write=True)
    document_id = first(invoice, 'documentId')
    if document_id:
        check('invoice_get_invoice', {'path': {'customerCode': CUSTOMER, 'documentId': document_id}})
        check('invoice_get_invoice_payment_status', {'path': {'customerCode': CUSTOMER, 'documentId': document_id}})
    else:
        report['limitations'].append('PDF retrieval was not attempted because invoice creation returned no documentId.')
    report['summary'] = {'attempted': len(rows),
        'read_ok': sum(row['status'] == 'ok' for row in rows),
        'sandbox_write_accepted': sum(row['status'] == 'accepted_unverified' for row in rows),
        'failed_or_unconfirmed': sum(row['status'] not in ('ok', 'accepted_unverified') for row in rows)}
    save()
    print(json.dumps(report['summary']), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('full', 'files'), default='full')
    parser.add_argument('--execute', action='store_true', help='Run public provider sandbox requests')
    parser.add_argument('--ca', type=Path, default=Path.home() / '.local/share/automation-integrations/greif/api-catalog/tochka-root.pem')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'docs/TOCHKA_SANDBOX_AUDIT.json')
    args = parser.parse_args()
    if not args.execute:
        parser.exit(message='No requests sent. Use --execute for the fixed public sandbox audit.\n')
    run(args.ca, args.output, args.profile)
