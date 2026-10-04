"""Serialized semantic topic styling. Model chooses; local code owns routing and exclusions."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class TopicStyles:
    def __init__(self, root):
        root = Path(root)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink() or root.stat().st_mode & 0o077:
            raise ValueError('private_topic_state_required')
        self.path = root / 'topics.sqlite3'
        if self.path.is_symlink():
            raise ValueError('invalid_topic_database')
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS topics(chat TEXT, thread INTEGER, title TEXT DEFAULT '', emoji TEXT DEFAULT '',
              icon TEXT DEFAULT '', updated REAL DEFAULT 0, PRIMARY KEY(chat,thread));
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, chat TEXT, thread INTEGER, context TEXT,
              created REAL, state TEXT DEFAULT 'queued', title TEXT, emoji TEXT, icon TEXT, error TEXT);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def recover(self):
        with self.db() as db:
            db.execute("UPDATE jobs SET state='outcome_unknown',error='restart_during_send',context='' WHERE state='sending'")
            db.execute("UPDATE jobs SET state='failed',error='restart_during_preparation',context='' WHERE state='preparing'")

    def enqueue(self, identity, chat, thread, context, now=None):
        if not str(thread).isdigit() or int(thread) <= 1 or not str(chat).lstrip('-').isdigit():
            raise ValueError('invalid_topic_route')
        now = time.time() if now is None else now
        with self.db() as db:
            db.execute("DELETE FROM jobs WHERE created<? AND state IN ('delivered','simulated','skipped','unchanged','superseded','failed')", (now-30*86400,))
            db.execute('INSERT OR IGNORE INTO topics(chat,thread) VALUES(?,?)', (str(chat), int(thread)))
            db.execute('INSERT OR IGNORE INTO jobs(id,chat,thread,context,created) VALUES(?,?,?,?,?)',
                       (identity, str(chat), int(thread), context[-12000:], now))

    def neighbors(self, chat, thread):
        # Checking both sides preserves the previous-three rule when an OLD topic changes.
        with self.db() as db:
            rows = list(db.execute('SELECT * FROM topics WHERE chat=? AND thread<? ORDER BY thread DESC LIMIT 3', (chat, thread)))
            rows += list(db.execute('SELECT * FROM topics WHERE chat=? AND thread>? ORDER BY thread ASC LIMIT 3', (chat, thread)))
        return {r['emoji'] for r in rows if r['emoji']}, {r['icon'] for r in rows if r['icon']}

    def step(self, catalog, choose, send, *, dry_run=True, stopped=lambda: False, now=None):
        now = time.time() if now is None else now
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created,id LIMIT 1").fetchone()
            if row is None:
                return False
            row = dict(row)
            # Unknown external state blocks this chat until explicitly reconciled.
            if db.execute("SELECT 1 FROM jobs WHERE chat=? AND state='outcome_unknown'", (row['chat'],)).fetchone():
                db.execute("UPDATE jobs SET state='blocked',error='unknown_prior_delivery',context='' WHERE id=?", (row['id'],))
                return True
            current = dict(db.execute('SELECT * FROM topics WHERE chat=? AND thread=?', (row['chat'],row['thread'])).fetchone())
            newer = db.execute("SELECT 1 FROM jobs WHERE chat=? AND thread=? AND created>?", (row['chat'],row['thread'],row['created'])).fetchone()
            if newer or now-row['created']>3600 or (current['updated'] and now-current['updated']<300):
                db.execute("UPDATE jobs SET state='skipped',context='' WHERE id=?", (row['id'],))
                return True
            db.execute("UPDATE jobs SET state='preparing' WHERE id=?", (row['id'],))
        try:
            excluded, icons = self.neighbors(row['chat'],row['thread'])
            allowed = {e:i for e,i in catalog.items() if e not in excluded and i not in icons}
            if not allowed:
                raise ValueError('no_available_icons')
            result = choose(row['context'], current, list(allowed))
            if result.get('change') is False:
                self.finish(row['id'],'unchanged')
                return True
            title, emoji = result.get('title'), result.get('emoji')
            if not isinstance(title,str) or not 1<=len(title.strip())<=64 or any(ord(c)<32 for c in title):
                raise ValueError('invalid_topic_title')
            if emoji not in allowed:
                raise ValueError('invalid_or_duplicate_icon')
            title=title.strip(); icon=allowed[emoji]
            if stopped():
                raise ValueError('plugin_stopped')
            with self.db() as db:
                # A newer event arrived while the model was working: discard the stale proposal.
                if db.execute('SELECT 1 FROM jobs WHERE chat=? AND thread=? AND created>?', (row['chat'],row['thread'],row['created'])).fetchone():
                    db.execute("UPDATE jobs SET state='superseded',context='' WHERE id=?",(row['id'],))
                    return True
                db.execute('UPDATE jobs SET state=?,title=?,emoji=?,icon=? WHERE id=?',
                           ('simulated' if dry_run else 'sending',title,emoji,icon,row['id']))
            if dry_run:
                self.finish(row['id'],'simulated')
                return True
            try:
                send(row['chat'],row['thread'],title,icon)
            except Exception:
                self.finish(row['id'],'outcome_unknown','delivery_not_confirmed')
                return True
            with self.db() as db:
                db.execute('UPDATE topics SET title=?,emoji=?,icon=?,updated=? WHERE chat=? AND thread=?',
                           (title,emoji,icon,now,row['chat'],row['thread']))
                db.execute("UPDATE jobs SET state='delivered',context='' WHERE id=?",(row['id'],))
        except Exception as exc:
            self.finish(row['id'],'failed',type(exc).__name__)
        return True

    def finish(self, identity, status, error=None):
        with self.db() as db:
            db.execute('UPDATE jobs SET state=?,error=?,context=? WHERE id=?',(status,error,'',identity))
