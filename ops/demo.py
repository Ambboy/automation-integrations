"""Disposable HTTP end-to-end demo. Never contacts Telegram or TTS."""
import json
import os
import secrets
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from automation_integrations.api import running


def main():
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="integrations-demo-") as tmp:
        root = Path(tmp)
        token = secrets.token_urlsafe(32)
        token_file = root / "token"
        token_file.write_text(token)
        config = {"schema": 1, "state_dir": str(root / "state"), "port": 0, "dry_run": True,
            "connections": {"demo": {"token_file": str(token_file), "modules": ["topic-icons", "voice-reply"],
                "routes": [{"profile": "demo", "platform": "telegram", "chat_id": "1", "user_id": "2", "thread_ids": ["3"]}]}}}
        with running(config) as server:
            url = f"http://127.0.0.1:{server.server_port}"
            jobs = []
            for kind, data in [("topic.observed", {"title": "Электрика дома"}),
                               ("reply.completed", {"text": "Оплатить 25 рублей.", "origin_type": "voice"})]:
                event = {"schema": 1, "event_id": kind, "kind": kind,
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "source": {"profile": "demo", "platform": "telegram", "chat_id": "1", "thread_id": "3",
                               "user_id": "2", "message_id": "4", "session_id": "demo", "turn_id": "demo"}, "data": data}
                request = urllib.request.Request(url + "/v1/events", data=json.dumps(event).encode(),
                    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=3) as response:
                    jobs.append(json.load(response)["job_id"])
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                results = [server.store.snapshot(job) for job in jobs]
                if all(r["state"] == "simulated" for r in results):
                    print(json.dumps({"dry_run": True, "results": results}, ensure_ascii=False, indent=2))
                    return
                time.sleep(0.05)
            raise RuntimeError("demo_did_not_complete")


if __name__ == "__main__":
    main()
