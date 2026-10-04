---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/limit-info.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/limit-info.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/limit-info.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получение информации о лимите

Запрос позволяет получить информацию по конкретному лимиту.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/limits?limit_id={ID лимита}
```

**Заголовки запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->
 

**Параметры запроса**

Запрос может содержать следующие необязательные параметры:

- `limit_id` - ID запрашиваемого лимита.

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `id`| id лимита. | Строка ||
|| `enabled` | Включен ли лимит для страны клиента. | Логическое ||
|| `title` | Название лимита. | Строка ||
|| `client_id` | id клиента. | Строка ||
|| `department_id` | id департамента, к которому относится лимит. Если департамент отсутствует, значит, это корневой департамент. | Строка ||
|| `categories` | Cписок доступных тарифных категорий. Указывается только для сервисов `taxi` и `cargo`. Формат списка "категория1","категория2", .... | Массив строк ||
|| `fuel_types` | Список доступных видов топлива. Указывается только для сервиса `tanker`. Формат списка "вид1","вид2", .... | Массив строк ||
|| `limits` | [Ограничения](#limits) | Объект ||
|| `geo_restrictions` | [Блок с информацией](#geo-restrictions) о разрешенных районах поездок. | Массив объектов ||
|| `time_restrictions` | [Блок с информацией](#time-restrictions) о временных ограничениях. | Массив объектов ||
|| `can_edit` | Признак, может ли пользователь изменить или удалить данный лимит. | Логическое ||
|| `counters` | Количество сотрудников с данным лимитом. Объект со структурой `{"users": <число>}`. | Объект ||
|| `is_default` | Признак, используется ли данный лимит по умолчанию (задан при активации сервиса клиенту). | Логическое ||
|| `is_qr_enabled` | Включена ли оплата по QR (только для сервисов Еда и Лавка). | Логическое ||
|| `service` | Идентификатор сервиса, для которого задается лимит. | Строка ||
|| `cities` | Города, в которых можно использовать сервис (только для сервиса Драйв). | Массив объектов ||
|| `tariffs` | Тарифы, доступные к заказу (только для сервиса Драйв). | Массив объектов ||
|| `cars_classes` | Классы машин, доступные к заказу (только для сервиса Драйв). | Массив строк||
|| `insurance_types` | Виды страхования (только для сервиса Драйв). | Массив строк||
|| `enable_toll_roads` | Разрешен ли проезд по платным дорогам (только для сервисов Такси и Драйв). | Логическое ||
|| `is_deleted` | Признак удаленного лимита. | Логическое ||
|| `is_fleet_limit` | Признак флит-лимита (только для Заправок). | Логическое ||
|| `travel_policy_id` | Идентификатор тревел-политики. | Строка ||
|| `hotel_policy` | Политика бронирования отелей. | Объект ||
|| `avia_policy` | Политика авиаперелетов. | Объект ||
|| `trains_policy` | Политика ЖД-поездок. | Объект ||
|| `taxi_policy` | Политика поездок на такси в командировках. | Объект ||
|| `allow_reservations_without_approve` | Разрешены ли бронирования без согласования. | Логическое ||
|| `approve_role` | Роль согласующего. Поле устарело. | Строка ||
|| `approve_roles` | Роли согласующих. | Массив строк ||
|| `company_funded_allowance_policies` | Настройки доплат за счет компании. | Объект ||
|#

Структура объекта `limits`: {#limits}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `orders_amount` | Ограничение на количество заказов. Используется для `taxi` и `cargo`. | Объект ||
|| `orders_cost` | Ограничение по стоимости. | Объект ||
|| `orders_time` | Ограничение по времени заказов. | Объект ||
|| `orders_distance` | Ограничение по расстоянию заказов. | Объект ||
|#

Структура числового или стоимостного ограничения:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `value` | Значение ограничения. Для стоимости передается строкой, для остальных ограничений — целым числом. | Строка или целое число ||
|| `period` | Период ограничения. | Строка ||
|| `kind` | Единица ограничения Заправок: `money` или `volume`. | Строка ||
|| `accumulation_rules` | Правила накопления остатка стоимостного лимита. | Объект ||
|#

Структура объекта `accumulation_rules`:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `accumulation_period` | Период накопления. | Строка ||
|| `started_at` | Дата начала накопления. | Строка ||
|#

Структура элемента массива `geo_restrictions`: {#geo-restrictions}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `source` | Идентификатор района начала поездки. Если поле не задано, то разрешен любой район. Должно быть задано хотя бы одно из полей `source` и `destination`. | Строка ||
|| `destination` | Идентификатор района конца поездки. Если поле не задано, то разрешен любой район. Должно быть задано хотя бы одно из полей `source` и `destination`. | Строка ||
|| `prohibiting_restriction` | Признак запрещающего географического правила. | Логическое ||
|| `forbid_intermediate_stops` | Запретить промежуточные остановки вне разрешенных зон. | Логическое ||
|| `allowed_intermediate_zones` | Геозоны, в которых разрешены промежуточные точки маршрута. | Массив строк ||
|#

Структура элемента массива `time_restrictions`: {#time-restrictions}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `type` | Тип ограничения: `weekly_date`, `calendar_date` или `range_date`. | Строка ||
|| `days` | Дни недели: `mo`, `tu`, `we`, `th`, `fr`, `sa`, `su`. | Массив строк ||
|| `start_time` | Время начала для `weekly_date` и `calendar_date`. | Строка ||
|| `end_time` | Время окончания для `weekly_date` и `calendar_date`. | Строка ||
|| `only_holidays` | Применять ограничение `calendar_date` только в праздники. | Логическое ||
|| `start_date` | Начало ограничения `range_date` в формате `YYYY-MM-DDTHH:MM:SS`. | Строка ||
|| `end_date` | Конец ограничения `range_date` в формате `YYYY-MM-DDTHH:MM:SS`. | Строка ||
|#

Структура объекта `counters`:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `users` | Количество сотрудников с лимитом. | Целое число ||
|#

Структура объекта `hotel_policy`:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `geo` | Географические правила стоимости отелей. | Массив объектов ||
|| `stars` | Разрешенная звездность отелей. | Массив целых чисел ||
|| `max_price_per_day` | Максимальная стоимость за сутки. | Целое число ||
|| `min_price_per_day` | Минимальная стоимость за сутки. | Целое число ||
|| `weekly_restrictions` | Разрешенные дни недели. | Массив строк ||
|#

Структура элемента массива `geo`:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `region` | Географический регион. | Объект ||
|| `max_price_per_day` | Максимальная стоимость за сутки для региона. | Целое число ||
|| `min_price_per_day` | Минимальная стоимость за сутки для региона. | Целое число ||
|#

Структура объекта `region`:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `geo_id` | Идентификатор региона. | Целое число ||
|| `type` | Тип региона. | Целое число ||
|| `name` | Название региона. | Строка ||
|#

Структура объекта `avia_policy`:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `max_price` | Максимальная стоимость билета. | Целое число ||
|| `min_price` | Минимальная стоимость билета. | Целое число ||
|| `percent_price` | Процентное ограничение стоимости. | Объект ||
|| `countries_restrictions` | Разрешенные группы стран: `rus`, `cis`. | Массив строк ||
|| `classes` | Разрешенные классы: `economy`, `business`, `premium`, `first`. | Массив строк ||
|| `extra_baggage` | Разрешен дополнительный багаж. | Логическое ||
|| `aeroexpress` | Разрешен Аэроэкспресс. | Логическое ||
|#

Структура объекта `percent_price`:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `value` | Процентное ограничение. | Целое число ||
|| `with_baggage` | Учитывать стоимость с багажом. | Логическое ||
|#

Структура объекта `trains_policy`:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `max_price` | Максимальная стоимость билета. | Целое число ||
|| `min_price` | Минимальная стоимость билета. | Целое число ||
|| `countries` | Разрешенные группы стран. | Массив строк ||
|| `service_classes` | Разрешенные классы обслуживания. | Массив строк ||
|| `car_types` | Разрешенные типы вагонов. | Массив строк ||
|| `extra_meal_allowed` | Разрешено дополнительное питание. | Логическое ||
|| `extra_baggage_allowed` | Разрешен дополнительный багаж. | Логическое ||
|| `refundability` | Требование к возвратности билета. | Строка ||
|#

Объект `taxi_policy` повторяет поля `categories`, `time_restrictions`, `geo_restrictions`,
`enable_toll_roads` и `limits`, а также содержит поле:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `is_enabled` | Включена ли возможность заказа такси в командировке. | Логическое ||
|#

Структура объекта `company_funded_allowance_policies`:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `surcharges_limit` | Максимальная сумма доплат за счет компании. | Целое число ||
|| `items` | Разрешенные типы доплат. | Массив строк ||
|#

## Пример запроса {#request-example}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/limits?limit_id=41...10
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#response-example}

Пример ответа для сервиса Такси:

```json
{
    "categories": [
        "cargo_hour",
        "child_tariff",
        "lite_b2b",
        "maybach",
        "minivan",
        "optimum_b2b",
        "premium_van",
        "standart_b2b",
        "ultimate",
        "vip"
    ],
    "time_restrictions": [],
    "geo_restrictions": [],
    "id": "41...10",
    "client_id": "a2...52",
    "service": "taxi",
    "title": "Такси",
    "limits": {},
    "counters": {
        "users": 1
    },
    "is_default": true,
    "enable_toll_roads": true,
    "can_edit": true
}
```

Пример ответа для сервиса Драйв:

```json
{
    "id": "26...40",
    "client_id": "a2...52",
    "service": "drive",
    "title": "Поездки на каршеринге",
    "limits": {
        "orders_cost": {
            "value": "10000",
            "period": "month"
        }
    },
    "counters": {
        "users": 1
    },
    "is_default": true,
    "cities": [
        "kzn",
        "msk",
        "sochi",
        "spb"
    ],
    "tariffs": [
        "fix_offer_regular",
        "flexible_pack_offer",
        "intercity_offer",
        "standart_offer"
    ],
    "cars_classes": [
        "cargo",
        "everyday",
        "holiday",
        "shuttle"
    ],
    "enable_toll_roads": true,
    "time_restrictions": [],
    "can_edit": true
}
```

Пример ответа для сервисов Еда и Лавка:

```json
{
    "id": "99...f7",
    "client_id": "a2...52",
    "service": "eats2",
    "title": "Обеды и перекусы",
    "time_restrictions": [
        {
            "type": "weekly_date",
            "start_time": "00:00:00",
            "end_time": "23:59:00",
            "days": [
                "sa",
                "su"
            ]
        },
        {
            "type": "weekly_date",
            "start_time": "00:00:00",
            "end_time": "23:59:00",
            "days": [
                "fr",
                "mo",
                "th",
                "tu",
                "we"
            ]
        },
        {
            "type": "weekly_date",
            "start_time": "00:00:00",
            "end_time": "23:59:00",
            "days": [
                "fr",
                "mo",
                "th",
                "tu",
                "we"
            ]
        },
        {
            "type": "weekly_date",
            "start_time": "00:00:00",
            "end_time": "23:59:00",
            "days": [
                "fr",
                "mo",
                "th",
                "tu",
                "we"
            ]
        }
    ],
    "geo_restrictions": [],
    "limits": {
        "orders_cost": {
            "value": "1000",
            "period": "month",
            "accumulation_rules": {
                "accumulation_period": "year"
            }
        }
    },
    "counters": {
        "users": 1
    },
    "is_default": true,
    "is_qr_enabled": false,
    "can_edit": true
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `404` — лимит не найден.
