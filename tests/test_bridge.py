import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path

from automation_integrations.api import running
from automation_integrations.store import Store
from tests.support import config

spec = importlib.util.spec_from_file_location("integration_bridge", Path(__file__).parents[1] / "bridges/hermes/bridge.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Bridge = module.Bridge


def origin():
    return {"profile": "server", "platform": "telegram", "chat_id": "123", "thread_id": "7",
            "user_id": "456", "message_id": "10", "session_id": "session", "message_type": "voice", "internal": False}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = config(self.root)

    def bridge(self, endpoint="http://127.0.0.1:9", contract="hermes-request-origin-v1"):
        return Bridge(endpoint=endpoint, token_file=self.config["connections"]["test"]["token_file"],
                      state_dir=str(self.root / "bridge"), profile="server", origin_contract=contract)

    def test_clean_host_without_origin_does_not_guess_routes(self):
        bridge = self.bridge(contract="unavailable")
        bridge.before(session_id="session", turn_id="turn", platform="telegram", request_origin=origin())
        bridge.after(session_id="session", turn_id="turn", assistant_response="Ответ.")
        with bridge.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM outbox").fetchone()[0], 0)

    def test_trusted_contract_still_requires_exact_session_profile_and_turn(self):
        bridge = self.bridge()
        for key in ("profile", "session_id", "platform"):
            o = origin()
            o[key] = "wrong"
            bridge.before(session_id="session", turn_id="turn", platform="telegram", request_origin=o)
        bridge.before(session_id="session", turn_id="", platform="telegram", request_origin=origin())
        bridge.after(session_id="session", turn_id="turn", assistant_response="Ответ.")
        with bridge.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM outbox").fetchone()[0], 0)

    def test_durable_outbox_survives_restart_and_duplicate_receipt(self):
        with running(self.config) as server:
            endpoint = f"http://127.0.0.1:{server.server_port}"
            bridge = self.bridge(endpoint)
            bridge.before(session_id="session", turn_id="turn", platform="telegram", request_origin=origin())
            # Recreate bridge between hook invocations: the origin binding is durable too.
            bridge = self.bridge(endpoint)
            bridge.after(session_id="session", turn_id="turn", assistant_response="Оплатить 25 рублей.")
            bridge.after(session_id="session", turn_id="turn", assistant_response="Оплатить 25 рублей.")
            self.assertTrue(bridge.flush_once())
            with bridge.db() as db:
                accepted = db.execute("SELECT id,state,job_id FROM outbox").fetchone()
                self.assertEqual(accepted[1], "accepted")
                # Lost HTTP receipt: sender retries the same durable body, no new ID/timestamp.
                db.execute("UPDATE outbox SET state='pending',next_attempt=0")
            self.assertTrue(bridge.flush_once())
            store = Store(self.config["state_dir"])
            self.assertEqual(sum(store.counts().values()), 1)
            self.assertIsNotNone(store.snapshot(accepted[2]))

    def test_unavailable_service_keeps_original_payload(self):
        bridge = self.bridge()
        bridge.before(session_id="session", turn_id="turn", platform="telegram", request_origin=origin())
        bridge.after(session_id="session", turn_id="turn", assistant_response="Ответ.")
        with bridge.db() as db:
            body = db.execute("SELECT body FROM outbox").fetchone()[0]
        bridge.flush_once()
        with bridge.db() as db:
            row = db.execute("SELECT state,body,attempts FROM outbox").fetchone()
        self.assertEqual(row, ("pending", body, 1))

    def test_text_only_preference_survives_internal_continuation(self):
        bridge = self.bridge()
        bridge.before(session_id="session", turn_id="turn", platform="telegram", request_origin=origin(),
                      user_message="Ответь только текстом")
        bridge.after(session_id="session", turn_id="turn", assistant_response="Ответ.")
        continuation = {**origin(), "internal": True}
        bridge.before(session_id="session", turn_id="later", platform="telegram", request_origin=continuation)
        bridge.after(session_id="session", turn_id="later", assistant_response="Продолжение.")
        with bridge.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM outbox").fetchone()[0], 0)

    def test_unknown_continuation_never_reuses_another_origin(self):
        bridge = self.bridge()
        continuation = {**origin(), "internal": True}
        bridge.before(session_id="session", turn_id="later", platform="telegram", request_origin=continuation)
        bridge.after(session_id="session", turn_id="later", assistant_response="Продолжение.")
        with bridge.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM outbox").fetchone()[0], 0)

    def test_reload_releases_sender_lock_and_stops_old_sender(self):
        first = self.bridge()
        first.start()
        second = self.bridge()
        try:
            with self.assertRaises(RuntimeError):
                second.start()
        finally:
            first.close()
        second.start()
        second.close()
        self.assertFalse(first.thread.is_alive())
        self.assertFalse(second.thread.is_alive())
