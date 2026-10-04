# Проверка кандидата 0.1 — 03.10.2026

## Результаты

| Проверка | Результат и граница |
|---|---|
| `python3 -m unittest discover -v`, SG staging | 24 passed, 0 skipped, 0 failed |
| Native PluginManager на официальном Hermes 298df082, штатный `scripts/run_tests.sh` | 1 passed: discovery, регистрация hooks, безопасный отказ без origin, unload и остановка sender |
| Loopback HTTP demo | Оба модуля завершились `simulated`, внешних вызовов нет |
| Реальное медиа | FFmpeg/FFprobe преобразовали 61 с синтетической тишины в две валидные Ogg/Opus-части ≤60 с; multipart принят HTTP fixture |
| Граница падения процесса | После принятия запроса HTTP fixture дочерний worker завершён через `os._exit(73)` до записи квитанции; восстановление дало `outcome_unknown`, повторной отправки нет |
| Дубликаты | 24 конкурентных приёма одного события создали одно задание; другой payload с тем же ID отклонён |
| Изоляция | Чужие profile/chat/user/thread отклонены; другое подключение не видит job/status первого |
| Изменение режима | Queued dry-run остаётся simulated после включения live; транспорт не создаётся |
| Устаревшие события | Поздно доставленное старое событие темы завершается superseded |
| Bridge | Durable origin binding/outbox переживает повторное создание, потерю HTTP receipt; «только текстом» сохраняется для внутренних продолжений |
| Статические проверки | compileall, JSON-пример, vendor SHA-256, отсутствие импортов внутренностей Hermes, systemd unit verify |

На Kronstadt media-тест пропускается из-за отсутствия FFmpeg/FFprobe; этот пропуск закрыт полным прогоном на SG. Native-проверка выполнялась на конечной копии bridge через реальный загрузчик и отдельный HERMES_HOME. Проверка не заменяет live-приёмку маршрутизации от настоящего сообщения.

## Не проверено и не включено

- Реальный TTS-провайдер, качество речи и живые отправки Telegram.
- Автоматический голос на чистой базе Hermes: необходимого origin-контракта там нет.
- Сохранение всех возможностей старого voice-dual-reply: модельное перефразирование не перенесено.
- Production systemd unit: проверен синтаксис, установка/автозапуск не выполнялись.
- Длительная нагрузка, retention и обслуживание больших очередей; один worker в v0.1 последовательно обрабатывает задания.
- Внешние уведомления об ошибках: пока только CLI/API/журнал.

## Сохранность production

До и после проверки: checkout `06076ba69743531248ee112df676c4ed23809283`, `git status --porcelain` пустой. `hermes-gateway-server.service`: active, PID `433541`, InvocationID `b0d7f9c5751b420e96d51247d1fe25bb` неизменны. В отдельной копии официального Hermes `git status --short` также пустой. Боевые плагины, конфигурация, gateway, VPN и токены не изменялись. Сообщения людям не отправлялись.


## Runs API прототип — 03.10.2026

- SG staging runs-project: **35 unittest tests passed**, без пропусков; включая 11 новых проверок клиента. Локальный предыдущий общий прогон: 33 tests, 1 media skip; два добавленных теста затем вошли в 11/11 целевых локальных и 35/35 SG.
- Чистый официальный Hermes 37dd129a, штатный scripts/run_tests.sh: **1 native test passed**. Настоящий loopback HTTP/auth/идемпотентность/SQLite, тестовый executor без модели. Проверены origin для трёх маршрутов, потерянное подтверждение, повтор после пересоздания компонентов, 401/409, три уникальных dry-run задания. Подробные границы в docs/RUNS_PROTOTYPE.md.
- ops/runs_demo.py локально и на SG: один тестовый Hermes run после потери квитанции, одно simulated задание, внешних вызовов нет.
- compileall и git diff --check прошли. Изменений исходников чистого Hermes и production нет (git status пустой).
- Production: active, MainPID 433541, InvocationID b0d7f9c5751b420e96d51247d1fe25bb — прежние. Плагины, VPN, Telegram updates, модельные credentials не менялись.


## Fixture ingress + настоящая модель — 03.10.2026

- SG: **36 unit tests passed**, без skip. Native-тест теперь включает HTTP fixture ingress → настоящие HTTP handlers Hermes → dry-run job; **1 passed**.
- Live harness на чистом Hermes 37dd129a и существующем runtime-интерпретаторе: `passed=true`, `state=completed`, `exact_answer=true`, `plugin_job=simulated`, `telegram_sent=false`, `toolsets=[]`, `real_model=gpt-6-sol-900k`, `production_auth_unchanged=true`.
- Использован отдельный временный профиль и snapshot только выбранной авторизации без refresh_token. Рабочие config/auth не менялись. Модель ответила точной синтетической строкой; реальная речь/Telegram не проверялись.
- Промежуточные неуспехи: test interpreter без PyYAML; конфликт имени пакета tests при импорте fixture (устранена зависимость live-harness от tests); первый реальный run завершился успешно, но job failed из-за PYTHONPATH дочернего normalizer. После задания абсолютного пути в окружении только стенда второй реальный run прошёл всю цепочку. Всего два успешных модельных ответа, из них один полный successful smoke.
- Live-harness не запускать через credential-scrubbing test runner: это явная runtime-проверка, требующая --execute. Unit/native проверки по-прежнему используют стандартные unittest/scripts/run_tests.sh соответственно.
- Конспект этапов внесён в Obsidian, проверены схемы/H2/wiki-ссылки. Материал в инфраструктурной ветке, ботам не опубликован.


## Настоящий STT/TTS — 03.10.2026

40 unit tests passed на SG. Один реальный ElevenLabs eleven_v3 synthesis через voice-reply → ffmpeg/ffprobe → 5.293 s Opus → cached local Whisper small, CPU/int8. Transcript: «Не включайте питание, напряжение 230 вольт, стоимость 25 рублей». Проверки negation/voltage/price true, production_config_unchanged true, model_downloaded false, telegram_sent false. Подробности и ограничения: docs/SPEECH_SMOKE.md. Это отдельная речевая проверка, не общий Telegram/LLM E2E и не оценка качества человеком.
