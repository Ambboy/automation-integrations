# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Installed plugin -> native dispatch -> installed runners -> actual reads.

Run under the committed Hermes Python/site-packages with bootstrap disabled.
No generation, external messages, reload or service changes occur here.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import hermes_yaml as yaml


def main():
    if sys.argv[1:] != ['--execute']:
        raise SystemExit('Requires --execute (read-only installed verification).')
    os.umask(0o077)
    live = Path('/home/operator/.hermes')
    root = Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')
    entry = yaml.safe_load((live / 'config.yaml').read_text())['plugins']['entries']['automation-api-catalog']
    owner = str(entry['settings']['owner_id'])
    chat = str(entry['settings']['chat_id'])
    launchers = [live / 'hermes-agent/.hermes/bin/hermes', Path('/home/operator/.local/bin/hermes'),
                 Path('/home/operator/.local/bin/hermes-agent')]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in launchers}
    checks = []
    generated = json.loads((root / 'update-20261004-media/live-inference.json').read_text())
    with tempfile.TemporaryDirectory(prefix='media-installed-') as temp:
        home = Path(temp)
        os.environ['HERMES_HOME'] = str(home)
        os.environ['HERMES_RUNTIME_DIR'] = str(home / 'runtime')
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
            tokens = set_session_vars(chat_type='dm', session_key='media-installed-validation',
                message_id='media-installed-read', platform='telegram', chat_id=chat,
                user_id=owner, session_id='media-installed')
            try:
                context = manager.invoke_hook('pre_llm_call', platform='telegram', sender_id=owner,
                    session_id='media-installed', turn_id='1', user_message='Проверка подключений чтением', conversation_history=[])
                for service in ('fal', 'inference'):
                    response = json.loads(registry.dispatch('integration_catalog',
                        {'service': service, 'view': 'capabilities', 'limit': 2}, scope=str(home)))
                    checks.append({'service': service, 'operation': 'catalog', 'ok': response.get('ok', False),
                                   'total': response.get('total')})
                requests = [
                    ('fal', 'models', {'limit': 1}, True),
                    ('fal', 'billing', {'expand': 'credits'}, False),
                    ('inference', 'balance', {}, True),
                    ('inference', 'job_result', {'job_id': generated['job_id']}, True),
                    ('inference', 'artifact_download', {'artifact_id': generated['artifacts'][0]['artifact_id']}, True),
                    ('yandex_go', 'users', {'limit': 1}, True),
                ]
                for service, operation, params, expected in requests:
                    response = json.loads(registry.dispatch('integration_read',
                        {'service': service, 'operation': operation, 'params': params}, scope=str(home)))
                    row = {'service': service, 'operation': operation, 'ok': response.get('ok', False),
                           'expected_ok': expected, 'error': response.get('error'), 'http_status': response.get('http_status')}
                    if operation == 'balance' and response.get('ok'):
                        row['balance_usd'] = response['data'].get('balance_usd')
                    if operation == 'artifact_download' and response.get('ok'):
                        row.update(bytes=response['data']['bytes'], sha256=response['data']['sha256'])
                    checks.append(row)
            finally:
                clear_session_vars(tokens)
        finally:
            manager.unload()
            reset_hermes_home_override(override)
    unchanged = all(hashlib.sha256(p.read_bytes()).hexdigest() == hashes[str(p)] for p in launchers)
    passed = bool(context) and unchanged and all(
        row['ok'] == row.get('expected_ok', True) and (
            row.get('expected_ok', True) or row.get('http_status') == 403) for row in checks)
    report = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'passed': passed,
              'installed_release': True, 'native_dispatch': True, 'checks': checks,
              'launchers_unchanged': unchanged, 'paid_requests': False, 'telegram_sent': False,
              'route': 'synthetic native-context validation; not a real inbound user message'}
    (root / 'update-20261004-media/installed-native.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
