"""Local upload staging and owner-bound provider artifact references.

Only configured media/data roots are readable. No network requests occur here;
provider URLs are recovered internally from a private, account-bound artifact
manifest and must never be included in tool output.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import zipfile

try:
    from .media_runtime import ArtifactStore, JobStore, MediaError, _url, canonical
except ImportError:
    from media_runtime import ArtifactStore, JobStore, MediaError, _url, canonical

LIMITS = {'fal': 8 * 1024 * 1024, 'inference': 32 * 1024 * 1024}
MIME_TYPES = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
    '.gif': 'image/gif', '.bmp': 'image/bmp', '.tif': 'image/tiff', '.tiff': 'image/tiff',
    '.avif': 'image/avif', '.heic': 'image/heic', '.heif': 'image/heif', '.svg': 'image/svg+xml',
    '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.oga': 'audio/ogg',
    '.opus': 'audio/opus', '.flac': 'audio/flac', '.aac': 'audio/aac', '.m4a': 'audio/mp4',
    '.aiff': 'audio/aiff', '.aif': 'audio/aiff', '.amr': 'audio/amr',
    '.mp4': 'video/mp4', '.m4v': 'video/mp4', '.mov': 'video/quicktime', '.webm': 'video/webm',
    '.mkv': 'video/x-matroska', '.avi': 'video/x-msvideo', '.mpeg': 'video/mpeg', '.mpg': 'video/mpeg',
    '.pdf': 'application/pdf', '.txt': 'text/plain', '.md': 'text/markdown',
    '.csv': 'text/csv', '.tsv': 'text/tab-separated-values', '.json': 'application/json',
    '.jsonl': 'application/x-ndjson', '.ndjson': 'application/x-ndjson', '.zip': 'application/zip',
}
_SECRET_STEMS = frozenset({'auth', 'authentication', 'credential', 'credentials', 'secret', 'secrets',
    'token', 'tokens', 'session', 'sessions', 'password', 'passwords', 'cookie', 'cookies',
    'vault', 'vaultwarden', 'bitwarden', 'config', 'settings', 'id_rsa', 'id_ed25519',
    'service_account', 'service-account', 'client_secret', 'client-secret'})
_SECRET_JSON_KEYS = frozenset({'private_key', 'client_secret', 'access_token', 'refresh_token',
    'api_key', 'apikey', 'password', 'bw_session', 'infsh_api_key', 'inference_api_key', 'fal_key'})
_PRIVATE_DIRECTORIES = frozenset({'.ssh', '.gnupg', '.aws', '.azure', '.config', '.codex',
    '.vaultwarden', '.bitwarden', '.kube', '.docker'})
_PREPARED_FIELDS = frozenset({'path', 'filename', 'content_type', 'bytes', 'sha256', '_stat'})


def _home(config):
    value = config.get('os_home') or str(Path.home())
    return _absolute(value, None)


def _absolute(value, home):
    if not isinstance(value, str) or not value or len(value) > 4096 or any(ord(c) < 32 for c in value):
        raise MediaError('invalid_upload_path')
    if home is not None and value.startswith('~/'):
        value = str(home) + value[1:]
    if not value.startswith('/') or any(part in ('.', '..') for part in value.split('/')):
        raise MediaError('upload_path_must_be_absolute_without_traversal')
    path = Path(value)
    if any(part in _PRIVATE_DIRECTORIES for part in path.parts):
        raise MediaError('private_configuration_upload_forbidden')
    return path


def _roots(config):
    home = _home(config)
    configured = config.get('media_upload_roots')
    state = _absolute(config['state_dir'], home) if config.get('state_dir') else None
    artifacts = set()
    if state:
        artifacts = {state / 'media' / 'artifacts', state / 'media' / 'media-artifacts'}
    if configured is None:
        values = [home / '.hermes' / 'image_cache', home / '.hermes' / 'audio_cache',
                  home / 'vaults' / 'Automation' / '80_Файлы', *sorted(artifacts)]
    elif isinstance(configured, list) and configured and all(isinstance(p, str) for p in configured):
        values = configured
    else:
        raise MediaError('invalid_media_upload_roots')
    roots = []
    for value in values:
        path = _absolute(str(value), home)
        if path in (Path('/'), home) or path == state:
            raise MediaError('unsafe_media_upload_root')
        if '.hermes' in path.parts and path not in artifacts:
            index = path.parts.index('.hermes')
            if len(path.parts) <= index + 1 or path.parts[index + 1] not in ('image_cache', 'audio_cache'):
                raise MediaError('unsafe_hermes_upload_root')
        roots.append(path)
    return roots, artifacts


def _filename(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 255 or value.startswith('.')
            or any(ord(c) < 32 for c in value) or '/' in value or '\\' in value):
        raise MediaError('invalid_upload_filename')
    lower = value.casefold()
    stem = Path(lower).stem
    if (stem in _SECRET_STEMS or lower.startswith(('.env', 'client_secret', 'credentials.', 'service-account'))
            or Path(lower).suffix not in MIME_TYPES):
        raise MediaError('upload_file_type_forbidden')
    return value


def _allowed_path(value, config):
    path = _absolute(value, _home(config))
    roots, artifact_roots = _roots(config)
    parent = next((root for root in roots if path != root and path.is_relative_to(root)), None)
    if parent is None:
        raise MediaError('upload_path_outside_allowed_roots')
    relative = path.relative_to(parent)
    if any(part.startswith('.') for part in relative.parts):
        raise MediaError('hidden_upload_path_forbidden')
    _filename(path.name)
    # ArtifactStore's JSON files are private manifests containing signed URLs,
    # not data assets. Downloads use a media extension or .bin (not uploaded here).
    if any(path.is_relative_to(root) for root in artifact_roots) and path.suffix.casefold() in ('.json', '.txt', '.md', '.csv', '.tsv', '.jsonl', '.ndjson'):
        raise MediaError('artifact_manifest_upload_forbidden')
    return path


@contextmanager
def _open_regular(path):
    """Open from / using openat + O_NOFOLLOW for every path component."""
    directory = None
    handle = None
    try:
        directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        handle = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(handle)
        if not stat.S_ISREG(before.st_mode):
            raise MediaError('upload_requires_regular_file')
        yield handle, before
    except MediaError:
        raise
    except (OSError, ValueError):
        raise MediaError('upload_file_unavailable_or_symlink') from None
    finally:
        if handle is not None:
            os.close(handle)
        if directory is not None:
            os.close(directory)


def _signature(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def _read(path, maximum):
    with _open_regular(path) as (handle, before):
        if not 0 < before.st_size <= maximum:
            raise MediaError('upload_size_out_of_range')
        pieces = []
        remaining = maximum + 1
        while remaining:
            piece = os.read(handle, min(1024 * 1024, remaining))
            if not piece:
                break
            pieces.append(piece)
            remaining -= len(piece)
        raw = b''.join(pieces)
        after = os.fstat(handle)
        if _signature(before) != _signature(after) or len(raw) != after.st_size:
            raise MediaError('upload_changed_during_read')
        if len(raw) > maximum:
            raise MediaError('upload_size_out_of_range')
        return raw, after


def _check_content(raw, suffix):
    # Do not upload plaintext private keys under an innocuous media filename.
    if re.search(br'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----', raw[:8192]):
        raise MediaError('secret_content_upload_forbidden')
    if suffix in ('.txt', '.md', '.csv', '.tsv', '.json', '.jsonl', '.ndjson', '.svg'):
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeError:
            raise MediaError('upload_text_must_be_utf8') from None
        if '\x00' in text:
            raise MediaError('invalid_text_upload')
        if re.search(r'(?im)^\s*(?:export\s+)?(?:BW_SESSION|INFSH_API_KEY|INFERENCE_API_KEY|FAL_KEY|OPENAI_API_KEY|AWS_SECRET_ACCESS_KEY)\s*=', text):
            raise MediaError('secret_content_upload_forbidden')
        if suffix in ('.json', '.jsonl', '.ndjson'):
            try:
                docs = [json.loads(text)] if suffix == '.json' else [json.loads(line) for line in text.splitlines() if line.strip()]
            except (ValueError, RecursionError):
                raise MediaError('invalid_json_upload') from None
            def check(value, depth=0):
                if depth > 64:
                    raise MediaError('upload_json_too_deep')
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key.casefold() in _SECRET_JSON_KEYS and child not in (None, '', '[redacted]'):
                            raise MediaError('secret_content_upload_forbidden')
                        check(child, depth+1)
                elif isinstance(value, list):
                    for child in value:
                        check(child, depth+1)
            for value in docs:
                check(value)
    if suffix == '.zip':
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                if len(entries) > 10000:
                    raise MediaError('upload_archive_too_many_entries')
                for entry in entries:
                    name = entry.filename.replace('\\', '/')
                    parts = name.rstrip('/').split('/')
                    if (name.startswith('/') or any(part in ('.', '..') or part.startswith('.') for part in parts)
                            or stat.S_ISLNK(entry.external_attr >> 16)):
                        raise MediaError('unsafe_upload_archive_path')
                    member = Path(name)
                    if (member.stem.casefold() in _SECRET_STEMS
                            or member.suffix.casefold() in ('.pem', '.key', '.p12', '.pfx', '.env', '.sqlite', '.sqlite3', '.db')):
                        raise MediaError('secret_content_upload_forbidden')
        except (zipfile.BadZipFile, ValueError, OSError):
            raise MediaError('invalid_zip_upload') from None
    # Require core file signatures for common image/document/archive formats so
    # renaming a credential file to .png cannot make it an eligible upload.
    expected = {'.png': (b'\x89PNG\r\n\x1a\n',), '.jpg': (b'\xff\xd8\xff',),
                '.jpeg': (b'\xff\xd8\xff',), '.gif': (b'GIF87a', b'GIF89a'),
                '.pdf': (b'%PDF-',), '.zip': (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'),
                '.flac': (b'fLaC',), '.ogg': (b'OggS',), '.oga': (b'OggS',),
                '.opus': (b'OggS',), '.bmp': (b'BM',), '.tif': (b'II*\x00', b'MM\x00*'),
                '.tiff': (b'II*\x00', b'MM\x00*'), '.webm': (b'\x1aE\xdf\xa3',),
                '.mkv': (b'\x1aE\xdf\xa3',)}
    if suffix in expected and not raw.startswith(expected[suffix]):
        raise MediaError('upload_content_type_mismatch')
    if suffix in ('.webp', '.wav', '.avi'):
        kind = {'.webp': b'WEBP', '.wav': b'WAVE', '.avi': b'AVI '}[suffix]
        if raw[:4] != b'RIFF' or raw[8:12] != kind:
            raise MediaError('upload_content_type_mismatch')


def prepare_upload(params, config, service):
    """Hash exact eligible bytes and retain private stat metadata for execution."""
    if service not in LIMITS:
        raise MediaError('unknown_media_service')
    if not isinstance(params, dict) or set(params) - {'path', 'filename', 'content_type'} or not params.get('path'):
        raise MediaError('invalid_upload_parameters')
    path = _allowed_path(params['path'], config)
    filename = _filename(params.get('filename', path.name))
    suffix = path.suffix.casefold()
    if Path(filename).suffix.casefold() != suffix:
        raise MediaError('upload_filename_extension_mismatch')
    content_type = params.get('content_type', MIME_TYPES[suffix])
    if content_type != MIME_TYPES[suffix]:
        raise MediaError('upload_content_type_mismatch')
    raw, info = _read(path, LIMITS[service])
    _check_content(raw, suffix)
    return {'path': str(path), 'filename': filename, 'content_type': content_type,
            'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), '_stat': _signature(info)}


def read_upload(prepared, config, service):
    """Read only the exact file reviewed by prepare_upload, across restarts."""
    if service not in LIMITS:
        raise MediaError('unknown_media_service')
    if (not isinstance(prepared, dict) or set(prepared) != _PREPARED_FIELDS
            or type(prepared.get('bytes')) is not int
            or not re.fullmatch('[a-f0-9]{64}', str(prepared.get('sha256', '')))
            or not isinstance(prepared.get('_stat'), list) or len(prepared['_stat']) != 5
            or any(type(value) is not int for value in prepared['_stat'])):
        raise MediaError('invalid_prepared_upload')
    path = _allowed_path(prepared['path'], config)
    filename = _filename(prepared['filename'])
    suffix = path.suffix.casefold()
    if Path(filename).suffix.casefold() != suffix or prepared['content_type'] != MIME_TYPES[suffix]:
        raise MediaError('upload_content_type_mismatch')
    raw, info = _read(path, LIMITS[service])
    if (_signature(info) != prepared['_stat'] or len(raw) != prepared['bytes']
            or hashlib.sha256(raw).hexdigest() != prepared['sha256']):
        raise MediaError('upload_changed_since_prepare')
    _check_content(raw, suffix)
    return raw


def resolve_artifact_references(value, state_dir, account):
    """Replace private artifact handles with their source URLs for provider input.

    `state_dir` is the shared media runtime directory (the same directory passed
    to ArtifactStore and JobStore), normally config.state_dir/media. This result
    is for internal request execution and must not be returned to the model.
    """
    if not isinstance(account, str) or not account:
        raise MediaError('artifact_account_required')
    stores = []
    def lookup(ident):
        if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{64}', ident):
            raise MediaError('invalid_artifact_id')
        if not stores:
            stores.extend([ArtifactStore(state_dir), JobStore(state_dir)])
        artifacts, jobs = stores
        view = artifacts.get(ident)
        jobs.get(view['job_id'], account=account)
        # Read only after the public manifest and owning account have passed
        # validation. _path also enforces the id format and rejects symlinks.
        path = artifacts._path(ident)
        with _open_regular(path) as (handle, before):
            if before.st_size > 65536 or before.st_mode & 0o077:
                raise MediaError('invalid_artifact_manifest')
            raw = os.read(handle, 65537)
            if _signature(before) != _signature(os.fstat(handle)) or len(raw) != before.st_size:
                raise MediaError('artifact_manifest_changed')
        try:
            row = json.loads(raw)
        except (ValueError, UnicodeError):
            raise MediaError('invalid_artifact_manifest') from None
        if row.get('id') != ident or row.get('job_id') != view['job_id'] or not isinstance(row.get('source_url'), str):
            raise MediaError('artifact_integrity_failed')
        url = row['source_url']
        if hashlib.sha256(canonical([row['job_id'], url]).encode()).hexdigest() != ident:
            raise MediaError('artifact_integrity_failed')
        _url(url, artifact=True)
        return url
    def walk(item, depth=0):
        if depth > 64:
            raise MediaError('artifact_reference_too_deep')
        if isinstance(item, str) and item.startswith('artifact:'):
            return lookup(item[len('artifact:'):])
        if isinstance(item, dict):
            if 'artifact_id' in item:
                if set(item) != {'artifact_id'}:
                    raise MediaError('invalid_artifact_reference')
                return lookup(item['artifact_id'])
            return {key: walk(child, depth+1) for key, child in item.items()}
        if isinstance(item, list):
            return [walk(child, depth+1) for child in item]
        return item
    return walk(value)
