# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Installed native plugin -> compiled contract -> provider read, without messaging."""
import argparse
import hermes_bootstrap
import hermes_yaml as yaml
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--only', choices=['yandex_go','etm','saby','tochka'])
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit('Requires --execute (four provider reads, no business writes or Telegram messages).')
    os.umask(0o077)
    live = Path('/home/operator/.hermes')
    root = Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')
    entry = yaml.safe_load((live / 'config.yaml').read_text())['plugins']['entries']['automation-api-catalog']
    rows = []
    with tempfile.TemporaryDirectory(prefix='compiled-installed-') as tmp:
        home = Path(tmp)
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
            tokens = set_session_vars(chat_type='dm', session_key='compiled-smoke', message_id='compiled-1',
                platform='telegram', chat_id='100001', user_id='100001', session_id='compiled-installed')
            try:
                contexts = manager.invoke_hook('pre_llm_call', platform='telegram', sender_id='100001',
                    session_id='compiled-installed', turn_id='1', user_message='Проверка API чтением', conversation_history=[])
                for service, operation, params in [
                    ('yandex_go', 'cost_center_list', {'query': {'limit': 1}}),
                    ('etm', 'goods_get', {'path': {'id': '5301409'}, 'query': {'type': 'etm'}}),
                    ('saby', 'current_user', {'body': {'Параметр': {}}}),
                    ('tochka', 'open_banking_get_accounts_list', {})]:
                    if args.only and service != args.only:
                        continue
                    response = json.loads(registry.dispatch('integration_read',
                        {'service': service, 'operation': operation, 'params': params}, scope=str(home)))
                    rows.append({'service': service, 'operation': operation, 'ok': response.get('ok', False),
                                 'error': response.get('error'), 'http_status': response.get('http_status')})
            finally:
                clear_session_vars(tokens)
        finally:
            manager.unload(); reset_hermes_home_override(override)
    previous_path = root / 'compiled-installed-smoke.json'
    if args.only and previous_path.exists():
        rows = json.loads(previous_path.read_text())['checks'] + rows
    latest = {row['service']: row for row in rows}
    report = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'passed': bool(contexts) and len(latest) == 4 and all(r['ok'] for r in latest.values()),
              'checks': rows, 'installed_release': True, 'native_tool_dispatch': True,
              'telegram_sent': False, 'business_writes': False}
    (root / 'compiled-installed-smoke.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
