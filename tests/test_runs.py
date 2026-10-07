import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation_integrations.contracts import Conflict, ContractError, Forbidden
from automation_integrations.runs import RunsPrototype, RemoteError
from automation_integrations.store import Store


ROUTES = [{"profile": "server", "platform": "telegram", "chat_id": chat,
           "user_id": "456", "thread_ids": ["7", "8"]} for chat in ["123", "999"]]


def origin(message="10", chat="123", thread="7", kind="voice"):
    return {"profile": "server", "platform": "telegram", "chat_id": chat, "thread_id": thread,
            "user_id": "456", "message_id": message, "message_type": kind}


class FakeRuns:
    binding = "test-only-server-binding"

    def __init__(self):
        self.runs, self.calls = {}, []
        self.lose_acceptance = False
        self.status = "completed"
        self.wrong_identity = False

    def request(self, method, path, body=None, key=None):
        self.calls.append((method, path, body, key))
        if method == "POST":
            if key in self.runs and self.runs[key][1] != body:
                raise RemoteError(409)
            self.runs.setdefault(key, ("run_" + key, body))
            if self.lose_acceptance:
                self.lose_acceptance = False
                raise RemoteError(0)
            return {"run_id": self.runs[key][0], "status": "started"}
        run, body = next(v for v in self.runs.values() if path.endswith(v[0]))
        return {"run_id": run, "session_id": "wrong" if self.wrong_identity else body["session_id"],
                "status": self.status, "output": "Ответ: " + body["input"]}


class RunsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.client = FakeRuns()
        self.proto = RunsPrototype(self.root / "runs", self.client, ROUTES)

    def finish(self, turn):
        self.assertEqual(self.proto.step(turn), "running")
        self.assertEqual(self.proto.step(turn), "completed")

    def test_chat_topic_mapping_and_out_of_order_completion(self):
        turns = [self.proto.submit(origin(chat=c, thread=t), c + t, mode="voice")
                 for c, t in [("123", "7"), ("999", "7"), ("123", "8")]]
        for turn in turns:
            self.proto.step(turn)
        for turn in reversed(turns):
            self.assertEqual(self.proto.step(turn), "completed")
            row = self.proto.snapshot(turn)
            event = json.loads(row["event"])
            self.assertEqual(event["source"]["chat_id"] + event["source"]["thread_id"], row["input"])
            self.assertEqual(event["source"]["turn_id"], row["run_id"])
        self.assertEqual(len({self.proto.snapshot(t)["scope"] for t in turns}), 3)

    def test_lost_post_acceptance_and_client_restart_reuses_exact_request(self):
        turn = self.proto.submit(origin(), "Первый", mode="voice")
        self.client.lose_acceptance = True
        self.assertEqual(self.proto.step(turn), "retryable")
        self.proto = RunsPrototype(self.root / "runs", self.client, ROUTES)
        self.finish(turn)
        self.assertEqual(len(self.client.runs), 1)
        self.assertEqual(self.client.calls[0], self.client.calls[1])

    def test_fifo_history_and_explicit_text_mode(self):
        first = self.proto.submit(origin(), "Голос", mode="voice")
        second = self.proto.submit(origin("11"), "Только текстом", mode="text")
        self.assertEqual(self.proto.step(second), "blocked_by_previous_turn")
        self.finish(first)
        self.finish(second)
        row = self.proto.snapshot(second)
        self.assertIsNone(row["event"])
        history = json.loads(row["body"])["conversation_history"]
        self.assertEqual(history[-1], {"role": "assistant", "content": "Ответ: Голос"})
        self.assertTrue(json.loads(self.proto.snapshot(first)["body"])["conversation_history"])

    def test_duplicate_and_conflicting_origin(self):
        one = self.proto.submit(origin(), "A")
        self.assertEqual(one, self.proto.submit(origin(), "A"))
        with self.assertRaises(Conflict):
            self.proto.submit(origin(), "B")
        with self.assertRaises(Forbidden):
            self.proto.submit(origin(chat="unlisted"), "A")
        with self.assertRaises(ContractError):
            self.proto.submit(origin(kind="text"), "A", mode="voice")

    def test_expired_unknown_acceptance_is_never_replayed(self):
        turn = self.proto.submit(origin(), "A")
        self.client.lose_acceptance = True
        self.proto.step(turn, now=100)
        self.assertEqual(self.proto.step(turn, now=100 + 23 * 3600), "outcome_unknown")
        self.assertEqual(len(self.client.calls), 1)

    def test_terminal_failures_and_approval_do_not_deliver_or_restart(self):
        for i, status in enumerate(["waiting_for_approval", "failed", "cancelled", "interrupted"]):
            turn = self.proto.submit(origin(str(i), thread="8"), "A", mode="voice")
            # Independent state root for each blocked lane.
            if i:
                self.proto = RunsPrototype(self.root / str(i), self.client, ROUTES)
                turn = self.proto.submit(origin(str(i)), "A", mode="voice")
            self.proto.step(turn)
            self.client.status = status
            self.assertEqual(self.proto.step(turn), status)
            self.assertIsNone(self.proto.snapshot(turn)["event"])
            if status != "waiting_for_approval":
                before = len(self.client.calls)
                self.proto.step(turn)
                self.assertEqual(len(self.client.calls), before)

    def test_identity_mismatch_and_missing_run_fail_closed(self):
        turn = self.proto.submit(origin(), "A", mode="voice")
        self.proto.step(turn)
        self.client.wrong_identity = True
        self.assertEqual(self.proto.step(turn), "outcome_unknown")
        self.assertIsNone(self.proto.snapshot(turn)["event"])

    def test_dry_run_job_crash_before_receipt_is_deduplicated(self):
        turn = self.proto.submit(origin(), "A", mode="voice")
        self.finish(turn)
        store = Store(self.root / "jobs")
        policy = {"routes": ROUTES, "modules": ["voice-reply"]}
        with patch.object(self.proto, "update", side_effect=RuntimeError("crash")):
            with self.assertRaises(RuntimeError):
                self.proto.publish_dry_run(turn, store, "test", policy)
        self.proto = RunsPrototype(self.root / "runs", self.client, ROUTES)
        job = self.proto.publish_dry_run(turn, store, "test", policy)
        self.assertEqual(job, self.proto.publish_dry_run(turn, store, "test", policy))
        with store.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT dry_run FROM jobs").fetchone()[0], 1)

    def test_changed_server_binding_and_revoked_route(self):
        turn = self.proto.submit(origin(), "A")
        self.proto.routes = []
        self.assertEqual(self.proto.step(turn), "rejected")
        self.client.binding = "different-server"
        with self.assertRaises(ContractError):
            RunsPrototype(self.root / "runs", self.client, ROUTES)

    def test_driver_lock_prevents_parallel_progress(self):
        turn = self.proto.submit(origin(), "A")
        other = RunsPrototype(self.root / "runs", self.client, ROUTES)
        with self.proto.lock():
            with self.assertRaises(ContractError):
                other.step(turn)
        self.assertEqual(len(self.client.calls), 0)

    def test_missing_run_does_not_create_replacement(self):
        turn = self.proto.submit(origin(), "A")
        self.proto.step(turn)
        with patch.object(self.client, "request", side_effect=RemoteError(404)):
            self.assertEqual(self.proto.step(turn), "outcome_unknown")
        self.assertEqual(self.proto.step(turn), "outcome_unknown")
        self.assertEqual(len(self.client.runs), 1)
