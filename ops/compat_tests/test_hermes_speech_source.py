"""Native hook→original recovery check; no paid calls or Telegram."""
import json
import shutil
import sqlite3
from pathlib import Path


def test_original_survives_native_cleanup_and_plugin_scope(tmp_path, monkeypatch):
    home = tmp_path / 'profile'
    home.mkdir(mode=0o700)
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setenv('HERMES_RUNTIME_DIR', str(tmp_path / 'runtime'))
    project = Path(__file__).resolve().parents[2]
    plugin = home / 'plugins/automation-speech-source'
    shutil.copytree(project / 'bridges/hermes_speech', plugin)
    shutil.copyfile(project / 'automation_integrations/speech_source.py', plugin / 'speech_source.py')
    state = tmp_path / 'state'
    (home / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': ['automation-speech-source'],
        'entries': {'automation-speech-source': {'settings': {'enabled': True, 'owner_id': '100001', 'state_dir': str(state)}}}}}))
    from hermes_cli.plugins import PluginManager
    from tools.tts_text_normalize import prepare_spoken_text
    manager = PluginManager(scope_key=str(home))
    try:
        manager.discover_and_load()
        assert manager.has_hook('transform_llm_output'), manager.list_plugins()
        original = 'Открой настройки → сохрани. Телефон +7 (999) 123-45-67. Дата: 2026-10-03.'
        manager.invoke_hook('pre_llm_call', session_id='s', turn_id='t', sender_id='100001',
                            platform='telegram', user_message='Прочитай реквизиты', conversation_history=[])
        manager.invoke_hook('pre_tool_call', session_id='s', turn_id='t', tool_name='text_to_speech', args={'text': original})
        with sqlite3.connect(state / 'sources.sqlite3') as db:
            assert json.loads(db.execute('SELECT payload FROM sources').fetchone()[0])['original'] == original
        result = manager.invoke_hook('transform_llm_output', session_id='s', turn_id='t',
                                     platform='telegram', response_text=original)
        assert all(x is None for x in result), 'Visible reply must not be replaced'
        with sqlite3.connect(state / 'sources.sqlite3') as db:
            rows = db.execute('SELECT fingerprint,payload FROM sources').fetchall()
        assert len(rows) == 1
        assert json.loads(rows[0][1])['original'] == original
        import hashlib
        cleaned = prepare_spoken_text(prepare_spoken_text(original, max_chars=None), max_chars=None)
        assert rows[0][0] == hashlib.sha256(cleaned.strip().encode()).hexdigest()
        manager.invoke_hook('pre_llm_call', session_id='other', turn_id='other', sender_id='stranger',
                            platform='telegram', user_message='other', conversation_history=[])
        manager.invoke_hook('transform_llm_output', session_id='other', turn_id='other', platform='telegram', response_text='other')
        with sqlite3.connect(state / 'sources.sqlite3') as db:
            assert db.execute('SELECT COUNT(*) FROM sources').fetchone()[0] == 1
    finally:
        manager.unload()
