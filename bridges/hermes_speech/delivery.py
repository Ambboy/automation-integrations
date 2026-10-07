"""Ordered speech segments, with a captured origin and no changes to Hermes core.

The final-output hook only queues work and returns None. The ordinary text reply
is untouched; platform delivery happens asynchronously after speech preparation.
Native auto-TTS must be disabled for the owner chat when this mode is enabled.
"""
import asyncio
import contextvars
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid

from .speech_source import Sources


_TEXT_ONLY = re.compile(r'только\s+текст(?:ом)?|без\s+(?:озвучки|голоса)|не\s+озвучивай|не\s+надо\s+голосом', re.I)
_MODES = {'on': 'voice_only', 'enable': 'voice_only', 'tts': 'all',
          'off': 'off', 'disable': 'off'}
_MODE_TEXT = {'voice_only': 'Озвучка ответов на голосовые сообщения включена.',
              'all': 'Озвучка всех ответов включена.', 'off': 'Озвучка отключена.'}


def _value(value):
    return str(getattr(value, 'value', value) or '')


class SpeechDelivery:
    def __init__(self, ctx):
        self.ctx = ctx
        self.sources = Sources(ctx.get_config('state_dir'))
        self.owner = str(ctx.get_config('owner_id'))
        self.chat = str(ctx.get_config('chat_id', self.owner))
        self.argv = ctx.get_config('tts_argv')
        if not isinstance(self.argv, list) or not self.argv or not all(isinstance(x, str) for x in self.argv):
            raise ValueError('speech_tts_argv_required')
        self.audio_root = Path(ctx.get_config('audio_dir', str(self.sources.root / 'audio')))
        self.audio_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.audio_root.is_absolute() or self.audio_root.is_symlink() or self.audio_root.stat().st_mode & 0o077:
            raise ValueError('private_speech_audio_directory_required')
        # Explicit tool artifacts must outlive the tool result for native MEDIA
        # delivery. Reclaim only this plugin's old directories on activation.
        cutoff = time.time() - 24 * 3600
        for directory in self.audio_root.glob('reply-*'):
            if directory.is_dir() and not directory.is_symlink() and directory.stat().st_mtime < cutoff:
                shutil.rmtree(directory, ignore_errors=True)
        self.synthesis_timeout = float(ctx.get_config('synthesis_timeout', 5400))
        self.delivery_timeout = float(ctx.get_config('delivery_timeout', 60))
        self.default_mode = ctx.get_config('default_mode', 'voice_only')
        if self.default_mode not in _MODE_TEXT:
            raise ValueError('invalid_speech_default_mode')
        self.logger = logging.getLogger(__name__)
        self.lock = threading.RLock()
        self.incoming, self.pending, self.tasks, self.processes = {}, {}, {}, {}
        self.queued = {}
        self.process_routes = {}
        self.route_locks = {}
        self.stopped = threading.Event()
        self.loop = self.bot = None
        with self.sources.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS delivery_jobs '
                       '(job TEXT PRIMARY KEY, state TEXT, sent INTEGER, created REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS delivery_preferences '
                       '(chat TEXT PRIMARY KEY, mode TEXT)')

    def register(self):
        # Hermes deduplicates native factories by (plugin, qualname), even after
        # unloading and recreating this object. This factory only captures the
        # transport; it installs no native handlers. Give each activation its
        # own identity so a rewire can bind the replacement instance.
        def bind_platform(native, adapter):
            self.platform_ready(native, adapter)
        bind_platform.__qualname__ = f'SpeechDelivery.platform_ready_{uuid.uuid4().hex}'
        self.ctx.register_platform_handler('telegram', bind_platform)
        self.ctx.register_hook('pre_gateway_dispatch', self.inbound)
        self.ctx.register_hook('pre_llm_call', self.before)
        self.ctx.register_hook('transform_llm_output', self.after)
        self.ctx.register_hook('agent_loop_stopped', self.interrupted)
        self.ctx.register_middleware('tool_execution', self.execute_tool)
        self.ctx.on_unload(self.close)

    def platform_ready(self, native, adapter):
        # Called on the gateway's event loop. The adapter is never modified.
        self.loop, self.bot = asyncio.get_running_loop(), native.bot

    def _mode(self):
        with self.sources.db() as db:
            row = db.execute('SELECT mode FROM delivery_preferences WHERE chat=?', (self.chat,)).fetchone()
        return row[0] if row else self.default_mode

    @staticmethod
    def _origin_key(route):
        return tuple(route[k] for k in ('chat_id', 'thread_id', 'user_id', 'message_id'))

    def _origin(self, event):
        source = event.source
        if (_value(source.platform) != 'telegram' or str(source.chat_id) != self.chat
                or str(source.user_id) != self.owner
                or _value(getattr(source, 'chat_type', '')) not in {'dm', 'private'}
                or getattr(event, 'internal', False)):
            return None
        route = {k: str(getattr(source, k, '') or '') for k in ('chat_id', 'thread_id', 'user_id')}
        route['message_id'] = str(getattr(source, 'message_id', None) or getattr(event, 'message_id', '') or '')
        return route if route['message_id'] else None

    @staticmethod
    def _send_options(route):
        metadata = {'chat_id': int(route['chat_id']), 'reply_to_message_id': int(route['message_id'])}
        if route['thread_id']:
            metadata['message_thread_id'] = int(route['thread_id'])
        return metadata

    async def _notice(self, route, content):
        if self.bot is None or self.stopped.is_set():
            return
        try:
            await asyncio.wait_for(self.bot.send_message(text=content, **self._send_options(route)),
                                   self.delivery_timeout)
        except Exception:
            self.logger.warning('Speech notice delivery failed; no automatic resend')

    async def inbound(self, event, **kwargs):
        route = self._origin(event)
        if route is None or self.stopped.is_set():
            return
        if self.loop is None or self.bot is None or self.loop.is_closed():
            # A same-name force reload may omit Hermes' plugin-loaded event.
            # The public inbound gateway and adapter rewire API can restore our
            # transport on the loop without touching the native handler table.
            gateway = kwargs.get('gateway')
            adapter = None
            try:
                from gateway.session_identity import identity_of
                identity = identity_of(event.source)
                if identity is not None:
                    adapter = identity.adapter()
            except ImportError:
                pass
            if adapter is None and not getattr(getattr(gateway, 'config', None), 'multiplex_profiles', False):
                adapters = getattr(gateway, 'adapters', {})
                adapter = next((value for platform, value in adapters.items()
                                if _value(platform) == 'telegram'), None)
            if adapter is not None:
                try:
                    adapter.rewire_plugin_handlers()
                except Exception:
                    self.logger.warning('Segmented speech rebind failed: platform_unavailable')
        text = str(getattr(event, 'text', '') or '')
        command = text.split(maxsplit=1)
        if command and command[0].split('@')[0].lower() == '/voice':
            arg = command[1].strip().lower() if len(command) > 1 else ''
            mode = self._mode()
            if arg in _MODES or not arg:
                mode = _MODES[arg] if arg else ('voice_only' if mode == 'off' else 'off')
                with self.sources.db() as db:
                    db.execute('INSERT OR REPLACE INTO delivery_preferences VALUES(?,?)', (self.chat, mode))
                if mode == 'off':
                    self._cancel_chat(self.chat)
            elif arg != 'status':
                await self._notice(route, 'Режимы озвучки: /voice on, /voice tts, /voice off, /voice status.')
                return {'action': 'skip', 'reason': 'segmented_speech_voice_command'}
            await self._notice(route, _MODE_TEXT[mode])
            return {'action': 'skip', 'reason': 'segmented_speech_voice_command'}
        if command and command[0].split('@')[0].lower() == '/stop':
            self._cancel_chat(self.chat, thread=route['thread_id'])
            return
        if text.startswith('/'):
            return
        with self.lock:
            now = time.monotonic()
            self.incoming = {key: item for key, item in self.incoming.items() if item['created'] > now - 600}
            if len(self.incoming) >= 128:
                return
            self.incoming[self._origin_key(route)] = {
                'created': now, 'route': route, 'voice': _value(getattr(event, 'message_type', '')) == 'voice',
                'text_only': bool(_TEXT_ONLY.search(text)),
            }

    def before(self, **event):
        if (self.stopped.is_set() or event.get('platform') != 'telegram'
                or str(event.get('sender_id')) != self.owner or event.get('parent_session_id')):
            return
        turn = (event.get('session_id'), event.get('turn_id'))
        if not all(turn):
            return
        # Require actual task-local bindings, never a process environment fallback.
        bound = {var.name: value for var, value in contextvars.copy_context().items()}
        if (bound.get('HERMES_SESSION_ID') not in (None, '', turn[0])
                or bound.get('HERMES_SESSION_PLATFORM') != 'telegram'):
            return
        route = {k: str(bound.get('HERMES_SESSION_' + k.upper(), '') or '')
                 for k in ('chat_id', 'thread_id', 'user_id', 'message_id')}
        route['session_key'] = str(bound.get('HERMES_SESSION_KEY', '') or '')
        with self.lock:
            item = self.incoming.pop(self._origin_key(route), None)
            if item is None:
                return
            history = [m for m in event.get('conversation_history', []) if m.get('role') in ('user', 'assistant')][-4:]
            context = json.dumps({'question': event.get('user_message'),
                                  'recent': [str(m.get('content') or '') for m in history]}, ensure_ascii=False)[-12000:]
            item['text_only'] = item['text_only'] or bool(_TEXT_ONLY.search(str(event.get('user_message') or '')))
            item.update(route=route, context=context, explicit=False)
            now = time.monotonic()
            self.pending = {key: value for key, value in self.pending.items() if value['created'] > now - 3600}
            if len(self.pending) < 128:
                self.pending[turn] = item

    def _claim(self, job):
        with self.sources.db() as db:
            return db.execute('INSERT OR IGNORE INTO delivery_jobs VALUES(?,?,?,?)',
                              (job, 'queued', 0, time.time())).rowcount == 1

    def _status(self, job, state, sent=0):
        with self.sources.db() as db:
            db.execute('UPDATE delivery_jobs SET state=?, sent=? WHERE job=?', (state, sent, job))

    def after(self, **event):
        turn = (event.get('session_id'), event.get('turn_id'))
        with self.lock:
            item = self.pending.pop(turn, None)
        original = event.get('response_text')
        if (item is None or item['explicit'] or item['text_only'] or self.stopped.is_set()
                or not isinstance(original, str) or not original.strip()
                or 'MEDIA:' in original or '[[audio_as_voice]]' in original):
            return
        mode = self._mode()
        if mode == 'off' or (mode == 'voice_only' and not item['voice']):
            return
        job = json.dumps(['auto', *turn])
        if self.loop is None or self.bot is None or self.loop.is_closed():
            self.logger.warning('Segmented speech skipped: platform_unavailable; no synthesis attempted')
            return
        if not self._claim(job):
            return
        with self.lock:
            self.queued[job] = item
        # call_soon_threadsafe captures the calling profile's contextvars.
        self.loop.call_soon_threadsafe(self._start, job, item, original)
        return None

    def _start(self, job, item, original):
        with self.lock:
            self.queued.pop(job, None)
        if self.stopped.is_set() or item.get('cancelled'):
            self._status(job, 'cancelled')
            return
        task = self.loop.create_task(self._deliver(job, item, original))
        self.tasks[job] = (task, item['route'])
        task.add_done_callback(lambda _: self.tasks.pop(job, None))

    def _prepare(self, job, original, context):
        if self.stopped.is_set():
            raise ValueError('speech_plugin_unloaded')
        directory = Path(tempfile.mkdtemp(prefix='reply-', dir=self.audio_root))
        try:
            source = directory / 'input.txt'
            source.write_text(original, encoding='utf-8')
            source.chmod(0o600)
            self.sources.put(job, original, original, context)
            output_dir = directory / 'audio'
            output_dir.mkdir(mode=0o700)
            argv = [arg.replace('{input_file}', str(source)).replace('{output_dir}', str(output_dir)) for arg in self.argv]
            self._status(job, 'synthesizing')
            return directory, argv
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    @staticmethod
    def _manifest(stdout, directory):
        payload = json.loads(stdout)
        paths, durations = payload.get('file_paths'), payload.get('durations')
        if (payload.get('success') is not True or not isinstance(paths, list) or not paths
                or not isinstance(durations, list) or len(paths) != len(durations)):
            raise ValueError('invalid_speech_parts_manifest')
        validated = []
        for path, duration in zip(paths, durations):
            p = Path(path)
            if (not p.is_absolute() or p.is_symlink() or not p.resolve().is_relative_to(directory.resolve())
                    or p.suffix != '.ogg' or not p.is_file() or p.stat().st_size == 0
                    or isinstance(duration, bool) or not isinstance(duration, (int, float))
                    or not math.isfinite(duration) or not 0 < duration <= 300):
                raise ValueError('invalid_speech_audio_segment')
            validated.append(str(p))
        if len(set(validated)) != len(validated):
            raise ValueError('duplicate_speech_audio_segment')
        return validated

    @staticmethod
    def _kill(proc):
        # The renderer's rewrite/conversion helpers may create their own process
        # groups. Snapshot descendants first, then reap every captured group.
        descendants = []
        pending = [proc.pid]
        while pending:
            parent = pending.pop()
            try:
                children = [int(pid) for pid in Path(f'/proc/{parent}/task/{parent}/children').read_text().split()]
            except (OSError, ValueError):
                children = []
            descendants.extend(children)
            pending.extend(children)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for pid in descendants:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    async def _render_async(self, job, argv, directory, route):
        proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, stdin=asyncio.subprocess.DEVNULL, start_new_session=True)
        with self.lock:
            self.processes[job] = proc
            self.process_routes[job] = route
        try:
            if self.stopped.is_set():
                raise asyncio.CancelledError()
            stdout, _ = await asyncio.wait_for(proc.communicate(), self.synthesis_timeout)
            if proc.returncode:
                raise ValueError('speech_synthesis_failed')
            return self._manifest(stdout, directory)
        finally:
            if proc.returncode is None:
                self._kill(proc)
                await proc.wait()
            with self.lock:
                self.processes.pop(job, None)
                self.process_routes.pop(job, None)

    async def _deliver(self, job, item, original):
        directory, sent, paths = None, 0, []
        route = item['route']
        route_key = (route['chat_id'], route['thread_id'])
        route_lock = self.route_locks.setdefault(route_key, asyncio.Lock())
        try:
            async with route_lock:
                if self.stopped.is_set() or self._mode() == 'off':
                    self._status(job, 'cancelled')
                    return
                directory, argv = self._prepare(job, original, item['context'])
                paths = await self._render_async(job, argv, directory, route)
                self._status(job, 'ready')
                for path in paths:
                    if self.stopped.is_set() or self._mode() == 'off':
                        raise asyncio.CancelledError()
                    self._status(job, 'sending', sent)
                    # Use the public PTB transport. The native adapter falls back
                    # to send_document on an uncertain send_voice outcome, which
                    # could duplicate an already accepted voice message.
                    with open(path, 'rb') as audio:
                        result = await asyncio.wait_for(self.bot.send_voice(
                            voice=audio, **self._send_options(route)), self.delivery_timeout)
                    if not getattr(result, 'message_id', None):
                        raise ValueError('speech_delivery_failed')
                    sent += 1
                    self._status(job, 'sending', sent)
                self._status(job, 'delivered', sent)
        except asyncio.CancelledError:
            self._status(job, 'cancelled', sent)
            raise
        except Exception:
            self._status(job, 'failed', sent)
            self.logger.warning('Segmented speech failed; sent=%s; no automatic retry', sent)
            message = (f'Озвучка прервалась: подтверждена отправка {sent} из {len(paths)} фрагментов. '
                       'Текст ответа сохранён; автоматически не повторяю.') if paths else (
                       'Не удалось подготовить озвучку. Текст ответа сохранён; автоматически не повторяю.')
            await self._notice(route, message)
        finally:
            if directory is not None:
                shutil.rmtree(directory, ignore_errors=True)

    def execute_tool(self, tool_name, args, next_call, **event):
        turn = (event.get('session_id'), event.get('turn_id'))
        with self.lock:
            item = self.pending.get(turn)
            if tool_name == 'text_to_speech' and item is not None:
                # Set before any work, so a failed explicit call cannot become auto-TTS.
                item['explicit'] = True
        if tool_name != 'text_to_speech' or item is None:
            return next_call(args)
        directory = None
        claimed = False
        job = json.dumps(['tool', *turn])
        try:
            if item['text_only']:
                raise ValueError('speech_disabled_for_text_only_turn')
            if item.get('cancelled'):
                raise ValueError('speech_cancelled')
            claimed = self._claim(job)
            if not claimed:
                raise ValueError('speech_already_attempted_for_turn')
            original = args.get('text')
            if not isinstance(original, str) or not original.strip():
                raise ValueError('speech_text_required')
            directory, argv = self._prepare(job, original, item['context'])
            if item.get('cancelled'):
                raise ValueError('speech_cancelled')
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    stdin=subprocess.DEVNULL, start_new_session=True)
            with self.lock:
                self.processes[job] = proc
                self.process_routes[job] = item['route']
            try:
                if self.stopped.is_set() or item.get('cancelled'):
                    raise ValueError('speech_cancelled')
                stdout, _ = proc.communicate(timeout=self.synthesis_timeout)
                if proc.returncode:
                    raise ValueError('speech_synthesis_failed')
                paths = self._manifest(stdout, directory)
            finally:
                if proc.poll() is None:
                    self._kill(proc)
                    proc.communicate()
                with self.lock:
                    self.processes.pop(job, None)
                    self.process_routes.pop(job, None)
            self._status(job, 'prepared')
            (directory / 'input.txt').unlink(missing_ok=True)
            # Native MEDIA delivery still needs these files. They are retained
            # for a day and reclaimed on a later plugin activation.
            return json.dumps({'success': True, 'file_path': paths[0], 'file_paths': paths,
                'media_tag': '[[audio_as_voice]]\n' + '\n '.join('MEDIA:' + p for p in paths),
                'provider': 'automation-speech', 'voice_compatible': True,
                'delivery_file_count': len(paths), 'combined_chunks': False}, ensure_ascii=False)
        except Exception as exc:
            # Never raise: Hermes middleware fails open on exceptions and would run
            # the original provider a second time, with uncertain paid outcomes.
            if claimed:
                try:
                    self._status(job, 'failed')
                except Exception:
                    self.logger.warning('Speech failure status could not be saved; no provider fallback')
            if directory is not None:
                shutil.rmtree(directory, ignore_errors=True)
            error = str(exc) if isinstance(exc, ValueError) else 'speech_preparation_failed'
            return json.dumps({'success': False, 'error': error}, ensure_ascii=False)

    def _cancel_chat(self, chat, thread=None):
        def matches(route):
            return route.get('chat_id') == chat and (thread is None or route.get('thread_id') == thread)
        for task, route in list(self.tasks.values()):
            if matches(route):
                task.cancel()
        with self.lock:
            for item in [*self.pending.values(), *self.queued.values()]:
                if matches(item['route']):
                    item['cancelled'] = True
            processes = [proc for job, proc in self.processes.items()
                         if matches(self.process_routes.get(job, {}))]
        for proc in processes:
            self._kill(proc)

    def interrupted(self, session_key, **kwargs):
        if self.loop is None or self.loop.is_closed():
            return
        def cancel():
            for task, route in list(self.tasks.values()):
                if route.get('session_key') == session_key:
                    task.cancel()
            with self.lock:
                for item in [*self.pending.values(), *self.queued.values()]:
                    if item['route'].get('session_key') == session_key:
                        item['cancelled'] = True
                processes = [proc for job, proc in self.processes.items()
                             if self.process_routes.get(job, {}).get('session_key') == session_key]
            for proc in processes:
                self._kill(proc)
        self.loop.call_soon_threadsafe(cancel)

    def close(self):
        self.stopped.set()
        with self.lock:
            processes = list(self.processes.values())
            self.incoming.clear()
            self.pending.clear()
            self.queued.clear()
        for proc in processes:
            self._kill(proc)
        if self.loop is not None and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self._cancel_chat, self.chat)
