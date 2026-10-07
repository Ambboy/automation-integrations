"""Private durable state and bounded network I/O for media-provider adapters.

No model, SDK, credential discovery, autonomous retries, or payment operations.
Amounts use integer nano-units internally; all budget transactions are atomic.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from email.utils import parsedate_to_datetime
import fcntl
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import sqlite3
import ssl
import time
import uuid
from urllib.parse import urlencode, urlsplit, urlunsplit


OFFICIAL_HOSTS = frozenset({
    'api.fal.ai', 'queue.fal.run', 'fal.run', 'rest.fal.ai', 'rest.alpha.fal.ai',
    'fal.ai', 'api.inference.sh', 'storage.googleapis.com',
    '3d0ae9f8488861468c48977d2886dac7.r2.cloudflarestorage.com',
})
AUTHENTICATED_HOSTS = frozenset({'api.fal.ai', 'queue.fal.run', 'fal.run',
    'rest.fal.ai', 'rest.alpha.fal.ai', 'api.inference.sh'})
ARTIFACT_DOMAINS = ('fal.media', 'fal.run', 'inference.sh', 'storage.googleapis.com',
                    'r2.cloudflarestorage.com')
USER_AGENT = 'Mozilla/5.0 (compatible; GreifIntegration/1.0)'
SECRET_KEYS = frozenset({'authorization', 'proxy-authorization', 'password', 'secret',
    'client_secret', 'api_key', 'apikey', 'access_token', 'refresh_token',
    'fal_key', 'inference_api_key', 'infsh_api_key'})
JOB_STATES = frozenset({'prepared', 'submitting', 'submitted', 'queued', 'running',
    'completed', 'failed', 'cancelled', 'outcome_unknown', 'rejected'})


class MediaError(Exception):
    def __init__(self, code, http_status=None, *, retry_after=None):
        self.code = code
        self.http_status = self.status = http_status
        self.retry_after = retry_after
        super().__init__(code)


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, UnicodeError):
        raise MediaError('invalid_json') from None


def account_fingerprint(credentials):
    """Bind state to a credential without persisting its plaintext."""
    if not isinstance(credentials, (dict, str)) or not credentials:
        raise MediaError('credential_missing')
    return hashlib.sha256(canonical(credentials).encode()).hexdigest()


def sanitize(value, secrets=(), *, redact_keys=()):
    """Retain IDs, pagination, usage and URLs; redact exact secrets and key fields.

    Adapters must additionally identify secret-bearing administrative response
    fields (for example a newly created API key named merely ``key``).
    """
    names = SECRET_KEYS | frozenset(str(k).casefold() for k in redact_keys)
    needles = sorted((s for s in secrets if isinstance(s, str) and s), key=len, reverse=True)
    def visit(item):
        if isinstance(item, dict):
            return {key: '[redacted]' if str(key).casefold() in names else visit(child)
                    for key, child in item.items()}
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, str):
            for secret in needles:
                item = item.replace(secret, '[redacted]')
        return item
    return visit(value)


def _url(url, allowed_hosts=None, *, artifact=False):
    if not isinstance(url, str) or len(url) > 16384 or any(ord(c) < 33 for c in url):
        raise MediaError('invalid_url')
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
        if (parsed.scheme != 'https' or not host or parsed.username is not None
                or parsed.password is not None or parsed.fragment or port not in (None, 443)
                or host.endswith('.') or '\\' in url or '%' in host):
            raise ValueError()
        host = host.encode('idna').decode('ascii').lower()
    except (ValueError, UnicodeError):
        raise MediaError('invalid_url') from None
    if artifact:
        if not any(host == suffix or host.endswith('.' + suffix) for suffix in ARTIFACT_DOMAINS):
            raise MediaError('artifact_host_not_allowed')
    elif host not in (OFFICIAL_HOSTS if allowed_hosts is None else allowed_hosts):
        raise MediaError('provider_host_not_allowed')
    return parsed, host


def _public_addresses(host):
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(row[4][0] for row in records))
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise MediaError('nonpublic_address_refused')
        return addresses
    except MediaError:
        raise
    except (OSError, ValueError):
        raise MediaError('dns_failed') from None


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self):
        # Resolve once, then connect to that public address while preserving SNI
        # and certificate hostname verification. Environment proxies are absent.
        sock = socket.create_connection((self._pinned_address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def _open_response(method, url, headers, data, timeout):
    parsed = urlsplit(url)
    host = parsed.hostname
    addresses = _public_addresses(host)
    connection = _PinnedHTTPSConnection(host, addresses[0], timeout)
    try:
        route = urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
        connection.request(method, route, body=data, headers=headers)
        return connection.getresponse(), connection
    except BaseException:
        connection.close()
        raise


def _status(response):
    status = response.status
    if 300 <= status < 400:
        raise MediaError('redirect_refused', status)
    if status >= 400:
        retry = response.getheader('Retry-After')
        try:
            retry = retry.strip() if retry else ''
            retry = (min(int(retry), 86400) if retry.isdigit() else
                     min(86400, max(0, math.ceil(parsedate_to_datetime(retry).timestamp() - time.time()))))
        except (ValueError, TypeError, OverflowError):
            retry = None
        code = {401: 'authentication_failed', 402: 'insufficient_credits', 403: 'access_denied',
                404: 'resource_not_found', 409: 'state_conflict', 429: 'rate_limited'}.get(
                    status, 'provider_unavailable' if status >= 500 else 'provider_http_error')
        if status == 403:
            # fal can express exhausted credit as account-lock HTTP 403. Inspect
            # a small private fragment only; never expose arbitrary provider text,
            # which may contain URLs, identifiers, prompts or credentials.
            try:
                fragment = response.read(4096).decode('utf-8', errors='replace').casefold()
            except Exception:
                fragment = ''
            if any(marker in fragment for marker in (
                    'exhausted balance', 'insufficient balance', 'insufficient credits',
                    'insufficient credit balance', 'credit balance exhausted',
                    'credits exhausted', 'out of credits', 'not enough credits',
                    'insufficient_credits', 'insufficient_balance')):
                code = 'insufficient_credits'
        raise MediaError(code, status, retry_after=retry)


class MediaHTTP:
    def __init__(self, allowed_hosts=None, *, max_json_bytes=4 * 1024 * 1024,
                 max_binary_bytes=64 * 1024 * 1024):
        self.allowed_hosts = frozenset(allowed_hosts) if allowed_hosts is not None else OFFICIAL_HOSTS
        self.max_json_bytes = max_json_bytes
        self.max_binary_bytes = max_binary_bytes

    def request(self, method, absolute_url, *, headers=None, query=None, body=None,
                timeout=30, response_kind='json'):
        parsed, host = _url(absolute_url, self.allowed_hosts)
        if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'):
            raise MediaError('invalid_http_method')
        if response_kind not in ('json', 'binary', 'text', 'sse'):
            raise MediaError('unsupported_response_kind')
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise MediaError('invalid_timeout')
        if headers is not None and not isinstance(headers, dict):
            raise MediaError('invalid_http_header')
        request_headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
        for key, value in (headers or {}).items():
            if (not isinstance(key, str) or not re.fullmatch(r'[!#$%&\'*+.^_`|~0-9A-Za-z-]+', key)
                    or not isinstance(value, str) or any(ord(c) < 32 or ord(c) > 126 for c in value)
                    or key.casefold() in ('host', 'connection', 'content-length', 'proxy-authorization')):
                raise MediaError('invalid_http_header')
            if host not in AUTHENTICATED_HOSTS and key.casefold() in (
                    'authorization', 'cookie', 'cookie2', 'x-api-key', 'api-key', 'x-fal-key'):
                raise MediaError('credential_forwarding_refused')
            request_headers[key] = value
        if query:
            try:
                def query_value(value):
                    if type(value) is bool:
                        return 'true' if value else 'false'
                    if isinstance(value, (list, tuple)):
                        return [query_value(item) for item in value]
                    return value
                items = query.items() if isinstance(query, dict) else query
                encoded = urlencode([(key, query_value(value)) for key, value in items], doseq=True)
            except (TypeError, ValueError):
                raise MediaError('invalid_query') from None
            absolute_url = urlunsplit(parsed._replace(query=parsed.query + ('&' if parsed.query else '') + encoded))
        if body is None:
            data = None
        elif isinstance(body, bytes):
            data = body
            if not any(key.casefold() == 'content-type' for key in request_headers):
                request_headers['Content-Type'] = 'application/octet-stream'
        else:
            data = canonical(body).encode('utf-8')
            request_headers['Content-Type'] = 'application/json; charset=utf-8'
        if data is not None and len(data) > (self.max_binary_bytes if isinstance(body, bytes) else self.max_json_bytes):
            raise MediaError('request_too_large')
        maximum = self.max_binary_bytes if response_kind == 'binary' else self.max_json_bytes
        connection = None
        try:
            response, connection = _open_response(method, absolute_url, request_headers, data, timeout)
            _status(response)
            length = response.getheader('Content-Length')
            if length and length.isdigit() and int(length) > maximum:
                raise MediaError('response_too_large')
            # read1 performs at most one underlying read, so a dribbling SSE
            # response cannot extend this call indefinitely by resetting a
            # per-socket timeout after every byte.
            chunks, count = [], 0
            deadline = time.monotonic() + timeout
            while count <= maximum:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MediaError('request_timeout')
                if getattr(connection, 'sock', None) is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(65536, maximum + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
            raw = b''.join(chunks)
            if len(raw) > maximum:
                raise MediaError('response_too_large')
            # HTTPResponse.read1() does not raise IncompleteRead when a server
            # closes before Content-Length. Never cache a partial media file
            # (or accept a coincidentally valid prefix of a JSON response).
            if (method != 'HEAD' and response.status not in (204, 304)
                    and length and length.isdigit() and len(raw) != int(length)):
                raise MediaError('incomplete_provider_response')
            if response_kind == 'binary':
                return raw
            if not raw:
                return {} if response_kind == 'json' else ''
            decoded = raw.decode('utf-8')
            return json.loads(decoded) if response_kind == 'json' else decoded
        except MediaError:
            raise
        except (TimeoutError, socket.timeout):
            raise MediaError('request_timeout') from None
        except ssl.SSLError:
            raise MediaError('tls_failed') from None
        except (http.client.HTTPException, OSError):
            raise MediaError('network_unavailable') from None
        except (ValueError, UnicodeError):
            raise MediaError('invalid_provider_response') from None
        finally:
            if connection:
                connection.close()


def _private_root(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise MediaError('private_state_required')
    return root


def _write_private(path, value):
    path = Path(path)
    if path.is_symlink():
        raise MediaError('invalid_state_file')
    tmp = path.with_name(path.name + '.' + os.urandom(8).hex() + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(value if isinstance(value, bytes) else canonical(value).encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        tmp.unlink(missing_ok=True)


class _Database:
    def __init__(self, root, name, schema):
        self.root = _private_root(root)
        self.path = self.root / name
        if self.path.is_symlink():
            raise MediaError('invalid_state_file')
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        self.path.chmod(0o600)
        with self.db() as db:
            db.executescript('PRAGMA journal_mode=WAL;' + schema)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try:
            yield db
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()


def job_exists(state_dir, job_id):
    """Membership check for write dispatch; never creates state or a database."""
    if not isinstance(job_id, str) or not re.fullmatch('[a-f0-9-]{36}', job_id):
        return False
    path = Path(state_dir) / 'media-jobs.sqlite3'
    if not path.is_file() or path.is_symlink():
        return False
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        return db.execute('SELECT 1 FROM jobs WHERE id=?', (job_id,)).fetchone() is not None
    finally:
        db.close()


class JobStore(_Database):
    def __init__(self, state_dir):
        super().__init__(state_dir, 'media-jobs.sqlite3', '''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, identity TEXT NOT NULL, account TEXT NOT NULL,
                provider TEXT NOT NULL, scope TEXT NOT NULL, request TEXT NOT NULL,
                state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                provider_job_id TEXT, endpoint TEXT, result TEXT, metadata TEXT,
                error TEXT);
            CREATE INDEX IF NOT EXISTS provider_jobs ON jobs(provider,account,provider_job_id);
        ''')

    @staticmethod
    def _record(row):
        if row is None:
            raise MediaError('job_not_found')
        result = dict(row)
        for field in ('request', 'scope', 'result', 'metadata'):
            if result.get(field) is not None:
                result[field] = json.loads(result[field])
        result['job_id'] = result['id']
        result['status'] = result['state']
        return result

    def prepare(self, identity, request, *, account, provider='', scope=''):
        if not isinstance(account, str) or not account or not isinstance(provider, str):
            raise MediaError('invalid_account_binding')
        ident = str(uuid.uuid5(uuid.NAMESPACE_URL, canonical([account, provider, scope, identity])))
        encoded = canonical(request)
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=?', (ident,)).fetchone()
            if row:
                if row['request'] != encoded:
                    raise MediaError('job_identity_conflict')
                db.commit()
                return self._record(row), False
            # A fresh owner message does not make a timed-out paid submission
            # safe to repeat. Keep its original identity until reconciled.
            uncertain = db.execute("SELECT * FROM jobs WHERE account=? AND provider=? AND request=? "
                                   "AND state IN ('submitting','outcome_unknown') ORDER BY created LIMIT 1",
                                   (account, provider, encoded)).fetchone()
            if uncertain:
                db.commit()
                return self._record(uncertain), False
            db.execute('INSERT INTO jobs(id,identity,account,provider,scope,request,state,created,updated) '
                       'VALUES(?,?,?,?,?,?,\'prepared\',?,?)',
                       (ident, canonical(identity), account, provider, canonical(scope), encoded, now, now))
            row = db.execute('SELECT * FROM jobs WHERE id=?', (ident,)).fetchone()
            db.commit()
        return self._record(row), True

    def exists(self, job_id):
        return job_exists(self.root, job_id)

    def get(self, job_id, *, account=None):
        with self.db() as db:
            result = self._record(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())
        if account is not None and result['account'] != account:
            raise MediaError('job_account_mismatch')
        return result

    def update(self, job_id, *, account=None, **values):
        if 'status' in values:
            if 'state' in values and values['state'] != values['status']:
                raise MediaError('invalid_job_update')
            values['state'] = values.pop('status')
        if not values or set(values) - {'state', 'provider_job_id', 'endpoint', 'result', 'metadata', 'error'}:
            raise MediaError('invalid_job_update')
        if 'state' in values and values['state'] not in JOB_STATES:
            raise MediaError('invalid_job_state')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            old = self._record(row)
            if account is not None and old['account'] != account:
                raise MediaError('job_account_mismatch')
            if values.get('state') == 'submitting' and old['state'] != 'prepared':
                raise MediaError('job_already_submitted')
            new_state = values.get('state', old['state'])
            if (new_state == 'prepared' and old['state'] != 'prepared') or (
                    old['state'] in ('completed', 'failed', 'cancelled', 'rejected') and new_state != old['state']):
                raise MediaError('invalid_job_transition')
            if old['provider_job_id'] and values.get('provider_job_id', old['provider_job_id']) != old['provider_job_id']:
                raise MediaError('provider_job_identity_conflict')
            normalized = {key: canonical(value) if key in ('result', 'metadata') else value
                          for key, value in values.items()}
            normalized['updated'] = time.time()
            db.execute('UPDATE jobs SET ' + ','.join(key + '=?' for key in normalized) + ' WHERE id=?',
                       (*normalized.values(), job_id))
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            db.commit()
        return self._record(row)

    def mark_submitting(self, job_id, *, account=None):
        return self.update(job_id, account=account, state='submitting')

    def submitted(self, job_id, provider_job_id, *, account=None, endpoint=None, result=None):
        if not isinstance(provider_job_id, str) or not provider_job_id:
            raise MediaError('missing_provider_job_id')
        return self.update(job_id, account=account, state='submitted', provider_job_id=provider_job_id,
                           endpoint=endpoint, result=result)

    def save_result(self, job_id, result, *, account=None, state=None):
        return self.update(job_id, account=account, result=result, **({'state': state} if state else {}))

    def find_provider_job(self, provider, provider_job_id, *, account):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE provider=? AND account=? AND provider_job_id=?',
                             (provider, account, provider_job_id)).fetchone()
        return self._record(row) if row else None

    def list(self, *, account='', scope=None, provider=None, statuses=None, limit=20):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise MediaError('invalid_pagination')
        query, values = 'SELECT * FROM jobs WHERE 1=1', []
        for column, value in (('account', account or None), ('provider', provider),
                              ('scope', canonical(scope) if scope is not None else None)):
            if value is not None:
                query += ' AND ' + column + '=?'
                values.append(value)
        if statuses is not None:
            if not isinstance(statuses, (list, tuple, set)) or not statuses or set(statuses) - JOB_STATES:
                raise MediaError('invalid_job_state')
            query += ' AND state IN (' + ','.join('?' for _ in statuses) + ')'
            values.extend(statuses)
        query += ' ORDER BY created DESC,id LIMIT ?'
        with self.db() as db:
            return [self._record(row) for row in db.execute(query, [*values, limit])]

    def recover(self):
        """Only call while no submission runners are active; never replays I/O."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            ids = [row[0] for row in db.execute("SELECT id FROM jobs WHERE state='submitting'")]
            db.execute("UPDATE jobs SET state='outcome_unknown',error='interrupted_submission',updated=? "
                       "WHERE state='submitting'", (time.time(),))
            db.commit()
        return ids


def _money(value):
    try:
        if type(value) is bool:
            raise ValueError()
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > Decimal('1000000000'):
            raise ValueError()
        return int((amount * 1_000_000_000).to_integral_value(rounding=ROUND_CEILING))
    except (ValueError, TypeError, InvalidOperation):
        raise MediaError('invalid_money_amount') from None


def _amount(nanos):
    return str(Decimal(nanos) / 1_000_000_000) if nanos is not None else None


class BudgetLedger(_Database):
    def __init__(self, state_dir, *, clock=time.time):
        self.clock = clock
        super().__init__(state_dir, 'media-budget.sqlite3', '''
            CREATE TABLE IF NOT EXISTS reservations (
                job_id TEXT PRIMARY KEY, provider TEXT NOT NULL, account TEXT NOT NULL,
                currency TEXT NOT NULL, created REAL NOT NULL, day TEXT NOT NULL, month TEXT NOT NULL,
                reserved INTEGER, actual INTEGER, state TEXT NOT NULL);
        ''')

    @staticmethod
    def _record(row):
        if row is None:
            raise MediaError('budget_reservation_not_found')
        return {**dict(row), 'estimated_cost': _amount(row['reserved']), 'actual_cost': _amount(row['actual'])}

    def reserve(self, job_id, provider, estimated_cost, *, account, limits=None, currency='USD'):
        limits = limits or {}
        if (not isinstance(limits, dict) or set(limits) - {'per_task', 'day', 'month', 'per_call', 'daily', 'monthly'}
                or not isinstance(account, str) or not account or not re.fullmatch('[A-Z]{3}', currency)):
            raise MediaError('invalid_budget_policy')
        aliases = {'per_task': 'per_call', 'day': 'daily', 'month': 'monthly'}
        caps = {}
        for key, value in limits.items():
            if value is None:
                continue
            name, amount = aliases.get(key, key), _money(value)
            if name in caps and caps[name] != amount:
                raise MediaError('conflicting_budget_limits')
            caps[name] = amount
        estimate = _money(estimated_cost) if estimated_cost is not None else None
        now = self.clock()
        day = time.strftime('%Y-%m-%d', time.gmtime(now))
        month = day[:7]
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM reservations WHERE job_id=?', (job_id,)).fetchone()
            if old:
                if any(old[key] != value for key, value in {'provider': provider, 'account': account,
                        'currency': currency, 'reserved': estimate}.items()):
                    raise MediaError('budget_identity_conflict')
                db.commit()
                return self._record(old)
            if estimate is None and caps:
                raise MediaError('cost_bound_required_for_budget')
            if 'per_call' in caps and estimate > caps['per_call']:
                raise MediaError('per_call_budget_exceeded')
            for period, stamp, column in (('daily', day, 'day'), ('monthly', month, 'month')):
                if period not in caps:
                    continue
                rows = db.execute('SELECT reserved,actual,state FROM reservations '
                                  'WHERE provider=? AND account=? AND currency=? AND ' + column + "=? AND state!='released'",
                                  (provider, account, currency, stamp)).fetchall()
                amounts = [row['actual'] if row['state'] == 'settled' else row['reserved'] for row in rows]
                if any(amount is None for amount in amounts):
                    raise MediaError('unbounded_previous_spend')
                if sum(amounts) + estimate > caps[period]:
                    raise MediaError(period + '_budget_exceeded')
            db.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?,?,?,NULL,\'reserved\')',
                       (job_id, provider, account, currency, now, day, month, estimate))
            row = db.execute('SELECT * FROM reservations WHERE job_id=?', (job_id,)).fetchone()
            db.commit()
        return self._record(row)

    def _change(self, job_id, state, actual=None, *, account=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM reservations WHERE job_id=?', (job_id,)).fetchone()
            record = self._record(row)
            if account is not None and row['account'] != account:
                raise MediaError('budget_account_mismatch')
            if row['state'] == 'settled':
                if state == 'settled' and row['actual'] == actual:
                    db.commit()
                    return record
                raise MediaError('budget_already_settled')
            if row['state'] == 'released' and state != 'released':
                raise MediaError('budget_already_released')
            db.execute('UPDATE reservations SET state=?,actual=? WHERE job_id=?', (state, actual, job_id))
            row = db.execute('SELECT * FROM reservations WHERE job_id=?', (job_id,)).fetchone()
            db.commit()
        return self._record(row)

    def reconcile(self, job_id, actual_cost, *, account=None):
        return self._change(job_id, 'settled', _money(actual_cost), account=account)

    def mark_unknown(self, job_id, *, account=None):
        return self._change(job_id, 'unknown', account=account)

    def release(self, job_id, *, account=None):
        """Only after explicit non-billable rejection; timeout/cancellation is insufficient."""
        return self._change(job_id, 'released', account=account)

    def snapshot(self, provider=None, *, account=None):
        query, values = 'SELECT * FROM reservations WHERE 1=1', []
        for column, value in (('provider', provider), ('account', account)):
            if value is not None:
                query += ' AND ' + column + '=?'
                values.append(value)
        with self.db() as db:
            rows = db.execute(query, values).fetchall()
        return {'reservations': [self._record(row) for row in rows],
                'unbounded_count': sum(row['reserved'] is None and row['actual'] is None
                                       and row['state'] != 'released' for row in rows)}


class ArtifactStore:
    def __init__(self, state_dir):
        self.root = _private_root(_private_root(state_dir) / 'media-artifacts')

    def _path(self, artifact_id):
        if not isinstance(artifact_id, str) or not re.fullmatch('[a-f0-9]{64}', artifact_id):
            raise MediaError('invalid_artifact_id')
        path = self.root / (artifact_id + '.json')
        if path.is_symlink():
            raise MediaError('invalid_artifact_manifest')
        return path

    @staticmethod
    def _view(row):
        return {key: row[key] for key in ('id', 'artifact_id', 'job_id', 'status', 'path', 'bytes',
                'sha256', 'mime_type', 'filename') if key in row}

    @contextmanager
    def _lock(self, artifact_id):
        self._path(artifact_id)
        fd = os.open(self.root / (artifact_id + '.lock'), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def register(self, url, job_id, metadata=None):
        _url(url, artifact=True)
        if not isinstance(job_id, str) or not job_id or len(job_id) > 256:
            raise MediaError('invalid_job_id')
        ident = hashlib.sha256(canonical([job_id, url]).encode()).hexdigest()
        path = self._path(ident)
        with self._lock(ident):
            if path.exists():
                return self.get(ident)
            row = {'id': ident, 'artifact_id': ident, 'job_id': job_id, 'status': 'remote',
                   'source_url': url, 'metadata': metadata or {}}
            _write_private(path, row)
            return self._view(row)

    def get(self, artifact_id):
        path = self._path(artifact_id)
        if not path.is_file():
            raise MediaError('artifact_not_found')
        row = json.loads(path.read_text())
        if row.get('id') != artifact_id:
            raise MediaError('artifact_integrity_failed')
        if row.get('status') == 'downloaded':
            if (not re.fullmatch('[a-f0-9]{64}', row.get('sha256', ''))
                    or row.get('extension') not in ('.png', '.jpg', '.gif', '.pdf', '.ogg', '.mp3',
                                                   '.flac', '.webp', '.wav', '.mp4', '.webm', '.bin')):
                raise MediaError('artifact_integrity_failed')
            target = self.root / (row['sha256'] + row['extension'])
            if (target.is_symlink() or not target.is_file() or target.stat().st_size != row['bytes']
                    or hashlib.sha256(target.read_bytes()).hexdigest() != row['sha256']):
                raise MediaError('artifact_integrity_failed')
            row['path'] = str(target)
        return self._view(row)

    def download(self, url, job_id, *, transport=None, max_bytes=256 * 1024 * 1024, metadata=None):
        manifest = self.register(url, job_id, metadata)
        return self.download_registered(manifest['id'], transport=transport, max_bytes=max_bytes)

    def download_registered(self, artifact_id, *, transport=None, max_bytes=256 * 1024 * 1024):
        with self._lock(artifact_id):
            return self._download_registered(artifact_id, transport=transport, max_bytes=max_bytes)

    def _download_registered(self, artifact_id, *, transport=None, max_bytes=256 * 1024 * 1024):
        view = self.get(artifact_id)
        if view['status'] == 'downloaded':
            return view
        if type(max_bytes) is not int or not 0 < max_bytes <= 1024 * 1024 * 1024:
            raise MediaError('invalid_artifact_size_limit')
        path = self._path(artifact_id)
        row = json.loads(path.read_text())
        _, host = _url(row['source_url'], artifact=True)
        # Even injected/test transports do not make arbitrary or private hosts eligible.
        _public_addresses(host)
        client = transport or MediaHTTP(allowed_hosts={host}, max_binary_bytes=max_bytes)
        raw = client.request('GET', row['source_url'], headers={}, timeout=60, response_kind='binary')
        if not isinstance(raw, bytes) or len(raw) > max_bytes:
            raise MediaError('artifact_too_large')
        if not raw:
            raise MediaError('empty_artifact')
        if raw.lstrip()[:100].lower().startswith((b'<!doctype html', b'<html', b'<script', b'<svg')):
            raise MediaError('unexpected_artifact_content')
        signatures = ((b'\x89PNG\r\n\x1a\n', 'image/png', '.png'), (b'\xff\xd8\xff', 'image/jpeg', '.jpg'),
                      (b'GIF8', 'image/gif', '.gif'), (b'%PDF-', 'application/pdf', '.pdf'),
                      (b'OggS', 'audio/ogg', '.ogg'), (b'ID3', 'audio/mpeg', '.mp3'),
                      (b'fLaC', 'audio/flac', '.flac'))
        mime, extension = 'application/octet-stream', '.bin'
        for signature, candidate, suffix in signatures:
            if raw.startswith(signature):
                mime, extension = candidate, suffix
                break
        if raw[:4] == b'RIFF' and raw[8:12] in (b'WEBP', b'WAVE'):
            mime, extension = ('image/webp', '.webp') if raw[8:12] == b'WEBP' else ('audio/wav', '.wav')
        elif raw[4:8] == b'ftyp':
            mime, extension = 'video/mp4', '.mp4'
        elif raw.startswith(b'\x1aE\xdf\xa3'):
            mime, extension = 'video/webm', '.webm'
        digest = hashlib.sha256(raw).hexdigest()
        destination = self.root / (digest + extension)
        if destination.exists():
            if destination.is_symlink() or hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                raise MediaError('artifact_integrity_failed')
        else:
            _write_private(destination, raw)
        row.update(status='downloaded', path=str(destination), bytes=len(raw), sha256=digest,
                   mime_type=mime, extension=extension, filename=digest[:16] + extension)
        _write_private(path, row)
        return self._view(row)
