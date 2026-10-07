# Yandex Go: рабочее расширение 04.10.2026

Реестр 2026-10-04.1, Hermes plugin automation-api-catalog v0.3.0.
Исходная версия 2026-10-03.2 сохранена в истории git. Запись отделена от чтения.

## Причина route_not_authorized

Это отказ нашего плагина до сети. До исправления native-проверка установленного
плагина: fresh=true, cached=false, foreign_user=false, group=false, provider_calls=0.
Логи рабочего агента показывают тот же рисунок: успешные инструменты на первом
ходе, отказ на следующем ходе тех же бесед без истечения часового TTL.

В gateway/run.py `_set_session_env` на каждом сообщении вызывает set_session_vars
без session_id. Новый агент заполняет ContextVar в agent_init; кешированный агент
не повторяет инициализацию. Наш старый route() требовал непустой SESSION_ID, а
before() дополнительно требовал совпадение с event.session_id, поэтому повторный
ход не получал допуск. Это воспроизведённый дефект контракта нашего плагина, не
отказ Яндекса, не истечение OAuth и не причина расширять пользовательский доступ.

Новый допуск привязан к доверенным native ContextVars: owner==chat, platform
telegram, chat_type=dm, session_key/message_id/thread_id и Hermes home. Hook также
проверяет event.sender_id/platform/session_id и отсутствие parent_session_id.
Если ContextVar session_id заполнена, её несовпадение отклоняется; её отсутствие
допустимо только вместе с полным контекстом конкретного входящего сообщения.
Инструменты проверяют ту же привязку и TTL; новая message_id требует нового hook.
Делегированные/background контексты запрещены. os.environ не даёт допуска.
Ошибка содержит local_authorization/reason/provider_called=false без идентификаторов.
Ядро Hermes не изменяется. Первые native-тесты v0.2 не моделировали кешированный
ход с пустой SESSION_ID; этот пробел закрыт регрессионным сценарием.

## Официальные контракты и границы

Полный прежний реестр просмотрен шестью страницами: 10+10+10+10+10+2 = 52 метода.
04.10 заново загружены официальный индекс, quickstart, routestats, zone-info,
order-create, order-cancel, order-info, travels-list. Используется проверка TLS:
valid hyphen frontdoor docs-viewer с canonical Host, без отключения сертификата.

- [Расчёт/оффер](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/routestats): POST /integration/2.0/orders/routestats, чтение предложения, не заказ.
- [Тарифы зоны](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/zone-info): GET /integration/2.0/zoneinfo.
- [Создание](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-create): POST /integration/2.0/orders/create, обязательный X-Idempotency-Token UUID.
- [Отмена](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-cancel): POST /integration/2.0/orders/cancel?order_id=..., state из текущих cancel_rules точного заказа.
- [Чтение точного заказа](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-info): GET /integration/2.0/orders/info?order_id=... .
- [Командировки](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/travels-list): POST /integration/2.0/travels/list, существующие командировки, не авиапоиск.

| Операция | Документирована | Адаптер | Аккаунт/договор | Реальный вызов |
|---|---|---|---|---|
| Прежние 9 чтений | Да | Да | Успешно на проверенной странице/объекте | Повторно успешны |
| routestats | Да | integration_read | Получены оффер и 9 тарифов | Да, без заказа |
| zone_info | Да | integration_read | Возвращены тарифы зоны | Да |
| order_create | Да | integration_write | Право записи не проверено | Нет; mock-тесты |
| order_cancel | Да | integration_write | Право записи не проверено | Нет; mock-тесты |
| flight_search | В Go API не найден | Нет | Не установлен отдельный доступ | Нет |

Для безопасной проверки расчёта использованы публичные координаты московского
маршрута из документации, а не предположение о городе вылета пользователя.
Прикладного sandbox для этих методов Business API в просмотренных контрактах не
найдено. Sandbox доставки/таксопарка относится к другим API и не использовался.

## Авиабилеты

В [публичном Go Business API](https://yandex.ru/dev/taxi/taxicorp/) подтверждены
52 метода, consumer API поиска авиабилетов среди них не найден. Это ограничение
подтверждённого доступного интерфейса, не утверждение, что у Яндекса невозможны
закрытые партнёрские интеграции. Отдельный авиадоступ/договор пока не установлен.

[Travel Partners API](https://yandex.ru/dev/travel-partners-api/doc/ru/) описывает
отельные предложения и бронирования. [Протокол авиабилетов Webmaster](https://yandex.ru/support/webmaster/ru/search-appearance/air-tickets)
описывает, как Яндекс запрашивает предложения у сайта авиакомпании/агентства.
Пример api.aviapartner.ru — адрес поставщика, не обнаруженный endpoint Яндекса.
Ни этот пример, ни браузер, ни travels/list не добавлены как поиск авиабилетов.

Исходный запрос сохранён как ограничение карточки: Пхукет, 21/22/23 ноября 2026,
двое, в одну сторону; пункт отправления неизвестен, возрастной состав не указан.
При появлении отдельно подтверждённого API нужны origin/destination/dates/passengers;
выдача должна хранить валюту, общую цену за двоих, пересадки, багаж и правила тарифа
при наличии в ответе. Сейчас flight_search возвращает unsupported_operation до
Vault/сети. Никаких результатов авиапоиска не заявляется.

## Параметры и выполнение

Точные JSON Schema опубликованы в operations/write_operations карточки и
adapter_parameter_schema capabilities. Реализация — yandex_contract.py, те же
схемы проверяются до доступа к Vault. Запрещены лишние ключи, bool вместо числа,
NaN/Infinity, неверные координаты/идентификаторы, пустые и длинные строки,
одинаковые точки. Координаты всегда [долгота, широта].

routestats: route (2–10 точек), optional user_id/use_toll_roads. zone_info: lon/lat.
Поддержанная запись — немедленная поездка: user_id, class, route из объектов
geopoint/fullname, optional comment/cost_center_values. Это строгий поднабор:
отложенная подача и произвольные городские requirements пока не реализованы.
Оффер для записи получает исполнитель; модель не может подставить цену/offer.
Создание разрешено только при наличии фиксированного предложения выбранного тарифа.
Отмена принимает только order_id, правила получает от Яндекса.

Ошибки разделены: local_authorization, adapter_not_implemented, unsupported_operation,
authentication_failed401, access_denied403, resource_not_found404,
offer_expired_or_price_changed406, state_conflict409, rate_limited429,
request_timeout/network_unavailable/tls_failed. Безопасный provider_code возвращается
отдельно, тело ошибки и секреты не выводятся. Пустая коллекция = ok:true и
result_state:empty, не отказ. 25-секундный HTTP timeout, ответ ≤2MiB, очищенный
результат ≤60KB; TLS/запрет redirects сохранены. Локальный лимит 1 запрос/с под
flock — наша консервативная политика, не заявленная квота Яндекса. Retry-After
учитывается как общий дисковый cooldown; автоматического retry HTTP нет.

## Обязательное подтверждение записи

1. integration_write(action=prepare, operation=order_create|order_cancel, params=...).
   Только чтение Яндекса и закрытый черновик; результата заказа ещё нет.
2. Показать владельцу весь preview: маршрут/пассажир/тариф/цена/условия или точный
   заказ и возможную плату за отмену. Предложить отдельное сообщение
   `ПОДТВЕРЖДАЮ <draft_id>`.
3. Только pre_llm_call с новым аутентифицированным входящим сообщением в той же
   личной беседе/теме подтверждает точный hash неизменяемого payload. Цитаты,
   история, confirmed:true и model tool arguments не являются подтверждением.
4. integration_write(action=execute,draft_id=...) выполняет подтверждённый черновик
   в течение 10 минут. Текст команды должен быть отдельным сообщением без цитат.

Перед отправкой под flock и fsync записывается submitting. Create использует UUID
черновика как неизменный X-Idempotency-Token. После timeout/5xx нет автоматического
повтора: outcome_unknown. Для неопределённого create в пределах срока можно вновь
явно подтвердить ТОТ ЖЕ черновик — повтор использует тот же токен/тело. Не готовить
новый черновик вместо неопределённого заказа. После истечения срока нужна ручная
сверка; ключ не заменяется. Неопределённая отмена не повторяется: status читает
точный заказ. При смене cancel_rules старое подтверждение аннулируется.

После ответа записи — обязательный GET точного order_id с совпадающим id и
проверкой status (для отмены cancelled). Если чтение не удалось, accepted_unverified;
status затем делает только чтение. Crash после submitting трактуется как
outcome_unknown. Дубли concurrent execute сериализуются, verified/rejected не
отправляют POST повторно. ok:true в workflow означает выдачу состояния; только
mutation_verified:true означает подтверждённую запись.

Черновики/бизнес-параметры хранятся 0600 в private state/yandex-writes, не в git,
Obsidian или диагностических отчётах. Сам OS-пользователь всё ещё имеет terminal/
vaultctl; это не обещание изоляции от произвольного кода владельца на хосте.

## Проверки и установка

ops/yandex_safe_live.py: все 11 чтений успешны; в отчёте только метаданные, без
токенов, адресов клиентов, сотрудников или содержимого заказов. 14 mock-тестов
записи покрывают подтверждение/границы/таймаут/406/отмену/сверку/конкурентный дубль.
Native contract проверяет новый/кешированный ход, чужого отправителя, группу,
дочернего агента, отсутствие admission и недопустимое model-подтверждение.
Общий результат и installed smoke фиксируются в приватном журнале после выполнения.

Обновление: PYTHONPATH=. python3 ops/update_catalog_release.py apply.
Резерв release/plugin/config hash/gateway state:
~/.local/share/automation-integrations/greif/api-catalog/update-20261004-yandex.
Новые модули api_write.py/yandex_contract.py устанавливаются рядом с api_read.py.
Config.yaml, голос, оформление тем и туннели не редактируются. После установки —
idle restart. Откат: та же команда rollback --release 20261004-yandex, затем idle
restart; последующие правки защищены SHA. Черновики не удаляются при откате:
неопределённые операции требуют сохранённого токена и сверки.

Итог установки: 85 unit passed, native contract1passed, installed route fresh/cached=true и foreign/group=false; installed estimate passed (9 тарифов). Gateway после idle restart running, Telegram connected. Config hash и installed file hashes проверены; запись в production не выполнялась.

Дополнительно: unresolved intent блокирует новый prepare с новым ключом даже после истечения срока старого черновика. Возвращается existing_unresolved_draft и прежний draft_id для сверки. Защита проверена отдельным mock-тестом, обновлённый api_write.py установлен с SHA guard без повторного restart; исполнитель запускается отдельным процессом на каждый вызов.
