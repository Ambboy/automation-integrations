"""Standalone speech command adapters; no imports from Hermes and no messaging transport."""
import argparse
import json
import os
import re
import socket
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

from .config import secret_file
from .contracts import ContractError, identifier
from .modules import _command, PreparationError
from .runs import NoRedirect


def checked_text(text):
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
        raise ContractError("speech_text_limit")
    if re.search(r"\d", text):
        raise ContractError("speech_requires_normalized_numbers")
    return text.strip()


def synthesize(text, config, output):
    text = checked_text(text)
    voice = identifier(config["voice_id"])
    model = identifier(config["model_id"])
    token = secret_file(config["token_file"])
    destination = Path(output)
    if not destination.is_absolute() or destination.exists() or destination.is_symlink():
        raise ContractError("new_absolute_output_required")
    if not destination.parent.is_dir() or destination.parent.stat().st_mode & 0o077:
        raise ContractError("private_output_directory_required")
    request = Request(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
                      data=json.dumps({"text": text, "model_id": model}).encode(),
                      headers={"xi-api-key": token, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    # Never retry a possibly billed synthesis and never forward the key on redirects.
    # Socket I/O may wait up to three minutes; this does not limit audio duration.
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=180) as response:
            if response.headers.get_content_type() not in {"audio/mpeg", "audio/mp3", "application/octet-stream"}:
                raise ContractError("unexpected_speech_content_type")
            audio = response.read(16 * 1024 * 1024 + 1)
            if not 0 < len(audio) <= 16 * 1024 * 1024:
                raise ContractError("speech_audio_limit")
    except HTTPError as exc:
        code = exc.code
        exc.close()
        raise ContractError(f"speech_provider_http_{code}") from None
    except (URLError, OSError) as exc:
        # Keep the outcome conservative, but retain a safe diagnostic category.
        # Exception messages/URLs/response bodies may contain secrets.
        reason = getattr(exc, 'reason', exc)
        if isinstance(reason, TimeoutError):
            category = 'timeout'
        elif isinstance(reason, socket.gaierror):
            category = 'dns'
        elif isinstance(reason, ConnectionError):
            category = 'connection'
        else:
            category = 'transport'
        raise ContractError('speech_provider_outcome_unknown:' + category) from None
    with tempfile.TemporaryDirectory(prefix="speech-", dir=destination.parent) as tmp:
        encoded, wave = Path(tmp) / "speech.mp3", Path(tmp) / "speech.wav"
        encoded.write_bytes(audio)
        _command([config.get("ffmpeg", "/usr/bin/ffmpeg"), "-nostdin", "-v", "error", "-i", str(encoded),
                  "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(wave)], timeout=30)
        # Exclusive publish: a concurrent writer cannot be overwritten after a billed call.
        os.link(wave, destination)
    return destination


def transcribe(path, model_dir, *, language="ru", ffprobe="/usr/bin/ffprobe"):
    source, model = Path(path), Path(model_dir)
    if not source.is_absolute() or source.is_symlink() or not source.is_file() or not 0 < source.stat().st_size <= 32 * 1024 * 1024:
        raise ContractError("invalid_transcription_input")
    if not model.is_absolute() or not (model / "model.bin").is_file():
        raise ContractError("cached_whisper_model_required")
    probe = json.loads(_command([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(source)], timeout=10))
    duration = float(probe["format"]["duration"])
    if not 0 < duration <= 120:
        raise ContractError("transcription_duration_limit")
    from faster_whisper import WhisperModel
    engine = WhisperModel(str(model), device="cpu", compute_type="int8", cpu_threads=2,
                          num_workers=1, local_files_only=True)
    segments, info = engine.transcribe(str(source), language=language, beam_size=5,
                                      condition_on_previous_text=False, vad_filter=True)
    text = " ".join(s.text.strip() for s in segments).strip()
    if not text or len(text) > 16000:
        raise ContractError("empty_or_oversized_transcript")
    return {"text": text, "language": info.language, "duration": duration}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    tts = sub.add_parser("tts")
    tts.add_argument("--config", required=True)
    tts.add_argument("--output", required=True)
    stt = sub.add_parser("stt")
    stt.add_argument("--input", required=True)
    stt.add_argument("--model-dir", required=True)
    args = parser.parse_args()
    try:
        if args.command == "tts":
            synthesize(sys.stdin.read(4001), json.loads(Path(args.config).read_text()), args.output)
        else:
            print(json.dumps(transcribe(args.input, args.model_dir), ensure_ascii=False))
    except (ContractError, PreparationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("speech_adapter_failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
