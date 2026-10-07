import json
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from automation_integrations.contracts import ContractError
from automation_integrations.speech_segments import combine_audio, split_audio, split_text


class SpeechTextSegmentsTests(unittest.TestCase):
    def test_sentence_boundaries_and_whitespace(self):
        self.assertEqual(split_text("  Первый ответ.\n\nВторой ответ.  ", 20),
                         ["Первый ответ.", "Второй ответ."])
        self.assertEqual(split_text("Да! Нет. Может быть?"), ["Да! Нет. Может быть?"])

    def test_long_script_preserves_every_word_and_order(self):
        text = ("Не открывай дверь. Сначала найди ключ, затем вернись. " * 350).strip()
        chunks = split_text(text)
        self.assertGreater(len(chunks), 20)
        self.assertTrue(all(0 < len(chunk) <= 600 for chunk in chunks))
        self.assertEqual(" ".join(chunks), text)
        self.assertEqual(split_text(text), chunks)

    def test_long_sentence_and_long_token(self):
        text = " ".join(["слово"] * 300)
        self.assertEqual(" ".join(split_text(text)), text)
        token = "я" * 1401
        chunks = split_text(token)
        self.assertEqual(list(map(len, chunks)), [600, 600, 201])
        self.assertEqual("".join(chunks), token)

    def test_input_limits_and_normalization(self):
        self.assertTrue(split_text("я" * 20000))
        for text in ("", " \n ", None, "я" * 20001, "Пять 5", "Пять ５"):
            with self.subTest(text=str(text)[:20]), self.assertRaises(ContractError):
                split_text(text)
        for limit in (0, 601, True, 2.5):
            with self.subTest(limit=limit), self.assertRaises(ContractError):
                split_text("Текст.", limit)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required")
class SpeechAudioSegmentsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def make_audio(self, duration):
        source = self.root / "input.wav"
        # The changing tone makes reordering/dropping a tail observable when
        # comparing decoded output to the original PCM signal.
        subprocess.run([
            "/usr/bin/ffmpeg", "-v", "error", "-f", "lavfi", "-i",
            f"aevalsrc=0.15*sin(2*PI*(220*t+1.2*t*t)):s=48000:d={duration}",
            "-ac", "1", "-c:a", "pcm_s16le", str(source),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return source

    def verify_audio(self, source, outputs, expected_count):
        self.assertEqual(len(outputs), expected_count)
        self.assertEqual(outputs, sorted(outputs))
        self.assertTrue(all(path.parent == outputs[0].parent for path in outputs))
        self.assertEqual(outputs[0].parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(set(outputs[0].parent.iterdir()), set(outputs))
        combined = bytearray()
        durations = []
        for path in outputs:
            metadata = json.loads(subprocess.check_output([
                "/usr/bin/ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=codec_name", "-of", "json", str(path),
            ]))
            self.assertEqual(metadata["streams"][0]["codec_name"], "opus")
            duration = float(metadata["format"]["duration"])
            self.assertLess(duration, 60)
            self.assertLessEqual(duration, 55)
            durations.append(duration)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            combined.extend(subprocess.check_output([
                "/usr/bin/ffmpeg", "-v", "error", "-i", str(path),
                "-f", "s16le", "-ac", "1", "-ar", "48000", "-",
            ]))
        with wave.open(str(source), "rb") as audio:
            original = audio.readframes(audio.getnframes())
            original_duration = audio.getnframes() / audio.getframerate()
        # Separate encoding preserves even the short tail sample-for-sample in
        # duration; ffprobe additionally counts a small per-file codec delay.
        self.assertEqual(len(combined), len(original))
        self.assertAlmostEqual(sum(durations), original_duration, delta=0.03 * len(outputs))
        from array import array
        reference, actual = array("h", original), array("h", combined)
        # Lossy encoding changes samples, but aligned correlation across every
        # window (including boundaries and tail) reveals gaps or reordered data.
        for start in range(0, len(reference), 24000):
            left = reference[start:start + 24000]
            right = actual[start:start + 24000]
            power = sum(value * value for value in left)
            error = sum((x - y) ** 2 for x, y in zip(left, right))
            self.assertLess(error / max(power, 1), 0.25)

    def test_short_audio(self):
        source = self.make_audio(2.37)
        self.verify_audio(source, split_audio(source, self.root), 1)

    def test_long_audio_preserves_boundaries_and_short_tail(self):
        source = self.make_audio(111.37)
        self.verify_audio(source, split_audio(source, self.root), 3)

    def test_short_final_tail_is_not_lost(self):
        source = self.make_audio(54.981)
        self.verify_audio(source, split_audio(source, self.root), 2)

    def test_failures_remove_own_outputs_and_preserve_others(self):
        source = self.make_audio(2)
        existing = self.root / "part-000001.ogg"
        existing.write_bytes(b"existing")
        with patch("automation_integrations.speech_segments.audio_duration", return_value=61):
            with self.assertRaisesRegex(ContractError, "speech_audio_segment_too_long"):
                split_audio(source, self.root)
        self.assertEqual(set(self.root.iterdir()), {source, existing})
        self.assertEqual(existing.read_bytes(), b"existing")

    def test_reject_symlinks_and_public_output_directory(self):
        source = self.make_audio(1)
        alias = self.root / "alias.wav"
        alias.symlink_to(source)
        with self.assertRaises(ContractError):
            split_audio(alias, self.root)
        alias_dir = self.root / "alias-dir"
        alias_dir.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ContractError):
            split_audio(alias_dir / source.name, self.root)
        with self.assertRaises(ContractError):
            split_audio(source, alias_dir)
        public = self.root / "public"
        public.mkdir(mode=0o755)
        public.chmod(0o755)
        with self.assertRaises(ContractError):
            split_audio(source, public)
        self.assertFalse(list(self.root.glob("speech-segments-*")))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required")
class SpeechAudioCombinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def make_sources(self, durations):
        sources, offset = [], 0
        for index, duration in enumerate(durations):
            source = self.root / f"source-{index:03d}.wav"
            # A continuously changing tone gives each source its own position
            # in the full reply, making reordered pieces detectable.
            time = f"(t+{offset})"
            subprocess.run([
                "/usr/bin/ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                f"aevalsrc=0.15*sin(2*PI*(220*{time}+0.6*{time}*{time})):s=48000:d={duration}",
                "-ac", "1", "-c:a", "pcm_s16le", str(source),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            with wave.open(str(source), "rb") as audio:
                offset += audio.getnframes() / audio.getframerate()
            sources.append(source)
        return sources

    def verify_combination(self, sources, outputs, expected_count, *, short_tail=False):
        from array import array
        self.assertEqual(len(outputs), expected_count)
        self.assertEqual(outputs, sorted(outputs))
        self.assertEqual(outputs[0].parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(set(outputs[0].parent.iterdir()), set(outputs))
        original, actual, lengths = bytearray(), bytearray(), []
        checkpoints = {0}
        for source in sources:
            checkpoints.add(len(original))
            with wave.open(str(source), "rb") as audio:
                original.extend(audio.readframes(audio.getnframes()))
        for index, path in enumerate(outputs):
            metadata = json.loads(subprocess.check_output([
                "/usr/bin/ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=codec_name", "-of", "json", str(path),
            ]))
            self.assertEqual(metadata["streams"][0]["codec_name"], "opus")
            duration = float(metadata["format"]["duration"])
            self.assertLessEqual(duration, 300)
            if expected_count > 1 and not (short_tail and index == len(outputs) - 1):
                self.assertGreaterEqual(duration, 180)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            decoded = subprocess.check_output([
                "/usr/bin/ffmpeg", "-v", "error", "-i", str(path),
                "-f", "s16le", "-ac", "1", "-ar", "48000", "-",
            ])
            checkpoints.add(len(actual))
            actual.extend(decoded)
            lengths.append(len(decoded) / 96000)
        # The complete timeline has exactly the same sample count, including
        # sub-frame final tails; comparing positions also detects reordering.
        self.assertEqual(len(actual), len(original))
        checkpoints.update(range(0, len(original), 30 * 96000))
        checkpoints.add(max(0, len(original) - 48000))
        for offset in checkpoints:
            left = array("h", original[offset:offset + 48000])
            right = array("h", actual[offset:offset + 48000])
            if len(left) < 480:
                continue  # codec fade at a sub-10 ms terminal tail
            power = sum(value * value for value in left)
            error = sum((x - y) ** 2 for x, y in zip(left, right))
            self.assertLess(error / max(power, 1), 0.3, f"waveform at {offset / 96000}s")
        return lengths

    def test_multiple_short_syntheses_merge_at_original_boundaries(self):
        sources = self.make_sources([50] * 10)
        lengths = self.verify_combination(sources, combine_audio(sources, self.root), 2)
        self.assertEqual(lengths, [250, 250])

    def test_three_hundred_seconds_plus_tiny_tail(self):
        sources = self.make_sources([100, 100, 100.001])
        lengths = self.verify_combination(sources, combine_audio(sources, self.root), 2, short_tail=True)
        self.assertAlmostEqual(lengths[0], 200, places=6)
        self.assertAlmostEqual(lengths[1], 100.001, places=6)

    def test_six_hundred_seconds_plus_tiny_tail_balances_three_parts(self):
        sources = self.make_sources([100] * 6 + [0.001])
        lengths = self.verify_combination(sources, combine_audio(sources, self.root), 3)
        self.assertEqual(lengths[:2], [200, 200])
        self.assertAlmostEqual(lengths[2], 200.001, places=6)

    def test_oversized_synthesis_is_balanced_without_dropping_pcm(self):
        sources = self.make_sources([601.001])
        lengths = self.verify_combination(sources, combine_audio(sources, self.root), 3)
        self.assertLess(max(lengths) - min(lengths), 1 / 48000 + 1e-9)

    def test_short_complete_reply(self):
        sources = self.make_sources([1.2, 1.171])
        lengths = self.verify_combination(sources, combine_audio(sources, self.root), 1)
        self.assertAlmostEqual(lengths[0], 2.371, places=6)

    def test_failed_combination_cleans_partial_outputs(self):
        sources = self.make_sources([1, 1])
        existing = self.root / "existing.ogg"
        existing.write_bytes(b"keep")
        with patch("automation_integrations.speech_segments.audio_duration", return_value=301):
            with self.assertRaisesRegex(ContractError, "speech_audio_segment_too_long"):
                combine_audio(sources, self.root)
        self.assertEqual(set(self.root.iterdir()), set(sources) | {existing})
        self.assertEqual(existing.read_bytes(), b"keep")

    def test_invalid_input_rejected_before_media_commands(self):
        sources = self.make_sources([1])
        alias = self.root / "alias.wav"
        alias.symlink_to(sources[0])
        public = self.root / "public"
        public.mkdir()
        public.chmod(0o755)
        with patch("automation_integrations.speech_segments._run") as run:
            for inputs, output, kwargs in (
                ([], self.root, {}), ([alias], self.root, {}),
                (sources, public, {}), (sources, self.root, {"max_seconds": 301}),
                (sources, self.root, {"min_seconds": 250}),
                (sources, self.root, {"target_seconds": float("nan")}),
            ):
                with self.subTest(kwargs=kwargs), self.assertRaises(ContractError):
                    combine_audio(inputs, output, **kwargs)
            run.assert_not_called()
        self.assertFalse(list(self.root.glob("speech-segments-*")))


if __name__ == "__main__":
    unittest.main()
