---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/promocodes-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/promocodes-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/promocodes-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Список заказов промокодов

Запрос позволяет получить список заказов промокодов.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/promocodes/orders/list?
limit=<количество записей> 
&cursor=<отметка от предыдущего запроса>
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

Запрос должен содержать параметр:

- `limit` — количество выводимых записей.

Запрос может содержать необязательныq параметр:

- `cursor` — отметка запроса (возвращается в теле ответа на предыдущий запрос). Для запроса первой страницы параметр указывать не нужно, для запросов последующих страниц — обязательно.

## Описание полей ответа {#response-description}

В ответе содержатся поля:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `orders` | Список [заказов](#orders). | Массив объектов ||
|| `next_cursor` | Отметка запроса. | Строка ||
|#

Структура элементов массива `orders`: {#orders}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `active_until` | Дата окончания действия промокода. | Строка ||
|| `count` | Количество промокодов в серии. | Число ||
|| `order_id` | Идентификатор заказа. | Строка ||
|| `pricing` | Подробная [информация о цене](#pricing). | Объект ||
|| `service` | Сервис, в котором можно применить промокоды. | Строка ||
|| `status` | Статус заказа. | Строка ||
|| `value` | Номинал одного промокода. | Число ||
|| `revoke_count` | Количество отозванных промокодов в заказе. | Число ||
|| `bin_ranges` | Диапазоны BIN-кодов: каждый элемент содержит начальное и конечное значения. | Массив пар ||
|| `bank_name` | Название банка на русском и английском языках. | Объект ||
|| `classes` | Список тарифных классов, на которые распространяется промокод в Такси. | Массив ||
|| `geo_restrictions` | Географические ограничения для сервисов Такси, Лавка, Еда и Карго. | Массив объектов ||
|| `order_kinds` | Типы заказов на Заправках, на которые распространяется промокод. | Массив строк ||
|| `fuel_types` | Список заправочных типов топлива, на которые распространяется промокод. Указывается только для сервиса «Заправки» (`fuel`). Возможные значения: "a80", "a80_premium", "a92", "a92_premium", "a95", "a95_premium", "a98", "a98_premium", "a100", "a100_premium", "diesel", "diesel_premium", "diesel_winter", "diesel_demiseason", "propane", "metan", "adblue". | Массив ||
|#

Структура элементов объекта `pricing`: {#pricing}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `cost` | Стоимость. | Строка ||
|| `cost_with_vat` | Стоимость с НДС. | Строка ||
|| `currency` | Валюта. | Строка ||
|| `vat` | Значение НДС. | Строка ||
|| `discount` | Скидка. | Объект ||
|#

Структура объекта `discount`: {#discount}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `cost` | Стоимость с учетом скидки. | Строка ||
|| `vat` | НДС с учетом скидки. | Строка ||
|| `cost_with_vat` | Стоимость с НДС с учетом скидки. | Строка ||
|#

Структура объекта `bank_name`: {#bank_name}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `ru` | Название банка на русском языке. | Строка ||
|| `en` | Название банка на английском языке. | Строка ||
|#

Структура элемента массива `geo_restrictions`: {#geo_restrictions}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `source` | Ограничение для точки отправления. | Объект ||
|| `destination` | Ограничение для точки назначения. | Объект ||
|| `max_intermediate_points` | Максимальное количество промежуточных точек. | Число ||
|#

Структура объектов `source` и `destination`: {#point}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `corp_geo_id` | Идентификатор района ограничения. | Строка ||
|| `name` | Название района ограничения. | Строка ||
|| `geo` | Географические данные. | Объект ||
|#

Структура объекта `geo`: {#geo}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `center` | Координаты центра окружности. | Массив чисел ||
|| `radius` | Радиус окружности в метрах. | Число ||
|#

## Пример запроса {#request-example}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/promocodes/orders/list?limit=4
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

```

## Пример ответа {#request-example1}

```json
{
    "next_cursor": "60e...602",
    "orders": [
        {
            "active_until": "2024-12-01",
            "classes": [
                "cargo"
            ],
            "count": 31,
            "order_id": "15b..7746",
            "pricing": {
                "cost": "6820.00",
                "cost_with_vat": "8184.00",
                "currency": "RUB",
                "vat": "0.20"
            },
            "service": "taxi",
            "status": "creation_success",
            "value": 220,
            "revoke_count": 0
        },
        {
            "active_until": "2024-10-31",
            "count": 12,
            "order_id": "895...48b",
            "pricing": {
                "cost": "1476.00",
                "cost_with_vat": "1771.20",
                "currency": "RUB",
                "vat": "0.20"
            },
            "service": "taxi",
            "status": "creation_success",
            "value": 123,
            "revoke_count": 1
        }
    ]
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
