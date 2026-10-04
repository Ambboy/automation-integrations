"""Hermes speech binding using public hooks, middleware and platform delivery."""
import json
import logging
import threading
import time


def register(ctx):
    if not ctx.get_config('enabled', False):
        return
    if ctx.get_config('segmented_delivery', False):
        from .delivery import SpeechDelivery
        SpeechDelivery(ctx).register()
        return
    # Bundled alongside this plugin on deployment; standalone source is authoritative.
    from .speech_source import Sources
    from tools.tts_text_normalize import prepare_spoken_text
    sources = Sources(ctx.get_config('state_dir'))
    pending, lock = {}, threading.Lock()
    owner = str(ctx.get_config('owner_id'))

    def before(**event):
        if event.get('platform') != 'telegram' or str(event.get('sender_id')) != owner or event.get('parent_session_id'):
            return
        turn = (event.get('session_id'), event.get('turn_id'))
        if not all(turn):
            return
        # Last conversational context only, not system prompts or tool bodies.
        history = [m for m in event.get('conversation_history', []) if m.get('role') in ('user', 'assistant')]
        texts = [str(m.get('content') or '') for m in history[-4:]]
        context = json.dumps({'question': event.get('user_message'), 'recent': texts}, ensure_ascii=False)[-12000:]
        with lock:
            now = time.monotonic()
            for k in list(pending):
                if pending[k][0] < now - 600:
                    del pending[k]
            if len(pending) >= 128:
                return
            pending[turn] = (now, context)

    def after(**event):
        turn = (event.get('session_id'), event.get('turn_id'))
        with lock:
            item = pending.pop(turn, None)
        if item is None or event.get('platform') != 'telegram':
            return
        original = event.get('response_text')
        if not isinstance(original, str):
            return
        try:
            # Match both native cleaning passes exactly; the command handles one full reply.
            cleaned = prepare_spoken_text(prepare_spoken_text(original, max_chars=None), max_chars=None)
            sources.put(json.dumps(turn), cleaned, original, item[1])
        except Exception:
            logging.getLogger(__name__).warning('Speech raw source registration failed')
        return None  # preserve the displayed/persisted answer

    def before_tool(**event):
        if event.get('tool_name') != 'text_to_speech':
            return
        turn = (event.get('session_id'), event.get('turn_id'))
        with lock:
            item = pending.get(turn)
        original = (event.get('args') or {}).get('text')
        if item is None or not isinstance(original, str):
            return
        try:
            # Explicit tool calls pass through the cleaner once; auto-TTS twice.
            sources.put(json.dumps(turn), prepare_spoken_text(original, max_chars=None), original, item[1])
        except Exception:
            logging.getLogger(__name__).warning('Speech tool source registration failed')

    ctx.register_hook('pre_llm_call', before)
    ctx.register_hook('transform_llm_output', after)
    ctx.register_hook('pre_tool_call', before_tool)
