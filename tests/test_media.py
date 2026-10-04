import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from automation_integrations.modules import PreparationError, TopicIcons, VoiceReply
from automation_integrations.store import Store
from automation_integrations.worker import Worker
from tests.support import config, event, fake_telegram


class ModuleTests(unittest.TestCase):
    def test_icons_respect_supported_catalog_and_recent_choices(self):
        e = event()
        catalog = {"💻": "one", "🤖": "two", "💬": "three"}
        action = TopicIcons().plan(e, {"icon_catalog": catalog, "recent_icons": ["💻"]})[0]
        self.assertEqual(action["emoji"], "🤖")
        with self.assertRaises(PreparationError):
            TopicIcons().plan(e, {"icon_catalog": catalog, "recent_icons": list(catalog)})

    def test_empty_or_oversized_speech_does_not_call_provider(self):
        for text in ("```hidden code```", "текст " * 2000):
            e = event(kind="reply.completed")
            e["data"]["text"] = text
            with self.assertRaises(PreparationError):
                VoiceReply().plan(e, {"dry_run": False})

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires real ffmpeg/ffprobe; run on isolated SG staging")
    def test_real_transcode_split_and_multipart_delivery(self):
        with tempfile.TemporaryDirectory() as tmp, fake_telegram() as (url, calls):
            root = Path(tmp)
            cfg = config(root, dry_run=False)
            cfg["telegram"] = {"base_url": url}
            # An actual executable provider produces a 61-second WAV fixture, not speech.
            # Production audio/voice quality is deliberately not asserted by this test.
            provider = root / "provider.py"
            provider.write_text('''import sys,wave
text=sys.stdin.read()
assert "двадцать пять" in text and "25" not in text
with wave.open(sys.argv[1],"wb") as out:
    out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000)
    out.writeframes(b"\\0\\0" * 8000 * 61)
''')
            cfg["voice"] = {"tts_argv": [sys.executable, str(provider), "{output_file}"],
                            "ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe")}
            store = Store(cfg["state_dir"])
            job, _ = store.accept("test", event(kind="reply.completed"), dry_run=False)
            Worker(store, cfg).once()
            result = store.snapshot(job)
            self.assertEqual(result["state"], "delivered", result)
            self.assertEqual(len(result["actions"]), 2)
            audio_calls = [raw for name, raw in calls if name == "sendVoice"]
            self.assertEqual(len(audio_calls), 2)
            self.assertTrue(all(b"OggS" in body and b"OpusHead" in body for body in audio_calls))
            self.assertTrue(all(b'name="message_thread_id"' in body for body in audio_calls))
            for row in store.actions(job):
                self.assertLessEqual(json.loads(row["payload"])["duration"], 60)
