---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/limit-update.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/limit-update.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/limit-update.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Редактирование персонального лимита сотрудника

Запрос позволяет изменить персональный лимит сотрудника.

## Синтаксис запроса {#request-syntax}

```
PUT https://b2b-api.go.yandex.ru/integration/2.0/limits/personal?user_id={id сотрудника}
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

Запрос содержит следующий параметр:

- `user_id` — идентификатор пользователя (сотрудника). 

**Тело запроса**

{% note warning %}

В данном запросе необходимо тело (body) запроса!

{% endnote %}

Данные передаются в теле запроса в формате JSON:

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`title` | Название лимита. | Строка | Да||
||`client_id` | Идентификатор клиента (кабинета). | Строка | Да||
||`service` | Сервис, к которому относится лимит:
- `taxi` — Такси;

- `eats2` — Еда и Лавка;

- `drive` — Драйв;

- `tanker` — Заправки;

- `travel` — Командировки. | Строка | Да||
||`сategories` | Указывается только для сервиса `taxi`. Список доступных тарифных категорий. Каждая категория приводится отдельно в кавычках через запятую. Доступные категории:
- `lite_b2b`;

- `standart_b2b`;

- `optimum_b2b`;

- `vip`;

- `maybach`;

- `ultimate`;

- `minivan`;

- `premium_van`;

- `child_tariff`. | Строка | Да||
||`limits` | Указывается только для сервисов `taxi` и `travel`:
-  `taxi` — cодержит параметры `orders_cost` и `orders_amount`;

-  `travel` — ограничение на общие траты, cодержит параметр `orders_cost` — лимит по общей стоимости командировок.| Объект | Нет ||
|#

Структура элемента массива `limits`: {#limits}

#|
||**Поле** | **Описание** | **Формат**||
||`orders_cost` | Ограничение на сумму, которую клиент может потратить за период. Объект со структурой `{"value": <число>, "period": <период>, "kind": <мера измерения>}`.
Для сервиса `taxi` период задается значениями `"day"`, `"week"` или `"month"`; для сервиса `travel` — значениями `"month"`, `"quarter"` или `"year"`.
`"kind"` указывается только для заправок, задается в виде строки: `"money"` или `"volume"`.  | Строка ||
||`orders_amount` | Указывается только для сервиса `taxi`. Ограничение на число поездок, которые клиент может совершить за период. 
Объект со структурой `{"value": <число>, "period": <период>}`.
Период задается в виде строки: `"day"` или `"week"` или `"month"`.  | Строка  ||
|#


Дополнительные элементы тела запроса (body): {#body-extra}

#|
||**Поле** | **Описание** | **Формат**||
||`time_restrictions` | Блок с информацией о [временных ограничениях](#time-restrictions).  | Массив объектов ||
||`geo_restrictions` | Указывается только для сервисов `taxi`, `eats2`, `tanker`. Блок с информацией о [гео ограничениях](#geo-restrictions).  | Массив объектов  ||
||`is_qr_enabled ` | Указывается только для сервиса `eats2`. Разрешена ли оплата по QR в вендоматах. | Логическое ||
||`fuel_types` | Указывается только для сервиса `tanker`. Список доступных видов топлива. Формат списка: "вид1","вид2",...  | Массив строк ||
||`cities` | Указывается только для сервиса `drive`. Список доступных городов.  | Массив ||
||`tariffs` | Указывается только для сервиса `drive`. Список доступных тарифов.  | Массив ||
||`cars_classes` | Указывается только для сервиса `drive`. Список доступных классов машин. | Массив строк ||
||`insurance_types` | Указывается только для сервиса `drive`. Доступные виды страхования. | Массив строк ||
||`enable_toll_roads` | Указывается только для сервиса `drive`. Доступны ли пользователю платные дороги.  | Логическое ||
|| `hotel_policy` | Указывается только для сервиса `travel`. Политика бронирования отелей. | Объект | Нет ||
|| `avia_policy` | Указывается только для сервиса `travel`. Политика бронирования авиабилетов. | Объект | Нет ||
|| `trains_policy` | Указывается только для сервиса `travel`. Политика бронирования ЖД билетов. | Объект | Нет ||
|| `taxi_policy` | Указывается только для сервиса `travel`. Политика использования такси в командировках. | Объект | Нет ||
|| `allow_reservations_without_approve` | Указывается только для сервиса `travel`. Разрешены ли самостоятельные бронирования без согласования при условии соблюдения тревел-политики. | Булево | Нет ||
|| `limits` | Ограничение на общие траты. | TravelLimits | Нет ||
|| `approve_roles` | Указывается только для сервиса `travel`. Список ролей, которые могут согласовывать бронирования: `client`, `department_manager`. | Массив строк | Нет ||
|| `company_funded_allowance_policies` | Настройки доплат за счет компании. | Объект | Нет ||
|#

Структура элемента массива `time_restrictions`: {#time-restrictions}

#|
||**Поле** | **Описание** | **Формат**||
||`type` | Тип ограничения. Возможные значения:
- `weekly_date` — ограничения по дням недели.
- `range_date` — ограничения по дате. Указывается только для сервисов`taxi`, `eats2`, `tanker`.  | Строка||
||`start_date` | Дата, начиная с которой будет доступен заказ. Формат значений: ГГГГ-ММ-ДДTЧЧ:ММ:СС. 
Поле используется только для ограничения с типом `range_date`. | Строка ||
||`end_date` | Дата, после которой будет доступен заказ. Формат значений: ГГГГ-ММ-ДДTЧЧ:ММ:СС. 
Поле используется только для ограничения с типом `range_date`. | Строка ||
||`start_time` | Время, начиная с которого будет доступен заказ. Формат значений: ЧЧ:ММ:СС. 
Поле используется только для ограничения с типом `weekly_date`. | Строка ||
||`end_time` | Время, до которого будет доступен заказ. Формат значений: ЧЧ:ММ:СС. 
Поле используется только для ограничения с типом `weekly_date`. | Строка ||
||`days` | Дни недели, в которые доступен заказ поездки. Возможные значения: 
- `mo` — понедельник.
- `tu` — вторник.
- `we` — среда.
- `th` — четверг.
- `fr` — пятница.
- `sa` — суббота.
- `su` — воскресенье.
Поле используется только для ограничения с типом `weekly_date`. | Массив строк ||
|#

Структура элемента массива `geo_restrictions`: {#geo-restrictions}

#|
||**Поле** | **Описание** | **Формат**||
||`source` | Идентификатор района начала поездки. Если поле не задано, то разрешен любой район. Должно быть задано хотя бы одно из полей `source` и `destination`.  | Строка ||
||`destination` | Идентификатор района конца поездки. Если поле не задано, то разрешен любой район. Должно быть задано хотя бы одно из полей `source` и `destination`.  | Строка ||
||`prohibiting_restriction` | Используется, чтобы запретить ехать в конкретную точку или из конкретной точки. Если имеет значение `true`, то поля `source` и `destination` недоступны для заказа зоны. | Логическое ||
||`forbid_intermediate_stops` | Запретить промежуточные остановки вне разрешенных зон. | Логическое ||
||`allowed_intermediate_zones` | Геозоны, в которых разрешены промежуточные точки маршрута. | Массив строк ||
|#

Структура объекта `hotel_policy`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `geo` | Географические правила стоимости отелей. | Массив объектов | Нет ||
|| `stars` | Разрешенная звездность отелей: `0`, `1`, `2`, `3`, `4`, `5`. | Массив чисел | Нет ||
|| `max_price_per_day` | Общая максимальная цена за сутки. Минимальное значение: 0. | Число | Нет ||
|| `min_price_per_day` | Общая минимальная цена за сутки. Минимальное значение: 0. | Число | Нет ||
|| `weekly_restrictions` | Разрешенные дни недели: `mo`, `tu`, `we`, `th`, `fr`, `sa`, `su`. | Массив строк | Нет ||
|#

Структура элемента массива `geo`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `region` | Географический регион. | Объект | Да ||
|| `max_price_per_day` | Максимальная стоимость за сутки для региона. | Целое число | Нет ||
|| `min_price_per_day` | Минимальная стоимость за сутки для региона. | Целое число | Нет ||
|#

Структура объекта `region`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `geo_id` | Идентификатор географического региона. | Целое число | Да ||
|| `type` | Тип региона. | Целое число | Нет ||
|| `name` | Название региона. | Строка | Нет ||
|#

Структура объекта `avia_policy`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `max_price` | Максимальная цена билета. Минимальное значение: 0. | Число | Нет ||
|| `min_price` | Минимальная цена билета. Минимальное значение: 0. | Число | Нет ||
|| `percent_price` | Ограничение цены в процентах. | Объект | Нет ||
|| `countries_restrictions` | Ограничения по странам: `rus` (Россия), `cis` (СНГ). | Массив строк | Нет ||
|| `classes` | Разрешенные классы обслуживания: `economy`, `business`, `premium`, `first`. | Массив строк | Нет ||
|| `extra_baggage` | Разрешен ли дополнительный багаж. Значение по умолчанию: `true` | Булево | Нет ||
|| `aeroexpress` | Разрешен ли аэроэкспресс. Значение по умолчанию: `true`. | Булево | Нет ||
|#

Структура объекта `percent_price`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `value` | Процентное ограничение. | Целое число | Нет ||
|| `with_baggage` | Учитывать стоимость с багажом. | Булево | Нет ||
|#

Структура объекта `trains_policy`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `max_price` | Максимальная цена билета. Минимальное значение: 0. | Число | Нет ||
|| `min_price` | Минимальная цена билета. Минимальное значение: 0. | Число | Нет ||
|| `countries` | Разрешенные страны: `rus` (Россия), `cis` (СНГ). | Массив строк | Нет ||
|| `service_classes` | Разрешенные классы обслуживания:
  - `premium_compartment` - премиум купе;
  - `conference_compartment` - конференц-купе;
  - `business_compartment` - бизнес-купе;
  - `first` - первый класс;
  - `suite_compartment` - люкс;
  - `business` - бизнес;
  - `comfort` - комфорт;
  - `family` - семейный;
  - `economy_plus` - эконом плюс;
  - `bistro_car` - вагон-бистро;
  - `economy` - эконом;
  - `base` - базовый. | Массив строк | Нет ||
|| `car_types` | Разрешенные типы вагонов: `Shared`, `Soft`, `Luxury`, `Compartment`, `ReservedSeat`, `Sedentary`, `Baggage`. | Массив строк | Нет ||
|| `refundability` | Требования к возвратности:
  - `only_non_refundable` - только невозвратные;
  - `only_refundable` - только возвратные;
  - `both` - любые. | Перечисление строк | Нет ||
|#

Структура объекта `taxi_policy`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `is_enabled` | Включена ли возможность заказа такси. | Булево | Нет ||
|| `categories` | Разрешенные категории такси. | Массив строк | Да ||
|| `time_restrictions` | Временные ограничения. | Массив TimeRestriction | Да ||
|| `geo_restrictions` | Географические ограничения. | Массив GeoRestriction | Да ||
|| `enable_toll_roads` | Разрешены ли платные дороги. | Булево | Нет ||
|| `limits` | Лимиты на такси. | TaxiLimits | Нет ||
|#

Структура массива `TimeRestriction`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `type` | Тип ограничения, например: `weekly_date`. | Строка | Да ||
|| `start_time` | Время начала, формат: `HH:MM`. | Время в формате строки | Да ||
|| `end_time` | Время окончания, формат: `HH:MM`. | Время в формате строки | Да ||
|| `days` | Дни недели: `mo`, `tu`, `we`, `th`, `fr`, `sa`, `su`. | Массив строк | Да ||
|#

Структура массива `GeoRestriction`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `source` | Точка отправления. | Строка | Нет ||
|| `destination` | Точка назначения. | Строка | Нет ||
|| `prohibiting_restriction` | Является ли ограничение запрещающим. | Булево | Нет ||
|| `forbid_intermediate_stops` | Запретить промежуточные остановки вне разрешенных зон. | Булево | Нет ||
|| `allowed_intermediate_zones` | Разрешенные геозоны промежуточных остановок. | Массив строк | Нет ||
|#

Структура объекта `TaxiLimits`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `orders_amount` | Лимит по количеству заказов. | Объект | Нет ||
|| `orders_time` | Лимит по времени поездок (в минутах). | Объект | Нет ||
|| `orders_distance` | Лимит по расстоянию (в км). | Объект | Нет ||
|| `orders_cost` | Лимит по стоимости. | Объект | Нет ||
|#

Структура объекта `orders_amount`/`orders_time`/`orders_distance`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `value` | Значение лимита. | Число | Да ||
|| `period` | Период: `day`, `week`, `month`, `year`. | Строка | Да ||
|#

Структура объекта `orders_cost`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `value` | Значение лимита — строка с целым положительным числом, например: `"300000"`. | Строка | Да ||
|| `period` | Период: `day`, `week`, `month`, `year`. | Строка | Да ||
|#

Структура объекта `company_funded_allowance_policies`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `surcharges_limit` | Максимальная сумма доплат за счет компании. Значение должно быть не меньше `0`. | Целое число | Нет ||
|| `items` | Разрешенные типы доплат за счет компании: `hotel_cancellation_with_fine`, `hotel_room_upgrade_with_payment`, `avia_additional_baggage`, `avia_ticket_exchange_with_payment`, `avia_train_refund_with_fine`, `avia_passenger_data_change_with_payment`, `avia_ural_airlines_change_passenger`. | Массив строк | Нет ||
|#

## Описание полей ответа {#response-description}

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `id` | Идентификатор созданного персонального лимита. | Строка | Нет ||
|#

## Пример запроса {#request-example}

```
PUT https://b2b-api.go.yandex.ru/integration/2.0/limits/personal?user_id=f1387…5e179
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

    { 
        примеры тела запроса см. ниже
    }
```

### Пример тела (body) запроса для задания лимита для сервиса Такси: {#body-taxi}

```json
{
    "title": "Название лимита",
    "client_id": "id клиента",
    "service": "taxi",
    "categories": [
        "child_tariff",
        "cargo",
        "business",
        "courier",
        "express",
        "premium_van",
        "comfortplus",
        "ultimate",
        "minivan",
        "vip",
        "maybach",
        "econom"
    ],
    "limits": {
        "orders_cost": { 
            "value": "818181", 
            "period": "month"
        }, 
        "orders_amount": {
            "value": 2,
            "period": "day"
        }
    },
    "time_restrictions": [
        {
            "type": "range_date",
            "start_date": "2022-09-02T00:00:00",
            "end_date": "2022-09-14T00:00:00"
        },
        {
            "type": "weekly_date",
            "start_time": "00:00:00",
            "end_time": "23:59:00",
            "days": ["fr", "mo", "th", "tu", "we"]
        }
    ],
    "geo_restrictions": [
        {
            "source": "e87d178829b24d20b9eba262da5eb966",
            "destination": "3ff4d32ef1074d4ca33c1db61047e06f",
            "prohibiting_restriction": true
        }
    ] 
}
```

### Пример тела (body) запроса для задания лимита для сервисов Еда и Лавка: {#body-eats2}

```json
{
    "title": "Название лимита",
    "client_id": "id клиента",
    "service": "eats2",
    "limits": {
        "orders_cost": { 
            "value": "818181", 
            "period": "month"
        }
    },
    "time_restrictions": [
        {
            "type": "range_date",
            "start_date": "2022-09-02T00:00:00",
            "end_date": "2022-09-14T00:00:00"
        },
        {
            "type": "weekly_date",
            "start_time": "00:00:00",
            "end_time": "23:59:00",
            "days": ["fr", "mo", "th", "tu", "we"]
        }
    ],
    "geo_restrictions": [
        {
            "destination": "e87d178829b24d20b9eba262da5eb966",
            "prohibiting_restriction": false
            }
    ],
    "is_qr_enabled": true
}
```

### Пример тела (body) запроса для задания лимита для сервиса Драйв: {#body-drive}

```json
{
    "title": "Название лимита",
    "client_id": "id клиента",
    "service": "drive",
    "limits": {
        "orders_cost": { 
            "value": "818181", 
            "period": "month"
        }
    },
    "time_restrictions": [
        {
            "type": "weekly_date",
            "start_time": "00:00:00",
            "end_time": "23:59:00",
            "days": ["fr", "mo", "th", "tu", "we"]
        }
    ],
    "cities": ["kzn", "msk", "spb", "sochi"],
    "tariffs": ["standart_offer", "fix_offer_regular", "hourly_offer","daily_offer", "flexible_pack_offer, intercity_offer", "pack_offer"],
    "cars_classes": ["everyday", "everydayplus", "holiday", "cargo", "shuttle"],
    "enable_toll_roads": "true" 
}
```

### Пример тела (body) запроса для задания лимита для сервиса Заправки: {#body-tanker}

```json
{
    "title": "Название лимита",
    "client_id": "id клиента",
    "service": "tanker",
    "limits": {
        "orders_cost": { 
            "value": "818181", 
            "period": "month",
            "kind": "money"
        }
    },
    "time_restrictions": [
        {
            "type": "range_date",
            "start_date": "2022-09-02T00:00:00",
            "end_date": "2022-09-14T00:00:00"
        },
        {
            "type": "weekly_date",
            "start_time": "00:00:00",
            "end_time": "23:59:00",
            "days": ["fr", "mo", "th", "tu", "we"]
        }
    ],
    "geo_restrictions": [
        {
            "source": "e87d178829b24d20b9eba262da5eb966",
            "destination": "3ff4d32ef1074d4ca33c1db61047e06f",
            "prohibiting_restriction": false
        }
    ],
    "fuel_types": [
        "carwash",
        "a80",
        "a92",
        "a95",
        "a98",
        "a100",
        "a92_premium",
        "a95_premium",
        "a98_premium",
        "a100_premium",
        "diesel",
        "diesel_winter",
        "diesel_demiseason",
        "diesel_premium",
        "metan",
        "propane",
        "icefree"
    ] 
}
```

### Пример тела (body) запроса для задания лимита для сервиса Командировки: {#body-travel}

```json
{
  "title": "Название лимита",
  "service": "travel",
  "hotel_policy": {
    "stars": [1, 4, 5],
    "min_price_per_day": 0,
    "max_price_per_day": 10000
  },
  "avia_policy": {
    "classes": ["economy"],
    "extra_baggage": true,
    "aeroexpress": false,
    "countries_restrictions": ["rus"],
    "min_price": 0,
    "max_price": 10000
  },
  "trains_policy": {
    "car_types": [
      "Shared",
      "Soft",
      "Luxury",
      "Compartment",
      "ReservedSeat",
      "Sedentary",
      "Baggage"
    ],
    "refundability": "both",
    "countries": ["rus", "cis"],
    "min_price": 0,
    "max_price": 10000
  },
  "approve_roles": ["client", "department_manager"],
  "limits": {
    "orders_cost": {
      "value": "122000",
      "period": "month"
    }
  },
  "allow_reservations_without_approve": true,
  "taxi_policy": {
    "categories": [
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
    "enable_toll_roads": false,
    "is_enabled": true
  }
}
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
    "id": "3caa...3b05e"
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `401` — был передан неверный [OAuth-токен](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
- `403` — у клиента не хватает прав на выполнение данного запроса. 
  - SELECT_CLIENT_HEADER_REQUIRED: в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED: в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
