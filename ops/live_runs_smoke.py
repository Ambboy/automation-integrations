"""Explicit live smoke: one synthetic prompt, isolated Hermes home, no Telegram/tools.

Requires --execute, existing profile and pinned Hermes source. No default live execution.
Copies only the selected provider's auth to a disposable private directory; never refreshes OAuth.
"""
import argparse
import asyncio
import contextlib
import json
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path


async def exercise(root, config):
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    from gateway.config import PlatformConfig
    from gateway.platforms.api_server import APIServerAdapter
    from hermes_cli.tools_config import _get_platform_tools
    from automation_integrations.runs import RunsHTTP, RunsPrototype
    from automation_integrations.ingress import running_ingress
    from automation_integrations.store import Store
    from automation_integrations.worker import Worker
    from urllib.request import Request, urlopen

    def post_fixture(url, token, payload):
        request = Request(url + "/v1/fixtures/telegram", data=json.dumps(payload).encode(),
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            return response.status, json.load(response)

    assert not _get_platform_tools(config, "api_server"), "tools_must_be_disabled"
    token = root / "api-token"
    token.write_text(secrets.token_urlsafe(32))
    ingress_token = root / "ingress-token"
    ingress_token.write_text(secrets.token_urlsafe(32))
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": token.read_text()}))
    app = web.Application()
    app.router.add_post("/v1/runs", adapter._handle_runs)
    app.router.add_get("/v1/runs/{run_id}", adapter._handle_get_run)
    route = {"profile": "smoke", "platform": "telegram", "chat_id": "123", "user_id": "456", "thread_ids": ["7"]}
    async with TestServer(app, host="127.0.0.1") as server:
        client = RunsHTTP(str(server.make_url("/")).rstrip("/"), str(token))
        prototype = RunsPrototype(root / "client", client, [route])
        with running_ingress(prototype, "smoke", str(ingress_token)) as ingress:
            payload = {"update": {"update_id": 1, "message": {"message_id": 1,
                       "from": {"id": 456, "is_bot": False},
                       "chat": {"id": 123, "type": "supergroup"}, "message_thread_id": 7,
                       "voice": {"file_id": "synthetic-never-download"}}}, "reply_mode": "voice"}
            payload["transcript"] = "Ответь ровно одной строкой: INTEGRATION_OK_25. Не используй инструменты."
            code, receipt = await asyncio.to_thread(post_fixture, f"http://127.0.0.1:{ingress.server_port}",
                                                   ingress_token.read_text(), payload)
            assert code == 202
        turn = receipt["turn_id"]
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            state = await asyncio.to_thread(prototype.step, turn)
            if state in {"completed", "failed", "interrupted", "cancelled", "rejected", "outcome_unknown", "waiting_for_approval"}:
                break
            await asyncio.sleep(.5)
        else:
            raise RuntimeError("smoke_deadline")
        row = prototype.snapshot(turn)
        if state != "completed":
            # Keep only classification; never print raw upstream/provider messages.
            remote = await asyncio.to_thread(client.request, "GET", "/v1/runs/" + row["run_id"]) if row["run_id"] else {}
            error = str(remote.get("error", "")).lower()
            reason = "auth" if any(w in error for w in ("auth", "token", "credential", "401")) else "model_execution"
            return {"passed": False, "state": state, "reason": reason}
        exact = row["output"].strip() == "INTEGRATION_OK_25"
        store = Store(root / "jobs")
        policy = {"routes": [route], "modules": ["voice-reply"]}
        job = prototype.publish_dry_run(turn, store, "smoke", policy)
        worker = Worker(store, {"dry_run": True, "connections": {"smoke": policy}})
        with store.worker_lock():
            worker.once()
        job_state = store.snapshot(job)["state"]
        await asyncio.gather(*list(adapter._background_tasks), return_exceptions=True)
        adapter._run_idempotency_store.close()
        return {"passed": exact and job_state == "simulated", "state": state,
                "exact_answer": exact, "plugin_job": job_state, "plugin_error": store.snapshot(job).get("error"), "telegram_sent": False,
                "toolsets": [], "real_model": config["model"]["default"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--hermes-source", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    import yaml
    original_config = yaml.safe_load((args.profile / "config.yaml").read_text())
    original_auth_bytes = (args.profile / "auth.json").read_bytes()
    original_auth = json.loads(original_auth_bytes)
    model = original_config["model"]
    provider = model["provider"]
    if provider != "openai-codex":
        raise SystemExit("This smoke is audited only for the existing openai-codex profile")
    # Snapshot selected credentials only, with refresh authority removed. Production auth stays untouched.
    pool = original_auth.get("credential_pool", {}).get(provider, [])
    def without_refresh(value):
        if isinstance(value, dict):
            return {k: without_refresh(v) for k, v in value.items() if k != "refresh_token"}
        if isinstance(value, list):
            return [without_refresh(v) for v in value]
        return value
    auth = {"version": original_auth.get("version", 1), "active_provider": provider,
            "providers": {provider: without_refresh(original_auth.get("providers", {}).get(provider, {}))},
            "credential_pool": {provider: without_refresh(pool)}}
    config = {"model": model, "platform_toolsets": {"api_server": []},
              "agent": {"max_turns": 2}, "plugins": {"enabled": []},
              "memory": {"memory_enabled": False, "user_profile_enabled": False},
              "mcp_servers": {}, "telemetry": {"enabled": False}}
    sys.path.insert(0, str(args.hermes_source.resolve()))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix="integration-live-") as tmp:
        root = Path(tmp)
        (root / "auth.json").write_text(json.dumps(auth))
        (root / "config.yaml").write_text(json.dumps(config))
        os.environ["HERMES_HOME"] = str(root)
        os.environ["HERMES_RUNTIME_DIR"] = str(root / "runtime")
        os.environ["HERMES_SAFE_MODE"] = "1"
        os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        os.chdir(root)
        with (root / "private.log").open("w") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                result = asyncio.run(exercise(root, config))
            except Exception as exc:
                result = {"passed": False, "reason": type(exc).__name__}
                if isinstance(exc, ModuleNotFoundError):
                    result["missing_module"] = exc.name
    # A read-only pre/post comparison; do not print hashes or credential contents.
    result["production_auth_unchanged"] = (args.profile / "auth.json").read_bytes() == original_auth_bytes
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
