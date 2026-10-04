"""Bound speech requests and produce short voice files without dropping audio."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
import wave
from pathlib import Path

from .contracts import ContractError


MAX_TEXT_LENGTH = 20000
MAX_CHUNK_CHARS = 600
_SAMPLE_RATE = 48000


def split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split normalized speech at sentence/word boundaries, preserving every word.

    Whitespace is normalized to spaces. A token longer than the request limit is
    split by characters, as it otherwise cannot fit into a bounded request.
    """
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= MAX_TEXT_LENGTH:
        raise ContractError("speech_text_limit")
    if type(max_chars) is not int or not 1 <= max_chars <= MAX_CHUNK_CHARS:
        raise ContractError("invalid_speech_chunk_limit")
    if re.search(r"\d", text):
        raise ContractError("speech_requires_normalized_numbers")
    normalized = " ".join(text.split())
    chunks: list[str] = []
    pending = ""
    for sentence in re.split(r"(?<=[.!?…])\s+", normalized):
        if len(sentence) <= max_chars:
            candidate = f"{pending} {sentence}" if pending else sentence
            if len(candidate) <= max_chars:
                pending = candidate
                continue
        if pending:
            chunks.append(pending)
            pending = ""
        while len(sentence) > max_chars:
            boundary = sentence.rfind(" ", 0, max_chars + 1)
            if boundary <= 0:
                boundary = max_chars
            chunks.append(sentence[:boundary])
            sentence = sentence[boundary:].lstrip()
        pending = sentence
    if pending:
        chunks.append(pending)
    return chunks


def _checked_path(path: Path, *, directory: bool = False) -> Path:
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ContractError("invalid_speech_audio_path")
    # Reject symlinks anywhere in the supplied path, including directory aliases.
    for component in (*reversed(path.parents), path):
        try:
            mode = component.lstat().st_mode
        except OSError:
            raise ContractError("invalid_speech_audio_path") from None
        if stat.S_ISLNK(mode):
            raise ContractError("invalid_speech_audio_path")
    if directory:
        if not stat.S_ISDIR(mode) or mode & 0o077:
            raise ContractError("private_output_directory_required")
    elif not stat.S_ISREG(mode):
        raise ContractError("invalid_speech_audio_path")
    return path


def _run(argv: list[str], *, pass_fds: tuple[int, ...] = ()) -> str:
    try:
        result = subprocess.run(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=120,
            check=True, pass_fds=pass_fds,
        )
    except subprocess.TimeoutExpired:
        raise ContractError("speech_media_command_timeout") from None
    except (OSError, subprocess.CalledProcessError):
        raise ContractError("speech_media_command_failed") from None
    return result.stdout


def audio_duration(path: Path) -> float:
    """Measure an existing local audio file with ffprobe."""
    path = _checked_path(path)
    try:
        metadata = json.loads(_run([
            "/usr/bin/ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
            "-show_entries", "format=duration", "-of", "json", str(path),
        ]))
        duration = float(metadata["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        raise ContractError("invalid_speech_audio_duration") from None
    if not math.isfinite(duration) or duration <= 0:
        raise ContractError("invalid_speech_audio_duration")
    return duration


def split_audio(source: Path, output_dir: Path, max_seconds: float = 55) -> list[Path]:
    """Return ordered OGG/Opus files, each at most max_seconds and below a minute.

    Both input paths must be absolute and free of symlinks; output_dir must be
    an existing private directory. Files live in a new private child directory,
    which is removed on failure. The caller owns that directory on success.
    All input samples, including the final short tail, are encoded exactly once.
    """
    if (isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float))
            or not math.isfinite(max_seconds) or not 1 <= max_seconds <= 59):
        raise ContractError("invalid_speech_audio_segment_limit")
    source = _checked_path(source)
    output_dir = _checked_path(output_dir, directory=True)
    work = Path(tempfile.mkdtemp(prefix="speech-segments-", dir=output_dir))
    try:
        # Use an already opened descriptor so a replacement of the source file
        # cannot redirect ffmpeg to a symlink after validation.
        with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW), "rb") as incoming:
            if not stat.S_ISREG(os.fstat(incoming.fileno()).st_mode):
                raise ContractError("invalid_speech_audio_path")
            decoded = work / "decoded.wav"
            _run([
                "/usr/bin/ffmpeg", "-nostdin", "-v", "error", "-n",
                "-protocol_whitelist", "file,pipe", "-i", f"/proc/self/fd/{incoming.fileno()}",
                "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(_SAMPLE_RATE),
                "-c:a", "pcm_s16le", str(decoded),
            ], pass_fds=(incoming.fileno(),))
        # Ogg's reported duration includes Opus pre-skip. Leave one codec frame
        # of headroom and check actual durations after encoding.
        frames_per_part = math.floor((max_seconds - 0.02) * _SAMPLE_RATE)
        outputs: list[Path] = []
        with wave.open(str(decoded), "rb") as audio:
            while True:
                frames = audio.readframes(frames_per_part)
                if not frames:
                    break
                raw = work / "part.wav"
                with raw.open("xb") as raw_file:
                    with wave.open(raw_file, "wb") as part:
                        part.setparams(audio.getparams())
                        part.writeframes(frames)
                destination = work / f"part-{len(outputs) + 1:06d}.ogg"
                _run([
                    "/usr/bin/ffmpeg", "-nostdin", "-v", "error", "-n",
                    "-protocol_whitelist", "file,pipe", "-i", str(raw),
                    "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(_SAMPLE_RATE),
                    "-c:a", "libopus", "-b:a", "48k", "-application", "voip",
                    "-f", "ogg", str(destination),
                ])
                duration = audio_duration(destination)
                if duration > max_seconds or duration >= 60:
                    raise ContractError("speech_audio_segment_too_long")
                destination.chmod(0o600)
                outputs.append(destination)
                raw.unlink()
        if not outputs:
            raise ContractError("empty_speech_audio")
        decoded.unlink()
        return outputs
    except BaseException:
        shutil.rmtree(work)
        raise


def _combined_frame_counts(source_frames, minimum, target, maximum):
    """Balance parts, using original source boundaries whenever feasible."""
    total = sum(source_frames)
    if total <= maximum:
        return [total]
    least_parts = (total + maximum - 1) // maximum
    most_full_parts = total // minimum
    preferred_parts = (total + target // 2) // target
    count = max(least_parts, min(preferred_parts, most_full_parts))
    all_full = total >= count * minimum
    boundaries = [0]
    for frames in source_frames:
        boundaries.append(boundaries[-1] + frames)
    # Dynamic programming finds a partition using only sentence boundaries if
    # one exists. Minimize duration imbalance among those possible partitions.
    states = {0: (0, [])}
    for part_index in range(count):
        following = {}
        last = part_index == count - 1
        for start, (score, lengths) in states.items():
            for end in boundaries[1:]:
                length = end - start
                if length <= 0 or length > maximum:
                    continue
                if length < minimum and not (last and not all_full):
                    continue
                if (end == total) != last:
                    continue
                cost = score + (length * count - total) ** 2
                if end not in following or cost < following[end][0]:
                    following[end] = (cost, lengths + [length])
        states = following
    if total in states:
        return states[total][1]
    # An oversized synthesis or sparse boundaries may require cutting PCM.
    # Keep enough audio for each remaining full part before selecting a nearby
    # original boundary; only an unavoidable final remainder may be short.
    lengths, position = [], 0
    for remaining_count in range(count, 1, -1):
        remaining = total - position
        lower = max(minimum, remaining - (remaining_count - 1) * maximum)
        reserved = ((remaining_count - 1) * minimum if all_full
                    else (remaining_count - 2) * minimum + 1)
        upper = min(maximum, remaining - reserved)
        ideal = position + max(lower, min(remaining // remaining_count, upper))
        candidates = [boundary for boundary in boundaries
                      if position + lower <= boundary <= position + upper]
        end = min(candidates, key=lambda value: (abs(value - ideal), value)) if candidates else ideal
        lengths.append(end - position)
        position = end
    lengths.append(total - position)
    return lengths


def combine_audio(sources, output_dir: Path, min_seconds: float = 180,
                  target_seconds: float = 240, max_seconds: float = 300) -> list[Path]:
    """Combine synthesis files into ordered OGG messages, normally 3–5 minutes.

    Prefer original synthesis boundaries and balanced lengths near the target.
    A short complete reply or an unavoidable final remainder may be shorter
    than min_seconds. No silence is inserted, and no samples are dropped or
    duplicated. Paths and ownership follow the same rules as split_audio.
    """
    limits = (min_seconds, target_seconds, max_seconds)
    if (any(isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) for value in limits)
            or not 1 <= min_seconds <= target_seconds <= max_seconds <= 300
            or max_seconds - min_seconds < 0.02):
        raise ContractError("invalid_speech_audio_segment_limit")
    if isinstance(sources, (str, bytes, Path)):
        raise ContractError("invalid_speech_audio_sources")
    sources = [_checked_path(source) for source in sources]
    if not sources:
        raise ContractError("empty_speech_audio")
    output_dir = _checked_path(output_dir, directory=True)
    work = Path(tempfile.mkdtemp(prefix="speech-segments-", dir=output_dir))
    try:
        combined = work / "combined.wav"
        source_frames = []
        with combined.open("xb") as combined_file:
            with wave.open(combined_file, "wb") as timeline:
                timeline.setnchannels(1)
                timeline.setsampwidth(2)
                timeline.setframerate(_SAMPLE_RATE)
                for source in sources:
                    decoded = work / "decoded.wav"
                    with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW), "rb") as incoming:
                        if not stat.S_ISREG(os.fstat(incoming.fileno()).st_mode):
                            raise ContractError("invalid_speech_audio_path")
                        _run([
                            "/usr/bin/ffmpeg", "-nostdin", "-v", "error", "-n",
                            "-protocol_whitelist", "file,pipe", "-i", f"/proc/self/fd/{incoming.fileno()}",
                            "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(_SAMPLE_RATE),
                            "-c:a", "pcm_s16le", str(decoded),
                        ], pass_fds=(incoming.fileno(),))
                    with wave.open(str(decoded), "rb") as audio:
                        frames = audio.getnframes()
                        if not frames:
                            raise ContractError("empty_speech_audio")
                        source_frames.append(frames)
                        while frames:
                            block = audio.readframes(min(_SAMPLE_RATE, frames))
                            if not block:
                                raise ContractError("incomplete_speech_audio")
                            timeline.writeframesraw(block)
                            frames -= len(block) // 2
                    decoded.unlink()
        # Reserve one Opus frame for the container's reported codec pre-skip.
        planned = _combined_frame_counts(
            source_frames, math.ceil(min_seconds * _SAMPLE_RATE),
            round(target_seconds * _SAMPLE_RATE), math.floor((max_seconds - 0.02) * _SAMPLE_RATE),
        )
        outputs = []
        with wave.open(str(combined), "rb") as audio:
            for index, frame_count in enumerate(planned):
                raw = work / "part.wav"
                with raw.open("xb") as raw_file:
                    with wave.open(raw_file, "wb") as part:
                        part.setparams(audio.getparams())
                        remaining = frame_count
                        while remaining:
                            block = audio.readframes(min(_SAMPLE_RATE, remaining))
                            if not block:
                                raise ContractError("incomplete_speech_audio")
                            part.writeframesraw(block)
                            remaining -= len(block) // 2
                destination = work / f"part-{index + 1:06d}.ogg"
                _run([
                    "/usr/bin/ffmpeg", "-nostdin", "-v", "error", "-n",
                    "-protocol_whitelist", "file,pipe", "-i", str(raw),
                    "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(_SAMPLE_RATE),
                    "-c:a", "libopus", "-b:a", "48k", "-application", "voip",
                    "-f", "ogg", str(destination),
                ])
                duration = audio_duration(destination)
                if duration > max_seconds:
                    raise ContractError("speech_audio_segment_too_long")
                if index < len(planned) - 1 and duration < min_seconds:
                    raise ContractError("speech_audio_segment_too_short")
                destination.chmod(0o600)
                outputs.append(destination)
                raw.unlink()
            if audio.readframes(1):
                raise ContractError("incomplete_speech_audio")
        combined.unlink()
        return outputs
    except BaseException:
        shutil.rmtree(work)
        raise
