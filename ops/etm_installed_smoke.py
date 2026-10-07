# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Installed native ETM discovery/read/prepare. Never confirm or execute a purchase."""
import argparse
from copy import deepcopy
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import tempfile

import hermes_bootstrap
import hermes_yaml as yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--product-code', default='6510970')
    parser.add_argument('--quantity', type=int, default=100)
    parser.add_argument('--continuous-cut', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit('Requires --execute: live read-only options/quote; no checkout submission.')
    os.umask(0o077)
    live = Path('/home/operator/.hermes')
    root = Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')
    report = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'installed_release': True, 'native_tool_dispatch': True,
              'telegram_sent': False, 'purchase_confirmation_sent': False,
              'business_writes_requested': False}
    with tempfile.TemporaryDirectory(prefix='etm-installed-readonly-') as tmp:
        home = Path(tmp)
        entry = deepcopy(yaml.safe_load((live / 'config.yaml').read_text())['plugins']['entries']['automation-api-catalog'])
        settings = entry['settings']
        private = json.loads(Path(settings['private_config']).read_text())
        private['state_dir'] = str(home / 'state')
        private_path = home / 'private.json'
        private_path.write_text(json.dumps(private))
        settings['private_config'] = str(private_path)
        settings['state_dir'] = str(home / 'state')
        shutil.copytree(live / 'plugins/automation-api-catalog', home / 'plugins/automation-api-catalog')
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
            tokens = set_session_vars(chat_type='dm', session_key='etm-installed-smoke', message_id='etm-readonly-1',
                platform='telegram', chat_id='100001', user_id='100001', session_id='etm-installed-readonly')
            try:
                context = manager.invoke_hook('pre_llm_call', platform='telegram', sender_id='100001',
                    session_id='etm-installed-readonly', turn_id='1',
                    user_message='Проверить возможности ЭТМ и подготовку без оформления заказа', conversation_history=[])
                def call(name, request):
                    return json.loads(registry.dispatch(name, request, scope=str(home)))
                catalog = call('integration_catalog', {'service': 'etm'})
                service = catalog.get('services', [{}])[0]
                report['checkout_discovered'] = 'order_checkout' in service.get('write_operations', {})
                report['invoice_create_discovered'] = 'invoice_create' in service.get('write_operations', {})
                options = call('integration_read', {'service': 'etm', 'operation': 'checkout_options',
                                                    'params': {'region': '34', 'pickup_store': '29100'}})
                report['options_ok'] = options.get('ok') is True
                report['options_error'] = options.get('error')
                prepared = call('integration_write', {'action': 'prepare', 'service': 'etm',
                    'operation': 'order_checkout', 'params': {'items': [{'code': args.product_code, 'quantity': args.quantity}],
                    'region': '34', 'pickup_store': '29100', 'payment_method': 'bill', 'pay_type': 'bill',
                    'continuous_cut': args.continuous_cut, 'allow_supplier_order': not args.continuous_cut}})
                report['prepare_ok'] = prepared.get('ok') is True
                report['prepare_status'] = prepared.get('status')
                report['prepare_error'] = prepared.get('error')
                items = (prepared.get('preview') or {}).get('items', [])
                report['quote_items'] = len(items)
                report['quote_preserves_requested_quantity'] = bool(items) and str(items[0].get('quantity')) == str(args.quantity)
                report['confirmation_required'] = prepared.get('confirmation_required')
                report['authorization_policy'] = prepared.get('authorization_policy')
                report['quoted_total_vat'] = (prepared.get('preview') or {}).get('estimated_total_vat')
                report['owner_command_discovered'] = (private.get('etm_order_authorization') != 'owner_command' or
                    (prepared.get('confirmation_required') is False and 'confirmation_command' not in prepared))
                report['passed'] = (bool(context) and report['checkout_discovered']
                                    and report['invoice_create_discovered'] and report['options_ok']
                                    and report['prepare_ok'] and report['quote_preserves_requested_quantity']
                                    and report['owner_command_discovered']
                                    and prepared.get('status') in ('prepared', 'blocked'))
            finally:
                clear_session_vars(tokens)
        finally:
            manager.unload()
            reset_hermes_home_override(override)
    (root / 'etm-installed-smoke.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
