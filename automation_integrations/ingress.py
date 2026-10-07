"""Authenticated loopback fixture ingress. Not a Telegram webhook or polling consumer."""
import hmac
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import secret_file
from .contracts import ContractError, Conflict, Forbidden, identifier


def normalize_fixture(payload, profile):
    if not isinstance(payload, dict) or set(payload) - {"update", "transcript", "reply_mode"}:
        raise ContractError("invalid_fixture")
    update = payload.get("update")
    if not isinstance(update, dict) or set(update) != {"update_id", "message"}:
        raise ContractError("only_message_updates_supported")
    if type(update["update_id"]) is not int or update["update_id"] < 0:
        raise ContractError("invalid_update_id")
    message = update["message"]
    if not isinstance(message, dict) or any(k in message for k in ("sender_chat", "forward_origin", "via_bot")):
        raise ContractError("unsupported_message")
    def number(value):
        if type(value) is not int or value == 0:
            raise ContractError("invalid_telegram_id")
        return str(value)
    try:
        user, chat = message["from"], message["chat"]
        if user.get("is_bot") is not False or chat.get("type") not in {"private", "group", "supergroup"}:
            raise ContractError("unsupported_sender_or_chat")
        voice = "voice" in message
        if voice:
            if "text" in message or not isinstance(message["voice"], dict):
                raise ContractError("invalid_voice_fixture")
            text = payload.get("transcript")
        else:
            if "transcript" in payload:
                raise ContractError("transcript_requires_voice")
            text = message.get("text")
        origin = {"profile": identifier(profile), "platform": "telegram", "chat_id": number(chat["id"]),
                  "user_id": number(user["id"]), "message_id": number(message["message_id"]),
                  "thread_id": number(message["message_thread_id"]) if "message_thread_id" in message else "",
                  "message_type": "voice" if voice else "text"}
    except (KeyError, TypeError, AttributeError):
        raise ContractError("invalid_message_fields") from None
    # Explicit modality: no interpretation of natural-language preferences in this fixture connector.
    mode = payload.get("reply_mode", "text")
    return origin, text, mode


class IngressServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, prototype, profile, token_file, port=0):
        self.prototype, self.profile = prototype, identifier(profile)
        self.token = secret_file(token_file)
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(("127.0.0.1", port), Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def log_message(self, *args):
        pass

    def reply(self, code, data):
        raw = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        return hmac.compare_digest(self.headers.get("Authorization", "").encode(),
                                   ("Bearer " + self.server.token).encode())

    def do_POST(self):
        if not self.authorized():
            self.reply(401, {"error": "unauthorized"})
            return
        if self.path != "/v1/fixtures/telegram":
            self.reply(404, {"error": "not_found"})
            return
        try:
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                raise ContractError("content_length_required")
            size = int(self.headers["Content-Length"])
            if not 0 < size <= 65536:
                self.reply(413, {"error": "body_too_large"})
                return
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ContractError("truncated_body")
            origin, text, mode = normalize_fixture(json.loads(raw), self.server.profile)
            turn = self.server.prototype.submit(origin, text, mode=mode)
            self.reply(202, {"turn_id": turn})
        except Forbidden:
            self.reply(403, {"error": "route_not_allowed"})
        except Conflict:
            self.reply(409, {"error": "message_payload_conflict"})
        except (ValueError, TypeError, UnicodeError):
            self.reply(400, {"error": "invalid_fixture"})


@contextmanager
def running_ingress(prototype, profile, token_file):
    server = IngressServer(prototype, profile, token_file)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
