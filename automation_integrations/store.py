"""Short SQLite transactions. A process lock owns worker recovery and outbound sends."""
from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .contracts import Conflict, KINDS, canonical, digest


class Store:
    def __init__(self, state_dir):
        self.root = Path(state_dir)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_mode & 0o077:
            raise ValueError("state_dir_requires_private_directory")
        self.path = self.root / "jobs.sqlite3"
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, connection TEXT NOT NULL, event_id TEXT NOT NULL,
                  event_hash TEXT NOT NULL, event TEXT NOT NULL, module TEXT NOT NULL,
                  state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                  error TEXT, dry_run INTEGER NOT NULL DEFAULT 1, UNIQUE(connection, event_id));
                CREATE TABLE IF NOT EXISTS actions (
                  id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), ordinal INTEGER,
                  payload TEXT NOT NULL, state TEXT NOT NULL, receipt TEXT, error TEXT,
                  UNIQUE(job_id, ordinal));
                CREATE TABLE IF NOT EXISTS icons (
                  connection TEXT, profile TEXT, chat TEXT, thread TEXT, emoji TEXT, updated REAL,
                  PRIMARY KEY(connection,profile,chat,thread));
                CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(state, created);
                CREATE TABLE IF NOT EXISTS journal (
                  sequence INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                  action_id TEXT, state TEXT NOT NULL, error TEXT, at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS topic_versions (
                  connection TEXT, profile TEXT, chat TEXT, thread TEXT, occurred REAL, job_id TEXT,
                  PRIMARY KEY(connection,profile,chat,thread));
            """)
            if "dry_run" not in {row[1] for row in db.execute("PRAGMA table_info(jobs)")}:
                db.execute("ALTER TABLE jobs ADD COLUMN dry_run INTEGER NOT NULL DEFAULT 1")
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def worker_lock(self):
        fd = os.open(self.root / "worker.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("worker_already_running") from None
            yield
        finally:
            os.close(fd)

    def accept(self, connection, event, *, dry_run=True):
        event_hash = digest(event)
        job_id = digest([connection, event["event_id"]])
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT id,event_hash FROM jobs WHERE connection=? AND event_id=?",
                             (connection, event["event_id"])).fetchone()
            if old:
                db.rollback()
                if old["event_hash"] != event_hash:
                    raise Conflict("event_id_payload_conflict")
                return old["id"], False
            now = time.time()
            db.execute("INSERT INTO jobs(id,connection,event_id,event_hash,event,module,state,created,updated,error,dry_run) "
                       "VALUES(?,?,?,?,?,?,?,?,?,NULL,?)",
                       (job_id, connection, event["event_id"], event_hash, canonical(event),
                        KINDS[event["kind"]], "queued", now, now, int(dry_run)))
            db.execute("INSERT INTO journal(job_id,state,at) VALUES(?,'queued',?)", (job_id, now))
            if event["kind"] == "topic.observed":
                src = event["source"]
                occurred = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00")).timestamp()
                db.execute("INSERT INTO topic_versions VALUES(?,?,?,?,?,?) "
                           "ON CONFLICT(connection,profile,chat,thread) DO UPDATE SET occurred=excluded.occurred,job_id=excluded.job_id "
                           "WHERE excluded.occurred>=topic_versions.occurred",
                           (connection, src["profile"], src["chat_id"], src["thread_id"], occurred, job_id))
            db.commit()
        return job_id, True

    def recover(self):
        # Called only while holding worker_lock. A interrupted preparation may have billed a
        # provider: do not automatically regenerate it. A send may have reached Telegram.
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            interrupted = [r[0] for r in db.execute("SELECT id FROM jobs WHERE state='running'")]
            db.execute("UPDATE actions SET state='outcome_unknown',error='worker_interrupted' WHERE state='sending'")
            db.execute("UPDATE jobs SET state='delivered',updated=? WHERE state='running' "
                       "AND EXISTS (SELECT 1 FROM actions WHERE job_id=jobs.id) "
                       "AND NOT EXISTS (SELECT 1 FROM actions WHERE job_id=jobs.id AND state<>'delivered')", (time.time(),))
            db.execute("UPDATE jobs SET state='outcome_unknown',error='worker_interrupted',updated=? "
                       "WHERE state='running' AND id IN (SELECT job_id FROM actions WHERE state='outcome_unknown')",
                       (time.time(),))
            db.execute("UPDATE jobs SET state='partial',error='worker_interrupted',updated=? "
                       "WHERE state='running' AND id IN (SELECT job_id FROM actions WHERE state='delivered')", (time.time(),))
            db.execute("UPDATE jobs SET state='failed',error='preparation_interrupted',updated=? WHERE state='running'",
                       (time.time(),))
            for job_id in interrupted:
                row = db.execute("SELECT state,error FROM jobs WHERE id=?", (job_id,)).fetchone()
                db.execute("INSERT INTO journal(job_id,state,error,at) VALUES(?,?,?,?)",
                           (job_id, row["state"], row["error"], time.time()))
            db.commit()

    def claim(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created,id LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET state='running',updated=? WHERE id=?", (time.time(), row["id"]))
                db.execute("INSERT INTO journal(job_id,state,at) VALUES(?,'running',?)", (row["id"], time.time()))
            db.commit()
        if row:
            result = dict(row)
            result["event"] = json.loads(result["event"])
            return result
        return None

    def finish(self, job_id, state, error=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE jobs SET state=?,error=?,updated=? WHERE id=?", (state, error, time.time(), job_id))
            db.execute("INSERT INTO journal(job_id,state,error,at) VALUES(?,?,?,?)", (job_id, state, error, time.time()))
            db.commit()

    def prepare_actions(self, job_id, actions):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for i, action in enumerate(actions):
                db.execute("INSERT INTO actions VALUES(?,?,?,?,?,NULL,NULL)",
                           (digest([job_id, i]), job_id, i, canonical(action), "prepared"))
            db.commit()

    def actions(self, job_id):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM actions WHERE job_id=? ORDER BY ordinal", (job_id,))]

    def action_state(self, action_id, state, receipt=None, error=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE actions SET state=?,receipt=?,error=? WHERE id=?",
                       (state, canonical(receipt) if receipt else None, error, action_id))
            db.execute("INSERT INTO journal(job_id,action_id,state,error,at) "
                       "SELECT job_id,id,?,?,? FROM actions WHERE id=?", (state, error, time.time(), action_id))
            db.commit()

    def delivered(self, action_id, receipt, connection, source, emoji=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE actions SET state='delivered',receipt=?,error=NULL WHERE id=?", (canonical(receipt), action_id))
            db.execute("INSERT INTO journal(job_id,action_id,state,at) SELECT job_id,id,'delivered',? FROM actions WHERE id=?",
                       (time.time(), action_id))
            if emoji:
                db.execute("INSERT INTO icons VALUES(?,?,?,?,?,?) ON CONFLICT(connection,profile,chat,thread) "
                           "DO UPDATE SET emoji=excluded.emoji,updated=excluded.updated",
                           (connection, source["profile"], source["chat_id"], source["thread_id"], emoji, time.time()))
            db.commit()

    def current_topic(self, connection, source, job_id):
        with self.db() as db:
            row = db.execute("SELECT job_id FROM topic_versions WHERE connection=? AND profile=? AND chat=? AND thread=?",
                             (connection, source["profile"], source["chat_id"], source["thread_id"])).fetchone()
            return row is not None and row[0] == job_id

    def snapshot(self, job_id, connection=None):
        with self.db() as db:
            row = db.execute("SELECT id,connection,event_id,module,state,created,updated,error,dry_run FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None or connection is not None and row["connection"] != connection:
                return None
            out = dict(row)
            out["actions"] = [dict(r) for r in db.execute(
                "SELECT ordinal,state,receipt,error FROM actions WHERE job_id=? ORDER BY ordinal", (job_id,))]
            out["history"] = [dict(r) for r in db.execute(
                "SELECT sequence,action_id,state,error,at FROM journal WHERE job_id=? ORDER BY sequence LIMIT 200", (job_id,))]
            return out

    def counts(self, connection=None):
        with self.db() as db:
            where, args = (" WHERE connection=?", (connection,)) if connection else ("", ())
            return dict(db.execute("SELECT state,COUNT(*) FROM jobs" + where + " GROUP BY state", args).fetchall())

    def recent_icons(self, connection, source):
        with self.db() as db:
            return [r[0] for r in db.execute(
                "SELECT emoji FROM icons WHERE connection=? AND profile=? AND chat=? AND thread<>? ORDER BY updated DESC LIMIT 4",
                (connection, source["profile"], source["chat_id"], source["thread_id"]))]
