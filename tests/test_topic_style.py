import tempfile
import unittest
from automation_integrations.topic_style import TopicStyles

CAT={e:str(i) for i,e in enumerate(['⚡','💡','🔌','🏠','💻','🔧','📁','🧪'],1)}

class TopicTests(unittest.TestCase):
    def test_restart_does_not_repeat_an_unconfirmed_edit(self):
        with tempfile.TemporaryDirectory() as root:
            s=TopicStyles(root);s.enqueue('a','1',10,'private context',now=1)
            with s.db() as db:db.execute("UPDATE jobs SET state='sending'")
            s.recover()
            with s.db() as db:
                row=db.execute('SELECT state,context FROM jobs').fetchone()
                self.assertEqual(tuple(row),('outcome_unknown',''))

    def test_four_neighbors_never_repeat_and_old_topic_checks_successors(self):
        with tempfile.TemporaryDirectory() as root:
            s=TopicStyles(root);seen=[]
            def choose(context,current,allowed):return {'change':True,'title':'Электрика','emoji':allowed[0]}
            for i in range(4):
                s.enqueue(str(i),'1',i+10,'розетки',now=i+1)
                s.step(CAT,choose,lambda *args:seen.append(args),dry_run=False,now=1000+i)
            self.assertEqual(len({r[3] for r in seen}),4)
            s.enqueue('edit','1',10,'ремонт',now=2000)
            s.step(CAT,choose,lambda *args:seen.append(args),dry_run=False,now=2000)
            self.assertNotIn(seen[-1][3],[r[3] for r in seen[1:4]])

    def test_forbidden_model_choice_never_sent(self):
        with tempfile.TemporaryDirectory() as root:
            s=TopicStyles(root);s.enqueue('1','1',10,'x',now=1)
            s.step(CAT,lambda *args:{'title':'x','emoji':'👾'},lambda *args:self.fail('sent'),dry_run=False,now=1)
            with s.db() as db:self.assertEqual(db.execute('SELECT state FROM jobs').fetchone()[0],'failed')

    def test_unknown_send_blocks_following_chat_actions(self):
        with tempfile.TemporaryDirectory() as root:
            s=TopicStyles(root)
            def choose(*args):return {'title':'Сеть','emoji':'💻'}
            def lost(*args):raise TimeoutError()
            s.enqueue('a','1',10,'x',now=1);s.step(CAT,choose,lost,dry_run=False,now=1)
            s.enqueue('b','1',11,'x',now=2);s.step(CAT,choose,lambda *args:self.fail('retry'),dry_run=False,now=2)
            with s.db() as db:self.assertEqual([r[0] for r in db.execute('SELECT state FROM jobs ORDER BY id')],['outcome_unknown','blocked'])

    def test_dry_run_no_network_or_false_applied_history(self):
        with tempfile.TemporaryDirectory() as root:
            s=TopicStyles(root);s.enqueue('a','1',10,'x',now=1);s.enqueue('a','1',10,'x',now=1)
            s.step(CAT,lambda *a:{'title':'Сеть','emoji':'💻'},lambda *a:self.fail('sent'),now=1)
            with s.db() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT icon FROM topics').fetchone()[0],'')

    def test_changed_while_model_runs_superseded(self):
        with tempfile.TemporaryDirectory() as root:
            s=TopicStyles(root);s.enqueue('a','1',10,'x',now=1)
            def choose(*args):
                s.enqueue('b','1',10,'new',now=2)
                return {'title':'Сеть','emoji':'💻'}
            s.step(CAT,choose,lambda *a:self.fail('stale send'),dry_run=False,now=1)
            with s.db() as db:self.assertEqual(db.execute("SELECT state FROM jobs WHERE id='a'").fetchone()[0],'superseded')
