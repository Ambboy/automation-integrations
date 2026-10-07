import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from automation_integrations.ingress import running_ingress
from automation_integrations.runs import RunsPrototype
from tests.test_runs import FakeRuns, ROUTES


def fixture(message=10, chat=123, thread=7, voice=False):
    data = {"message_id": message, "from": {"id": 456, "is_bot": False},
            "chat": {"id": chat, "type": "supergroup"}, "message_thread_id": thread}
    payload = {"update": {"update_id": message, "message": data}, "reply_mode": "voice" if voice else "text"}
    if voice:
        data["voice"] = {"file_id": "synthetic-never-download"}
        payload["transcript"] = "Сколько будет 2+2?"
    else:
        data["text"] = "Сколько будет 2+2?"
    return payload


def post_fixture(url, token, payload):
    request = Request(url + "/v1/fixtures/telegram", data=json.dumps(payload).encode(),
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=5) as result:
            return result.status, json.load(result)
    except HTTPError as exc:
        return exc.code, json.load(exc)


class IngressTests(unittest.TestCase):
    def test_http_auth_origin_duplicates_modes_and_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token = root / "token"
            token.write_text("synthetic-fixture-token-000000000000")
            token.chmod(0o600)
            proto = RunsPrototype(root / "state", FakeRuns(), ROUTES)
            with running_ingress(proto, "server", str(token)) as server:
                url = f"http://127.0.0.1:{server.server_port}"
                send = lambda payload, key=token.read_text(): post_fixture(url, key, payload)
                self.assertEqual(send(fixture(), "wrong")[0], 401)
                voice = fixture(voice=True)
                code, result = send(voice)
                self.assertEqual(code, 202)
                self.assertEqual(result, send(voice)[1])
                row = proto.snapshot(result["turn_id"])
                self.assertEqual(row["mode"], "voice")
                self.assertEqual(json.loads(row["origin"])["thread_id"], "7")
                voice["transcript"] = "Changed"
                self.assertEqual(send(voice)[0], 409)
                self.assertEqual(send(fixture(chat=4567))[0], 403)
                self.assertEqual(send(fixture(thread=100))[0], 403)
                text = fixture(message=11)
                text["reply_mode"] = "voice"
                self.assertEqual(send(text)[0], 400)
                text["reply_mode"] = "text"
                self.assertEqual(send(text)[0], 202)
                no_transcript = fixture(message=12, voice=True)
                del no_transcript["transcript"]
                self.assertEqual(send(no_transcript)[0], 400)
                forbidden = fixture(message=13)
                forbidden["update"]["message"]["from"]["is_bot"] = True
                self.assertEqual(send(forbidden)[0], 400)
