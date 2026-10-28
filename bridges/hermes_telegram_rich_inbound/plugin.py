"""Rich-only Telegram ingress bridge; no core imports, mutations, or outbound IO."""
import asyncio
import inspect
import json
import math
import logging
import re
import uuid

LOG = logging.getLogger('automation.telegram_rich_inbound')
MESSAGE_FIELDS = ('message', 'edited_message', 'channel_post', 'edited_channel_post')


class CompatibilityError(RuntimeError):
    """Installed native dispatch contract no longer satisfies the bridge."""


MAX_DEPTH = 32
MAX_NODES = 4096
MAX_CHARS = 32768
TEXT_STYLES = {'bold', 'italic', 'underline', 'strikethrough', 'spoiler',
               'subscript', 'superscript', 'marked'}


class RichError(ValueError):
    pass


def _validate_budget(value):
    """Bound every branch, including unknown fields, before rendering or JSON fallback."""
    nodes = chars = 0

    def visit(item, depth):
        nonlocal nodes, chars
        nodes += 1
        if depth > MAX_DEPTH:
            raise RichError('depth limit exceeded')
        if nodes > MAX_NODES:
            raise RichError('node limit exceeded')
        if isinstance(item, str):
            chars += len(item)
            if chars > MAX_CHARS:
                raise RichError('input text limit exceeded')
        elif isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise RichError('non-string object key')
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child, depth + 1)
        elif item is None or isinstance(item, bool):
            pass
        elif isinstance(item, int):
            if item.bit_length() > 256:
                raise RichError('numeric limit exceeded')
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise RichError('non-finite number')
        else:
            raise RichError('non-JSON content')
    visit(value, 0)


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _extras(value, used):
    rest = {key: item for key, item in value.items() if key not in used}
    return ' [rich metadata: ' + _json(rest) + ']' if rest else ''


def _join(parts, separator=''):
    chunks, size = [], 0
    for part in parts:
        size += len(part) + (len(separator) if chunks else 0)
        if size > MAX_CHARS:
            raise RichError('output limit exceeded')
        chunks.append(part)
    return separator.join(chunks)


def _code(text, *, block=False):
    # Visible delimiters are essential: the gateway recognizes controls from text,
    # independently of Telegram entities. Do not flatten code into leading '/...'.
    longest = max((len(m.group()) for m in re.finditer(r'`+', text)), default=0)
    fence = '`' * max(3 if block else 1, longest + 1)
    pad = '\n' if block else (' ' if text.startswith('`') or text.endswith('`') else '')
    return _join((fence, pad, text, pad, fence))


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return _join(_text(item) for item in value)
    if not isinstance(value, dict):
        raise RichError('invalid RichText')
    kind = value.get('type')
    if kind in TEXT_STYLES:
        return _text(value['text']) + _extras(value, {'type', 'text'})
    if kind == 'code':
        return _code(_text(value['text'])) + _extras(value, {'type', 'text'})
    targets = {'url': 'url', 'email_address': 'email_address', 'phone_number': 'phone_number',
               'bank_card_number': 'bank_card_number', 'mention': 'username',
               'hashtag': 'hashtag', 'cashtag': 'cashtag', 'bot_command': 'bot_command'}
    if kind in targets:
        key = targets[kind]
        label, target = _text(value['text']), value[key]
        if not isinstance(target, str):
            raise RichError('invalid inline target')
        return label + (f' ({target})' if label != target else '') + _extras(value, {'type', 'text', key})
    return '[unsupported rich text: ' + _json(value) + ']'


def _blocks(value):
    if not isinstance(value, (list, tuple)):
        raise RichError('invalid block list')
    return _join((_block(item) for item in value), '\n\n')


def _block(value):
    if not isinstance(value, dict):
        raise RichError('invalid block')
    kind = value.get('type')
    if kind in {'paragraph', 'heading', 'footer'}:
        return _text(value['text']) + _extras(value, {'type', 'text'})
    if kind == 'pre':
        return _code(_text(value['text']), block=True) + _extras(value, {'type', 'text'})
    if kind in {'expandable_blockquote', 'pullquote'}:
        return _join(('> ' + line for line in _text(value['text']).split('\n')), '\n') + _extras(value, {'type', 'text'})
    if kind == 'divider':
        return '---' + _extras(value, {'type'})
    if kind == 'blockquote':
        return _join(('> ' + line for line in _blocks(value['blocks']).split('\n')), '\n') + _extras(value, {'type', 'blocks'})
    if kind == 'list':
        if not isinstance(value['items'], (list, tuple)):
            raise RichError('invalid list items')
        lines, size = [], 0
        for item in value['items']:
            if not isinstance(item, dict) or not isinstance(item.get('label'), str):
                raise RichError('invalid list item')
            label = item['label']
            checkbox = ('[x] ' if item.get('is_checked') else '[ ] ') if item.get('has_checkbox') else ''
            content = checkbox + _blocks(item['blocks'])
            # Keep all metadata, including value/type and unusual checkbox states.
            content += _extras(item, {'label', 'blocks'})
            prefix = label + ' '
            rows = content.split('\n')
            line = _join((prefix + rows[0], _join('\n' + ' ' * len(prefix) + row for row in rows[1:])))
            size += len(line) + bool(lines)
            if size > MAX_CHARS:
                raise RichError('output limit exceeded')
            lines.append(line)
        return _join(lines, '\n') + _extras(value, {'type', 'items'})
    return '[unsupported rich block: ' + _json(value) + ']'


def render_rich(value):
    """Return readable content or an explicit bounded failure; never silently truncate."""
    try:
        _validate_budget(value)
        if not isinstance(value, dict):
            raise RichError('invalid RichMessage')
        text = _blocks(value['blocks']) + _extras(value, {'blocks'})
        if len(text) > MAX_CHARS:
            raise RichError('output limit exceeded')
        return text or '[rich_message empty]'
    except RichError as error:
        return '[rich_message error: ' + str(error) + '; content not rendered]'
    except (KeyError, TypeError, ValueError):
        return '[rich_message error: malformed content; content not rendered]'


def _leading_semantic_command(value):
    """First rendered inline node only; caller has already validated/rendered it."""
    if isinstance(value, (list, tuple)):
        for item in value:
            if _text(item):
                return _leading_semantic_command(item)
    elif isinstance(value, dict):
        kind = value.get('type')
        if kind in TEXT_STYLES:
            return _leading_semantic_command(value['text'])
        if kind == 'bot_command':
            target = value['bot_command']
            if re.fullmatch(r'/[A-Za-z0-9_]+(?:@[A-Za-z0-9_]+)?', target) and _text(value['text']) == target:
                return target
    return None


def normalize(update):
    """Copy public PTB representations, never alter the received update or SDK objects."""
    from telegram import Update
    field = next((key for key in MESSAGE_FIELDS if getattr(update, key, None) is not None), None)
    if field is None:
        raise CompatibilityError('Rich ingress has no supported native message slot')
    message = getattr(update, field)
    data = update.to_dict()
    message_data = data[field]
    payload = getattr(message, 'rich_message', None) or message.api_kwargs.get('rich_message')
    text = render_rich(payload)
    message_data['text'] = text
    # Any preexisting entity offsets refer to absent text, not our new representation.
    entities = []
    # No inference from arbitrary rendered '/...'. Only a complete semantic command
    # at offset zero in an unquoted text block can acquire a bot_command entity.
    # A leading slash also proves render_rich succeeded (all errors begin with '[').
    if text.startswith('/') and payload['blocks'][0].get('type') in {'paragraph', 'heading', 'footer'}:
        command = _leading_semantic_command(payload['blocks'][0]['text'])
        if command and text.startswith(command) and (len(text) == len(command) or text[len(command)].isspace()):
            entities.append({'type': 'bot_command', 'offset': 0, 'length': len(command)})
    message_data['entities'] = entities
    data[field] = message_data
    return Update.de_json(data, update.get_bot())


def matching_handler(application, adapter, normalized, own):
    """Select only the first match; compatibility may inspect official filters only."""
    from telegram.ext import MessageHandler
    handlers = tuple(h for h in application.handlers.get(0, ()) if h is not own)
    official = tuple(h for h in handlers if isinstance(h, MessageHandler)
                     and getattr(inspect.unwrap(h.callback), '__self__', None) is adapter)
    error = 'Rich ingress incompatible: no matching official group-0 MessageHandler; disable plugin and run compatibility tests'
    if not official:
        raise CompatibilityError(error)
    checked = {}
    selected = None
    for handler in handlers:
        check = handler.check_update(normalized)
        checked[id(handler)] = check
        if check is not None and check is not False:
            selected = (handler, check)
            break  # Later third-party filters are unreachable in real PTB dispatch.
    # Retain the matching-official compatibility gate without evaluating any
    # unreachable third-party filter (or checking a selected core filter twice).
    for handler in official:
        check = checked[id(handler)] if id(handler) in checked else handler.check_update(normalized)
        if check is not None and check is not False:
            return selected
    raise CompatibilityError(error)


class Wiring:
    """Own one SDK registration; stable instance key permits real unload/re-enable."""
    def __init__(self):
        self.key = uuid.uuid4().hex
        self.active = True
        self.bindings = []

    def __repr__(self):
        # Hermes keys callable instances by repr when no function qualname exists.
        return f'RichInboundWiring({self.key})'

    def __call__(self, application, adapter):
        import telegram
        from telegram.ext import MessageHandler, filters
        if telegram.__version__ != '22.8':
            raise CompatibilityError('Rich ingress requires reviewed PTB 22.8; run version-scoped tests before updating the plugin pin')
        if not all(callable(getattr(application, name, None)) for name in ('add_handler', 'remove_handler')):
            raise CompatibilityError('Rich ingress requires native PTB handler registration APIs')
        if not self.active or any(app is application for app, _, _ in self.bindings):
            return
        owner = self

        class RichOnly(filters.UpdateFilter):
            def filter(self, update):
                if not owner.active or not any(getattr(update, key, None) is not None for key in MESSAGE_FIELDS):
                    return False
                message = update.effective_message
                return bool(message is not None and message.text is None and message.caption is None
                            and not message.effective_attachment
                            and (getattr(message, 'rich_message', None) is not None
                                 or 'rich_message' in message.api_kwargs))

        async def receive(update, context):
            if not owner.active:
                return
            try:
                normalized = normalize(update)
                target, check = matching_handler(application, adapter, normalized, handler)
                await target.handle_update(normalized, application, check, context)
            except CompatibilityError:
                LOG.error('Rich ingress compatibility failure; run offline compatibility probe before enabling')
                raise

        loop = asyncio.get_running_loop()  # Fail before registration if called off-loop.
        handler = MessageHandler(RichOnly(), receive, block=True)
        application.add_handler(handler, group=0)
        self.bindings.append((application, handler, loop))

    def close(self):
        self.active = False  # Immediately prevents dispatch even if cleanup is cross-thread.
        bindings, self.bindings = self.bindings, []
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        for application, handler, loop in bindings:
            if loop is current or not loop.is_running():
                application.remove_handler(handler, group=0)
            else:
                loop.call_soon_threadsafe(application.remove_handler, handler, 0)


def register(ctx):
    wiring = Wiring()
    ctx.on_unload(wiring.close)
    ctx.register_platform_handler('telegram', wiring)
