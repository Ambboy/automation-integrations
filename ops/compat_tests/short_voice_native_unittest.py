"""Real Hermes hook/middleware/media contracts, fixture renderer and Telegram sink.

Safe standalone invocation (does not bootstrap, install or publish launchers):
  python3 ops/compat_tests/short_voice_native_unittest.py --hermes-root /path/to/hermes-agent

Do not wrap this test in ``import hermes_bootstrap``: source bootstrap can
publish launchers in the checkout even when HERMES_HOME points at a fixture.
"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import weakref
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]


class NativeShortVoice(unittest.IsolatedAsyncioTestCase):
    async def test_native_hooks_cached_context_reload_tool_and_media_contract(self):
        from hermes_cli.plugins import PluginManager
        from hermes_cli.middleware import run_tool_execution_middleware
        from gateway.config import Platform
        from gateway.session import SessionSource
        from gateway.platforms.event import MessageEvent, MessageType
        from gateway.session_context import set_session_vars, clear_session_vars
        from gateway.session_identity import RoutingIdentity
        from gateway.run import _collect_auto_append_media_tags
        from plugins.platforms.telegram.adapter import TelegramAdapter
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / 'profile'; home.mkdir(mode=0o700)
            plugin = home / 'plugins/automation-speech-source'
            shutil.copytree(PROJECT / 'bridges/hermes_speech', plugin)
            shutil.copyfile(PROJECT / 'automation_integrations/speech_source.py', plugin / 'speech_source.py')
            state = root / 'state'
            script = root / 'fixture.py'
            script.write_text('''import sys,json
from pathlib import Path
source,out=map(Path,sys.argv[1:])
assert out.is_dir() and out.stat().st_mode & 0o077 == 0
paths=[]
for n in range(3):
 p=out/f'part-{n}.ogg'; p.write_bytes(b'OggS'+bytes([n])); paths.append(str(p))
print(json.dumps({'success':True,'file_paths':paths,'durations':[180,240,300]}))
''')
            settings = {'enabled': True, 'owner_id': '100001', 'segmented_delivery': True,
                        'state_dir': str(state), 'audio_dir': str(root / 'audio'),
                        'tts_argv': [sys.executable, str(script), '{input_file}', '{output_dir}']}
            (home / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': ['automation-speech-source'],
                'entries': {'automation-speech-source': {'settings': settings}}}}))
            deliveries = []

            class Bot:
                async def send_voice(self, **kwargs):
                    deliveries.append({**kwargs, 'voice': kwargs['voice'].read()})
                    return SimpleNamespace(message_id=100 + len(deliveries))

                async def send_message(self, **kwargs):
                    raise AssertionError('Unexpected failure notice: ' + str(kwargs))

            override = set_hermes_home_override(home)
            with patch.dict(os.environ, {'HERMES_HOME': str(home), 'HERMES_RUNTIME_DIR': str(root / 'runtime')}):
                manager = PluginManager(scope_key=str(home))
                try:
                    manager.discover_and_load()
                    factories = manager.get_platform_handler_factories('telegram')
                    self.assertEqual(len(factories), 1, manager.list_plugins())
                    native = SimpleNamespace(bot=Bot())
                    # Run the installed adapter's real deduplication path, with
                    # no connection, Telegram polling or network transport.
                    adapter = object.__new__(TelegramAdapter)
                    adapter.platform = Platform.TELEGRAM
                    with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                        adapter._wire_plugin_handlers(native)
                    original_bridge = manager._hooks['pre_llm_call'][0].__self__
                    self.assertIs(original_bridge.bot, native.bot)

                    async def incoming(message, turn):
                        source = SessionSource(platform=Platform.TELEGRAM, chat_id='100001', user_id='100001',
                                               chat_type='dm', thread_id='314', message_id=message)
                        # In production this is stamped once by ingress before
                        # the hook; use the real frozen identity/adapter accessor.
                        source._identity = RoutingIdentity(transport_profile='default', runtime_profile='default',
                            authorization_home=home, runtime_home=home, transport=weakref.ref(adapter))
                        event = MessageEvent(text='', source=source, message_id=message, message_type=MessageType.VOICE)
                        with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                            await manager.ainvoke_hook('pre_gateway_dispatch', event=event,
                                gateway=SimpleNamespace(adapters={}, config=SimpleNamespace(multiplex_profiles=True)))
                        # Exactly the cached-agent gateway case: no HERMES_SESSION_ID.
                        tokens = set_session_vars(platform='telegram', chat_id='100001', user_id='100001',
                            chat_type='dm', thread_id='314', message_id=message, session_key='owner-thread')
                        manager.invoke_hook('pre_llm_call', session_id='session', turn_id=turn,
                            platform='telegram', sender_id='100001', user_message='Расскажи механики', conversation_history=[])
                        return tokens

                    tokens = await incoming('315', 'auto-turn')
                    try:
                        result = manager.invoke_hook('transform_llm_output', session_id='session', turn_id='auto-turn',
                                                     platform='telegram', response_text='Оригинал с 20% здоровья.')
                        self.assertTrue(all(x is None for x in result))
                    finally:
                        clear_session_vars(tokens)
                    for _ in range(100):
                        with sqlite3.connect(state / 'sources.sqlite3') as db:
                            done = db.execute("select count(*) from delivery_jobs where state='delivered'").fetchone()[0]
                        if done:
                            break
                        await asyncio.sleep(.03)
                    self.assertEqual(len(deliveries), 3)
                    self.assertEqual([x['voice'][-1] for x in deliveries], [0, 1, 2])
                    self.assertTrue(all(str(x['message_thread_id']) == '314' for x in deliveries))
                    self.assertTrue(all(str(x['reply_to_message_id']) == '315' for x in deliveries))

                    # The real force reload unloads the old instance. Current
                    # Hermes does not emit plugin-loaded for unchanged names.
                    # The next real inbound hook must recover via the public
                    # adapter rewire API, including its qualname deduplication.
                    manager.discover_and_load(force=True)
                    self.assertTrue(original_bridge.stopped.is_set())
                    replacement_bridge = manager._hooks['pre_llm_call'][0].__self__
                    self.assertIsNot(replacement_bridge, original_bridge)
                    self.assertIsNone(replacement_bridge.bot)
                    tokens = await incoming('318', 'reloaded-auto-turn')
                    self.assertIs(replacement_bridge.bot, native.bot)
                    self.assertIs(replacement_bridge.loop, asyncio.get_running_loop())
                    with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                        wired = len(adapter._plugin_handlers_wired)
                        adapter.rewire_plugin_handlers()
                    self.assertEqual(len(adapter._plugin_handlers_wired), wired)
                    try:
                        manager.invoke_hook('transform_llm_output', session_id='session',
                            turn_id='reloaded-auto-turn', platform='telegram', response_text='После перезагрузки.')
                    finally:
                        clear_session_vars(tokens)
                    for _ in range(100):
                        with sqlite3.connect(state / 'sources.sqlite3') as db:
                            done = db.execute("select count(*) from delivery_jobs where state='delivered'").fetchone()[0]
                        if done == 2:
                            break
                        await asyncio.sleep(.03)
                    self.assertEqual(len(deliveries), 6)
                    self.assertTrue(all(str(x['reply_to_message_id']) == '318' for x in deliveries[3:]))

                    tokens = await incoming('322', 'tool-turn')
                    try:
                        def next_call(args):
                            raise AssertionError('Native provider must not synthesize again')
                        with patch('hermes_cli.plugins._delivery_manager', return_value=manager):
                            raw = run_tool_execution_middleware('text_to_speech', {'text': 'Весь исходный ответ.'},
                                next_call, session_id='session', turn_id='tool-turn')
                        result = json.loads(raw)
                        self.assertTrue(result['success'], result)
                        messages = [{'role': 'assistant', 'tool_calls': [{'id': 'tool-call', 'type': 'function',
                            'function': {'name': 'text_to_speech', 'arguments': '{}'}}]},
                            {'role': 'tool', 'tool_call_id': 'tool-call', 'content': raw}]
                        tags, voice = _collect_auto_append_media_tags(messages)
                        self.assertTrue(voice)
                        self.assertEqual(tags, ['MEDIA:' + p for p in result['file_paths']])
                        manager.invoke_hook('transform_llm_output', session_id='session', turn_id='tool-turn',
                                             platform='telegram', response_text='Готово.')
                        await asyncio.sleep(.05)
                        self.assertEqual(len(deliveries), 6, 'Explicit TTS must not create automatic duplicate')
                    finally:
                        clear_session_vars(tokens)
                finally:
                    manager.unload()
                    await asyncio.sleep(.05)
                    reset_hermes_home_override(override)


def run_native_isolated(hermes_root, args):
    """Read the committed runtime, then run the fixture without bootstrapping it."""
    root = Path(hermes_root).resolve()
    sys.path.insert(0, str(root))
    from hermes_cli._launchers import resolve_store_python
    from pm.environments import committed_venv, runtime_facts_path, site_packages, store_root

    python, environment = resolve_store_python(root), committed_venv(root)
    if python is None or environment is None:
        raise RuntimeError('Native test requires an existing committed Hermes runtime')
    dependencies = site_packages(environment)
    if not dependencies.is_dir():
        raise RuntimeError('Committed Hermes dependencies are unavailable')
    protected = [root / '.hermes/bin/hermes', root / '.hermes/bin/hermes-acp',
                 root / 'install-stamp.json', runtime_facts_path(root), store_root(root) / 'facts.json']
    before = {path: path.read_bytes() if path.is_file() else None for path in protected}
    script = (
        'import runpy,site,sys; '
        'site.addsitedir(sys.argv[2]); sys.path.insert(0,sys.argv[1]); '
        'test=sys.argv[3]; sys.argv=[test,*sys.argv[4:]]; '
        "runpy.run_path(test,run_name='__main__')"
    )
    with tempfile.TemporaryDirectory(prefix='hermes-speech-native-') as tmp:
        env = dict(os.environ, HERMES_HOME=tmp, HERMES_RUNTIME_DIR=tmp + '/runtime',
                   HERMES_DISABLE_LAZY_INSTALLS='1')
        result = subprocess.run([str(python), '-I', '-c', script, str(root), str(dependencies),
                                 str(Path(__file__).resolve()), *args], env=env)
    changed = [str(path) for path, original in before.items()
               if (path.read_bytes() if path.is_file() else None) != original]
    if changed:
        raise RuntimeError('Native test changed protected runtime files: ' + ', '.join(changed))
    return result.returncode


if __name__ == '__main__':
    if '--hermes-root' in sys.argv:
        import argparse
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('--hermes-root', required=True)
        options, remaining = parser.parse_known_args()
        raise SystemExit(run_native_isolated(options.hermes_root, remaining))
    unittest.main()
