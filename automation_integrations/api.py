"""Local authenticated admission API; acknowledge only committed SQLite events."""
from __future__ import annotations

import hmac
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import secret_file
from .contracts import Conflict, ContractError, Forbidden, validate_event
from .store import Store
from .worker import Worker


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 16

    def __init__(self, config, store, worker):
        self.config, self.store, self.worker = config, store, worker
        self.tokens = {name: secret_file(c["token_file"]) for name, c in config["connections"].items()}
        self.slots = threading.BoundedSemaphore(16)
        self.worker_thread = None
        super().__init__(("127.0.0.1", config.get("port", 8787)), Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "AutomationIntegrations/0.1"

    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def log_message(self, *args):
        pass

    def reply(self, code, value):
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def authenticated_connection(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        supplied = auth[7:].encode()
        for name, token in self.server.tokens.items():
            if hmac.compare_digest(supplied, token.encode()):
                return name
        return None

    def do_GET(self):
        if self.path == "/health":
            alive = self.server.worker_thread is not None and self.server.worker_thread.is_alive()
            self.reply(200 if alive else 503, {"ready": alive, "schema": 1})
            return
        name = self.authenticated_connection()
        if name is None:
            self.reply(401, {"error": "unauthorized"})
        elif self.path == "/v1/status":
            self.reply(200, {"connection": name, "dry_run": self.server.config["dry_run"],
                             "jobs": self.server.store.counts(name)})
        elif self.path.startswith("/v1/jobs/"):
            job = self.server.store.snapshot(self.path.removeprefix("/v1/jobs/"), name)
            self.reply(200 if job else 404, job or {"error": "not_found"})
        else:
            self.reply(404, {"error": "not_found"})

    def do_POST(self):
        name = self.authenticated_connection()
        if name is None:
            self.reply(401, {"error": "unauthorized"})
            return
        if self.path != "/v1/events":
            self.reply(404, {"error": "not_found"})
            return
        try:
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                raise ContractError("content_length_required")
            length = int(self.headers["Content-Length"])
            if not 0 < length <= 128 * 1024:
                self.reply(413, {"error": "body_too_large"})
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ContractError("truncated_body")
            event = validate_event(json.loads(raw), self.server.config["connections"][name])
            job_id, created = self.server.store.accept(name, event, dry_run=self.server.config["dry_run"])
            self.reply(202 if created else 200, {"job_id": job_id, "created": created})
        except Forbidden as exc:
            self.reply(403, {"error": str(exc)})
        except Conflict as exc:
            self.reply(409, {"error": str(exc)})
        except (ContractError, ValueError, TypeError, KeyError, UnicodeError):
            self.reply(400, {"error": "invalid_event"})
        except Exception:
            self.reply(503, {"error": "admission_unavailable"})


@contextmanager
def running(config, connector_factory=None):
    store = Store(config["state_dir"])
    with store.worker_lock():
        store.recover()
        worker = Worker(store, config, **({"connector_factory": connector_factory} if connector_factory else {}))
        server = Server(config, store, worker)
        thread = threading.Thread(target=worker.run, name="integrations-worker", daemon=True)
        server.worker_thread = thread
        http = threading.Thread(target=server.serve_forever, name="integrations-http", daemon=True)
        thread.start()
        http.start()
        try:
            yield server
        finally:
            server.shutdown()
            server.server_close()
            worker.stop.set()
            thread.join(timeout=35)
            if thread.is_alive():
                # Do not release ownership while the worker could still send. systemd may kill
                # the process at TimeoutStopSec; restart will recover sending as unknown.
                thread.join()
            http.join(timeout=5)
