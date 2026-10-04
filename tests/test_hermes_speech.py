import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation_integrations.hermes_speech import run_tts
from automation_integrations.contracts import ContractError
from automation_integrations.speech_source import Sources


class HermesSpeechTests(unittest.TestCase):
    def test_missing_raw_source_never_falls_back_to_damaged_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'input.txt'
            source.write_text('Дата.')
            with patch('automation_integrations.hermes_speech.synthesize') as synth:
                with self.assertRaisesRegex(ValueError, 'source_missing'):
                    run_tts(source, root / 'out.wav', {'raw_source_dir': str(root / 'state')})
                synth.assert_not_called()

    def test_rejected_rewrite_never_reaches_paid_speech(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'input.txt'
            source.write_text('Дата.')
            Sources(root / 'state').put('turn', 'Дата.', 'Дата: 2026-10-03.', 'question')
            with patch('automation_integrations.hermes_speech._command', return_value='{"verified":false,"speech":"wrong"}'), patch('automation_integrations.hermes_speech.synthesize') as synth:
                with self.assertRaisesRegex(ContractError, 'unverified'):
                    run_tts(source, root / 'out.wav', {'raw_source_dir': str(root / 'state'), 'rewrite_argv': ['fake']})
                synth.assert_not_called()

    def test_numbers_and_negation_reach_provider_and_private_wave_is_cleaned(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "input.txt", Path(tmp) / "output.wav"
            source.write_text("Не включайте питание. Напряжение 230 вольт.")
            seen = []

            def fake_synthesis(text, config, wave):
                self.assertIn("Не включайте", text)
                self.assertNotRegex(text, r"\d")
                self.assertEqual(wave.parent.stat().st_mode & 0o077, 0)
                seen.append(wave)
                wave.write_bytes(b"test-wave")

            with patch("automation_integrations.hermes_speech.synthesize", side_effect=fake_synthesis):
                run_tts(source, target, {})
            self.assertEqual(target.read_bytes(), b"test-wave")
            self.assertFalse(seen[0].exists())

    def test_existing_output_and_symlink_refused_before_paid_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "input.txt", Path(tmp) / "output.wav"
            source.write_text("Тест")
            target.symlink_to(Path(tmp) / "missing.wav")
            with patch("automation_integrations.hermes_speech.synthesize") as synth:
                with self.assertRaises(ContractError):
                    run_tts(source, target, {})
                synth.assert_not_called()
