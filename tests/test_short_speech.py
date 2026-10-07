import json
import sqlite3
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from automation_integrations.contracts import ContractError
from automation_integrations.hermes_speech import run_tts_parts
from automation_integrations.speech_source import Sources


def write_wave(path, seconds=1):
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b'\0\0' * (seconds * 24000))


class ShortSpeechTests(unittest.TestCase):
    def setup_request(self, root, script):
        source = root / 'input.txt'
        source.write_text('Исходный ответ: двадцать процентов здоровья.')
        state = root / 'state'
        Sources(state).put('turn', source.read_text(), 'Исходный ответ: 20% здоровья.', 'Вопрос')
        return source, {'raw_source_dir': str(state), 'rewrite_argv': ['fake']}

    def test_short_requests_are_combined_into_three_to_five_minute_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = 'Сначала спрячься за бочкой. Затем атакуй босса. ' * 90
            source, config = self.setup_request(root, script)
            seen = []

            def synth(text, config, path):
                seen.append(text)
                write_wave(path, seconds=35)

            with patch('automation_integrations.hermes_speech._command', return_value=json.dumps({'verified': True, 'speech': script})) as rewrite, \
                    patch('automation_integrations.hermes_speech.synthesize', side_effect=synth):
                result = run_tts_parts(source, root, config)
            self.assertTrue(result['success'])
            self.assertGreater(len(seen), 4)
            self.assertEqual(len(result['file_paths']), 1)
            self.assertEqual(' '.join(seen).split(), script.split())
            self.assertTrue(all(len(x) <= 600 for x in seen))
            self.assertTrue(all(180 <= d <= 300 for d in result['durations']))
            self.assertAlmostEqual(sum(result['durations']), 35 * len(seen), delta=0.03)
            self.assertEqual(result['chunk_count'], len(seen))
            self.assertTrue(all(Path(x).is_file() and x.endswith('.ogg') for x in result['file_paths']))
            self.assertEqual(rewrite.call_count, 1)

    def test_assembly_failure_cleans_all_audio_without_resynthesizing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = 'Проверь укрытие перед выстрелом. ' * 80
            source, config = self.setup_request(root, script)
            seen = []

            def synth(text, config, path):
                seen.append(text)
                write_wave(path)

            with patch('automation_integrations.hermes_speech._command', return_value=json.dumps({'verified': True, 'speech': script})), \
                    patch('automation_integrations.hermes_speech.synthesize', side_effect=synth), \
                    patch('automation_integrations.hermes_speech.combine_audio', side_effect=ContractError('speech_media_command_failed')) as combine:
                with self.assertRaisesRegex(ContractError, '^speech_media_command_failed$'):
                    run_tts_parts(source, root, config)
            self.assertEqual(' '.join(seen).split(), script.split())
            self.assertGreater(len(seen), 1)
            combine.assert_called_once()
            self.assertEqual(list(root.glob('speech-parts-*')), [])

    def test_later_chunk_failure_cleans_earlier_audio_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = 'Проверь укрытие перед выстрелом. ' * 80
            source, config = self.setup_request(root, script)
            calls = []

            def synth(text, config, path):
                calls.append(text)
                if len(calls) == 2:
                    raise ContractError('speech_provider_outcome_unknown:timeout')
                write_wave(path)

            with patch('automation_integrations.hermes_speech._command', return_value=json.dumps({'verified': True, 'speech': script})), \
                    patch('automation_integrations.hermes_speech.synthesize', side_effect=synth):
                with self.assertRaisesRegex(ContractError, 'timeout'):
                    run_tts_parts(source, root, config)
            self.assertEqual(len(calls), 2)
            self.assertEqual(list(root.glob('speech-parts-*')), [])
            with sqlite3.connect(root / 'state/sources.sqlite3') as db:
                statuses = [r[0] for r in db.execute('select status from events order by created')]
            self.assertIn('chunk_1_synthesized', statuses)
            self.assertIn('chunk_2_started', statuses)
            self.assertEqual(statuses[-1], 'failed:speech_provider_outcome_unknown:timeout')

    def test_invalid_late_script_never_starts_first_paid_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = 'Проверь укрытие. ' * 90 + '20% здоровья.'
            source, config = self.setup_request(root, script)
            with patch('automation_integrations.hermes_speech._command', return_value=json.dumps({'verified': True, 'speech': script})), \
                    patch('automation_integrations.hermes_speech.synthesize') as synth:
                with self.assertRaises(ContractError):
                    run_tts_parts(source, root, config)
                synth.assert_not_called()
            self.assertEqual(list(root.glob('speech-parts-*')), [])
