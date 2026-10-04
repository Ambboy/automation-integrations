"""Real pinned Hermes HTTP handlers + durable run store; only model execution is replaced.

Run via Hermes scripts/run_tests.sh. Uses loopback, private temp profile, synthetic token.
No production gateway, external model, Telegram, or monkey patches in shipped code.
"""
import asyncio
import json
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer


@pytest.mark.asyncio
async def test_runs_http_origin_replay_restart_and_plugin_admission(tmp_path, monkeypatch):
    project = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(project))
    from automation_integrations.runs import RunsHTTP, RunsPrototype, RemoteError
    from automation_integrations.store import Store
    from automation_integrations.ingress import running_ingress
    from tests.test_ingress import fixture, post_fixture
    from gateway.config import PlatformConfig
    from gateway.platforms.api_server import APIServerAdapter
    from gateway.platforms.api_server_run_idempotency import RunIdempotencyStore
    from gateway.platforms import api_server_runs

    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HERMES_HOME", str(home))
    token = tmp_path / "token"
    token.write_text("synthetic-test-only-token-0000000000000")
    token.chmod(0o600)
    db_path = tmp_path / "hermes-runs.sqlite3"
    executions = []

    async def execute(adapter, launch, **kwargs):
        # Admission must disable detached delivery BEFORE the executor is called.
        assert launch.session_history_delivery is False
        executions.append(launch.run_id)
        adapter._set_run_status(launch.run_id, "completed", output="Ответ 25 рублей.")

    monkeypatch.setattr(api_server_runs, "_execute_run", execute)

    def make_adapter():
        adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": token.read_text()}))
        adapter._run_idempotency_store.close()
        adapter._run_idempotency_store = RunIdempotencyStore(str(db_path))
        return adapter

    box = [make_adapter()]
    async def post(request):
        return await box[0]._handle_runs(request)
    async def get(request):
        return await box[0]._handle_get_run(request)
    app = web.Application()
    app.router.add_post("/v1/runs", post)
    app.router.add_get("/v1/runs/{run_id}", get)
    routes = [{"profile": "server", "platform": "telegram", "chat_id": c,
               "user_id": "456", "thread_ids": ["7", "8"]} for c in ["123", "999"]]
    async with TestServer(app, host="127.0.0.1") as server:
        client = RunsHTTP(str(server.make_url("/")).rstrip("/"), str(token))
        proto = RunsPrototype(tmp_path / "client", client, routes)
        ingress_token = tmp_path / "ingress-token"
        ingress_token.write_text("synthetic-separate-ingress-token-0000000000")
        ingress_token.chmod(0o600)
        with running_ingress(proto, "server", str(ingress_token)) as ingress:
            ingress_url = f"http://127.0.0.1:{ingress.server_port}"
            turns = []
            for chat, thread in [(123, 7), (999, 7), (123, 8)]:
                code, receipt = await asyncio.to_thread(post_fixture, ingress_url, ingress_token.read_text(),
                                                        fixture(chat=chat, thread=thread, voice=True))
                assert code == 202
                turns.append(receipt["turn_id"])
        real_request = client.request
        lost = [False]
        def lose_once(*args, **kwargs):
            result = real_request(*args, **kwargs)
            if not lost[0]:
                lost[0] = True
                raise RemoteError(0)
            return result
        client.request = lose_once
        assert await asyncio.to_thread(proto.step, turns[0]) == "retryable"
        client.request = real_request
        proto = RunsPrototype(tmp_path / "client", client, routes)
        for turn in turns:
            assert await asyncio.to_thread(proto.step, turn) == "running"
        for _ in range(100):
            if len(executions) == 3:
                break
            await asyncio.sleep(.01)
        assert len(executions) == 3
        # Replace Hermes adapter and reload its real durable status DB at the same endpoint.
        await asyncio.gather(*list(box[0]._background_tasks))
        box[0]._run_idempotency_store.close()
        box[0] = make_adapter()
        store = Store(tmp_path / "jobs")
        policy = {"routes": routes, "modules": ["voice-reply"]}
        for turn in reversed(turns):
            assert await asyncio.to_thread(proto.step, turn) == "completed"
            row = proto.snapshot(turn)
            event = json.loads(row["event"])
            assert event["source"]["chat_id"] == json.loads(row["origin"])["chat_id"]
            assert event["source"]["thread_id"] == json.loads(row["origin"])["thread_id"]
            assert event["source"]["turn_id"] == row["run_id"]
            job = proto.publish_dry_run(turn, store, "test", policy)
            assert job == proto.publish_dry_run(turn, store, "test", policy)
        # A replay is still the same run after server-state reload.
        row = proto.snapshot(turns[0])
        replay = await asyncio.to_thread(client.request, "POST", "/v1/runs", json.loads(row["body"]), turns[0])
        assert replay["run_id"] == row["run_id"]
        with pytest.raises(RemoteError) as error:
            await asyncio.to_thread(client.request, "POST", "/v1/runs", {"input": "changed"}, turns[0])
        assert error.value.code == 409
        bad = tmp_path / "wrong-token"
        bad.write_text("wrong-synthetic-token-000000000000000")
        bad.chmod(0o600)
        with pytest.raises(RemoteError) as error:
            await asyncio.to_thread(RunsHTTP(client.endpoint, str(bad)).request, "GET", "/v1/runs/" + row["run_id"])
        assert error.value.code == 401
        assert len(executions) == 3
        with store.db() as db:
            assert db.execute("SELECT COUNT(*) FROM jobs WHERE dry_run=1").fetchone()[0] == 3
    box[0]._run_idempotency_store.close()
