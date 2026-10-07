"""Durable ABCP business writes through the native owner bridge.

The bridge owns Telegram authentication and creates ``context`` independently
of model arguments. The local OS user is trusted, as with the other connectors.
Every provider submission is attempted at most once per immutable draft. HTTP
acceptance, partial success and interrupted submissions require readback; none
of them authorizes a new draft for the same business intent.
"""
from contextlib import contextmanager
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

try:
    from . import abcp_api as api
except ImportError:
    import abcp_api as api


_ACTIONS = {
    'prepare': {'action', 'service', 'operation', 'params'},
    'confirm': {'action', 'confirmation_text'},
    'execute': {'action', 'draft_id'},
    'status': {'action', 'draft_id'},
}
_FINAL = {'accepted_unverified', 'partial', 'provider_rejected', 'outcome_unknown'}
_STATUSES = _FINAL | {'prepared', 'confirmed', 'submitting'}
_NATIVE_FIELDS = {'source', 'message_id', 'scope', 'text_sha256'}
_EMPTY_TEXT_HASH = hashlib.sha256(b'').hexdigest()
_IMMUTABLE_FIELDS = (
    'draft_id', 'operation', 'params', 'scope', 'created_message', 'created_at',
    'expires_at', 'target_hash', 'payload_hash', 'contract_hash', 'intent_hash',
    'preview', 'source',
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _clone(value):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError):
        raise api.AbcpError('invalid_write_parameters') from None


def _preview(value):
    """Show business details without echoing passwords or uploaded file bytes."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = key.casefold()
            if lowered in api.SECRET_KEYS or lowered.startswith(('password', 'access')):
                out[key] = '[redacted]'
            elif lowered == 'content_base64':
                try:
                    raw = base64.b64decode(item, validate=True)
                except (ValueError, TypeError):
                    raise api.AbcpError('invalid_upload_base64') from None
                out[key] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            else:
                out[key] = _preview(item)
        return out
    if isinstance(value, list):
        return [_preview(item) for item in value]
    return value


def _identity(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise api.AbcpError('invalid_draft_id') from None
    return value


def _validate_context(context):
    if not isinstance(context, dict):
        raise api.AbcpError('invalid_write_context')
    scope, message = context.get('scope'), context.get('message_id')
    if (not isinstance(scope, list) or len(scope) != 4
            or not all(isinstance(value, str) for value in scope)
            or not scope[0] or scope[0] != scope[1] or not scope[2]
            or not isinstance(message, str) or not message.strip()):
        raise api.AbcpError('invalid_write_context')
    return scope, message


def _native_message(context):
    native = context.get('owner_message')
    if (not isinstance(native, dict) or set(native) != _NATIVE_FIELDS
            or native.get('source') != 'native_owner_telegram'
            or native.get('message_id') != context['message_id']
            or native.get('scope') != context['scope']):
        return None
    text_hash = native.get('text_sha256')
    if (not isinstance(text_hash, str)
            or not re.fullmatch(r'[a-f0-9]{64}', text_hash)
            or text_hash == _EMPTY_TEXT_HASH):
        return None
    return {'policy': 'owner_command', 'message_id': native['message_id'],
            'text_sha256': text_hash}


def _owner_command(context, config, row):
    if (config.get('write_policy', 'explicit_confirmation') != 'owner_command'
            or context['message_id'] != row['created_message']):
        return None
    return _native_message(context)


def _save(path, row):
    api.atomic_json(path, row)
    # A durable rename also requires fsync of the containing directory.
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def _lock(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    fd = os.open(root / 'workflow.lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _read(path):
    try:
        row = json.loads(path.read_text())
        if (not isinstance(row, dict) or row.get('draft_id') != path.stem
                or row.get('status') not in _STATUSES
                or row.get('payload_hash') != digest(row['params'])
                or row.get('integrity_hash') != digest({key: row[key] for key in _IMMUTABLE_FIELDS})):
            raise ValueError()
        return row
    except FileNotFoundError:
        raise api.AbcpError('draft_not_found') from None
    except (OSError, ValueError, TypeError, KeyError):
        raise api.AbcpError('draft_integrity_failed') from None


def _view(row, context, config):
    out = {key: row.get(key) for key in (
        'draft_id', 'operation', 'status', 'expires_at', 'preview', 'source',
        'last_error', 'http_status', 'provider_code', 'result',
    )}
    out.update(ok=True, service='abcp', business_status=row['status'],
               provider_accepted=row['status'] == 'accepted_unverified',
               partial_success=row['status'] == 'partial', mutation_verified=False,
               provider_called='submitted_at' in row,
               verification='Проверьте результат документированным методом чтения ABCP. '
                            'Ответ API сам по себе не подтверждает завершение операции. '
                            'Не повторяйте отправку; частичный или неизвестный результат '
                            'требует сверки с ABCP.')
    if row['status'] == 'prepared':
        direct = _owner_command(context, config, row)
        out['confirmation_required'] = direct is None
        if direct:
            out.update(authorization_policy='owner_command', instruction=
                       'Проверьте точные параметры относительно текущей команды владельца '
                       'и вызовите execute. Запрос цены или статуса не разрешает бизнес-операцию.')
        else:
            out.update(authorization_policy='explicit_confirmation',
                       confirmation_command='ПОДТВЕРЖДАЮ ' + row['draft_id'], instruction=
                       'Покажите владельцу полный предпросмотр. Для исполнения нужна '
                       'эта точная команда в новом аутентифицированном сообщении владельца.')
    return _clone(out)


def _blocker(root, intent, scope, now, *, exclude=None):
    # A single outer process lock makes this scan atomic with every submission.
    for path in sorted(root.glob('*.json')):
        row = _read(path)
        if row['draft_id'] == exclude or row['intent_hash'] != intent:
            continue
        if row['status'] == 'provider_rejected':
            continue
        if row['expires_at'] < now and 'submitted_at' not in row:
            continue
        if row['scope'] != scope:
            return {'ok': False, 'error': 'other_unresolved_intent',
                    'instruction': 'Эта операция уже подготовлена или отправлена в другом '
                                   'диалоге. Сначала сверьте исходную операцию с ABCP.'}
        return {'ok': False, 'error': 'existing_unresolved_draft',
                'draft_id': row['draft_id'], 'status': row['status'],
                'instruction': 'Используйте status этого черновика и методы чтения ABCP. '
                               'Не заменяйте его новым черновиком до сверки результата.'}
    return None


def process(request, context, config, *, clock=time.time):
    """Process trusted bridge context and untrusted model request separately."""
    scope, message = _validate_context(context)
    if not isinstance(request, dict) or not isinstance(config, dict):
        raise api.AbcpError('invalid_write_request')
    action = request.get('action')
    if not isinstance(action, str) or action not in _ACTIONS or set(request) - _ACTIONS[action]:
        raise api.AbcpError('invalid_write_request')
    if config.get('write_policy', 'explicit_confirmation') not in ('explicit_confirmation', 'owner_command'):
        raise api.AbcpError('invalid_write_policy')
    if action == 'prepare':
        if 'service' in request and request['service'] != 'abcp':
            raise api.AbcpError('invalid_write_request')
        operation = request.get('operation')
        if not isinstance(operation, str):
            raise api.AbcpError('invalid_write_request')
        params = _clone(api.validate(operation, request.get('params', {}), write=True))
        metadata = _clone(api.operation(operation))
        if metadata.get('effect') not in ('business_write', 'write', 'report_generation'):
            raise api.AbcpError('write_operation_required')
        target = api.fingerprint(config)
        ident = str(uuid.uuid4())
    elif action == 'confirm':
        text = request.get('confirmation_text')
        if not isinstance(text, str) or not re.fullmatch(r'ПОДТВЕРЖДАЮ [a-f0-9-]{36}', text):
            raise api.AbcpError('exact_confirmation_required')
        ident = _identity(text.split(' ')[1])
        if 'owner_message' in context:
            native = _native_message(context)
            if not native or native['text_sha256'] != hashlib.sha256(text.encode()).hexdigest():
                raise api.AbcpError('native_confirmation_mismatch')
    else:
        ident = _identity(request.get('draft_id'))
    state_dir = config.get('state_dir')
    if not isinstance(state_dir, str) or not state_dir:
        raise api.AbcpError('invalid_state_directory')
    root = Path(state_dir) / 'abcp-writes'
    path = root / (ident + '.json')

    with _lock(root):
        if action == 'prepare':
            now = clock()
            intent = digest({'operation': operation, 'params': params, 'target': target})
            blocker = _blocker(root, intent, scope, now)
            if blocker:
                return blocker
            preview = {'service': 'abcp', 'operation': operation,
                       'title': metadata.get('title', metadata.get('description', operation)),
                       'method': metadata.get('method'), 'path': metadata.get('path'),
                       'effect': metadata['effect'], 'parameters': _preview(params),
                       'completion': 'Один запрос ABCP. Деловой результат требует сверки чтением.'}
            if len(json.dumps(preview, ensure_ascii=False)) > 18000:
                raise api.AbcpError('write_preview_too_large')
            row = {'draft_id': ident, 'operation': operation, 'params': params,
                   'scope': _clone(scope), 'created_message': message, 'created_at': now,
                   'expires_at': now + 600, 'target_hash': target,
                   'payload_hash': digest(params), 'contract_hash': digest(metadata),
                   'intent_hash': intent, 'status': 'prepared', 'preview': preview,
                   'source': metadata.get('source')}
            row['integrity_hash'] = digest({key: row[key] for key in _IMMUTABLE_FIELDS})
            _save(path, row)
            return _view(row, context, config)

        row = _read(path)
        if row['scope'] != scope:
            raise api.AbcpError('draft_scope_mismatch')
        if row['status'] == 'submitting':
            row.update(status='outcome_unknown', last_error='interrupted_submission')
            _save(path, row)
        if action == 'status':
            return _view(row, context, config)
        if action == 'confirm':
            if row['status'] != 'prepared':
                raise api.AbcpError('draft_not_confirmable')
            if message == row['created_message']:
                raise api.AbcpError('new_owner_message_required')
            if row['expires_at'] < clock():
                raise api.AbcpError('draft_expired_prepare_again')
            row.update(status='confirmed', approved_hash=row['payload_hash'], confirmed_message=message)
            _save(path, row)
            return _view(row, context, config)
        if row['status'] in _FINAL:
            return _view(row, context, config)
        direct = _owner_command(context, config, row)
        if row['status'] == 'prepared' and direct:
            row.update(status='confirmed', approved_hash=row['payload_hash'],
                       confirmed_message=message, authorization=direct)
        if row['status'] != 'confirmed' or row.get('approved_hash') != row['payload_hash']:
            raise api.AbcpError('owner_confirmation_required')
        if row['expires_at'] < clock():
            raise api.AbcpError('confirmation_expired')
        normalized = api.validate(row['operation'], row['params'], write=True)
        metadata = api.operation(row['operation'])
        if (digest(normalized) != row['payload_hash']
                or digest(metadata) != row['contract_hash']
                or api.fingerprint(config) != row['target_hash']):
            raise api.AbcpError('draft_contract_or_target_changed')
        blocker = _blocker(root, row['intent_hash'], scope, clock(), exclude=ident)
        if blocker:
            return blocker
        row.update(status='submitting', submitted_at=clock())
        _save(path, row)  # Durable intent must precede every possible external effect.
        try:
            result = api.execute(config, row['operation'], row['params'], write=True)
            status = result.get('business_status') if isinstance(result, dict) else None
            if status not in ('accepted_unverified', 'partial', 'provider_rejected', 'outcome_unknown'):
                row.update(status='outcome_unknown', last_error='unrecognized_provider_result')
            else:
                row.update(status=status, last_error=None)
                # Preserve known acceptance before converting a potentially large result.
                _save(path, row)
                row['result'] = api.bound_result(config, _clone(result))
        except api.AbcpError as exc:
            # A transport-level HTTP error cannot establish that no rows changed.
            # Only an explicit, parsed provider_rejected envelope establishes rejection.
            if row['status'] == 'submitting':
                row['status'] = 'outcome_unknown'
            row.update(last_error=exc.code, http_status=exc.http_status,
                       provider_code=exc.provider_code)
        except Exception:
            if row['status'] == 'submitting':
                row['status'] = 'outcome_unknown'
            row['last_error'] = 'unexpected_execution_error'
        _save(path, row)
        return _view(row, context, config)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if len(argv) != 1:
            raise api.AbcpError('config_path_required')
        # Reserve room for the bridge context around a maximum-size API payload.
        limit = api.MAX_REQUEST + 16384
        body = sys.stdin.read(limit + 1)
        if len(body.encode('utf-8')) > limit:
            raise api.AbcpError('write_input_too_large')
        incoming = json.loads(body)
        if not isinstance(incoming, dict) or set(incoming) != {'request', 'context'}:
            raise api.AbcpError('invalid_write_input')
        config = api.load_config(argv[0])
        result = process(incoming['request'], incoming['context'], config)
    except api.AbcpError as exc:
        result = {'ok': False, 'error': exc.code}
    except (ValueError, TypeError):
        result = {'ok': False, 'error': 'invalid_write_input'}
    except Exception:
        result = {'ok': False, 'error': 'write_runner_failed'}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n')
    # The bridge distinguishes process failure from a structured business error.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
