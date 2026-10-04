"""Wire-only adapter with a durable outbox. Never infer routes from conversation text.

Clean baseline 298df082 lacks request_origin: callbacks remain inert, with a diagnostic.
The explicit origin contract may be enabled ONLY on a separately verified host build.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import re
import sqlite3
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("automation-bridge")
FIELDS = ("profile", "platform", "chat_id", "thread_id", "user_id", "message_id", "session_id")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class Bridge:
    def __init__(self, *, endpoint, token_file, state_dir, profile, origin_contract="unavailable",
                 topic_icons=False, voice_reply=True):
        parsed = urllib.parse.urlparse(endpoint)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username
                or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError("bridge_requires_loopback_http_endpoint")
        root = Path(state_dir)
        if not root.is_absolute():
            raise ValueError("bridge_requires_absolute_state_dir")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink() or root.stat().st_mode & 0o077:
            raise ValueError("bridge_state_permissions")
        self.path = root / "outbox.sqlite3"
        self.profile, self.endpoint = profile, endpoint.rstrip("/")
        fd = os.open(token_file, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if info.st_mode & 0o077 or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError("bridge_token_permissions")
            self.token = os.read(fd, 8192).decode().strip()
            if len(self.token) < 24 or any(c.isspace() for c in self.token):
                raise ValueError("invalid_bridge_token")
        finally:
            os.close(fd)
        self.origin_supported = origin_contract == "hermes-request-origin-v1"
        self._warned_missing_origin = False
        self.topic_icons, self.voice_reply = topic_icons, voice_reply
        self.stopped = threading.Event()
        self.thread = None
        self.lock_fd = None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS bindings (
                  session TEXT, turn TEXT, body TEXT, created REAL,
                  PRIMARY KEY(session,turn));
                CREATE TABLE IF NOT EXISTS outbox (
                  id TEXT PRIMARY KEY, body TEXT NOT NULL, state TEXT NOT NULL,
                  attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
                  job_id TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS preferences (
                  origin TEXT PRIMARY KEY, speech_enabled INTEGER NOT NULL, created REAL NOT NULL);
            """)
        self.path.chmod(0o600)
        if not self.origin_supported:
            logger.warning("automation-bridge: automatic routing unavailable; verified request_origin contract missing")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def before(self, *, session_id="", turn_id="", request_origin=None, platform="",
               user_message="", is_first_turn=False, **kwargs):
        if not self.origin_supported:
            return
        origin = request_origin
        if (not isinstance(origin, dict) or any(not isinstance(origin.get(k), str) for k in FIELDS)
                or origin["session_id"] != session_id or origin["platform"] != platform
                or origin["profile"] != self.profile or not isinstance(turn_id, str) or not turn_id
                or type(origin.get("internal")) is not bool
                or origin.get("message_type") not in ("voice", "text")
                or not origin["message_id"] or not origin["chat_id"] or not origin["user_id"]):
            if not self._warned_missing_origin:
                logger.warning("automation-bridge: missing or invalid request_origin; automatic routing suppressed")
                self._warned_missing_origin = True
            return
        body = {
            "source": {**{k: origin[k] for k in FIELDS}, "turn_id": turn_id},
            "origin_type": origin["message_type"], "first": is_first_turn is True,
            "internal": origin["internal"],
            "topic_hint": user_message[:128] if isinstance(user_message, str) else "",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        origin_key = json.dumps([origin[k] for k in FIELDS if k != "session_id"])
        with self.db() as db:
            db.execute("DELETE FROM bindings WHERE created<?", (time.time() - 86400,))
            db.execute("DELETE FROM preferences WHERE created<?", (time.time() - 86400,))
            if origin["internal"]:
                saved = db.execute("SELECT speech_enabled FROM preferences WHERE origin=?", (origin_key,)).fetchone()
                if saved is None:
                    return  # no original request preference, no permission to voice a continuation
                body["speech_enabled"] = bool(saved[0])
            else:
                body["speech_enabled"] = not bool(re.search(
                    r"только\s+текстом|без\s+голос\w*|не\s+озвуч\w*",
                    user_message if isinstance(user_message, str) else "", re.I))
                db.execute("INSERT INTO preferences VALUES(?,?,?) ON CONFLICT(origin) DO NOTHING",
                           (origin_key, int(body["speech_enabled"]), time.time()))
            # Same turn must not change identity when a host erroneously invokes the hook twice.
            db.execute("INSERT OR IGNORE INTO bindings VALUES(?,?,?,?)",
                       (session_id, turn_id, json.dumps(body), time.time()))

    def after(self, *, session_id="", turn_id="", assistant_response=None, **kwargs):
        if (not self.origin_supported or not isinstance(assistant_response, str) or not assistant_response.strip()
                or assistant_response.strip() in {"NO_REPLY", "HEARTBEAT_OK"}):
            return
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM bindings WHERE session=? AND turn=?", (session_id, turn_id)).fetchone()
            if not row:
                return
            binding = json.loads(row[0])
            events = []
            if self.voice_reply and binding["origin_type"] == "voice" and binding.get("speech_enabled", False):
                events.append(("reply.completed", {"text": assistant_response, "origin_type": "voice"}))
            if (self.topic_icons and binding["first"] and not binding["internal"]
                    and binding["source"]["thread_id"] and binding["topic_hint"].strip()):
                # A classification hint, not a claim to observe Hermes's generated topic title.
                events.append(("topic.observed", {"title": binding["topic_hint"]}))
            for kind, data in events:
                key = json.dumps([self.profile, session_id, turn_id, kind], separators=(",", ":"))
                event_id = hashlib.sha256(key.encode()).hexdigest()
                event = {"schema": 1, "event_id": event_id, "kind": kind,
                         "occurred_at": binding["occurred_at"], "source": binding["source"], "data": data}
                db.execute("INSERT OR IGNORE INTO outbox(id,body,state) VALUES(?,?,'pending')",
                           (event_id, json.dumps(event, ensure_ascii=False)))
            db.execute("DELETE FROM bindings WHERE session=? AND turn=?", (session_id, turn_id))

    def flush_once(self):
        with self.db() as db:
            row = db.execute("SELECT id,body,attempts FROM outbox WHERE state='pending' AND next_attempt<=? ORDER BY rowid LIMIT 1",
                             (time.time(),)).fetchone()
        if not row:
            return False
        event_id, body, attempts = row
        req = urllib.request.Request(self.endpoint + "/v1/events", data=body.encode(), headers={
            "Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        code, result = 0, {}
        try:
            with self.opener.open(req, timeout=3) as response:
                code = response.status
                result = json.loads(response.read(65536))
        except urllib.error.HTTPError as exc:
            code = exc.code
        except (OSError, ValueError, urllib.error.URLError):
            pass
        if code in (200, 202) and isinstance(result, dict) and isinstance(result.get("job_id"), str):
            state, error, job_id = "accepted", None, result["job_id"]
        elif code in (400, 401, 403, 404, 409, 413):
            state, error, job_id = "rejected", "admission_rejected_" + str(code), None
        else:
            state, error, job_id = "pending", "admission_unavailable", None
        with self.db() as db:
            db.execute("UPDATE outbox SET state=?,attempts=?,next_attempt=?,job_id=?,error=? WHERE id=?",
                       (state, attempts + 1, time.time() + min(60, 2 ** min(attempts, 6)), job_id, error, event_id))
        return True

    def _run(self):
        while not self.stopped.is_set():
            try:
                self.flush_once()
            except Exception:
                logger.warning("automation-bridge: outbox unavailable")
            self.stopped.wait(0.5)

    def start(self):
        self.lock_fd = os.open(self.path.parent / "sender.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.lock_fd)
            self.lock_fd = None
            raise RuntimeError("bridge_sender_already_running") from None
        self.thread = threading.Thread(target=self._run, name="automation-bridge-outbox", daemon=True)
        self.thread.start()

    def close(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                self.thread.join()
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None
