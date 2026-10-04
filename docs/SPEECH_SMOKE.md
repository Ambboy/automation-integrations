# Речевые адаптеры и проверка — 03.10.2026

Реализованы самостоятельные командные адаптеры `automation_integrations/speech.py`: ElevenLabs TTS → WAV и локальный faster-whisper → JSON transcript. Импорты ядра Hermes отсутствуют. Используется уже установленный runtime Python и уже закешированная модель Whisper small; managed environments Hermes не изменялись.

## Контракт TTS

```bash
python -m automation_integrations.speech tts --config /absolute/private/tts.json --output /absolute/private/new.wav
```

Текст поступает через stdin; выход — mono PCM WAV 24 кГц. Конфигурация содержит token_file, voice_id, model_id, опциональный абсолютный путь ffmpeg. Ключ читается из приватного файла владельца; в argv передаётся только его путь. Должен быть выбран соответствующий Python и установлен/доступен пакет automation_integrations.

Адаптер совместим с voice.tts_argv существующего voice-reply: `{output_file}` заменяется на путь WAV. Текст должен пройти числовой нормализатор: сырые цифры и текст длиннее 4000 символов отвергаются до обращения к провайдеру. HTTP endpoint фиксирован на api.elevenlabs.io; прокси и redirects отключены, автоматических повторов нет. Ошибки провайдера показываются только как безопасный код HTTP; тело ошибки не выводится. При неизвестном результате повторный synthesis не выполняется автоматически. Максимум 16 МиБ ответа; преобразование FFmpeg ограничено timeout. Существующий output не перезаписывается.

Использован стандартный [ElevenLabs Create speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert): запрос text/model_id с выбранным voice_id, получение MP3 и локальное преобразование в WAV. Нормализация и разбиение на Opus остаются в нашем voice-reply.

## Контракт STT

```bash
python -m automation_integrations.speech stt --input /absolute/audio.ogg --model-dir /absolute/cached/model/snapshot
```

На stdout возвращается JSON с text, language, duration. Вход: существующий локальный файл до 32 МиБ и 120 секунд; отсутствие модели, пустой transcript или слишком длинная расшифровка завершаются ошибкой. Whisper работает на CPU/int8, два потока, один worker, local_files_only=True, VAD включён, язык ru. Сетевой upload для STT и автозагрузка модели отсутствуют. Вызывающий процесс должен ограничивать длительность всего STT: smoke делает это отдельным subprocess с timeout 180 секунд. [Документация faster-whisper](https://github.com/SYSTRAN/faster-whisper).

## Живая проверка

`ops/speech_smoke.py` требует --execute, путь существующего профиля, cached model dir и **новый** output-dir. Повторный запуск в тот же output-dir запрещён, чтобы ошибку/неизвестный synthesis нельзя было незаметно повторить с новым списанием. Временный файл выбранного ElevenLabs-ключа удаляется после TTS. Рабочие .env/config не переписываются.

На SG использованы:

- Источник настроек: профиль server; ElevenLabs eleven_v3 и ранее выбранный голос.
- Python: `/home/operator/.hermes/installs/8b8318f23a592d07/environments/3b1ecdde41374a838811c475f339974b/venv/bin/python`.
- Модель: `/home/operator/.cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots/536b0662742c02347bc0e980a01041f333bce120`.
- Отчёт: `/home/operator/workspaces/automation-integrations-compat/speech-smoke-20261003/report.json`.
- Аудио SG: `speech-smoke-20261003/audio/part-000.ogg`; локальная копия вне git: `artifacts/speech-smoke-20261003/sample.ogg`.

Один реальный TTS-запрос. Исходный текст: «Не включайте питание. Напряжение 230 вольт. Стоимость 25 рублей». Перед провайдером числа преобразованы в слова. Наш voice-reply выполнил TTS → WAV → Ogg/Opus; ffprobe подтвердил Opus и длительность **5,293 с**. Whisper вернул «Не включайте питание, напряжение 230 вольт, стоимость 25 рублей». Автоматические проверки отрицания, напряжения и цены прошли; provider-конфигурация побайтово неизменна. Ни одного Telegram-вызова, нового LLM-вызова или скачивания модели в этом этапе.

Общий SG прогон: **40 unit tests passed**. Четыре новых теста проверяют отклонение ненормализованного/слишком длинного текста, отсутствие повторов при HTTP 429, отсутствие утечки тела ошибки, запрет перезаписи output и недопустимый STT-вход.

## Границы доказанного

Это проверка синтетической речи в тихой записи, а не качества микрофона, шумов, диалектов, естественности голоса или всех числовых конструкций. Прослушивание человеком ещё не подтверждено. Путь Telegram audio download → STT → модель → озвучка в одной живой сессии ещё не проверен: модельный и речевой этапы испытаны отдельно. STT пока командный; fixture ingress принимает явный transcript. Production polling/webhook, плагины, VPN и модельные настройки не переключались.

Следующий содержательный этап — связать локальный аудиовход с ingress и сделать полную изолированную голосовую сессию, затем пилот на отдельно согласованном Telegram-маршруте с единственным владельцем получения updates и отправок.
