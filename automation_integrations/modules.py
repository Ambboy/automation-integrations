"""Extension interface: plan(event, context) -> serializable outbound actions.

No Hermes objects, session database access, transport credentials, or sends here.
"""
from __future__ import annotations

import json
import math
import os
import re
import signal
import subprocess
import sys

class PreparationError(ValueError):
    pass


ICON_RULES = (
    (r"электр|розет|щит|кабел", ("⚡️", "💡", "🔌")),
    (r"голос|речь|аудио|звук", ("🎙", "🗣", "🎵")),
    (r"сервер|программ|код|плагин|интеграц", ("💻", "🤖", "🧪")),
    (r"счёт|счет|оплат|бюджет|деньг", ("💰", "💳", "📈")),
    (r"дом|стро|ремонт|объект", ("🏠", "🏗", "🛠")),
)
FALLBACK_ICONS = ("💬", "📁", "📝", "💡", "🔎", "📚")


class TopicIcons:
    name = "topic-icons"
    version = "0.1.0"
    event_kind = "topic.observed"

    def plan(self, event, context):
        title = event["data"]["title"]
        allowed = context["icon_catalog"]
        used = context["recent_icons"]
        preferred = next((icons for pattern, icons in ICON_RULES if re.search(pattern, title, re.I)), ())
        candidates = list(dict.fromkeys((*preferred, *FALLBACK_ICONS, *sorted(allowed))))
        emoji = next((x for x in candidates if x in allowed and x not in used), None)
        if emoji is None:
            raise PreparationError("no_available_topic_icon")
        return [{"kind": "topic.icon", "emoji": emoji, "icon_id": allowed[emoji]}]


def _command(argv, *, text=None, timeout=120):
    try:
        proc = subprocess.Popen(argv, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        raise PreparationError("media_command_failed") from None
    try:
        stdout, _ = proc.communicate(text, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise PreparationError("media_command_timeout") from None
    if proc.returncode:
        raise PreparationError("media_command_failed")
    return stdout


class VoiceReply:
    name = "voice-reply"
    version = "0.1.0"
    event_kind = "reply.completed"

    def plan(self, event, context):
        original = event["data"]["text"]
        # Deterministic baseline only. Do not rewrite with an LLM or claim semantic equivalence.
        # Avoid reading hidden reasoning/code/URLs aloud; keep all other words incl. negations.
        script = re.sub(r"<think>.*?</think>|```.*?```", "", original, flags=re.S)
        script = re.sub(r"https?://\S+", "", script)
        script = re.sub(r"(?m)^#{1,6}\s+", "", script).replace("**", "").replace("`", "")
        if not script.strip():
            raise PreparationError("empty_speech")
        # Existing owner-written guard has known limits. Failure stops this job, never sends
        # unvalidated raw text to TTS. Bound input before its regular expressions.
        if len(script) > 8000:
            raise PreparationError("speech_too_long_for_v1")
        script = _command([sys.executable, "-m", "automation_integrations.normalizer"], text=script, timeout=5)
        if context["dry_run"]:
            return [{"kind": "voice.preview", "characters": len(script)}]
        voice = context["voice"]
        directory = context["work_dir"]
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        output = directory / "speech.wav"
        argv = [arg.replace("{output_file}", str(output)) for arg in voice["tts_argv"]]
        _command(argv, text=script, timeout=min(voice.get("timeout_seconds", 120), 600))
        if not output.is_file() or output.is_symlink() or not 0 < output.stat().st_size <= 128 * 1024 * 1024:
            raise PreparationError("invalid_tts_output")
        ffmpeg, ffprobe = voice.get("ffmpeg", "/usr/bin/ffmpeg"), voice.get("ffprobe", "/usr/bin/ffprobe")
        _command([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                  "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-c:a", "libopus",
                  "-b:a", "32k", "-f", "segment", "-segment_time", "55", "-reset_timestamps", "1",
                  str(directory / "part-%03d.ogg")])
        parts = sorted(directory.glob("part-*.ogg"))
        if not 1 <= len(parts) <= 30:
            raise PreparationError("invalid_voice_part_count")
        actions = []
        for part in parts:
            raw = _command([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_name",
                            "-of", "json", str(part)])
            try:
                probe = json.loads(raw)
                duration = float(probe["format"]["duration"])
                valid = any(s.get("codec_name") == "opus" for s in probe["streams"])
                if not valid or not math.isfinite(duration) or not 0 < duration <= 60:
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise PreparationError("invalid_voice_audio") from None
            actions.append({"kind": "voice.send", "file": str(part), "duration": duration})
        output.unlink()
        return actions


# Closed explicit registry for v1; add a module here with the same narrow interface.
# Installation never imports an arbitrary module name supplied in a network event.
MODULES = {module.name: module for module in (TopicIcons(), VoiceReply())}
