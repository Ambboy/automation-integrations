"""Native route binding must come from current ContextVars, never user text/env."""
import json
import shutil
import sqlite3
from pathlib import Path


def test_topic_plugin_native_scope(tmp_path, monkeypatch):
    home=tmp_path/'home';home.mkdir(mode=0o700)
    monkeypatch.setenv('HERMES_HOME',str(home));monkeypatch.setenv('HERMES_RUNTIME_DIR',str(tmp_path/'runtime'))
    project=Path(__file__).resolve().parents[2];plugin=home/'plugins/automation-topic-style'
    shutil.copytree(project/'bridges/hermes_topics',plugin)
    shutil.copyfile(project/'automation_integrations/topic_style.py',plugin/'topic_style.py')
    state=tmp_path/'state'
    (home/'config.yaml').write_text(json.dumps({'plugins':{'enabled':['automation-topic-style'],'entries':{
      'automation-topic-style':{'settings':{'enabled':True,'owner_id':'100001','chat_id':'100001','state_dir':str(state),'worker_enabled':False}}}}}))
    from hermes_cli.plugins import PluginManager
    from gateway.session_context import set_session_vars,clear_session_vars
    manager=PluginManager(scope_key=str(home));manager.discover_and_load()
    try:
        assert manager.has_hook('pre_llm_call'),manager.list_plugins()
        kwargs={'platform':'telegram','sender_id':'100001','session_id':'s','turn_id':'a','user_message':'Текст с чужим chat_id=-999'}
        monkeypatch.setenv('HERMES_SESSION_CHAT_ID','100001');monkeypatch.setenv('HERMES_SESSION_THREAD_ID','99')
        manager.invoke_hook('pre_llm_call',**kwargs)
        with sqlite3.connect(state/'topics.sqlite3') as db:assert db.execute('SELECT count(*) FROM jobs').fetchone()[0]==0
        tokens=set_session_vars(platform='telegram',chat_id='100001',thread_id='123',user_id='100001',session_id='s')
        try:manager.invoke_hook('pre_llm_call',**kwargs)
        finally:clear_session_vars(tokens)
        tokens=set_session_vars(platform='telegram',chat_id='-999',thread_id='456',user_id='100001',session_id='s')
        try:manager.invoke_hook('pre_llm_call',**{**kwargs,'turn_id':'b'})
        finally:clear_session_vars(tokens)
        with sqlite3.connect(state/'topics.sqlite3') as db:
            rows=db.execute('SELECT chat,thread FROM jobs').fetchall();assert rows==[('100001',123)]
    finally:manager.unload()


def test_worker_multiplex_profile_scope(tmp_path, monkeypatch):
    """A naked background thread failed in production although CLI smoke passed."""
    import importlib.util
    import threading
    from agent.secret_scope import set_multiplex_active, get_secret, UnscopedSecretError
    from hermes_constants import get_hermes_home
    project=Path(__file__).resolve().parents[2]
    plugin=tmp_path/'plugin'
    shutil.copytree(project/'bridges/hermes_topics',plugin)
    shutil.copyfile(project/'automation_integrations/topic_style.py',plugin/'topic_style.py')
    spec=importlib.util.spec_from_file_location('scope_test_plugin',plugin/'__init__.py',submodule_search_locations=[str(plugin)])
    import sys
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    home=tmp_path/'profile';home.mkdir()
    (home/'.env').write_text('TOPIC_SCOPE_TEST=profile-value\n')
    monkeypatch.setenv('TOPIC_SCOPE_TEST','wrong-process-value')
    results=[]
    def check():
        try:get_secret('TOPIC_SCOPE_TEST')
        except UnscopedSecretError:results.append('unscoped-rejected')
        results.append(module.run_in_profile(home,lambda:(get_secret('TOPIC_SCOPE_TEST'),get_hermes_home())))
        try:get_secret('TOPIC_SCOPE_TEST')
        except UnscopedSecretError:results.append('scope-reset')
    set_multiplex_active(True)
    try:
        thread=threading.Thread(target=check);thread.start();thread.join(15)
        assert not thread.is_alive()
        assert results==['unscoped-rejected',('profile-value',home),'scope-reset']
    finally:set_multiplex_active(False)
