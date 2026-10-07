"""Explicit live speech loopback: existing ElevenLabs voice → Opus → offline Whisper.

Sends only a synthetic phrase to ElevenLabs. No Hermes imports, LLM, or Telegram.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from automation_integrations.modules import VoiceReply, _command
from automation_integrations.vendor.ru_numbers import normalize

PHRASE = "Не включайте питание. Напряжение 230 вольт. Стоимость 25 рублей."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    import yaml
    from dotenv import dotenv_values
    original = (args.profile / "config.yaml").read_bytes()
    settings = yaml.safe_load(original)
    assert settings["tts"]["provider"] == "elevenlabs"
    assert settings["stt"]["provider"] == "local"
    assert (args.model_dir / "model.bin").is_file(), "cached_model_required"
    assert args.output_dir.is_absolute()
    # A failed/unknown synthesis is never silently retried on the same evidence directory.
    args.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    os.environ["HF_HUB_OFFLINE"] = "1"
    report = {"passed": False, "phrase": PHRASE, "telegram_sent": False, "model_downloaded": False}
    try:
        with tempfile.TemporaryDirectory(prefix="speech-secrets-") as tmp:
            private = Path(tmp)
            token = private / "token"
            key = dotenv_values(args.profile / ".env").get("ELEVENLABS_API_KEY")
            if not key:
                raise RuntimeError("elevenlabs_key_unavailable")
            token.write_text(key)
            cfg = private / "tts.json"
            cfg.write_text(json.dumps({"token_file": str(token),
                "voice_id": settings["tts"]["elevenlabs"]["voice_id"],
                "model_id": settings["tts"]["elevenlabs"]["model_id"]}))
            actions = VoiceReply().plan({"data": {"text": PHRASE}}, {
                "dry_run": False, "work_dir": args.output_dir / "audio",
                "voice": {"timeout_seconds": 120, "tts_argv": [sys.executable, "-m", "automation_integrations.speech",
                    "tts", "--config", str(cfg), "--output", "{output_file}"]}})
        assert len(actions) == 1
        part = Path(actions[0]["file"])
        # Bounded subprocess: no daemon, no shared production model cache in memory.
        result = json.loads(_command([sys.executable, "-m", "automation_integrations.speech", "stt",
                            "--input", str(part), "--model-dir", str(args.model_dir)], timeout=180))
        transcript = result["text"]
        canonical = " ".join(re.findall(r"[а-яё]+", normalize(transcript).lower()))
        checks = {"negation": "не включайте питание" in canonical,
                  "voltage": "двести тридцать вольт" in canonical,
                  "price": "двадцать пять рублей" in canonical}
        report.update(passed=all(checks.values()), checks=checks, transcript=transcript,
                      normalized_input=normalize(PHRASE), duration=actions[0]["duration"],
                      audio_file=str(part), tts_model=settings["tts"]["elevenlabs"]["model_id"],
                      stt_model="small", stt_device="cpu", stt_compute_type="int8")
    except Exception as exc:
        # No raw SDK/network errors, secret paths or process stderr.
        report.update(error=type(exc).__name__)
    report["production_config_unchanged"] = (args.profile / "config.yaml").read_bytes() == original
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
