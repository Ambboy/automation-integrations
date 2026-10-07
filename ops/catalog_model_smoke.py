# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Real model discovery via native hook/context/tool registration; no business writes or Telegram."""
import contextlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import hermes_bootstrap  # Activate the existing runtime BEFORE selecting a disposable home.
import hermes_yaml as yaml

PROJECT = Path('/home/operator/workspaces/automation-integrations')
HOME = Path('/home/operator/.hermes')
ROOT = Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')


def main():
    if sys.argv[1:] != ['--execute']:
        raise SystemExit('Requires --execute (four real model requests, no business API calls)')
    os.umask(0o077)
    attempt = ROOT / 'model-attempt.json'
    assert not attempt.exists(), 'Review previous model attempt before repeating'
    attempt.write_text('{"started":true}')
    original = (HOME / 'auth.json').read_bytes()
    auth = json.loads(original)
    model = yaml.safe_load((HOME / 'config.yaml').read_text())['model']
    assert model['provider'] == 'openai-codex'
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if k != 'refresh_token'}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    auth = {'version': auth.get('version', 1), 'active_provider': 'openai-codex',
            'providers': {'openai-codex': clean(auth.get('providers', {}).get('openai-codex', {}))},
            'credential_pool': {'openai-codex': clean(auth.get('credential_pool', {}).get('openai-codex', []))}}
    report = {'passed': False, 'cases': [], 'telegram_sent': False, 'business_api_called': False}
    with tempfile.TemporaryDirectory(prefix='greif-catalog-model-') as tmp:
        home = Path(tmp)
        (home / 'auth.json').write_text(json.dumps(auth))
        plugin = home / 'plugins/automation-api-catalog'
        shutil.copytree(PROJECT / 'bridges/hermes_catalog', plugin, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(PROJECT / 'automation_integrations/catalog.py', plugin / 'catalog.py')
        settings = {'enabled': True, 'owner_id': '100001', 'chat_id': '100001',
                    'catalog_path': str(PROJECT / 'registry/catalog.json'),
                    'state_dir': str(ROOT / 'state'), 'runner_path': '/nonexistent', 'private_config': '/nonexistent'}
        (home / 'config.yaml').write_text(json.dumps({'model': model, 'memory': {'memory_enabled': False},
            'mcp_servers': {}, 'telemetry': {'enabled': False}, 'plugins': {'enabled': ['automation-api-catalog'],
            'entries': {'automation-api-catalog': {'settings': settings}}}}))
        os.environ['HERMES_HOME'] = tmp; os.environ['HERMES_RUNTIME_DIR'] = tmp + '/runtime'
        sys.path.insert(0, str(HOME / 'hermes-agent'))
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import get_plugin_manager
        from tools.registry import registry
        from gateway.session_context import set_session_vars, clear_session_vars
        from agent.turn_context import compose_user_api_content
        from agent.auxiliary_client import call_llm
        override = set_hermes_home_override(home)
        manager = get_plugin_manager()
        with (ROOT / 'model-private.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                manager.discover_and_load()
                schemas = [{'type': 'function', 'function': registry.get_entry(n, scope=str(home)).schema}
                           for n in ('integration_catalog', 'integration_read')]
                # Alternatives are offered to the model, but are never executed by this harness.
                schemas.append({'type': 'function', 'function': {'name': 'web_search',
                    'description': 'Search the web for ways to access a service',
                    'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']}}})
                cases = [('saby', 'Найди входящие закрывающие документы.'),
                         ('etm', 'Нужно посмотреть цену и остаток кабеля в ЭТМ.'),
                         ('tochka', 'Посмотри остатки на наших банковских счетах.'),
                         ('yandex_go', 'Посмотри наших сотрудников в Яндекс Go.')]
                for index, (expected, prompt) in enumerate(cases):
                    session = 'catalog-model-' + str(index)
                    tokens = set_session_vars(chat_type='dm', session_key='owner-dm-thread', message_id='message-1', platform='telegram', chat_id='100001', user_id='100001', session_id=session)
                    try:
                        contexts = manager.invoke_hook('pre_llm_call', platform='telegram', sender_id='100001',
                            session_id=session, turn_id='fresh', user_message=prompt, conversation_history=[])
                        content = compose_user_api_content(prompt, '', contexts[0]['context'])
                        response = call_llm(provider=model['provider'], model=model['default'],
                            messages=[{'role': 'system', 'content': 'Ты Грейф, помощник владельца. Используй доступные инструменты.'},
                                      {'role': 'user', 'content': content}], tools=schemas, max_tokens=900, timeout=90)
                        calls = response.choices[0].message.tool_calls or []
                        names = [c.function.name for c in calls]
                        matched = False
                        for call in calls:
                            if call.function.name == 'integration_catalog':
                                result = json.loads(registry.dispatch('integration_catalog', json.loads(call.function.arguments), scope=str(home)))
                                matched |= expected in [s['id'] for s in result.get('services', [])]
                        report['cases'].append({'service': expected, 'tools': names,
                                                'passed': bool(names) and set(names) == {'integration_catalog'} and matched})
                        (ROOT / 'model-report.json').write_text(json.dumps(report, indent=2))
                    finally:
                        clear_session_vars(tokens)
                report['passed'] = all(c['passed'] for c in report['cases']) and len(report['cases']) == 4
            except Exception as exc:
                report['error_type'] = type(exc).__name__
            finally:
                manager.unload(); reset_hermes_home_override(override)
    report['production_auth_unchanged'] = (HOME / 'auth.json').read_bytes() == original
    (ROOT / 'model-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    raise SystemExit(0 if report['passed'] and report['production_auth_unchanged'] else 1)


if __name__ == '__main__':
    main()
