# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Run with Greif's bootstrapped Python and an isolated HERMES_HOME.

Explicit --execute is required: one paid synthesis, no model or Telegram calls.
"""
import json
import os
import sys
from pathlib import Path

if sys.argv[1:] != ["--execute"]:
    raise SystemExit("Requires --execute (one paid speech request)")
home = Path(os.environ["HERMES_HOME"])
assert home.name == "native-smoke", "Must use isolated speech home"
assert not (home / "report.json").exists(), "Do not repeat a paid smoke implicitly"
os.environ["HERMES_SESSION_PLATFORM"] = "telegram"

from tools.transcription_tools import transcribe_audio
from tools.tts_tool import text_to_speech_tool

sample = Path("/home/operator/workspaces/automation-integrations/artifacts/speech-smoke-20261003/sample.ogg")
input_result = transcribe_audio(str(sample), source="gateway")
assert input_result.get("success"), input_result
result = json.loads(text_to_speech_tool(
    "Проверка Грейфа. Не включайте питание. Напряжение 230 вольт. Стоимость 25 рублей.",
    output_path=str(home / "response.wav")))
assert result.get("success"), result
assert result.get("voice_compatible"), result
assert result["file_path"].endswith(".ogg"), result
output_result = transcribe_audio(result["file_path"], source="gateway")
assert output_result.get("success"), output_result
text = output_result["transcript"].lower()
checks = {"negation": "не включайте" in text, "voltage": "230" in text,
          "price": "25" in text, "voice_compatible": result["voice_compatible"]}
report = {"passed": all(checks.values()), "input": input_result, "output": output_result,
          "checks": checks, "audio": result["file_path"], "telegram_sent": False}
(home / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False))
assert report["passed"]
