import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def config(root, dry_run=True):
    token = root / "api-token"
    token.write_text("a" * 40)
    token.chmod(0o600)
    bot = root / "bot-token"
    bot.write_text("123456:" + "b" * 32)
    bot.chmod(0o600)
    return {"schema": 1, "state_dir": str(root / "state"), "dry_run": dry_run, "port": 0,
            "connections": {"test": {"token_file": str(token), "telegram_token_file": str(bot),
                "modules": ["topic-icons", "voice-reply"],
                "routes": [{"profile": "server", "platform": "telegram", "chat_id": "123",
                            "user_id": "456", "thread_ids": ["7"]}]}}}


def event(event_id="one", kind="topic.observed"):
    return {"schema": 1, "event_id": event_id, "kind": kind,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "source": {"profile": "server", "platform": "telegram", "chat_id": "123", "thread_id": "7",
                       "user_id": "456", "message_id": "10", "session_id": "session", "turn_id": "turn"},
            "data": {"title": "Сервер и плагины"} if kind == "topic.observed" else {"text": "Оплатить 25 рублей.", "origin_type": "voice"}}


@contextmanager
def fake_telegram(mode="ok"):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            calls.append((self.path.rsplit("/", 1)[-1], raw))
            if self.path.endswith("getForumTopicIconStickers"):
                result = {"ok": True, "result": [{"emoji": e, "custom_emoji_id": str(i)}
                           for i, e in enumerate(["💻", "🤖", "🧪", "💬", "📁", "📝", "💡", "🔎"])]}
            elif mode == "unknown":
                self.close_connection = True
                return
            elif mode == "reject":
                result = {"ok": False, "error_code": 403, "description": "SECRET MUST NOT LEAK"}
            elif self.path.endswith("sendVoice"):
                result = {"ok": True, "result": {"message_id": len(calls) + 100}}
            else:
                result = {"ok": True, "result": True}
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
