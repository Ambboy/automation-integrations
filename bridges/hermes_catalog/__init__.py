"""Native plugin: refresh discovery each turn; authorize again at every tool call."""
import contextvars
import hashlib
import json
import subprocess
import threading
import time
from pathlib import Path

from .catalog import Catalog


def register(ctx):
    if not ctx.get_config('enabled', False):
        return
    from hermes_constants import get_hermes_home
    home = Path(get_hermes_home()).resolve()
    owner = str(ctx.get_config('owner_id', ''))
    chat = str(ctx.get_config('chat_id', ''))
    catalog = Catalog(ctx.get_config('catalog_path'), ctx.get_config('state_dir'))
    runner = Path(ctx.get_config('runner_path')).resolve()
    write_runner = Path(ctx.get_config('write_runner_path', str(runner.with_name('api_write.py')))).resolve()
    private = Path(ctx.get_config('private_config')).resolve()
    service_cards = catalog.load()['services']
    service_ids = [item['id'] for item in service_cards]
    service_names = ', '.join(item['name'] for item in service_cards)

    def bounded_limit(name, default, maximum):
        value = ctx.get_config(name, default)
        if type(value) is not int or not 1024 <= value <= maximum:
            raise ValueError('invalid_plugin_payload_limit')
        return value

    read_request_limit = bounded_limit('max_request_chars', 12000, 2097152)
    write_request_limit = bounded_limit('max_write_request_chars', 262144, 2097152)
    read_output_limit = bounded_limit('max_read_output_chars', 70000, 1048576)
    write_output_limit = bounded_limit('max_write_output_chars', 100000, 1048576)
    # Hooks run on bounded native worker threads: ContextVar writes there do not
    # propagate back to the agent. Store admissions by authenticated session instead.
    admissions = {}
    lock = threading.Lock()

    def route():
        bound = {var.name: value for var, value in contextvars.copy_context().items()}
        from agent.delegation_context import is_delegated_child_context
        if is_delegated_child_context() or bound.get('hermes_non_dispatcher_owned_context'):
            return None, 'child_or_background_context'
        if Path(get_hermes_home()).resolve() != home:
            return None, 'home_mismatch'
        if (not owner or owner != chat or bound.get('HERMES_SESSION_PLATFORM') != 'telegram'
                or str(bound.get('HERMES_SESSION_CHAT_ID')) != chat
                or str(bound.get('HERMES_SESSION_USER_ID')) != owner
                or bound.get('HERMES_SESSION_CHAT_TYPE') != 'dm'):
            return None, 'owner_private_telegram_required'
        key, message = bound.get('HERMES_SESSION_KEY'), bound.get('HERMES_SESSION_MESSAGE_ID')
        if not key or not message:
            return None, 'message_context_missing'
        # Gateway binds these on EVERY inbound message, including cached agents.
        # SESSION_ID is only populated by new-agent construction/rotation.
        return (str(key), str(message), str(bound.get('HERMES_SESSION_THREAD_ID') or ''),
                str(bound.get('HERMES_SESSION_ID') or '')), None

    def before(**event):
        current, reason = route()
        if not current:
            return
        anchor = current[:3]
        with lock:
            admissions.pop(anchor, None)
        if (not event.get('session_id') or (current[3] and event['session_id'] != current[3])
                or event.get('parent_session_id') or event.get('platform') != 'telegram'
                or str(event.get('sender_id')) != owner):
            return
        with lock:
            now = time.monotonic()
            for key, value in list(admissions.items()):
                if value[0] < now:
                    admissions.pop(key, None)
            if len(admissions) >= 4096:
                return
            message = event.get('user_message')
            evidence = None
            if isinstance(message, str) and message.strip():
                evidence = {'source': 'native_owner_telegram', 'message_id': current[1],
                            'scope': [owner, chat, current[0], current[2]],
                            'text_sha256': hashlib.sha256(message.encode('utf-8')).hexdigest()}
            admissions[anchor] = (now + 3600, event['session_id'], evidence)
        confirmation = ''
        # Only the current, authenticated inbound message can approve a draft.
        # Model arguments, quoted history and tool output cannot grant consent.
        message = event.get('user_message')
        if isinstance(message, str) and message.startswith('ПОДТВЕРЖДАЮ '):
            confirmation = run_write({'action': 'confirm', 'confirmation_text': message}, current)
        try:
            return {'context': catalog.context() + ('\nWrite confirmation result: ' + confirmation if confirmation else '')}
        except Exception:
            return {'context': 'Реестр API временно недоступен. Не считать это отсутствием API/секретов.'}

    def authorization():
        current, reason = route()
        if not current:
            return None, reason
        with lock:
            admitted = admissions.get(current[:3])
        if not admitted or admitted[0] <= time.monotonic():
            return None, 'message_not_admitted'
        if current[3] and current[3] != admitted[1]:
            return None, 'session_mismatch'
        return current, None

    def denied(reason):
        return json.dumps({'ok': False, 'error': 'route_not_authorized',
                           'error_layer': 'local_authorization', 'reason': reason,
                           'provider_called': False})

    def authorized():
        return authorization()[0] is not None

    def run_write(args, current):
        try:
            payload = {'request': args, 'context': {'scope': [owner, chat, current[0], current[2]],
                                                   'message_id': current[1]}}
            with lock:
                admitted = admissions.get(current[:3])
                if admitted and admitted[0] > time.monotonic() and admitted[2]:
                    # Provenance comes from the authenticated inbound hook, never
                    # from tool arguments, quoted history, or a model assertion.
                    payload['context']['owner_message'] = admitted[2]
            encoded = json.dumps(payload, ensure_ascii=False)
            if len(encoded) > write_request_limit:
                return json.dumps({'ok': False, 'error': 'request_too_large', 'provider_called': False})
            result = subprocess.run(['/usr/bin/python3', str(write_runner), str(private)],
                input=encoded, capture_output=True, text=True, timeout=300,
                env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
            if result.returncode or len(result.stdout) > write_output_limit:
                raise ValueError()
            return json.dumps(json.loads(result.stdout), ensure_ascii=False)
        except Exception:
            return json.dumps({'ok': False, 'error': 'write_runner_unavailable',
                               'retry': 'Inspect persisted draft status; never prepare a replacement after an uncertain submit.'})

    def write(args, **kwargs):
        current, reason = authorization()
        if not current:
            return denied(reason)
        if (not isinstance(args, dict) or args.get('action') not in ('prepare', 'execute', 'status')
                or set(args) - {'action', 'service', 'operation', 'params', 'draft_id'}
                or ('service' in args and args['service'] not in service_ids)):
            return json.dumps({'ok': False, 'error': 'invalid_write_request'})
        return run_write(args, current)

    def lookup(args, **kwargs):
        current, reason = authorization()
        if not current:
            return denied(reason)
        try:
            if not isinstance(args, dict) or set(args) - {'query', 'service', 'view', 'offset', 'limit', 'capability_id'}:
                raise ValueError('invalid_arguments')
            if any(not isinstance(v, str) or len(v) > 1000 for k, v in args.items() if k not in ('offset', 'limit')):
                raise ValueError('invalid_arguments')
            return json.dumps({'ok': True, **catalog.find(**args)}, ensure_ascii=False)
        except Exception:
            return json.dumps({'ok': False, 'error': 'catalog_unavailable'})

    def read(args, **kwargs):
        current, reason = authorization()
        if not current:
            return denied(reason)
        try:
            if not isinstance(args, dict) or args.get('service') not in service_ids:
                return json.dumps({'ok': False, 'error': 'invalid_read_request', 'provider_called': False})
            request = json.dumps(args, ensure_ascii=False)
            if len(request) > read_request_limit:
                return json.dumps({'ok': False, 'error': 'request_too_large', 'provider_called': False})
            result = subprocess.run(['/usr/bin/python3', str(runner), str(private)],
                                    input=request, capture_output=True, text=True, timeout=100,
                                    env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
            if result.returncode or len(result.stdout) > read_output_limit:
                raise ValueError('runner_failed')
            payload = json.loads(result.stdout)
            return json.dumps(payload, ensure_ascii=False)
        except subprocess.TimeoutExpired:
            return json.dumps({'ok': False, 'error': 'read_timeout', 'retry': 'No automatic retry'})
        except Exception:
            return json.dumps({'ok': False, 'error': 'read_runner_unavailable'})

    def schema(name, description, properties):
        return {'name': name, 'description': description,
                'parameters': {'type': 'object', 'properties': properties, 'additionalProperties': False}}

    ctx.register_tool('integration_catalog', 'automation-api', schema(
        'integration_catalog', 'Find existing APIs before browser/web exploration: ' + service_names +
        '. Get operations, schemas, parameters and verification status. No secrets.',
        {'query': {'type': 'string', 'description': 'Service name or task: поездка, товар, УПД, оплата…'},
         'service': {'type': 'string', 'description': 'Exact service id for its full card'},
         'view': {'type': 'string', 'enum': ['service', 'capabilities'], 'description': 'Service card or full documented method inventory'},
         'capability_id': {'type': 'string', 'description': 'Exact inventory id to include parameter/body details'},
         'offset': {'type': 'integer', 'minimum': 0},
         'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20}}), lookup)
    read_schema = schema('integration_read', 'Execute an existing read operation. First consult '
        'integration_catalog for exact service, operation, parameters and limits. Does not place orders, '
        'sign documents or move money. Output may contain private business data; use only for this task.',
        {'service': {'type': 'string', 'enum': service_ids},
         'operation': {'type': 'string'}, 'params': {'type': 'object', 'description': 'Parameters from catalog'}})
    read_schema['parameters']['required'] = ['service', 'operation']
    ctx.register_tool('integration_read', 'automation-api', read_schema, read)
    write_description = ('Provider writes for ' + service_names + '. prepare is read-only and returns exact parameters. '
        'Follow the returned confirmation_required policy. When confirmation is required, only a NEW authenticated owner message '
        'can approve the returned confirmation command. Read-only questions must not trigger execute. '
        'status shows the durable result; verify completion with documented reads. Never blindly retry uncertain writes. ')
    if 'etm' in service_ids:
        write_description += (
        'For an owner request to order or arrange shipment in ETM, confirmation_required=false means the standing owner policy applies: '
        'call execute immediately after checking the preview against the request; do not ask for a UUID or another confirmation. ')
    if {'fal', 'inference'} & set(service_ids):
        write_description += (
        'For fal/inference, prepare returns the provider/model, exact input, cost estimate and configured spending policy. '
        'When confirmation_required=false, execute the requested owner task without another confirmation. '
        'Long generations return a durable job ID: poll job_status and retrieve job_result; never resubmit after timeout. ')
    write_schema = schema('integration_write', write_description,
        {'action': {'type': 'string', 'enum': ['prepare', 'execute', 'status']},
         'service': {'type': 'string', 'enum': service_ids},
         'operation': {'type': 'string'},
         'params': {'type': 'object', 'description': 'Use the exact parameter schema of the selected service and operation in integration_catalog.write_operations'},
         'draft_id': {'type': 'string', 'format': 'uuid'}})
    write_schema['parameters']['required'] = ['action']
    ctx.register_tool('integration_write', 'automation-api', write_schema, write)
    ctx.register_hook('pre_llm_call', before)
    ctx.on_unload(admissions.clear)
