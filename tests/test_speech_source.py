import tempfile
import unittest
from automation_integrations.speech_source import Sources
from automation_integrations.hermes_speech import speech_chunks


class SourceTests(unittest.TestCase):
    def test_different_originals_with_same_cleaned_text_refused(self):
        with tempfile.TemporaryDirectory() as root:
            store = Sources(root)
            store.put('a', 'Дата.', 'Дата: 2026-10-03.', 'one', now=10)
            self.assertEqual(store.get('Дата.', now=11)['original'], 'Дата: 2026-10-03.')
            store.put('b', 'Дата.', 'Дата: 2027-10-03.', 'two', now=12)
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                store.get('Дата.', now=13)

    def test_missing_partial_and_expired_refused(self):
        with tempfile.TemporaryDirectory() as root:
            store = Sources(root)
            store.put('a', 'Полный ответ.', 'Полный ответ.', 'question', now=10)
            for text, now in [('ответ.', 11), ('Полный ответ.', 611)]:
                with self.assertRaises(ValueError):
                    store.get(text, now=now)

    def test_replayed_same_turn_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as root:
            store = Sources(root)
            for _ in range(2):
                store.put('same', 'Текст.', 'Текст.', 'question', now=10)
            self.assertEqual(store.get('Текст.', now=11)['context'], 'question')

    def test_chunks_preserve_every_word(self):
        text = 'Не включайте питание. Затем проверьте напряжение. ' * 200
        chunks = speech_chunks(text)
        self.assertTrue(all(len(x) <= 3000 for x in chunks))
        self.assertEqual(' '.join(chunks).split(), text.split())
