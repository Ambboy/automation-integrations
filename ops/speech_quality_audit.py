"""Offline corpus through the actual Hermes cleaner and our numeric guard; no API calls."""
import argparse
import importlib.util
import json
import subprocess
from pathlib import Path
from automation_integrations.vendor.ru_numbers import normalize

CASES = [
    ('sequence', 'Открой настройки → выбери сеть → сохрани изменения.'),
    ('cause', 'Перегрев ⇒ отключение питания.'),
    ('phone_ru', 'Телефон: +7 (999) 123-45-67.'),
    ('phone_de', 'Телефон: +49 151 23456789.'),
    ('document', 'Документ № 00123456789012345678.'),
    ('date_ru', 'Дата: 03.10.2026.'),
    ('date_iso', 'Дата: 2026-10-03.'),
    ('units', 'Температура 20°C, влажность 45%.'),
    ('foreign', 'Подключи Whisper к ElevenLabs через API.'),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--hermes-source', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.hermes_source)
    spec = importlib.util.spec_from_file_location('hermes_cleanup_audit', root / 'tools/tts_text_normalize.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = []
    for name, original in CASES:
        # Native auto-TTS first cleans in the adapter, then again inside the tool.
        first = module.prepare_spoken_text(original, max_chars=None)
        cleaned = module.prepare_spoken_text(first, max_chars=None)
        try:
            spoken, error = normalize(cleaned), None
        except Exception as exc:
            spoken, error = None, type(exc).__name__
        results.append(dict(case=name, original=original, adapter_cleaned=first,
                            tool_cleaned=cleaned, spoken=spoken, error=error))
    report = {'hermes_sha': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
              'scope': 'Offline text preparation only; no audio, STT or semantic acceptance', 'cases': results}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'{len(results)} cases recorded; this audit does not assert speech quality passed')


if __name__ == '__main__':
    main()
