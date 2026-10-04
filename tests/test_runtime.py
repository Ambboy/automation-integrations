import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from automation_integrations.api import running
from automation_integrations.config import load_config
from automation_integrations.contracts import Conflict, ContractError, Forbidden, validate_event
from automation_integrations.store import Store
from automation_integrations.worker import Worker
from tests.support import config, event, fake_telegram


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = config(self.root)
        self.store = Store(self.config["state_dir"])

    def test_concurrent_admission_commits_one_job_and_conflict_rejects(self):
        e = event()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.store.accept("test", e), range(24)))
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(len(set(job for job, _ in results)), 1)
        e["data"]["title"] = "Другое"
        with self.assertRaises(Conflict):
            self.store.accept("test", e)

    def test_scope_modality_age_and_module_gates(self):
        conn = self.config["connections"]["test"]
        validate_event(event(), conn)
        for key in ("profile", "chat_id", "user_id", "thread_id"):
            e = event()
            e["source"][key] = "other"
            with self.subTest(key=key), self.assertRaises(Forbidden):
                validate_event(e, conn)
        e = event(kind="reply.completed")
        e["data"]["origin_type"] = "text"
        with self.assertRaises(ContractError):
            validate_event(e, conn)
        e = event()
        e["occurred_at"] = "2020-01-01T00:00:00Z"
        with self.assertRaises(ContractError):
            validate_event(e, conn)
        conn["modules"] = ["voice-reply"]
        with self.assertRaises(Forbidden):
            validate_event(event(), conn)

    def test_execution_rechecks_revoked_routes(self):
        job, _ = self.store.accept("test", event())
        self.config["connections"]["test"]["routes"] = []
        Worker(self.store, self.config).once()
        self.assertEqual(self.store.snapshot(job)["error"], "route_not_allowed")

    def test_dry_run_never_creates_transport(self):
        def forbidden(*args):
            raise AssertionError("transport created in dry-run")
        for kind in ("topic.observed", "reply.completed"):
            job, _ = self.store.accept("test", event(kind, kind))
            Worker(self.store, self.config, forbidden).once()
            self.assertEqual(self.store.snapshot(job)["state"], "simulated")

    def test_worker_lock_prevents_parallel_senders(self):
        with self.store.worker_lock():
            with self.assertRaises(RuntimeError):
                with Store(self.config["state_dir"]).worker_lock():
                    pass

    def test_queued_dry_run_never_becomes_live_after_config_change(self):
        job, _ = self.store.accept("test", event(), dry_run=True)
        self.config["dry_run"] = False
        def forbidden(*args):
            raise AssertionError("transport must not be created")
        Worker(self.store, self.config, forbidden).once()
        self.assertEqual(self.store.snapshot(job)["state"], "simulated")

    def test_delayed_old_topic_event_cannot_overwrite_newer_choice(self):
        newer = event("newer")
        older = event("older")
        older["occurred_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        new_job, _ = self.store.accept("test", newer)
        old_job, _ = self.store.accept("test", older)
        worker = Worker(self.store, self.config)
        worker.once()
        worker.once()
        self.assertEqual(self.store.snapshot(new_job)["state"], "simulated")
        self.assertEqual(self.store.snapshot(old_job)["state"], "superseded")

    def test_partial_delivery_is_not_replayed_on_recovery(self):
        job, _ = self.store.accept("test", event(kind="reply.completed"))
        self.store.claim()
        self.store.prepare_actions(job, [{"kind": "voice.send"}, {"kind": "voice.send"}])
        first = self.store.actions(job)[0]
        self.store.action_state(first["id"], "delivered", {"message_id": 1})
        with self.store.worker_lock():
            self.store.recover()
        self.assertEqual(self.store.snapshot(job)["state"], "partial")
        self.assertIsNone(self.store.claim())

    def test_recovery_never_repeats_ambiguous_send(self):
        job, _ = self.store.accept("test", event())
        self.store.claim()
        self.store.prepare_actions(job, [{"kind": "topic.icon"}])
        action = self.store.actions(job)[0]
        self.store.action_state(action["id"], "sending")
        fresh = Store(self.config["state_dir"])
        with fresh.worker_lock():
            fresh.recover()
            self.assertIsNone(fresh.claim())
        self.assertEqual(fresh.snapshot(job)["state"], "outcome_unknown")

    def test_process_death_after_provider_acceptance_never_resends(self):
        with fake_telegram() as (url, calls):
            self.config["dry_run"] = False
            self.config["telegram"] = {"base_url": url}
            cfg_path = self.root / "config.json"
            cfg_path.write_text(json.dumps(self.config))
            job, _ = self.store.accept("test", event(), dry_run=False)
            script = '''import json,os,sys
from automation_integrations.store import Store
from automation_integrations.worker import Worker
from automation_integrations.telegram import Telegram
class DieAfterAck(Telegram):
    def send(self, source, action):
        super().send(source, action)
        os._exit(73)
config=json.load(open(sys.argv[1]))
store=Store(config["state_dir"])
with store.worker_lock():
    store.recover()
    Worker(store,config,DieAfterAck).once()
'''
            proc = subprocess.run([sys.executable, "-c", script, str(cfg_path)], timeout=10, capture_output=True)
            self.assertEqual(proc.returncode, 73)
            fresh = Store(self.config["state_dir"])
            with fresh.worker_lock():
                fresh.recover()
                self.assertFalse(Worker(fresh, self.config).once())
            self.assertEqual(fresh.snapshot(job)["state"], "outcome_unknown")
            self.assertEqual([c[0] for c in calls].count("editForumTopic"), 1)

    def test_recovery_preserves_confirmed_delivery(self):
        job, _ = self.store.accept("test", event())
        self.store.claim()
        self.store.prepare_actions(job, [{"kind": "topic.icon"}])
        action = self.store.actions(job)[0]
        self.store.action_state(action["id"], "delivered", {"accepted": True})
        with self.store.worker_lock():
            self.store.recover()
        self.assertEqual(self.store.snapshot(job)["state"], "delivered")

    def test_real_http_outbound_confirmed_rejected_and_ambiguous(self):
        self.config["dry_run"] = False
        for mode, expected in (("ok", "delivered"), ("reject", "failed"), ("unknown", "outcome_unknown")):
            with self.subTest(mode=mode), fake_telegram(mode) as (url, calls):
                self.config["telegram"] = {"base_url": url}
                job, _ = self.store.accept("test", event(mode), dry_run=False)
                worker = Worker(self.store, self.config)
                worker.once()
                self.assertEqual(self.store.snapshot(job)["state"], expected)
                self.assertFalse(worker.once())
                self.assertEqual([c[0] for c in calls].count("editForumTopic"), 1)
                self.assertNotIn("SECRET", json.dumps(self.store.snapshot(job)))

    def test_http_auth_isolation_and_receipt_after_commit(self):
        other = self.root / "other-token"
        other.write_text("c" * 40)
        other.chmod(0o600)
        self.config["connections"]["other"] = {**self.config["connections"]["test"], "token_file": str(other)}
        with running(self.config) as server:
            url = f"http://127.0.0.1:{server.server_port}"
            e = event()
            def req(path, token="a" * 40, body=None):
                request = urllib.request.Request(url + path, headers={"Authorization": "Bearer " + token},
                    data=json.dumps(body).encode() if body is not None else None)
                return urllib.request.urlopen(request, timeout=3)
            with self.assertRaises(urllib.error.HTTPError) as error:
                req("/v1/events", token="wrong", body=e)
            self.assertEqual(error.exception.code, 401)
            with req("/v1/events", body=e) as response:
                self.assertEqual(response.status, 202)
                receipt = json.load(response)
            self.assertIsNotNone(self.store.snapshot(receipt["job_id"]))
            with req("/v1/events", body=e) as response:
                self.assertEqual(response.status, 200)
                self.assertFalse(json.load(response)["created"])
            with self.assertRaises(urllib.error.HTTPError) as error:
                req("/v1/jobs/" + receipt["job_id"], token="c" * 40)
            self.assertEqual(error.exception.code, 404)
            with req("/v1/status", token="c" * 40) as response:
                self.assertEqual(json.load(response)["jobs"], {})

    def test_live_config_requires_explicit_provider_and_private_tokens(self):
        path = self.root / "config.json"
        path.write_text(json.dumps(self.config))
        self.assertTrue(load_config(path)["dry_run"])
        self.config["dry_run"] = False
        path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractError):
            load_config(path)
        self.config["dry_run"] = True
        Path(self.config["connections"]["test"]["token_file"]).chmod(0o644)
        path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractError):
            load_config(path)


if __name__ == "__main__":
    unittest.main()
