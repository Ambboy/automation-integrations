"""File-based command providers for Hermes; no Hermes imports or Telegram access."""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from .contracts import ContractError
from .modules import PreparationError, _command
from .speech import synthesize, transcribe
from .speech_source import Sources
from .speech_segments import combine_audio, split_text, audio_duration


def speech_chunks(text, limit=600):
    return split_text(text, max_chars=limit)


def run_tts(source, destination, config):
    store = Sources(config['raw_source_dir']) if config.get('raw_source_dir') else None
    fingerprint_text = ''
    if store:
        with open(source, encoding='utf-8') as stream:
            fingerprint_text = stream.read(16001)
        store.record(fingerprint_text, 'started')
    try:
        _run_tts(source, destination, config)
    except Exception:
        if store:
            store.record(fingerprint_text, 'failed')
        raise
    if store:
        store.record(fingerprint_text, 'synthesized')


def _read_source(source):
    source = Path(source)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 32000:
        raise ContractError("invalid_speech_text_file")
    with source.open('rb') as stream:
        data = stream.read(32001)
    if len(data) > 32000:
        raise ContractError('invalid_speech_text_file')
    return data.decode('utf-8')


def _prepare_text(source, config):
    incoming = _read_source(source)
    if config.get('raw_source_dir'):
        original = Sources(config['raw_source_dir']).get(incoming)
        result = json.loads(_command(config['rewrite_argv'], text=json.dumps(original, ensure_ascii=False), timeout=230))
        if result.get('verified') is not True:
            raise ContractError('unverified_speech_script')
        text = result['speech']
    else:
        # Legacy mode, retained for rollback only.
        text = _command([sys.executable, "-m", "automation_integrations.normalizer"], text=incoming, timeout=5)
    # Validate the entire script before the first potentially billed call.
    chunks = speech_chunks(text)
    if not 1 <= len(chunks) <= 80:
        raise ContractError('speech_chunk_limit')
    return chunks


def _run_tts(source, destination, config):
    destination = Path(destination)
    if not destination.is_absolute() or destination.exists() or destination.is_symlink():
        raise ContractError("new_absolute_output_required")
    chunks = _prepare_text(source, config)
    with tempfile.TemporaryDirectory(prefix="greif-speech-") as temp:
        wave = Path(temp) / "speech.wav"
        parts = []
        for index, chunk in enumerate(chunks):
            part = Path(temp) / f'part-{index}.wav'
            synthesize(chunk, config, part)
            parts.append(part)
        if len(parts) == 1:
            parts[0].rename(wave)
        else:
            playlist = Path(temp) / 'parts.txt'
            playlist.write_text(''.join(f"file '{part}'\n" for part in parts))
            _command([config.get('ffmpeg', '/usr/bin/ffmpeg'), '-nostdin', '-v', 'error',
                      '-f', 'concat', '-safe', '0', '-i', str(playlist), '-c', 'copy', str(wave)], timeout=30)
        # Hermes owns the output directory and subsequent Ogg/Opus conversion.
        # Exclusive create also refuses symlinks and concurrent replacement.
        with destination.open("xb") as output, wave.open("rb") as audio:
            shutil.copyfileobj(audio, output)


def run_tts_parts(source, output_dir, config):
    """Produce measured three-to-five-minute voice files. No delivery or retries.

    The legacy single-WAV command remains available for rollback. This entry point
    is consumed by our plugin, bypassing the native tool's automatic reassembly.
    All parts must succeed before publishing a manifest; a failed billed request
    never starts again. Each synthesis request contains at most 600 characters;
    its audio is combined with adjacent requests before splitting for delivery.
    A short complete answer or final remainder may be under three minutes.
    """
    root = Path(output_dir)
    if (not root.is_absolute() or '..' in root.parts
            or any(p.is_symlink() for p in (root, *root.parents))
            or not root.is_dir() or root.stat().st_mode & 0o077):
        raise ContractError('private_output_directory_required')
    incoming = _read_source(source)
    store = Sources(config['raw_source_dir']) if config.get('raw_source_dir') else None
    if store:
        store.record(incoming, 'started')
    work = Path(tempfile.mkdtemp(prefix='speech-parts-', dir=root))
    paths, durations = [], []
    try:
        chunks = _prepare_text(source, config)
        waves = []
        for index, chunk in enumerate(chunks, 1):
            wave = work / f'synthesis-{index:03d}.wav'
            if store:
                store.record(incoming, f'chunk_{index}_started')
            synthesize(chunk, config, wave)
            waves.append(wave)
            if store:
                store.record(incoming, f'chunk_{index}_synthesized')
        parts = combine_audio(waves, work)
        for part in parts:
            seconds = audio_duration(part)
            if not 0 < seconds <= 300:
                raise ContractError('speech_part_duration_limit')
            paths.append(str(part))
            durations.append(seconds)
        for wave in waves:
            wave.unlink()
        if store:
            store.record(incoming, 'synthesized')
        return {'success': True, 'file_paths': paths, 'durations': durations,
                'voice_compatible': True, 'chunk_count': len(chunks)}
    except BaseException as exc:
        shutil.rmtree(work)
        if store:
            code = str(exc) if isinstance(exc, (ContractError, PreparationError)) else type(exc).__name__
            store.record(incoming, 'failed:' + code[:160])
        raise


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    tts = sub.add_parser("tts")
    tts.add_argument("--input", required=True)
    tts.add_argument("--output", required=True)
    tts.add_argument("--config", required=True)
    parts = sub.add_parser('tts-parts')
    parts.add_argument('--input', required=True)
    parts.add_argument('--output-dir', required=True)
    parts.add_argument('--config', required=True)
    stt = sub.add_parser("stt")
    stt.add_argument("--input", required=True)
    stt.add_argument("--output", required=True)
    stt.add_argument("--model-dir", required=True)
    stt.add_argument("--language", default="ru")
    args = parser.parse_args()
    try:
        if args.command == "tts":
            run_tts(args.input, args.output, json.loads(Path(args.config).read_text()))
        elif args.command == 'tts-parts':
            print(json.dumps(run_tts_parts(args.input, args.output_dir, json.loads(Path(args.config).read_text()))))
        else:
            result = transcribe(args.input, args.model_dir, language=args.language)
            with open(args.output, "x", encoding="utf-8") as output:
                output.write(result["text"])
    except (ContractError, PreparationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("hermes_speech_command_failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
