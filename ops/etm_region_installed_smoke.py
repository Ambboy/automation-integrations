# Public example: configure deployment paths before explicit live diagnostics.
"""Exercise installed ETM discovery and prepare only; never confirm or execute an order.

--execute permits live diagnostic reads and reversible region selection. No order,
reservation, basket edit, payment, supplier message or Telegram message is requested.
"""
import argparse
from copy import deepcopy
import datetime as dt
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

import hermes_bootstrap
import hermes_yaml as yaml


LIVE = Path('/home/operator/.hermes')
ROOT = Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')


def error_code(result):
    value = result.get('error')
    return value if isinstance(value, str) and re.fullmatch(r'[a-z0-9_]{1,120}', value) else None


def fields(value, names):
    return {name: value.get(name) for name in names} if isinstance(value, dict) else {}


def options_summary(result, store):
    data = result.get('data') or {}
    return {'ok': result.get('ok') is True, 'error': error_code(result),
            **fields(data, ('region', 'region_verified', 'order_route', 'portal_pickup_offered',
                            'public_api_ordering_enabled', 'default_contract_id')),
            'requested_pickup': fields(data.get('requested_pickup'), ('id', 'address', 'available_pick')),
            'portal_has_requested_store': any(str(row.get('code')) == store
                for row in data.get('pickup_stores', []) if isinstance(row, dict))}


def installed_lock():
    spec = importlib.util.spec_from_file_location(
        '_etm_installed_procurement', ROOT / 'release/etm_authorization.py')
    if spec is None or spec.loader is None:
        raise ValueError('Installed procurement lock is unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.procurement_lock


def run(report, items):
    entry = deepcopy(yaml.safe_load((LIVE / 'config.yaml').read_text())
                     ['plugins']['entries']['automation-api-catalog'])
    settings = entry['settings']
    production_private = json.loads(Path(settings['private_config']).read_text())
    owner, chat = str(settings.get('owner_id', '')), str(settings.get('chat_id', ''))
    if not owner or owner != chat:
        raise ValueError('Expected configured owner private-chat route')
    if Path(settings['runner_path']).resolve() != ROOT / 'release/api_read.py':
        raise ValueError('Unexpected installed read runner')
    if Path(settings.get('write_runner_path', ROOT / 'release/api_write.py')).resolve() != ROOT / 'release/api_write.py':
        raise ValueError('Unexpected installed write runner')

    with tempfile.TemporaryDirectory(prefix='etm-region-installed-readonly-') as tmp:
        home = Path(tmp)
        private = deepcopy(production_private)
        private['state_dir'] = str(home / 'state')
        private_path = home / 'private.json'
        private_path.write_text(json.dumps(private))
        settings['private_config'] = str(private_path)
        settings['state_dir'] = str(home / 'state')
        shutil.copytree(LIVE / 'plugins/automation-api-catalog', home / 'plugins/automation-api-catalog')
        (home / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': ['automation-api-catalog'],
            'entries': {'automation-api-catalog': entry}}}))
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import get_plugin_manager
        from tools.registry import registry
        from gateway.session_context import set_session_vars, clear_session_vars

        override = set_hermes_home_override(home)
        manager = get_plugin_manager()
        try:
            manager.discover_and_load()
            tokens = set_session_vars(chat_type='dm', session_key='etm-region-installed-smoke',
                message_id='etm-region-readonly-1', platform='telegram', chat_id=chat,
                user_id=owner, session_id='etm-region-installed-readonly')
            try:
                # Temporary drafts must not bypass serialization of this account's
                # live session preferences. Child runners lock their separate temp
                # state; this outer lock serializes the entire diagnostic with production.
                with installed_lock()(production_private):
                    report['production_procurement_lock_held'] = True
                    context = manager.invoke_hook('pre_llm_call', platform='telegram', sender_id=owner,
                        session_id='etm-region-installed-readonly', turn_id='1',
                        user_message='Диагностика ЭТМ: проверить Ростов и Батайск, только варианты и подготовка; '
                                     'не подтверждать, не оформлять заказ и ничего не оплачивать.',
                        conversation_history=[])

                    def call(name, request):
                        if not (name == 'integration_catalog'
                                or name == 'integration_read' and request.get('operation') == 'checkout_options'
                                or name == 'integration_write' and request.get('action') == 'prepare'
                                   and request.get('operation') == 'order_checkout'):
                            raise ValueError('Diagnostic operation is not allowlisted')
                        return json.loads(registry.dispatch(name, request, scope=str(home)))

                    catalog = call('integration_catalog', {'service': 'etm'})
                    services = [item for item in catalog.get('services', []) if item.get('id') == 'etm']
                    service = services[0] if len(services) == 1 else {}
                    write_ops = service.get('write_operations', {})
                    report['checkout_discovered'] = 'order_checkout' in write_ops
                    report['customer_reference_discovered'] = 'customer_order_number' in (
                        write_ops.get('order_checkout', {}).get('params', {}))
                    rostov = call('integration_read', {'service': 'etm', 'operation': 'checkout_options',
                        'params': {'region': '61', 'pickup_store': '25140'}})
                    report['rostov_options'] = options_summary(rostov, '25140')
                    data = rostov.get('data') or {}
                    default_contract = str(data.get('default_contract_id') or '')
                    matches = [row for row in data.get('contracts', [])
                               if str(row.get('id')) == default_contract]
                    prepared = {}
                    if rostov.get('ok') is True and default_contract and len(matches) == 1:
                        prepared = call('integration_write', {'action': 'prepare', 'service': 'etm',
                            'operation': 'order_checkout', 'params': {'items': deepcopy(items),
                            'region': '61', 'pickup_store': '25140', 'contract_id': default_contract,
                            'payment_method': 'bill', 'pay_type': 'bill',
                            'continuous_cut': False, 'allow_supplier_order': True}})
                    else:
                        report['prepare_skipped'] = 'No verified unambiguous default contract'
                    preview = prepared.get('preview') or {}
                    report['prepare'] = {'ok': prepared.get('ok') is True,
                        'status': prepared.get('status'), 'error': error_code(prepared),
                        'checkout_started': prepared.get('checkout_started'),
                        'mutation_verified': prepared.get('mutation_verified'),
                        'confirmation_required': prepared.get('confirmation_required'),
                        'authorization_policy': prepared.get('authorization_policy'),
                        'manual_confirmation_command_present': 'confirmation_command' in prepared,
                        **fields(preview, ('estimated_total_vat', 'maximum_total_vat', 'currency',
                                         'customer_order_number', 'customer_order_number_kind',
                                         'allow_supplier_order', 'can_submit')),
                        'pickup': fields(preview.get('pickup'), ('code', 'name', 'address')),
                        'contract': fields(preview.get('contract'), ('id', 'name')),
                        'items': [fields(row, ('code', 'quantity', 'unit_price_vat', 'line_estimate_vat'))
                                  for row in preview.get('items', [])]}
                    ident = prepared.get('draft_id', '')
                    durable = {}
                    if isinstance(ident, str) and re.fullmatch(
                            r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', ident):
                        path = home / 'state/etm-writes' / (ident + '.json')
                        if path.is_file():
                            durable = json.loads(path.read_text())
                    saved = durable.get('prepared') or {}
                    reference = preview.get('customer_order_number')
                    report['prepare']['route'] = saved.get('route')
                    report['prepare']['customer_reference_generated_and_persisted'] = bool(
                        reference and reference == 'AI-' + ident.replace('-', '').upper()
                        and reference == (saved.get('params') or {}).get('customer_order_number')
                        and reference == (saved.get('create_body') or {}).get('OrderNumber'))
                    actual_items = {str(row.get('code')): Decimal(str(row.get('quantity')))
                                    for row in preview.get('items', [])}
                    report['prepare']['requested_quantities_preserved'] = actual_items == {
                        row['code']: Decimal(row['quantity']) for row in items}
                    report['prepare']['default_contract_preserved'] = (
                        (preview.get('contract') or {}).get('id') == default_contract)
                    volgograd = call('integration_read', {'service': 'etm', 'operation': 'checkout_options',
                        'params': {'region': '34', 'pickup_store': '29100'}})
                    report['volgograd_options'] = options_summary(volgograd, '29100')
                    r, p, v = report['rostov_options'], report['prepare'], report['volgograd_options']
                    report['passed'] = bool(context) and all((
                        catalog.get('ok') is True, report['checkout_discovered'],
                        report['customer_reference_discovered'], r['ok'], r.get('region_verified') is True,
                        r.get('order_route') == 'public_api', p['ok'], p['status'] == 'prepared',
                        p['route'] == 'public_api', p.get('can_submit') is True,
                        p['pickup'].get('code') == '25140', p['default_contract_preserved'],
                        p['requested_quantities_preserved'], p['customer_reference_generated_and_persisted'],
                        p['allow_supplier_order'] is True, p['checkout_started'] is False,
                        p['mutation_verified'] is False, not p['manual_confirmation_command_present'],
                        p['confirmation_required'] is False, p['authorization_policy'] == 'owner_command',
                        v['ok'], v.get('region_verified') is True, v.get('order_route') == 'portal',
                        v['portal_has_requested_store'], v.get('portal_pickup_offered') is True))
            finally:
                clear_session_vars(tokens)
        finally:
            manager.unload()
            reset_hermes_home_override(override)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true',
                        help='Run live diagnostic discovery and prepare only; never submit an order')
    parser.add_argument('--product-code', required=True, help='Product to quote; no order is placed')
    parser.add_argument('--quantity', required=True, type=Decimal)
    args = parser.parse_args()
    if (not re.fullmatch(r'[0-9]{1,20}', args.product_code) or not args.quantity.is_finite()
            or not 0 < args.quantity <= 10**10):
        raise SystemExit('A valid product code and positive quantity are required.')
    if not args.execute:
        raise SystemExit('Requires --execute: live diagnostic options/prepare only; no confirmation, order or payment.')
    os.umask(0o077)
    report = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'passed': False,
              'installed_release': True, 'native_tool_dispatch': True,
              'temporary_draft_state': True, 'telegram_sent': False,
              'purchase_confirmation_sent': False, 'order_submission_requested': False,
              'payments_requested': False, 'business_writes_requested': False}
    try:
        run(report, [{'code': args.product_code, 'quantity': str(args.quantity)}])
    except Exception as exc:
        # Exception text and tracebacks can carry private runtime details.
        report.update(passed=False, fatal_error='installed_region_smoke_failed',
                      failure_type=type(exc).__name__)
    output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    report_path = ROOT / 'etm-region-installed-smoke.json'
    fd, temporary = tempfile.mkstemp(prefix='.' + report_path.name + '.', dir=ROOT)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(output)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, report_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(output, end='')
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
