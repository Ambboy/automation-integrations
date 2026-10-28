"""Independent offline probes; candidate and live sources stay unchanged."""
import asyncio
import copy
import json
import unittest
from unittest.mock import AsyncMock, patch
from telegram import Update
from telegram.ext import MessageHandler, filters
from hermes_cli.plugins import PluginContext
from hermes_cli.plugins_manifest import PluginManifest, parse_manifest_file
import plugin
from tests import test_native as native

class ReviewProbes(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = native.NativeTests.asyncSetUp
    asyncTearDown = native.NativeTests.asyncTearDown
    dispatch = native.NativeTests.dispatch

    async def test_preformatted_and_quoted_slashes_are_not_controls(self):
        cases = [
            ('pre', {'type': 'pre', 'text': '/stop'}),
            ('inline-code', {'type': 'paragraph', 'text': {'type': 'code', 'text': '/stop'}}),
            ('expandable_blockquote', {'type': 'expandable_blockquote', 'text': '/stop'}),
            ('pullquote', {'type': 'pullquote', 'text': '/stop'}),
        ]
        for i, (name, block) in enumerate(cases, 100):
            with self.subTest(name=name):
                original = native.incoming(self.app.bot, uid=i, rich_message={'blocks': [block]})
                before = copy.deepcopy(original.to_dict())
                normalized = plugin.normalize(original)
                await self.dispatch(original)
                event = self.adapter.delivered[-1]
                intercepted = AsyncMock()
                with patch.object(self.adapter, '_dispatch_active_session_command', intercepted):
                    await self.adapter._handle_message_while_active(event, 'review-synthetic-session')
                print('CONTROL_PROBE', json.dumps({'case': name, 'text': event.text,
                    'entities': [e.to_dict() for e in normalized.message.entities],
                    'type': str(event.message_type), 'command': event.get_command(),
                    'native_stop_branch': intercepted.await_count, 'original_unchanged': original.to_dict() == before}))
                self.assertFalse(event.is_command(), 'Quoted/preformatted content became gateway control')

    async def test_plain_code_baseline_already_uses_text_control(self):
        await self.dispatch(native.incoming(self.app.bot, text='/stop',
            entities=[{'type': 'pre', 'offset': 0, 'length': 5}]))
        event = self.adapter.delivered[-1]
        print('PLAIN_CODE_BASELINE', str(event.message_type), event.get_command())
        self.assertEqual(event.get_command(), 'stop')

    async def test_structured_blockquote_and_semantic_command_controls(self):
        await self.dispatch(native.incoming(self.app.bot, uid=101, rich_message={
            'blocks': [{'type': 'blockquote', 'blocks': [{'type': 'paragraph', 'text': '/stop'}]}]}))
        self.assertFalse(self.adapter.delivered[-1].is_command())
        await self.dispatch(native.incoming(self.app.bot, uid=102, rich_message={
            'blocks': [{'type': 'paragraph', 'text': {'type': 'bot_command', 'text': '/status', 'bot_command': '/status'}}]}))
        self.assertEqual(self.adapter.delivered[-1].get_command(), 'status')

    async def test_full_unload_directory_reload_preserves_native_handlers(self):
        core_ids = self.adapter._core_handler_ids.copy()
        core_callbacks = {id(h): h.callback for group in self.app.handlers.values() for h in group if id(h) in core_ids}
        keys = []
        for cycle in range(4):
            self.manager.unload()
            await asyncio.sleep(0)
            self.assertFalse(any(h.check_update(native.incoming(self.app.bot, rich_message=native.rich())) for h in self.app.handlers[0]))
            manifest = parse_manifest_file(native.ROOT/'plugin.yaml', native.ROOT, 'user', '')
            self.manager._load_plugin(manifest)
            self.assertTrue(self.manager._plugins[native.NAME].enabled)
            self.adapter.rewire_plugin_handlers()
            self.adapter.rewire_plugin_handlers()
            factories = self.manager.get_platform_handler_factories('telegram')
            self.assertEqual(len(factories), 1)
            keys.append(repr(factories[0][0]))
            update = native.incoming(self.app.bot, uid=200+cycle, rich_message=native.rich('cycle '+str(cycle)))
            self.assertEqual(sum(bool(h.check_update(update)) for h in self.app.handlers[0]), 1)
            await self.dispatch(update)
            self.assertEqual(len(self.adapter.delivered), cycle+1)
        self.assertEqual(len(set(keys)), 4)
        self.manager.unload(native.NAME)
        await asyncio.sleep(0)
        after = {id(h):h.callback for group in self.app.handlers.values() for h in group}
        self.assertEqual(after, core_callbacks)
        await self.dispatch(native.incoming(self.app.bot, uid=210, rich_message=native.rich('disabled')))
        self.assertEqual(len(self.adapter.delivered), 4)
        await self.dispatch(native.incoming(self.app.bot, uid=211, text='native stays'))
        self.assertEqual(self.adapter.delivered[-1].text, 'native stays')
        print('LIFECYCLE', json.dumps({'full_reload_cycles': 4, 'unique_keys': len(set(keys)),
             'native_callbacks_unchanged': True, 'cache_entries': len(self.adapter._plugin_handlers_wired),
             'disabled_residual_factories': len(self.manager.get_platform_handler_factories('telegram'))}))

    async def test_rich_only_nested_list_real_handoff_and_disabled_baseline(self):
        value = {'blocks': [{'type': 'paragraph', 'text': 'Copied items'},
            {'type': 'list', 'items': [{'label': '1.', 'blocks': [
                {'type': 'paragraph', 'text': 'Outer'}, {'type': 'list', 'items': [
                    {'label': '•', 'blocks': [{'type': 'paragraph', 'text': 'Inner'}]}]}]},
                {'label': '2.', 'blocks': [{'type': 'paragraph', 'text': 'Last'}]}]}]}
        original = native.incoming(self.app.bot, uid=300, thread=777, rich_message=value)
        before = copy.deepcopy(original.to_dict())
        await self.dispatch(original)
        self.assertEqual(len(self.adapter.delivered), 1)
        event = self.adapter.delivered[0]
        self.assertEqual(event.text, 'Copied items\n\n1. Outer\n   \n   • Inner\n2. Last')
        self.assertEqual(str(event.source.thread_id), '777')
        self.assertEqual(original.to_dict(), before)
        self.manager.unload(native.NAME)
        await self.dispatch(native.incoming(self.app.bot, uid=301, thread=777, rich_message=value))
        self.assertEqual(len(self.adapter.delivered), 1)
        print('MAIN_LIST', json.dumps({'enabled_handoffs': 1, 'disabled_extra_handoffs': 0,
            'text': event.text, 'original_unchanged': original.to_dict() == before}))

    async def test_first_match_does_not_evaluate_later_handlers(self):
        calls = []
        class LaterFilter(filters.UpdateFilter):
            def filter(self, update):
                calls.append('checked')
                raise RuntimeError('later filter must not run after first native match')
        async def later(update, context):
            raise AssertionError('later callback must never run')
        later_handler = MessageHandler(LaterFilter(), later)
        self.app.add_handler(later_handler, 0)
        await self.dispatch(native.incoming(self.app.bot, uid=400, text='baseline'))
        self.assertEqual(calls, [])
        await self.app.process_update(native.incoming(self.app.bot, uid=401, rich_message=native.rich('rich')))
        print('FIRST_MATCH', json.dumps({'later_filter_calls': len(calls), 'errors': [str(e) for e in self.errors],
                                        'delivered': [e.text for e in self.adapter.delivered]}))
        self.assertEqual(calls, [], 'Bridge evaluated handlers after first native match')
