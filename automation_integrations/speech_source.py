"""Bounded raw-response handoff. Never infer a source from a similar/partial string."""
import hashlib
from contextlib import contextmanager
import json
import os
import sqlite3
import time
from pathlib import Path


def key(text):
    return hashlib.sha256(text.strip().encode()).hexdigest()


class Sources:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_mode & 0o077:
            raise ValueError('private_source_directory_required')
        self.path = self.root / 'sources.sqlite3'
        if self.path.is_symlink():
            raise ValueError('invalid_source_database')
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sources (turn TEXT PRIMARY KEY, fingerprint TEXT, payload TEXT, expires REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS events (created REAL, fingerprint TEXT, status TEXT)')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def put(self, turn, cleaned, original, context, now=None):
        now = time.time() if now is None else now
        if not cleaned.strip() or not 0 < len(original) <= 16000:
            raise ValueError('source_size_limit')
        payload = json.dumps({'original': original, 'context': context[-12000:]}, ensure_ascii=False)
        with self.db() as db:
            db.execute('DELETE FROM sources WHERE expires < ?', (now,))
            db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?,?)', (turn, key(cleaned), payload, now + 600))

    def get(self, cleaned, now=None):
        now = time.time() if now is None else now
        with self.db() as db:
            db.execute('DELETE FROM sources WHERE expires < ?', (now,))
            rows = db.execute('SELECT payload FROM sources WHERE fingerprint=?', (key(cleaned),)).fetchall()
        # Same cleaned response can hide DIFFERENT dates/numbers. Never select the newest.
        if len(rows) != 1:
            raise ValueError('raw_speech_source_missing_or_ambiguous')
        return json.loads(rows[0][0])

    def record(self, cleaned, status):
        with self.db() as db:
            db.execute('DELETE FROM events WHERE created < ?', (time.time() - 7 * 86400,))
            db.execute('INSERT INTO events VALUES(?,?,?)', (time.time(), key(cleaned), status))
