"""Isolated Runs API prototype. Trusted synthetic ingress; never sends Telegram messages."""
from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

from .config import secret_file
from .contracts import ContractError, Conflict, Forbidden, canonical, digest, identifier, validate_event

# Nonempty caller-owned history disables detached delivery in the pinned Hermes API.
SEED = [{"role": "system", "content": "Conversation history is managed by the integration client."}]
FINAL = {"completed", "failed", "cancelled", "interrupted", "rejected", "outcome_unknown"}
ACTIVE = {"queued", "running", "started", "stopping", "waiting_for_approval"}


class RemoteError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(f"remote_http_{code}")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class RunsHTTP:
    def __init__(self, endpoint, token_file, timeout=5):
        p = urlsplit(endpoint)
        if (p.scheme != "http" or p.hostname != "127.0.0.1" or not p.port
                or p.username or p.password or p.path not in ("", "/") or p.query or p.fragment):
            raise ContractError("prototype_requires_loopback_endpoint")
        self.endpoint = endpoint.rstrip("/")
        self.token = secret_file(token_file)
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        # A persisted queue cannot silently move to another server/auth principal.
        self.binding = digest([self.endpoint, self.token])

    def request(self, method, path, body=None, key=None):
        headers = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}
        if key:
            headers["Idempotency-Key"] = key
        req = Request(self.endpoint + path, data=canonical(body).encode() if body is not None else None,
                      method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                raw = response.read(262145)
                if len(raw) > 262144:
                    raise ContractError("oversized_remote_response")
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ContractError("invalid_remote_response")
                return result
        except HTTPError as exc:
            code = exc.code
            exc.close()
            raise RemoteError(code) from None
        except (URLError, TimeoutError, OSError):
            raise RemoteError(0) from None
        except (ValueError, UnicodeError):
            raise ContractError("invalid_remote_response") from None


class RunsPrototype:
    """Durable origin → request → run → result → dry-run plugin job.

    Public methods are for a trusted test harness, not an unauthenticated ingress API.
    Polling is explicit; no unbounded retry loop and no automatic approval/continuation.
    """
    def __init__(self, root, client, routes):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or self.root.stat().st_mode & 0o077:
            raise ContractError("private_state_required")
        self.client, self.routes = client, routes
        self.path = self.root / "runs.sqlite3"
        if self.path.is_symlink():
            raise ContractError("invalid_state_file")
        with self.db() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS binding (value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS turns (
                  seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                  origin TEXT NOT NULL, input TEXT NOT NULL, mode TEXT NOT NULL, scope TEXT NOT NULL,
                  fingerprint TEXT NOT NULL, state TEXT NOT NULL, body TEXT, first_attempt REAL,
                  run_id TEXT UNIQUE, output TEXT, event TEXT, error TEXT, job_id TEXT);
            ''')
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT value FROM binding").fetchone()
            if old and old[0] != client.binding:
                raise ContractError("endpoint_or_credential_changed")
            if not old:
                db.execute("INSERT INTO binding VALUES(?)", (client.binding,))
            db.commit()
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def lock(self):
        fd = os.open(self.root / "driver.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ContractError("driver_already_running") from None
            yield
        finally:
            os.close(fd)

    def submit(self, origin, text, *, mode="text"):
        fields = {"profile", "platform", "chat_id", "thread_id", "user_id", "message_id", "message_type"}
        if not isinstance(origin, dict) or set(origin) != fields:
            raise ContractError("invalid_origin")
        for k, v in origin.items():
            if k == "thread_id" and v == "":
                continue
            identifier(v)
        if origin["platform"] != "telegram" or origin["message_type"] not in {"voice", "text"}:
            raise ContractError("invalid_origin_type")
        if mode not in {"text", "voice"} or (mode == "voice" and origin["message_type"] != "voice"):
            raise ContractError("invalid_response_mode")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 16000:
            raise ContractError("invalid_input")
        if not self.allowed(origin):
            raise Forbidden("route_not_allowed")
        identity = [origin[k] for k in ("profile", "platform", "chat_id", "thread_id", "user_id")]
        scope = digest(identity)
        turn = digest(identity + [origin["message_id"]])
        fingerprint = digest([origin, text, mode])
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT fingerprint FROM turns WHERE id=?", (turn,)).fetchone()
            if row and row[0] != fingerprint:
                raise Conflict("message_payload_conflict")
            if not row:
                db.execute("INSERT INTO turns(id,origin,input,mode,scope,fingerprint,state) VALUES(?,?,?,?,?,?,'pending')",
                           (turn, canonical(origin), text, mode, scope, fingerprint))
            db.commit()
        return turn

    def allowed(self, origin):
        return any(all(origin[k] == route[k] for k in ("profile", "platform", "chat_id", "user_id"))
                   and origin["thread_id"] in route["thread_ids"] for route in self.routes)

    def snapshot(self, turn):
        with self.db() as db:
            row = db.execute("SELECT * FROM turns WHERE id=?", (turn,)).fetchone()
        if row is None:
            raise ContractError("unknown_turn")
        return dict(row)

    def update(self, turn, **values):
        with self.db() as db:
            db.execute("UPDATE turns SET " + ",".join(k + "=?" for k in values) + " WHERE id=?",
                       (*values.values(), turn))

    def step(self, turn, *, now=None):
        with self.lock():
            return self._step(turn, time.time() if now is None else now)

    def _step(self, turn, now):
        row = self.snapshot(turn)
        if row["state"] in FINAL:
            return row["state"]
        if not self.allowed(json.loads(row["origin"])):
            self.update(turn, state="rejected", error="route_revoked")
            return "rejected"
        if row["body"] is None:
            with self.db() as db:
                previous = db.execute("SELECT * FROM turns WHERE scope=? AND seq<? ORDER BY seq",
                                      (row["scope"], row["seq"])).fetchall()
            # Unknown/failed/cancelled turns block the lane for explicit operator reconciliation.
            if any(p["state"] != "completed" for p in previous):
                return "blocked_by_previous_turn"
            history = list(SEED)
            for p in previous:
                history.extend([{"role": "user", "content": p["input"]},
                                {"role": "assistant", "content": p["output"]}])
            body = {"input": row["input"], "session_id": "integration-" + row["scope"],
                    "conversation_history": history}
            if len(canonical(body).encode()) > 120000:
                self.update(turn, state="rejected", error="history_limit")
                return "rejected"
            self.update(turn, body=canonical(body), first_attempt=now, state="submitting")
            row = self.snapshot(turn)
        try:
            if not row["run_id"]:
                # Hermes retains idempotency keys for 24h; never replay beyond a conservative window.
                if now - row["first_attempt"] >= 23 * 3600 or now < row["first_attempt"]:
                    self.update(turn, state="outcome_unknown", error="retry_window_expired")
                    return "outcome_unknown"
                result = self.client.request("POST", "/v1/runs", json.loads(row["body"]), turn)
                run = identifier(result.get("run_id"))
                self.update(turn, run_id=run, state="running", error=None)
                return "running"
            result = self.client.request("GET", "/v1/runs/" + row["run_id"])
            if result.get("run_id") != row["run_id"] or result.get("session_id") != "integration-" + row["scope"]:
                raise ContractError("remote_identity_mismatch")
            status = result.get("status")
            if status in ACTIVE:
                self.update(turn, state=status, error=None)
                return status
            if status not in {"completed", "failed", "cancelled", "interrupted"}:
                raise ContractError("unknown_remote_status")
            if status != "completed":
                self.update(turn, state=status, error="remote_" + status)
                return status
            output = result.get("output")
            if not isinstance(output, str) or len(output) > 24000:
                raise ContractError("invalid_final_output")
            event = None
            if row["mode"] == "voice" and output.strip() and output.strip() not in {"NO_REPLY", "HEARTBEAT_OK"}:
                origin = json.loads(row["origin"])
                source = {k: v for k, v in origin.items() if k != "message_type"}
                source.update(session_id="integration-" + row["scope"], turn_id=row["run_id"])
                event = {"schema": 1, "event_id": "runs-" + turn, "kind": "reply.completed",
                         "occurred_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                         "source": source, "data": {"text": output, "origin_type": "voice"}}
            self.update(turn, state="completed", output=output, event=canonical(event) if event else None, error=None)
            return "completed"
        except RemoteError as exc:
            if exc.code in {0, 408, 429} or exc.code >= 500:
                self.update(turn, error="transient_remote_failure")
                return "retryable"
            state = "outcome_unknown" if row["run_id"] else "rejected"
            self.update(turn, state=state, error=f"remote_http_{exc.code}")
            return state
        except (ContractError, sqlite3.IntegrityError):
            self.update(turn, state="outcome_unknown", error="remote_contract_violation")
            return "outcome_unknown"

    def publish_dry_run(self, turn, store, connection, policy):
        """Replay-safe admission into the existing job engine. Live delivery is impossible here."""
        with self.lock():
            row = self.snapshot(turn)
            if row["job_id"]:
                return row["job_id"]
            if row["state"] != "completed" or not row["event"]:
                return None
            event = validate_event(json.loads(row["event"]), policy)
            if not self.allowed(event["source"]):
                raise Forbidden("route_revoked")
            job_id, _ = store.accept(connection, event, dry_run=True)
            self.update(turn, job_id=job_id)
            return job_id
