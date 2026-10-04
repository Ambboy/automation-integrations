import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from automation_integrations.speech import checked_text, synthesize, transcribe
from automation_integrations.contracts import ContractError


class SpeechTests(unittest.TestCase):
    def test_network_error_category_is_safe_and_never_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token = root / 'token'
            token.write_text('test-only-speech-token-00000000000000')
            token.chmod(0o600)
            for failure, category in [(TimeoutError('SECRET'), 'timeout'),
                                      (URLError(TimeoutError('SECRET')), 'timeout'),
                                      (ConnectionResetError('SECRET'), 'connection'),
                                      (URLError('SECRET'), 'transport')]:
                with self.subTest(category=category), patch('automation_integrations.speech.build_opener') as opener:
                    opener.return_value.open.side_effect = failure
                    with self.assertRaisesRegex(ContractError, '^speech_provider_outcome_unknown:' + category + '$'):
                        synthesize('Тест.', {'voice_id': 'voice', 'model_id': 'model', 'token_file': str(token)}, root / 'new.wav')
                    self.assertEqual(opener.return_value.open.call_count, 1)
                    self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 180)
                    self.assertFalse((root / 'new.wav').exists())

    def test_response_body_timeout_is_reported_without_retry_or_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token = root / 'token'
            token.write_text('test-only-speech-token-00000000000000')
            token.chmod(0o600)
            with patch('automation_integrations.speech.build_opener') as opener:
                response = opener.return_value.open.return_value.__enter__.return_value
                response.headers.get_content_type.return_value = 'audio/mpeg'
                response.read.side_effect = TimeoutError('SECRET')
                with self.assertRaisesRegex(ContractError, '^speech_provider_outcome_unknown:timeout$'):
                    synthesize('Тест.', {'voice_id': 'voice', 'model_id': 'model',
                                        'token_file': str(token)}, root / 'new.wav')
                self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 180)
                self.assertEqual(opener.return_value.open.call_count, 1)
                self.assertEqual(response.read.call_count, 1)
                self.assertFalse((root / 'new.wav').exists())

    def test_invalid_text_is_rejected_before_billed_call(self):
        for text in ("", "x" * 4001, "Цена 25 рублей", "Размер ２ метра"):
            with self.assertRaises(ContractError):
                checked_text(text)
        self.assertEqual(checked_text(" Не включайте свет. "), "Не включайте свет.")

    def test_provider_failure_no_retry_and_no_body_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token = root / "token"
            token.write_text("test-only-speech-token-00000000000000")
            token.chmod(0o600)
            with patch("automation_integrations.speech.build_opener") as opener:
                opener.return_value.open.side_effect = HTTPError("https://example.invalid", 429, "SECRET", {}, None)
                with self.assertRaisesRegex(ContractError, "^speech_provider_http_429$"):
                    synthesize("Тест.", {"voice_id": "voice", "model_id": "model", "token_file": str(token)}, root / "new.wav")
                self.assertEqual(opener.return_value.open.call_count, 1)
                self.assertFalse((root / "new.wav").exists())

    def test_output_collision_rejected_before_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token = root / "token"
            token.write_text("test-only-speech-token-00000000000000")
            token.chmod(0o600)
            with patch("automation_integrations.speech.build_opener") as opener:
                with self.assertRaises(ContractError):
                    synthesize("Тест.", {"voice_id": "voice", "model_id": "model", "token_file": str(token)}, token)
                opener.assert_not_called()

    def test_stt_rejects_invalid_input_without_model_import(self):
        with self.assertRaises(ContractError):
            transcribe("relative.ogg", "/no/model")
