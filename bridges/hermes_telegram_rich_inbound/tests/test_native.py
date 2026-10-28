"""Synthetic offline integration. Only final model handoff is a test subclass seam."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from telegram import Update
from telegram.ext import Application
from telegram.request import BaseRequest
from gateway.config import PlatformConfig
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.plugins import PluginContext, get_plugin_manager
from hermes_cli.plugins_manifest import PluginManifest
from plugins.platforms.telegram.adapter import TelegramAdapter
from plugins.platforms.telegram.update_admission import TelegramApplication
import plugin

NAME = 'automation-telegram-rich-inbound'
ROOT = Path(__file__).resolve().parents[1]

class NoNetwork(BaseRequest):
    @property
    def read_timeout(self): return 1
    async def initialize(self): pass
    async def shutdown(self): pass
    async def do_request(self, url, method, request_data=None, **kwargs):
        assert url.rsplit('/', 1)[-1] == 'getMe', 'No send, poll, or model transport allowed'
        return 200, json.dumps({'ok': True, 'result': {
            'id': 111, 'is_bot': True, 'first_name': 'Synthetic fixture', 'username': 'offline_bot'
        }}).encode()

class CaptureAdapter(TelegramAdapter):
    def __init__(self):
        super().__init__(PlatformConfig(enabled=True, token='111:synthetic-offline', extra={'require_mention': False}))
        self.delivered = []
    def _start_session_processing(self, event, session_key, **kwargs):
        self.delivered.append(event)
        return True
    async def _set_status_indicator(self, *args, **kwargs):
        pass  # Outbound effect boundary only.


def incoming(bot, uid=1, user=88, thread=None, **content):
    msg = {'message_id': 472, 'date': 1800000000,
           'chat': {'id': 42, 'type': 'private'},
           'from': {'id': user, 'is_bot': False, 'first_name': 'Synthetic fixture'}, **content}
    if thread is not None:
        msg.update(message_thread_id=thread, is_topic_message=True)
    return Update.de_json({'update_id': uid, 'message': msg}, bot)


def rich(text='Hello rich'):
    return {'blocks': [{'type': 'paragraph', 'text': text}]}


class NativeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='offline-', dir=os.environ['TMPDIR'])
        self.home_token = set_hermes_home_override(Path(self.temp.name))
        self.env = patch.dict(os.environ, {'TELEGRAM_ALLOWED_USERS': '88', 'TELEGRAM_ALLOW_ALL_USERS': 'false'})
        self.env.start()
        self.manager = get_plugin_manager()
        self.context = PluginContext(PluginManifest(name=NAME, key=NAME, path=str(ROOT)), self.manager)
        self.adapter = CaptureAdapter()
        self.app = (Application.builder().token('111:synthetic-offline')
                    .application_class(TelegramApplication, {'adapter': self.adapter})
                    .request(NoNetwork()).get_updates_request(NoNetwork()).build())
        self.adapter._app = self.app
        self.adapter._bot = self.app.bot
        self.errors = []
        async def error(update, context): self.errors.append(context.error)
        self.app.add_error_handler(error)
        plugin.register(self.context)
        self.adapter._wire_plugin_handlers(self.app)
        self.adapter._register_handlers(self.app)
        await self.app.initialize()
        self.adapter._mark_connected()
        self.adapter._text_batch_delay_seconds = 0.001
        self.adapter._text_batch_split_delay_seconds = 0.001
        async def forbidden_model(event): raise AssertionError('Model work forbidden')
        self.adapter.set_message_handler(forbidden_model)

    async def asyncTearDown(self):
        self.manager.unload()
        await asyncio.sleep(0)
        for task in list(self.adapter._pending_text_batch_tasks.values()): task.cancel()
        await asyncio.gather(*self.adapter._pending_text_batch_tasks.values(), return_exceptions=True)
        if self.adapter._update_receipt_flush is not None:
            await self.adapter._update_receipt_flush
        await self.app.shutdown()
        self.env.stop()
        reset_hermes_home_override(self.home_token)
        self.temp.cleanup()

    async def dispatch(self, update):
        await self.app.process_update(update)
        await asyncio.gather(*list(self.adapter._pending_text_batch_tasks.values()))
        self.assertEqual(self.errors, [])

    async def test_plain_positive_control(self):
        await self.dispatch(incoming(self.app.bot, text='Hello plain'))
        self.assertEqual([e.text for e in self.adapter.delivered], ['Hello plain'])

    async def test_rich_reaches_actual_core_handoff(self):
        await self.dispatch(incoming(self.app.bot, rich_message=rich()))
        self.assertEqual([e.text for e in self.adapter.delivered], ['Hello rich'])

    async def test_unauthorized_rejected_before_batching(self):
        await self.dispatch(incoming(self.app.bot, user=99, rich_message=rich()))
        self.assertEqual(self.adapter.delivered, [])
        self.assertEqual(self.adapter._pending_text_batches, {})

    async def test_identity_topic_and_original_unchanged(self):
        import copy
        original = incoming(self.app.bot, thread=777, rich_message=rich('Topic text'))
        before = copy.deepcopy(original.to_dict())
        normalized = plugin.normalize(original)
        self.assertIsNot(original, normalized)
        self.assertIsNot(original.message, normalized.message)
        actual = normalized.to_dict()
        actual['message'].pop('text')
        actual['message'].pop('entities', None)
        self.assertEqual(actual, before)
        self.assertEqual(normalized.effective_user.id, 88)
        self.assertEqual(normalized.effective_chat.id, 42)
        self.assertEqual(normalized.update_id, original.update_id)
        await self.dispatch(original)
        self.assertEqual(original.to_dict(), before)
        event = self.adapter.delivered[0]
        self.assertEqual(event.message_id, '472')
        self.assertEqual(str(event.source.user_id), '88')
        self.assertEqual(str(event.source.chat_id), '42')
        self.assertEqual(str(event.source.thread_id), '777')

    async def test_duplicate_updates_actual_admission_sequential(self):
        update = incoming(self.app.bot, rich_message=rich())
        await self.dispatch(update)
        await self.dispatch(update)
        self.assertEqual(len(self.adapter.delivered), 1)
        self.assertEqual(self.adapter._updates_dispatched_total, 2)
        self.assertIn('111:1', self.adapter._seen_update_ids)

    async def test_duplicate_updates_actual_admission_concurrent(self):
        update = incoming(self.app.bot, rich_message=rich())
        await asyncio.gather(self.app.process_update(update), self.app.process_update(update))
        await asyncio.gather(*list(self.adapter._pending_text_batch_tasks.values()))
        self.assertEqual(len(self.adapter.delivered), 1)
        self.assertEqual(self.errors, [])

    def own_handler(self):
        factories = self.manager.get_platform_handler_factories('telegram')
        active = [factory for factory, name in factories if name == NAME and factory.active]
        self.assertEqual(len(active), 1)
        return active[0].bindings[0][1]

    async def test_plain_command_media_and_callbacks_not_claimed(self):
        handler = self.own_handler()
        for content in (
            {'text': 'plain', 'rich_message': rich()},
            {'text': '/status', 'entities': [{'type': 'bot_command', 'offset': 0, 'length': 7}]},
            {'caption': 'caption', 'rich_message': rich()},
            {'photo': [{'file_id': 'synthetic', 'file_unique_id': 'synthetic', 'width': 1, 'height': 1}], 'rich_message': rich()},
            {'location': {'latitude': 0.0, 'longitude': 0.0}, 'rich_message': rich()},
        ):
            with self.subTest(content=content):
                self.assertFalse(handler.check_update(incoming(self.app.bot, **content)))
        callback = Update.de_json({'update_id': 500, 'callback_query': {
            'id': 'synthetic', 'from': {'id': 88, 'is_bot': False, 'first_name': 'Synthetic'},
            'chat_instance': 'synthetic', 'data': 'synthetic',
            'message': incoming(self.app.bot, rich_message=rich()).message.to_dict()}}, self.app.bot)
        self.assertFalse(handler.check_update(callback))

    async def test_original_command_native_path_untouched(self):
        from gateway.platforms.event import MessageType
        await self.dispatch(incoming(self.app.bot, text='/status', entities=[{'type': 'bot_command', 'offset': 0, 'length': 7}]))
        self.assertEqual(len(self.adapter.delivered), 1)
        self.assertEqual(self.adapter.delivered[0].message_type, MessageType.COMMAND)

    async def test_rich_semantic_command_uses_native_command_path(self):
        from gateway.platforms.event import MessageType
        await self.dispatch(incoming(self.app.bot, rich_message=rich({
            'type': 'bot_command', 'text': '/status', 'bot_command': '/status'})))
        self.assertEqual(len(self.adapter.delivered), 1)
        self.assertEqual(self.adapter.delivered[0].message_type, MessageType.COMMAND)
        self.assertEqual(self.adapter.delivered[0].text, '/status')

    async def test_late_rewire_unload_reenable_no_duplicate_dispatch(self):
        self.manager.unload(NAME)
        self.assertFalse(any(h.check_update(incoming(self.app.bot, rich_message=rich())) for h in self.app.handlers[0]))
        plugin.register(self.context)
        for _ in range(3): self.adapter.rewire_plugin_handlers()
        factory = [f for f, name in self.manager.get_platform_handler_factories('telegram') if name == NAME and f.active][0]
        factory(self.app, self.adapter)  # Direct repeated wiring is also idempotent.
        self.assertEqual(len(factory.bindings), 1)
        update = incoming(self.app.bot, rich_message=rich('Late'))
        self.assertEqual(sum(bool(h.check_update(update)) for h in self.app.handlers[0]), 1)
        await self.dispatch(update)
        self.assertEqual([e.text for e in self.adapter.delivered], ['Late'])
        self.manager.unload(NAME)
        await self.dispatch(incoming(self.app.bot, uid=2, rich_message=rich('Disabled')))
        self.assertEqual([e.text for e in self.adapter.delivered], ['Late'])
        await self.dispatch(incoming(self.app.bot, uid=3, text='Still plain'))
        self.assertEqual([e.text for e in self.adapter.delivered], ['Late', 'Still plain'])

    async def test_missing_official_handler_is_explicit_compatibility_error(self):
        import inspect
        for handler in tuple(self.app.handlers[0]):
            if getattr(inspect.unwrap(handler.callback), '__self__', None) is self.adapter:
                self.app.remove_handler(handler, 0)
        with self.assertLogs(plugin.LOG, level='ERROR'):
            await self.app.process_update(incoming(self.app.bot, rich_message=rich()))
        self.assertEqual(len(self.errors), 1)
        self.assertIsInstance(self.errors[0], plugin.CompatibilityError)
        self.assertIn('no matching official', str(self.errors[0]))
        self.assertEqual(self.adapter.delivered, [])

    async def test_parser_error_reaches_authorized_core_handoff(self):
        await self.dispatch(incoming(self.app.bot, rich_message={'blocks': None}))
        self.assertIn('[rich_message error:', self.adapter.delivered[0].text)

    async def test_group_gate_not_bypassed(self):
        self.adapter.config.extra['require_mention'] = True
        data = incoming(self.app.bot, rich_message=rich('Unaddressed')).to_dict()
        data['message']['chat']['type'] = 'supergroup'
        await self.dispatch(Update.de_json(data, self.app.bot))
        self.assertEqual(self.adapter.delivered, [])

    async def test_real_directory_loader_manifest_and_late_wiring(self):
        from hermes_cli.plugins_manifest import parse_manifest_file, requires_hermes_error
        self.manager.unload(NAME)
        manifest = parse_manifest_file(ROOT / 'plugin.yaml', ROOT, 'user', '')
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest.requires_hermes, '==0.22.5')
        self.assertIsNone(requires_hermes_error(manifest))
        # Exercise installed directory loader in the disposable home, not production discovery.
        self.manager._load_plugin(manifest)
        loaded = self.manager._plugins[NAME]
        self.assertTrue(loaded.enabled, loaded.error)
        self.assertIsNotNone(loaded.module)
        self.adapter.rewire_plugin_handlers()
        await self.dispatch(incoming(self.app.bot, rich_message=rich('Loaded package')))
        self.assertEqual([e.text for e in self.adapter.delivered], ['Loaded package'])
        self.manager.unload(NAME)
        self.assertFalse(any(h.check_update(incoming(self.app.bot, rich_message=rich())) for h in self.app.handlers[0]))

    async def test_prior_native_guard_still_takes_precedence(self):
        from telegram.ext import MessageHandler, filters
        guarded = []
        async def guard(update, context): guarded.append(update.effective_message.text)
        existing = tuple(self.app.handlers[0])
        for handler in existing: self.app.remove_handler(handler, 0)
        self.app.add_handler(MessageHandler(filters.TEXT, guard), 0)
        for handler in existing: self.app.add_handler(handler, 0)
        await self.dispatch(incoming(self.app.bot, rich_message=rich('Guarded')))
        self.assertEqual(guarded, ['Guarded'])
        self.assertEqual(self.adapter.delivered, [])

    async def test_unload_from_other_thread_removes_only_owned_handlers(self):
        own = self.own_handler()
        before = [h for h in self.app.handlers[0] if h is not own]
        await asyncio.to_thread(self.manager.unload, NAME)
        await asyncio.sleep(0)
        self.assertEqual(self.app.handlers[0], before)

    async def test_edited_and_channel_slots_preserved(self):
        for slot in ('edited_message', 'channel_post', 'edited_channel_post'):
            with self.subTest(slot=slot):
                data = incoming(self.app.bot, rich_message=rich()).to_dict()
                data[slot] = data.pop('message')
                original = Update.de_json(data, self.app.bot)
                normalized = plugin.normalize(original)
                self.assertIsNone(normalized.message)
                self.assertEqual(getattr(normalized, slot).text, 'Hello rich')
                self.assertIsNone(getattr(original, slot).text)

