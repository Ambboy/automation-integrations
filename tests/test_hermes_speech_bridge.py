"""Speech bridge integration without Telegram, model calls or provider APIs."""
import asyncio
import contextvars
import importlib
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from automation_integrations import speech_source

# Production deployment bundles the canonical module beside the thin binding.
sys.modules['bridges.hermes_speech.speech_source'] = speech_source
SpeechDelivery = importlib.import_module('bridges.hermes_speech.delivery').SpeechDelivery


class Context:
    def __init__(self, settings):
        self.settings, self.hooks, self.middleware, self.unload = settings, {}, {}, []

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_platform_handler(self, platform, callback):
        self.platform_callback = callback

    def register_hook(self, hook, callback):
        self.hooks[hook] = callback

    def register_middleware(self, kind, callback):
        self.middleware[kind] = callback

    def on_unload(self, callback):
        self.unload.append(callback)


class SpeechBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.renderer = self.root / 'renderer.py'
        self.renderer.write_text('''import argparse, json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--input');p.add_argument('--output-dir')
a=p.parse_args()
out=Path(a.output_dir)
assert out.is_dir() and not out.stat().st_mode & 0o077
paths=[]
for i in range(3):
    part=out/f'part-{i}.ogg';part.write_bytes(b'OggS'+bytes([i]));paths.append(str(part))
print(json.dumps({'success':True,'file_paths':paths,'durations':[180,240,300], 'voice_compatible':True}))
''')
        self.ctx = Context({'state_dir': str(self.root / 'state'), 'owner_id': '42',
                            'audio_dir': str(self.root / 'audio'),
                            'tts_argv': [sys.executable, str(self.renderer), '--input', '{input_file}',
                                         '--output-dir', '{output_dir}'], 'synthesis_timeout': 5})
        self.adapter = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(message_id=100)),
                                       send_voice=AsyncMock(return_value=SimpleNamespace(message_id=101)))
        self.adapter.send_message = self.adapter.send
        self.bridge = SpeechDelivery(self.ctx)
        self.bridge.register()
        self.ctx.platform_callback(SimpleNamespace(bot=self.adapter), None)

    async def asyncTearDown(self):
        self.bridge.close()
        await asyncio.sleep(0)
        tasks = [task for task, _ in self.bridge.tasks.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.temp.cleanup()

    @staticmethod
    def incoming(message='10', thread='7', voice=True, text='Расскажи', user='42', chat='42'):
        return SimpleNamespace(source=SimpleNamespace(platform='telegram', chat_id=chat, user_id=user,
            chat_type='dm', thread_id=thread, message_id=message), message_id=message,
            message_type='voice' if voice else 'text', text=text, internal=False)

    async def bind(self, *, turn='turn', session='session', event=None, parent='', user_message='Вопрос', context_session=True):
        event = event or self.incoming()
        await self.bridge.inbound(event)
        values = {'ID': session, 'PLATFORM': 'telegram', 'CHAT_ID': event.source.chat_id,
                  'THREAD_ID': event.source.thread_id, 'USER_ID': event.source.user_id,
                  'MESSAGE_ID': event.source.message_id, 'KEY': 'gateway-session'}
        if not context_session:
            values.pop('ID')
        variables = [contextvars.ContextVar('HERMES_SESSION_' + k) for k in values]
        tokens = [var.set(value) for var, value in zip(variables, values.values())]
        try:
            self.bridge.before(session_id=session, turn_id=turn, sender_id=event.source.user_id,
                platform='telegram', parent_session_id=parent, user_message=user_message, conversation_history=[])
        finally:
            for var, token in zip(variables, tokens):
                var.reset(token)

    async def finish(self, *, turn='turn', original='Полный исходный ответ: 2026 год.'):
        result = self.bridge.after(session_id='session', turn_id=turn, response_text=original)
        self.assertIsNone(result)
        await self.drain()

    async def drain(self):
        await asyncio.sleep(0)
        tasks = [task for task, _ in self.bridge.tasks.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_full_original_preserved_order_origin_and_cleanup(self):
        await self.bind()
        original = 'Не включайте питание. Дата: 2026-10-04. Стоимость: 230 рублей.'
        await self.finish(original=original)
        calls = self.adapter.send_voice.call_args_list
        self.assertEqual([Path(c.kwargs['voice'].name).name for c in calls],
                         ['part-0.ogg', 'part-1.ogg', 'part-2.ogg'])
        for call in calls:
            self.assertEqual(call.kwargs['chat_id'], 42)
            self.assertEqual(call.kwargs['reply_to_message_id'], 10)
            self.assertEqual(call.kwargs['message_thread_id'], 7)
            self.assertFalse(Path(call.kwargs['voice'].name).exists())
        self.assertEqual(self.bridge.sources.get(original)['original'], original)
        self.adapter.send.assert_not_called()
        with self.bridge.sources.db() as db:
            self.assertEqual(db.execute('SELECT state,sent FROM delivery_jobs').fetchone(), ('delivered', 3))

    async def test_cached_agent_without_context_session_id_keeps_exact_origin(self):
        await self.bind(context_session=False)
        await self.finish()
        self.assertEqual(self.adapter.send_voice.call_count, 3)

    async def test_platform_factory_identity_changes_after_plugin_reload(self):
        first = self.ctx.platform_callback
        self.bridge.close()
        self.bridge = SpeechDelivery(self.ctx)
        self.bridge.register()
        replacement = self.ctx.platform_callback
        self.assertNotEqual(first.__qualname__, replacement.__qualname__)
        self.assertIsNone(self.bridge.loop)
        replacement(SimpleNamespace(bot=self.adapter), None)
        await self.bind()
        await self.finish()
        self.assertEqual(self.adapter.send_voice.call_count, 3)

    async def test_unbound_platform_logs_safe_reason_and_never_synthesizes(self):
        await self.bind()
        self.bridge.loop = self.bridge.bot = None
        with self.assertLogs(self.bridge.logger, level='WARNING') as logs:
            await self.finish()
        self.assertIn('platform_unavailable', logs.output[0])
        self.assertNotIn('Полный исходный ответ', logs.output[0])
        self.adapter.send_voice.assert_not_called()
        with self.bridge.sources.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM delivery_jobs').fetchone()[0], 0)

    async def test_owner_inbound_restores_unbound_standalone_platform_once(self):
        self.bridge.loop = self.bridge.bot = None
        transport = SimpleNamespace(rewire_plugin_handlers=Mock(
            side_effect=lambda: self.ctx.platform_callback(SimpleNamespace(bot=self.adapter), None)))
        gateway = SimpleNamespace(adapters={'telegram': transport}, config=SimpleNamespace(multiplex_profiles=False))
        await self.bridge.inbound(self.incoming(), gateway=gateway)
        await self.bridge.inbound(self.incoming(message='11'), gateway=gateway)
        transport.rewire_plugin_handlers.assert_called_once_with()
        await self.bind()
        await self.finish()
        self.assertEqual(self.adapter.send_voice.call_count, 3)

    async def test_foreign_owner_never_requests_platform_rewire(self):
        self.bridge.loop = self.bridge.bot = None
        transport = SimpleNamespace(rewire_plugin_handlers=Mock())
        await self.bridge.inbound(self.incoming(user='99'),
            gateway=SimpleNamespace(adapters={'telegram': transport}))
        transport.rewire_plugin_handlers.assert_not_called()
        self.assertIsNone(self.bridge.bot)

    async def test_multiplex_without_exact_identity_never_borrows_default_transport(self):
        self.bridge.loop = self.bridge.bot = None
        transport = SimpleNamespace(rewire_plugin_handlers=Mock())
        gateway = SimpleNamespace(adapters={'telegram': transport}, config=SimpleNamespace(multiplex_profiles=True))
        with patch.dict(sys.modules, {'gateway.session_identity': SimpleNamespace(identity_of=lambda source: None)}):
            await self.bridge.inbound(self.incoming(), gateway=gateway)
        transport.rewire_plugin_handlers.assert_not_called()
        self.assertIsNone(self.bridge.bot)

    async def test_multiplex_recovers_only_exact_receiving_transport(self):
        self.bridge.loop = self.bridge.bot = None
        receiving = SimpleNamespace(rewire_plugin_handlers=Mock(
            side_effect=lambda: self.ctx.platform_callback(SimpleNamespace(bot=self.adapter), None)))
        default = SimpleNamespace(rewire_plugin_handlers=Mock())
        gateway = SimpleNamespace(adapters={'telegram': default}, config=SimpleNamespace(multiplex_profiles=True))
        identity = SimpleNamespace(adapter=lambda: receiving)
        with patch.dict(sys.modules, {'gateway.session_identity': SimpleNamespace(identity_of=lambda source: identity)}):
            await self.bridge.inbound(self.incoming(), gateway=gateway)
        receiving.rewire_plugin_handlers.assert_called_once_with()
        default.rewire_plugin_handlers.assert_not_called()
        self.assertIs(self.bridge.bot, self.adapter)

    async def test_partial_delivery_failure_reports_once_without_retry(self):
        self.adapter.send_voice.side_effect = [SimpleNamespace(message_id=101), RuntimeError('uncertain_delivery')]
        await self.bind()
        await self.finish()
        self.assertEqual(self.adapter.send_voice.call_count, 2)
        self.assertEqual(self.adapter.send.call_count, 1)
        self.assertIn('1 из 3', self.adapter.send.call_args.kwargs['text'])
        await self.bind()
        await self.finish()
        self.assertEqual(self.adapter.send_voice.call_count, 2)
        with self.bridge.sources.db() as db:
            self.assertEqual(db.execute('SELECT state,sent FROM delivery_jobs').fetchone(), ('failed', 1))

    async def test_same_topic_turns_are_ordered_and_different_origins_retained(self):
        await self.bind(turn='a', event=self.incoming(message='10'))
        await self.bind(turn='b', event=self.incoming(message='11'))
        self.bridge.after(session_id='session', turn_id='a', response_text='Первый ответ.')
        self.bridge.after(session_id='session', turn_id='b', response_text='Второй ответ.')
        await self.drain()
        self.assertEqual([call.kwargs['reply_to_message_id'] for call in self.adapter.send_voice.call_args_list],
                         [10, 10, 10, 11, 11, 11])

    async def test_outside_owner_scope_subagents_and_text_only_do_not_speak(self):
        for i, options in enumerate([
            {'event': self.incoming(user='99')}, {'event': self.incoming(chat='99')},
            {'parent': 'parent'}, {'event': self.incoming(voice=False)},
            {'event': self.incoming(text='Ответь только текстом')},
            {'user_message': '[Голосовое] Расскажи без озвучки'},
        ]):
            turn = str(i)
            await self.bind(turn=turn, **options)
            await self.finish(turn=turn)
        self.adapter.send_voice.assert_not_called()
        self.assertEqual(list((self.root / 'audio').iterdir()), [])

    async def test_missing_task_origin_never_borrows_another_message(self):
        await self.bridge.inbound(self.incoming(message='10'))
        self.bridge.before(session_id='session', turn_id='turn', sender_id='42', platform='telegram')
        await self.finish()
        self.adapter.send_voice.assert_not_called()

    async def test_voice_commands_persist_and_skip_native_command(self):
        response = await self.bridge.inbound(self.incoming(text='/voice off', voice=False))
        self.assertEqual(response['action'], 'skip')
        await self.bind()
        await self.finish()
        self.adapter.send_voice.assert_not_called()
        other = SpeechDelivery(self.ctx)
        self.assertEqual(other._mode(), 'off')
        await self.bridge.inbound(self.incoming(text='/voice tts', voice=False))
        self.assertEqual(other._mode(), 'all')
        await self.bind(turn='all', event=self.incoming(voice=False))
        await self.finish(turn='all')
        self.assertEqual(self.adapter.send_voice.call_count, 3)
        other.close()

    async def test_explicit_tool_returns_segments_without_duplicate_auto_delivery(self):
        await self.bind()
        downstream = Mock()
        raw = self.bridge.execute_tool('text_to_speech', {'text': 'Скажи: 230 вольт.'}, downstream,
                                      session_id='session', turn_id='turn')
        payload = json.loads(raw)
        self.assertTrue(payload['success'])
        self.assertEqual(len(payload['file_paths']), 3)
        self.assertTrue(all(Path(p).is_file() for p in payload['file_paths']))
        self.assertEqual(payload['media_tag'].count('MEDIA:'), 3)
        downstream.assert_not_called()
        again = json.loads(self.bridge.execute_tool('text_to_speech', {'text': 'Повтори'}, downstream,
                                      session_id='session', turn_id='turn'))
        self.assertFalse(again['success'])
        await self.finish()
        self.adapter.send_voice.assert_not_called()
        with self.bridge.sources.db() as db:
            self.assertEqual(db.execute('SELECT state FROM delivery_jobs').fetchone()[0], 'prepared')

    async def test_explicit_failure_does_not_fall_back_or_trigger_auto(self):
        self.renderer.write_text('raise SystemExit(1)')
        await self.bind()
        downstream = Mock()
        payload = json.loads(self.bridge.execute_tool('text_to_speech', {'text': 'Ответ'}, downstream,
                                      session_id='session', turn_id='turn'))
        self.assertFalse(payload['success'])
        downstream.assert_not_called()
        await self.finish()
        self.adapter.send_voice.assert_not_called()
        self.assertEqual(list((self.root / 'audio').iterdir()), [])

    async def test_status_failure_after_synthesis_never_escapes_to_native_provider(self):
        await self.bind()
        original_status = self.bridge._status
        def broken_status(job, state, sent=0):
            if state in {'prepared', 'failed'}:
                raise RuntimeError('database unavailable')
            return original_status(job, state, sent)
        self.bridge._status = broken_status
        downstream = Mock()
        payload = json.loads(self.bridge.execute_tool('text_to_speech', {'text': 'Ответ'}, downstream,
                                      session_id='session', turn_id='turn'))
        self.assertFalse(payload['success'])
        downstream.assert_not_called()
        self.assertEqual(list((self.root / 'audio').iterdir()), [])

    async def test_stop_isolates_topic_and_cancels_explicit_process(self):
        first, other = Mock(), Mock()
        proc_first, proc_other = SimpleNamespace(pid=100), SimpleNamespace(pid=200)
        self.bridge.tasks = {'a': (first, {'chat_id': '42', 'thread_id': '7'}),
                             'b': (other, {'chat_id': '42', 'thread_id': '8'})}
        self.bridge.processes = {'explicit_a': proc_first, 'explicit_b': proc_other}
        self.bridge.process_routes = {'explicit_a': {'chat_id': '42', 'thread_id': '7'},
                                      'explicit_b': {'chat_id': '42', 'thread_id': '8'}}
        self.bridge._kill = Mock()
        await self.bridge.inbound(self.incoming(text='/stop', thread='7', voice=False))
        first.cancel.assert_called_once()
        other.cancel.assert_not_called()
        self.bridge._kill.assert_called_once_with(proc_first)
        self.bridge.tasks.clear()
        self.bridge.processes.clear()

    async def test_stop_before_scheduled_auto_task_prevents_synthesis(self):
        await self.bind()
        self.bridge.after(session_id='session', turn_id='turn', response_text='Ответ')
        await self.bridge.inbound(self.incoming(text='/stop', voice=False))
        await self.drain()
        self.adapter.send_voice.assert_not_called()
        self.assertEqual(list((self.root / 'audio').iterdir()), [])

    async def test_stop_during_explicit_preparation_prevents_provider_spawn(self):
        await self.bind()
        entered, resume = threading.Event(), threading.Event()
        original_prepare = self.bridge._prepare
        def slow_prepare(*args):
            result = original_prepare(*args)
            entered.set()
            resume.wait(2)
            return result
        self.bridge._prepare = slow_prepare
        with patch('bridges.hermes_speech.delivery.subprocess.Popen') as spawn:
            rendering = asyncio.create_task(asyncio.to_thread(self.bridge.execute_tool, 'text_to_speech',
                {'text': 'Ответ'}, Mock(), session_id='session', turn_id='turn'))
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            await self.bridge.inbound(self.incoming(text='/stop', voice=False))
            resume.set()
            payload = json.loads(await rendering)
            self.assertEqual(payload['error'], 'speech_cancelled')
            spawn.assert_not_called()

    async def test_unowned_tools_pass_through_once(self):
        downstream = Mock(return_value='ordinary result')
        result = self.bridge.execute_tool('text_to_speech', {'text': 'Текст'}, downstream,
                                          session_id='other', turn_id='other')
        self.assertEqual(result, 'ordinary result')
        downstream.assert_called_once_with({'text': 'Текст'})

    async def test_invalid_manifest_never_sends_audio(self):
        self.renderer.write_text(self.renderer.read_text().replace('[180,240,300]', '[180,300.001,300]'))
        await self.bind()
        await self.finish()
        self.adapter.send_voice.assert_not_called()
        self.adapter.send.assert_called_once()

    async def test_manifest_accepts_three_to_five_minutes_and_short_final_part(self):
        directory = self.root / 'manifest'
        directory.mkdir()
        paths = []
        for index in range(4):
            path = directory / f'part-{index}.ogg'
            path.write_bytes(b'OggS')
            paths.append(str(path))
        payload = {'success': True, 'file_paths': paths, 'durations': [180, 240, 300, 0.01]}
        self.assertEqual(self.bridge._manifest(json.dumps(payload), directory), paths)

    async def test_manifest_rejects_out_of_range_or_nonfinite_duration(self):
        directory = self.root / 'manifest'
        directory.mkdir()
        path = directory / 'part.ogg'
        path.write_bytes(b'OggS')
        for duration in (300.000001, 0, -1, float('inf'), float('-inf'), float('nan'), True, '180'):
            with self.subTest(duration=duration):
                payload = {'success': True, 'file_paths': [str(path)], 'durations': [duration]}
                with self.assertRaisesRegex(ValueError, '^invalid_speech_audio_segment$'):
                    self.bridge._manifest(json.dumps(payload), directory)

    async def test_unload_cancels_active_synthesis_and_kills_separate_child_group(self):
        pid_file = self.root / 'child.pid'
        self.renderer.write_text('''import subprocess,sys,time
from pathlib import Path
p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True)
Path(sys.argv[1]).write_text(str(p.pid))
time.sleep(60)
''')
        self.bridge.argv = [sys.executable, str(self.renderer), str(pid_file)]
        await self.bind()
        self.bridge.after(session_id='session', turn_id='turn', response_text='Ответ')
        for _ in range(100):
            if pid_file.exists():
                break
            await asyncio.sleep(.01)
        self.assertTrue(pid_file.exists())
        child_pid = int(pid_file.read_text())
        self.bridge.close()
        await self.drain()
        self.adapter.send_voice.assert_not_called()
        self.adapter.send.assert_not_called()
        self.assertFalse(self.bridge.processes)
        child_stat = Path(f'/proc/{child_pid}/stat')
        if child_stat.exists():
            self.assertEqual(child_stat.read_text().split()[2], 'Z')
        self.assertEqual(list((self.root / 'audio').iterdir()), [])
