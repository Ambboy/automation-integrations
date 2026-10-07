# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Installed release + native plugin dispatch + actual read API, no messenger traffic."""
import hermes_bootstrap
import hermes_yaml as yaml
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def main():
    if sys.argv[1:] != ['--execute']:
        raise SystemExit('Requires --execute (prepare management preview and reject unconfirmed execution; no controller mutation)')
    os.umask(0o077)
    live = Path('/home/operator/.hermes')
    root = Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')
    config = yaml.safe_load((live / 'config.yaml').read_text())
    entry = config['plugins']['entries']['automation-api-catalog']
    with tempfile.TemporaryDirectory(prefix='catalog-installed-') as tmp:
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
            tokens = set_session_vars(chat_type='dm', session_key='owner-dm-thread', message_id='message-1', platform='telegram', chat_id='100001', user_id='100001', session_id='installed-smoke')
            try:
                ctx = manager.invoke_hook('pre_llm_call', platform='telegram', sender_id='100001',
                    session_id='installed-smoke', turn_id='1', user_message='Проверка контроллеров Wiren Board', conversation_history=[])
                catalog = json.loads(registry.dispatch('integration_catalog', {'service': 'wirenboard'}, scope=str(home)))
                serial = json.loads((root / 'wirenboard-control-target.json').read_text())['serial_number']
                response = json.loads(registry.dispatch('integration_write', {'action': 'prepare',
                    'service': 'wirenboard', 'operation': 'controller_update',
                    'params': {'serial_number': serial, 'fields': {'description': 'Integration preview; not applied'}}}, scope=str(home)))
                denied = json.loads(registry.dispatch('integration_write', {'action': 'execute',
                    'draft_id': response.get('draft_id')}, scope=str(home)))
                report = {'passed': bool(ctx) and catalog.get('ok') and response.get('ok')
                          and response.get('status') == 'prepared' and denied.get('error') == 'owner_confirmation_required',
                          'error': response.get('error'), 'telegram_sent': False,
                          'operation': 'wirenboard.controller_update.prepare', 'controller_mutation': False,
                          'unconfirmed_execution': denied.get('error'),
                          'write_operations': len(catalog.get('services', [{}])[0].get('write_operations', {})),
                          'installed_release': True, 'native_tool_dispatch': True}
                # Remove only this unsubmitted synthetic smoke draft.
                if response.get('draft_id'):
                    draft = root / 'state/wirenboard-writes' / (response['draft_id'] + '.json')
                    row = json.loads(draft.read_text())
                    if row['status'] == 'prepared' and row['created_message'] == 'message-1' and 'submitted_at' not in row:
                        draft.unlink()
            finally:
                clear_session_vars(tokens)
        finally:
            manager.unload(); reset_hermes_home_override(override)
    (root / 'wirenboard-control-installed-smoke.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
