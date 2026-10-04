"""Outbound-only Bot API connector. No getUpdates, setWebhook or messaging token locks."""
from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import secret_file


class DeliveryUnknown(RuntimeError):
    pass


class DeliveryRejected(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Telegram:
    def __init__(self, config, connection):
        self.base = config.get("telegram", {}).get("base_url", "https://api.telegram.org").rstrip("/")
        self.token = secret_file(connection["telegram_token_file"])
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(self, method, fields, file=None):
        if file is None:
            body = urllib.parse.urlencode(fields).encode()
            content_type = "application/x-www-form-urlencoded"
        else:
            boundary = "integration-" + secrets.token_hex(16)
            chunks = []
            for key, value in fields.items():
                chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
            path = Path(file)
            if path.is_symlink() or not 0 < path.stat().st_size <= 8 * 1024 * 1024:
                raise DeliveryRejected("invalid_voice_artifact")
            chunks.extend([
                f'--{boundary}\r\nContent-Disposition: form-data; name="voice"; filename="voice.ogg"\r\nContent-Type: audio/ogg\r\n\r\n'.encode(),
                path.read_bytes(), f"\r\n--{boundary}--\r\n".encode(),
            ])
            body = b"".join(chunks)
            content_type = f"multipart/form-data; boundary={boundary}"
        req = urllib.request.Request(f"{self.base}/bot{self.token}/{method}", data=body,
                                     headers={"Content-Type": content_type})
        try:
            with self.opener.open(req, timeout=30) as response:
                raw = response.read(1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            # Treat only a well-formed Telegram rejection as a known failure; a proxy's
            # 5xx or a redirect says nothing about whether the upstream accepted the send.
            raw = exc.read(1024 * 1024 + 1)
        except (OSError, urllib.error.URLError):
            raise DeliveryUnknown("transport_outcome_unknown") from None
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError):
            raise DeliveryUnknown("invalid_provider_receipt") from None
        if not isinstance(result, dict):
            raise DeliveryUnknown("invalid_provider_receipt")
        if result.get("ok") is False and type(result.get("error_code")) is int:
            raise DeliveryRejected("telegram_rejected_" + str(result["error_code"]))
        if result.get("ok") is not True or "result" not in result:
            raise DeliveryUnknown("invalid_provider_receipt")
        return result["result"]

    def catalog(self):
        stickers = self.call("getForumTopicIconStickers", {})
        if not isinstance(stickers, list):
            raise DeliveryRejected("invalid_icon_catalog")
        return {s["emoji"]: s["custom_emoji_id"] for s in stickers
                if isinstance(s, dict) and isinstance(s.get("emoji"), str)
                and isinstance(s.get("custom_emoji_id"), str)}

    def send(self, source, action):
        fields = {"chat_id": source["chat_id"]}
        if source["thread_id"]:
            fields["message_thread_id"] = source["thread_id"]
        if action["kind"] == "topic.icon":
            result = self.call("editForumTopic", {**fields, "icon_custom_emoji_id": action["icon_id"]})
            if result is not True:
                raise DeliveryUnknown("topic_ack_missing")
            return {"accepted": True}
        if action["kind"] != "voice.send":
            raise DeliveryRejected("unsupported_action")
        result = self.call("sendVoice", fields, file=action["file"])
        if not isinstance(result, dict) or type(result.get("message_id")) is not int:
            raise DeliveryUnknown("message_id_missing")
        return {"message_id": result["message_id"]}
