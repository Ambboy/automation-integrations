"""Run with the unmodified Hermes checkout's scripts/run_tests.sh.

Exercises its real discovery, hook dispatcher and teardown with a separate HERMES_HOME.
No gateway, provider, messaging token, or external network request is used.
"""
import json
import shutil
import sqlite3
import threading
from pathlib import Path


def test_bridge_discovery_hook_and_unload_on_clean_hermes(tmp_path, monkeypatch):
    home = tmp_path / "isolated-profile"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_RUNTIME_DIR", str(tmp_path / "runtime"))
    project = Path(__file__).resolve().parents[2]
    shutil.copytree(project / "bridges/hermes", home / "plugins/automation-bridge")
    token = tmp_path / "token"
    token.write_text("test-only-not-a-real-secret-000000000000")
    token.chmod(0o600)
    state = tmp_path / "bridge-state"
    settings = {"enabled": True, "endpoint": "http://127.0.0.1:9",
                "token_file": str(token), "state_dir": str(state), "origin_contract": "unavailable"}
    (home / "config.yaml").write_text(json.dumps({"plugins": {
        "enabled": ["automation-bridge"], "entries": {"automation-bridge": {"settings": settings}}}}))
    from hermes_cli.plugins import PluginManager
    manager = PluginManager(scope_key=str(home))
    try:
        manager.discover_and_load()
        loaded = [p for p in manager.list_plugins() if p["name"] == "automation-bridge"]
        assert loaded and loaded[0]["enabled"] and not loaded[0].get("error"), loaded
        assert manager.has_hook("pre_llm_call")
        assert manager.has_hook("post_llm_call")
        # Exact baseline hook contract: it has no structured request_origin.
        manager.invoke_hook("pre_llm_call", session_id="s", turn_id="t", platform="telegram",
                            user_message="Голосовое сообщение", is_first_turn=True)
        manager.invoke_hook("post_llm_call", session_id="s", turn_id="t", platform="telegram",
                            assistant_response="Ответ")
        with sqlite3.connect(state / "outbox.sqlite3") as db:
            assert db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
        assert manager.unload("automation-bridge")
        assert not manager.has_hook("post_llm_call")
        assert not any(t.name == "automation-bridge-outbox" and t.is_alive() for t in threading.enumerate())
    finally:
        manager.unload()
