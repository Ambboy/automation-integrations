"""Verify installed ABCP code via native Hermes hooks/tools and two real reads.

Run through the installed Hermes runtime/bootstrap. A temporary Hermes profile
loads an exact copy of the deployed plugin with its deployed absolute runner,
catalog and private-config paths. No model, Telegram send, confirmation or API
write is invoked. Only a safe summary is written to --output.
"""
from __future__ import annotations

import argparse
import contextvars
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid


PLUGIN = 'automation-api-catalog'
OWNER = '999000111'
VERSION = 'abcp_client_get_orders_version'
BRANDS = 'abcp_client_get_search_brands'


class ProbeError(Exception):
    pass


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, report):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.abcp-probe-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fchmod(handle.fileno(), 0o600)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def probe(live):
    import hermes_bootstrap  # noqa: F401 -- native launcher dependency environment
    import hermes_yaml as yaml
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from hermes_cli.plugins import get_plugin_manager
    from tools.registry import registry
    from model_tools import get_tool_definitions
    from gateway.session_context import set_session_vars, clear_session_vars
    from agent.delegation_context import delegated_child_context

    report = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'passed': False,
              'installed_release': True, 'native_tool_dispatch': True, 'mocked_transport': False,
              'isolated_native_profile': True, 'telegram_sent': False, 'model_called': False,
              'business_writes_requested': False, 'reads': {}}
    config = live / 'config.yaml'
    deployed = live / 'plugins' / PLUGIN
    config_hash = digest(config)
    plugin_hashes = {name: digest(deployed / name) for name in ('__init__.py', 'catalog.py', 'plugin.yaml')}
    cfg = yaml.safe_load(config.read_text())
    entry = cfg['plugins']['entries'][PLUGIN]
    settings = entry['settings']
    if (PLUGIN not in cfg['plugins']['enabled'] or not settings.get('enabled')
            or str(settings.get('owner_id')) != OWNER or str(settings.get('chat_id')) != OWNER):
        raise ProbeError('unexpected_installed_plugin_settings')
    catalog_path = Path(settings['catalog_path'])
    local_catalog = json.loads(catalog_path.read_text())
    if [row['id'] for row in local_catalog['services']] != ['abcp']:
        raise ProbeError('installed_catalog_is_not_abcp_only')
    operations = local_catalog['services'][0]['operations']
    if VERSION not in operations or BRANDS not in operations:
        raise ProbeError('required_reads_missing_from_catalog')
    inventory = json.loads((catalog_path.parent / 'capabilities/abcp.json').read_text())
    version_rows = [row for row in inventory['capabilities']
                    if str(row.get('path', '')).strip('/') == 'orders/version' and row.get('adapter') == VERSION]
    if len(version_rows) != 1:
        raise ProbeError('orders_version_capability_not_unique')
    version_id = version_rows[0]['id']

    with tempfile.TemporaryDirectory(prefix='abcp-native-readonly-') as temporary:
        home = Path(temporary) / 'hermes'
        home.mkdir(mode=0o700)
        plugin = home / 'plugins' / PLUGIN
        shutil.copytree(deployed, plugin, ignore=shutil.ignore_patterns('__pycache__'))
        if {name: digest(plugin / name) for name in plugin_hashes} != plugin_hashes:
            raise ProbeError('deployed_plugin_changed_during_copy')
        (home / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': [PLUGIN], 'entries': {PLUGIN: entry}}}))
        previous_runtime = os.environ.get('HERMES_RUNTIME_DIR')
        os.environ['HERMES_RUNTIME_DIR'] = str(home / 'runtime')
        override = set_hermes_home_override(home)
        manager = get_plugin_manager()
        try:
            manager.discover_and_load()
            plugins = [row for row in manager.list_plugins() if row['name'] == PLUGIN]
            report['plugin_loaded'] = len(plugins) == 1 and not plugins[0]['error']
            definitions = get_tool_definitions(enabled_toolsets=['automation-api'], quiet_mode=True,
                                               skip_tool_search_assembly=True)
            schemas = {row['function']['name']: row['function'] for row in definitions}
            report['only_abcp_tool_schemas'] = all(
                schemas.get(name, {}).get('parameters', {}).get('properties', {}).get('service', {}).get('enum') == ['abcp']
                for name in ('integration_read', 'integration_write'))

            def call(name, request):
                return json.loads(registry.dispatch(name, request, scope=str(home)))

            request = {'service': 'abcp', 'operation': VERSION, 'params': {}}
            unbound = call('integration_read', request)
            report['unbound_denied'] = unbound.get('error') == 'route_not_authorized' and unbound.get('provider_called') is False
            sid = 'abcp-native-probe-' + uuid.uuid4().hex
            tokens = set_session_vars(chat_type='dm', session_key=sid, message_id='abcp-probe-read-1',
                                     platform='telegram', chat_id=OWNER, user_id=OWNER, session_id=sid)
            try:
                contexts = manager.invoke_hook('pre_llm_call', platform='telegram', sender_id=OWNER,
                    session_id=sid, turn_id='abcp-probe-1',
                    user_message='Проверить API ABCP: версия заказов и марки по артикулу OC90. Только чтение.',
                    conversation_history=[])
                report['context_admitted'] = any('ABCP' in item.get('context', '') for item in contexts if isinstance(item, dict))
                report['context_agent_specific'] = all('Грейфа' not in item.get('context', '') for item in contexts if isinstance(item, dict))
                discovery = call('integration_catalog', {'service': 'abcp'})
                report['catalog_discovered'] = (discovery.get('ok') is True and
                    [row['id'] for row in discovery.get('services', [])] == ['abcp'])
                detail = call('integration_catalog', {'service': 'abcp', 'view': 'capabilities',
                                                     'capability_id': version_id})
                report['exact_capability_discovered'] = (detail.get('ok') is True and
                    len(detail.get('capabilities', [])) == 1 and detail['capabilities'][0].get('adapter') == VERSION)
                # Real tool subprocesses inherit the authenticated native context.
                with ThreadPoolExecutor(max_workers=1) as pool:
                    version = pool.submit(contextvars.copy_context().run, call, 'integration_read', request).result()
                report['reads']['orders_version'] = {'ok': version.get('ok') is True,
                    'version_supported': isinstance(version.get('data'), dict) and version['data'].get('version') in (1, 2),
                    'provider_called': version.get('provider_called') is True, 'http_status': version.get('http_status')}
                brands = call('integration_read', {'service': 'abcp', 'operation': BRANDS, 'params': {'number': 'OC90'}})
                data = brands.get('data')
                report['reads']['search_brands'] = {'ok': brands.get('ok') is True,
                    'nonempty': isinstance(data, (list, dict)) and bool(data),
                    'provider_called': brands.get('provider_called') is True, 'http_status': brands.get('http_status')}
                with delegated_child_context():
                    child = call('integration_read', request)
                report['child_denied'] = (child.get('reason') == 'child_or_background_context'
                                          and child.get('provider_called') is False)
            finally:
                clear_session_vars(tokens)
            tokens = set_session_vars(chat_type='dm', session_key=sid, message_id='abcp-probe-read-1',
                                     platform='telegram', chat_id=OWNER, user_id='999999999', session_id=sid)
            try:
                outsider = call('integration_read', request)
                report['outsider_denied'] = (outsider.get('reason') == 'owner_private_telegram_required'
                                             and outsider.get('provider_called') is False)
            finally:
                clear_session_vars(tokens)
        finally:
            manager.unload()
            report['unloaded'] = registry.get_entry('integration_catalog', scope=str(home)) is None
            reset_hermes_home_override(override)
            if previous_runtime is None:
                os.environ.pop('HERMES_RUNTIME_DIR', None)
            else:
                os.environ['HERMES_RUNTIME_DIR'] = previous_runtime
    report['installed_config_preserved'] = digest(config) == config_hash
    report['installed_plugin_preserved'] = {name: digest(deployed / name) for name in plugin_hashes} == plugin_hashes
    checks = ('plugin_loaded', 'only_abcp_tool_schemas', 'unbound_denied', 'context_admitted',
              'context_agent_specific', 'catalog_discovered', 'exact_capability_discovered',
              'child_denied', 'outsider_denied', 'unloaded', 'installed_config_preserved', 'installed_plugin_preserved')
    report['passed'] = (all(report.get(key) is True for key in checks)
        and all(report['reads']['orders_version'][key] is True for key in ('ok', 'version_supported', 'provider_called'))
        and all(report['reads']['search_brands'][key] is True for key in ('ok', 'nonempty', 'provider_called')))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home() / '.hermes')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        report = probe(args.home.resolve())
    except ProbeError as exc:
        report = {'passed': False, 'error': str(exc), 'telegram_sent': False, 'model_called': False,
                  'business_writes_requested': False}
    except Exception:
        # Never print provider data, config contents or exception details.
        report = {'passed': False, 'error': 'native_probe_failed', 'telegram_sent': False,
                  'model_called': False, 'business_writes_requested': False}
    save(args.output.absolute(), report)
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
