"""Disposable prototype demo with a test double for Hermes. No network/provider calls."""
import json
import os
import tempfile
from pathlib import Path

from automation_integrations.runs import RunsPrototype
from automation_integrations.store import Store
from automation_integrations.worker import Worker
from tests.test_runs import FakeRuns, ROUTES, origin


def main():
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="runs-demo-") as tmp:
        root = Path(tmp)
        fake = FakeRuns()
        prototype = RunsPrototype(root / "client", fake, ROUTES)
        turn = prototype.submit(origin(), "Оплатить 25 рублей", mode="voice")
        fake.lose_acceptance = True
        assert prototype.step(turn) == "retryable"
        prototype = RunsPrototype(root / "client", fake, ROUTES)
        assert prototype.step(turn) == "running"
        assert prototype.step(turn) == "completed"
        store = Store(root / "jobs")
        policy = {"routes": ROUTES, "modules": ["voice-reply"]}
        job = prototype.publish_dry_run(turn, store, "demo", policy)
        assert job == prototype.publish_dry_run(turn, store, "demo", policy)
        worker = Worker(store, {"dry_run": True, "connections": {"demo": policy}})
        with store.worker_lock():
            assert worker.once()
        result = store.snapshot(job)
        assert result["state"] == "simulated"
        print(json.dumps({"hermes": "test double", "server_runs": len(fake.runs),
                          "lost_acceptance_recovered": True, "plugin_job": result["state"],
                          "telegram_sent": False}, indent=2))


if __name__ == "__main__":
    main()
