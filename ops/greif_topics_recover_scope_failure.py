# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Explicit one-time recovery of observed pre-send failures using native session history."""
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from automation_integrations.topic_style import TopicStyles
if sys.argv[1:] != ['--execute']:raise SystemExit('Requires --execute: edits three existing owner topics')
state=TopicStyles('/home/operator/.local/share/automation-integrations/greif/topics/state')
source=sqlite3.connect('file:/home/operator/.hermes/state.db?mode=ro',uri=True)
source.row_factory=sqlite3.Row
for thread in (100004,100005,100006):
    with state.db() as db:
        row=db.execute("select * from jobs where thread=? and state='failed' and error='UnscopedSecretError' order by created desc limit 1",(thread,)).fetchone()
        assert row is not None
        identity='scope-fix-recovery:'+row['id']
        assert db.execute('select 1 from jobs where id=?',(identity,)).fetchone() is None,'Already attempted; no implicit retry'
        assert db.execute("select 1 from topics where chat=? and thread=? and updated=0",(row['chat'],thread)).fetchone()
    sid=json.loads(row['id'])[0]
    route=source.execute('select * from sessions where id=?',(sid,)).fetchone()
    assert route['source']=='telegram' and route['user_id']==route['chat_id']=='100001' and int(route['thread_id'])==thread
    messages=source.execute("select role,content from messages where session_id=? and role in ('user','assistant') and content!='' order by id",(sid,)).fetchall()
    first=next(m['content'] for m in messages if m['role']=='user')
    context=json.dumps({'question':first,'recent':[m['content'] for m in messages[-4:]]},ensure_ascii=False)
    state.enqueue(identity,route['chat_id'],thread,context)
    print('Queued verified recovery:',thread)
source.close()
