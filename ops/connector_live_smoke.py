"""Installed native plugin acceptance with a fixed read-only provider allowlist.

No orders, payments, report generation, uploads, messages or model calls.
Metadata is saved, provider data stays in memory. Run using the installed
Hermes Python with hermes_bootstrap available on PYTHONPATH.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time


PROBES = (
    ('yandex_go', 'auth_list', {}),
    ('yandex_go', 'cost_center_list', {'query': {'limit': 1}}),
    ('etm', 'login_check', {}),
    ('etm', 'goods_get', {'path': {'id': '1234567'}, 'query': {'type': 'etm'}}),
    ('saby', 'version', {}),
    ('saby', 'documents', {'page_size': 1}),
    ('tochka', 'accounts', {}),
    ('tochka', 'balances', {}),
    ('wirenboard', 'me', {}),
    ('wirenboard', 'controllers', {'page_size': 1}),
    ('fal', 'get_models', {'limit': 1, 'sort': 'recent'}),
    ('fal', 'get_pricing', {'endpoint_id': 'fal-ai/flux/schnell'}),
    ('inference', 'identity', {}),
    ('inference', 'app_list', {'limit': 1}),
    ('inference', 'balance', {}),
)


def safe_error(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', value) else None


def summarize(result, service, operation, elapsed):
    data = result.get('data')
    return {'service': service, 'operation': operation,
        'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'ok': result.get('ok') is True and result.get('service') == service
              and result.get('operation') == operation and isinstance(data, (dict, list)),
        'error': safe_error(result.get('error')), 'http_status': result.get('http_status'),
        'provider_code': safe_error(result.get('provider_code')),
        'retry_after_seconds': result.get('retry_after_seconds'),
        'data_type': type(data).__name__, 'elapsed_seconds': round(elapsed, 2)}


def run(live, only=(), etm_product_id=None):
    if (not only or 'etm' in only) and not re.fullmatch(r'[0-9]{1,20}', str(etm_product_id or '')):
        raise ValueError('A real ETM product ID is required for ETM probes')
    import hermes_bootstrap  # noqa: F401
    import hermes_yaml as yaml
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from hermes_cli.plugins import get_plugin_manager
    from tools.registry import registry
    from gateway.session_context import set_session_vars, clear_session_vars

    config_path = live / 'config.yaml'
    before = hashlib.sha256(config_path.read_bytes()).hexdigest()
    entry = deepcopy(yaml.safe_load(config_path.read_text())['plugins']['entries']['automation-api-catalog'])
    settings = entry['settings']
    owner, chat = str(settings['owner_id']), str(settings['chat_id'])
    if owner != chat or settings.get('enabled') is not True:
        raise ValueError('Expected enabled owner private-chat plugin')
    checks = []
    with tempfile.TemporaryDirectory(prefix='connector-native-audit-') as tmp:
        home = Path(tmp)
        shutil.copytree(live / 'plugins/automation-api-catalog', home / 'plugins/automation-api-catalog')
        (home / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': ['automation-api-catalog'],
            'entries': {'automation-api-catalog': entry}}}))
        override = set_hermes_home_override(home)
        manager = get_plugin_manager()
        try:
            manager.discover_and_load()
            tokens = set_session_vars(chat_type='dm', session_key='connector-read-audit',
                message_id='connector-audit-1', platform='telegram', chat_id=chat, user_id=owner,
                session_id='connector-read-audit')
            try:
                contexts = manager.invoke_hook('pre_llm_call', platform='telegram', sender_id=owner,
                    session_id='connector-read-audit', turn_id='1',
                    user_message='Проверить доступность подключений только чтением', conversation_history=[])
                for service, operation, params in PROBES:
                    if only and service not in only:
                        continue
                    if service == 'etm' and operation == 'goods_get':
                        params = {'path': {'id': etm_product_id}, 'query': {'type': 'etm'}}
                    start = time.monotonic()
                    try:
                        result = json.loads(registry.dispatch('integration_read',
                            {'service': service, 'operation': operation, 'params': params}, scope=str(home)))
                        row = summarize(result, service, operation, time.monotonic() - start)
                    except Exception as exc:
                        row = {'service': service, 'operation': operation, 'ok': False,
                               'error': type(exc).__name__, 'elapsed_seconds': round(time.monotonic() - start, 2)}
                    checks.append(row)
                    print(json.dumps(row), flush=True)
            finally:
                clear_session_vars(tokens)
        finally:
            manager.unload()
            reset_hermes_home_override(override)
    preserved = hashlib.sha256(config_path.read_bytes()).hexdigest() == before
    return {'schema_version': 1, 'native_installed_plugin': True, 'checks': checks,
            'dispatch_context': 'Copy of installed plugin in an isolated native Hermes home; configured installed runner and current provider credentials.',
            'actual_gateway_model_turn': False,
            'passed': bool(contexts) and preserved and bool(checks) and all(row['ok'] for row in checks),
            'config_preserved': preserved, 'business_writes': False, 'telegram_sent': False,
            'scope': 'Fixed representative reads. Does not prove all methods, write permissions or end-to-end business outcomes.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--home', type=Path, default=Path.home() / '.hermes')
    parser.add_argument('--only', action='append', choices=sorted({s for s, _, _ in PROBES}), default=[])
    parser.add_argument('--etm-product-id', help='Existing ETM catalog product ID; required when ETM is selected')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.execute:
        parser.error('--execute is required for current-account read probes')
    if (not args.only or 'etm' in args.only) and not re.fullmatch(r'[0-9]{1,20}', args.etm_product_id or ''):
        parser.error('--etm-product-id is required and must be numeric when ETM is selected')
    os.umask(0o077)
    report = run(args.home, args.only, args.etm_product_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'checks': len(report['checks'])}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
