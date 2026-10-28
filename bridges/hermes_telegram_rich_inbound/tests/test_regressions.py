"""R1/R2 regressions at the native boundary; no live gateway or external effects."""
import asyncio
import copy
import unittest
from unittest.mock import AsyncMock, patch

from gateway.platforms.event import MessageType
from telegram.ext import MessageHandler, filters

import plugin
from tests import test_native as native


def semantic(command='/stop'):
    return {'type': 'bot_command', 'text': command, 'bot_command': command}


class RegressionTests(unittest.IsolatedAsyncioTestCase):
    # Reuse fixtures without importing/inheriting a TestCase into discovery twice.
    asyncSetUp = native.NativeTests.asyncSetUp
    asyncTearDown = native.NativeTests.asyncTearDown
    dispatch = native.NativeTests.dispatch
    own_handler = native.NativeTests.own_handler

    async def assert_native_control(self, payload, expected_text, command, uid=100):
        original = native.incoming(self.app.bot, uid=uid, rich_message=payload)
        before = copy.deepcopy(original.to_dict())
        normalized = plugin.normalize(original)
        await self.dispatch(original)
        event = self.adapter.delivered[-1]
        intercepted = AsyncMock()
        # Only the effectful cancel/reply boundary is replaced, not native control selection.
        with patch.object(self.adapter, '_dispatch_active_session_command', intercepted):
            await self.adapter._handle_message_while_active(event, f'offline-control-{uid}')
        self.assertEqual(original.to_dict(), before)
        self.assertEqual(normalized.message.text, expected_text)
        # Native text batching strips outer whitespace; test it, not an invented lossless handoff.
        self.assertEqual(event.text, expected_text.strip())
        self.assertEqual(event.get_command(), command)
        self.assertEqual(intercepted.await_count, int(command == 'stop'))
        if command == 'stop':
            self.assertEqual(intercepted.await_args.args[-1], 'stop')
        else:
            self.assertFalse(event.is_command())
        return normalized, event

    async def test_reviewer_four_boundaries_never_dispatch_stop(self):
        cases = [
            ('pre', {'type': 'pre', 'text': '/stop'}, '```\n/stop\n```'),
            ('inline-code', {'type': 'paragraph', 'text': {'type': 'code', 'text': '/stop'}}, '`/stop`'),
            ('expandable_blockquote', {'type': 'expandable_blockquote', 'text': '/stop'}, '> /stop'),
            ('pullquote', {'type': 'pullquote', 'text': '/stop'}, '> /stop'),
        ]
        for uid, (name, block, expected) in enumerate(cases, 100):
            with self.subTest(case=name):
                normalized, event = await self.assert_native_control({'blocks': [block]}, expected, None, uid)
                self.assertEqual(normalized.message.entities, ())
                self.assertEqual(event.message_type, MessageType.TEXT)

    async def test_semantic_stop_keeps_entity_and_native_stop_branch(self):
        normalized, event = await self.assert_native_control(native.rich(semantic()), '/stop', 'stop')
        self.assertEqual([e.to_dict() for e in normalized.message.entities],
                         [{'type': 'bot_command', 'offset': 0, 'length': 5}])
        self.assertEqual(event.message_type, MessageType.COMMAND)

    async def test_bare_paragraph_stop_keeps_core_text_control_without_entity(self):
        normalized, event = await self.assert_native_control(native.rich('/stop'), '/stop', 'stop')
        self.assertEqual(normalized.message.entities, ())
        self.assertEqual(event.message_type, MessageType.TEXT)

    async def test_entities_require_complete_leading_semantic_command(self):
        positive = [semantic(), [semantic('/stop@offline_bot'), ' now'],
                    {'type': 'bold', 'text': ['', semantic(), ' now']}]
        for text in positive:
            with self.subTest(positive=text):
                message = plugin.normalize(native.incoming(self.app.bot, rich_message=native.rich(text))).message
                self.assertEqual(len(message.entities), 1)
                self.assertEqual(message.entities[0].type, 'bot_command')
                self.assertEqual(message.entities[0].offset, 0)
                self.assertEqual(message.parse_entity(message.entities[0]), message.text.split()[0])
        negative = [
            '/stop', ['/', 'stop'], {'type': 'bold', 'text': '/stop'},
            {'type': 'url', 'text': '/stop', 'url': 'https://example.invalid'},
            {'type': 'bot_command', 'text': '/stop', 'bot_command': '/status'},
            semantic('/stop?'), [semantic('/st'), 'op'], ['prefix ', semantic()],
            {'type': 'code', 'text': semantic()},
        ]
        for text in negative:
            with self.subTest(negative=text):
                message = plugin.normalize(native.incoming(self.app.bot, rich_message=native.rich(text))).message
                self.assertEqual(message.entities, ())

    async def test_nested_semantic_nodes_stay_inside_code_and_quote(self):
        blocks = [
            {'type': 'pre', 'text': semantic()},
            {'type': 'expandable_blockquote', 'text': {'type': 'bold', 'text': semantic()}},
            {'type': 'pullquote', 'text': semantic()},
            {'type': 'blockquote', 'blocks': [native.rich(semantic())['blocks'][0]]},
            {'type': 'paragraph', 'text': [' \n', {'type': 'code', 'text': semantic()}]},
        ]
        for uid, block in enumerate(blocks, 200):
            with self.subTest(block=block):
                normalized = plugin.normalize(native.incoming(self.app.bot, rich_message={'blocks': [block]}))
                await self.assert_native_control({'blocks': [block]}, normalized.message.text, None, uid)
                self.assertEqual(normalized.message.entities, ())

    async def test_empty_leading_block_cannot_expose_quoted_stop(self):
        for uid, kind in enumerate(('pre', 'expandable_blockquote', 'pullquote'), 300):
            payload = {'blocks': [native.rich('')['blocks'][0], {'type': kind, 'text': ' \n/stop'}]}
            normalized = plugin.normalize(native.incoming(self.app.bot, rich_message=payload))
            await self.assert_native_control(payload, normalized.message.text, None, uid)
            self.assertEqual(normalized.message.entities, ())

    async def test_exact_late_raising_filter_is_not_touched(self):
        calls = []
        class LaterFilter(filters.UpdateFilter):
            def filter(self, update):
                calls.append('checked')
                raise RuntimeError('later filter must not run after first native match')
        async def later(update, context):
            raise AssertionError('later callback must never run')
        self.app.add_handler(MessageHandler(LaterFilter(), later), 0)
        await self.dispatch(native.incoming(self.app.bot, uid=400, text='baseline'))
        self.assertEqual(calls, [])
        await self.app.process_update(native.incoming(self.app.bot, uid=401, rich_message=native.rich('rich')))
        await asyncio.gather(*list(self.adapter._pending_text_batch_tasks.values()))
        self.assertEqual(calls, [])
        self.assertEqual(self.errors, [])
        self.assertEqual([e.text for e in self.adapter.delivered], ['baseline', 'rich'])

    async def test_prior_guard_wins_without_touching_unreachable_third_party_filter(self):
        calls = []
        async def guard(update, context): calls.append(('guard', update.effective_message.text))
        class LaterFilter(filters.UpdateFilter):
            def filter(self, update):
                if update.effective_message.text is not None:
                    raise AssertionError('unreachable filter after prior guard')
                return False
        async def later(update, context): raise AssertionError('unreachable callback')
        existing = tuple(self.app.handlers[0])
        for handler in existing: self.app.remove_handler(handler, 0)
        self.app.add_handler(MessageHandler(filters.TEXT, guard), 0)
        self.app.add_handler(MessageHandler(LaterFilter(), later), 0)
        for handler in existing: self.app.add_handler(handler, 0)
        await self.dispatch(native.incoming(self.app.bot, rich_message=native.rich('Guarded')))
        self.assertEqual(calls, [('guard', 'Guarded')])
        self.assertEqual(self.adapter.delivered, [])

    async def test_prior_guard_does_not_hide_absent_official_handler(self):
        import inspect
        guarded = []
        async def guard(update, context): guarded.append(update)
        for handler in tuple(self.app.handlers[0]):
            if getattr(inspect.unwrap(handler.callback), '__self__', None) is self.adapter:
                self.app.remove_handler(handler, 0)
        self.app.add_handler(MessageHandler(filters.TEXT, guard), 0)
        with self.assertLogs(plugin.LOG, level='ERROR'):
            await self.app.process_update(native.incoming(self.app.bot, rich_message=native.rich('Guarded')))
        self.assertEqual(len(self.errors), 1)
        self.assertIsInstance(self.errors[0], plugin.CompatibilityError)
        self.assertIn('official', str(self.errors[0]))
        self.assertEqual(guarded, [])
        self.assertEqual(self.adapter.delivered, [])
