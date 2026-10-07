---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/promocodes-info.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/promocodes-info.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/promocodes-info.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получение информации о заказе промокодов

Запрос позволяет получить подробную информацию о заказе.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/promocodes/orders/info?order_id={идентификатор заказа}
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

Запрос содержит обязательный параметр:

* `order_id` — идентификатор заказа.

## Описание полей ответа {#response-description}

В ответе содержатся поля:

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
|| `classes` | Список тарифных классов, на которые распространяется промокод. | Массив строк ||
|| `order_kinds` | Типы заказов на Заправках, на которые распространяется промокод. | Массив строк ||
|| `fuel_types` | Типы топлива, на которые распространяется промокод. | Массив строк ||
|| `geo_restrictions` | Информация о [географических ограничениях](#geo_restrictions). | Массив объектов ||
|#

Структура объекта `pricing`: {#pricing}

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

Структура элементов массива `geo_restrictions`: {#geo_restrictions}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `destination` | [Географические ограничения](#point) точки назначения. | Объект ||
|| `source` | [Географические ограничения](#point) точки отправления. | Объект ||
|| `max_intermediate_points` | Максимальное число промежуточных точек. | Число ||
|#

Структура объектов `destination` и `source`: {#point}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `corp_geo_id` | Идентификатор района ограничения. | Строка ||
|| `geo` | [Географические данные](#geo). | Объект ||
|| `name` | Название района ограничения. | Строка ||
|#

Структура объекта `geo`: {#geo}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `center` | Координаты центра окружности. | Массив ||
|| `radius` | Радиус окружности с точкой `center`, в которой действуют ограничения. Указывается в метрах. | Число ||
|#

## Пример запроса {#request-example}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/promocodes/orders/info?order_id=017...5dd
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#request-example}

```json
{
  "active_until": "2024-12-31",
  "count": 30,
  "geo_restrictions": [
    {
      "destination": {
        "corp_geo_id": "91d...a3c",
        "geo": {
          "center": [ 55.754572, 37.621182 ],
          "radius": 200
        },
        "name": "Финиш"
      },
      "max_intermediate_points": 2,
      "source": {
        "corp_geo_id": "be9...d4a",
        "geo": {
          "center": [ 55.754572, 37.621182 ],
          "radius": 200
        },
        "name": "Старт"
      }
    }
  ],
  "order_id": "017...5dd",
  "pricing": {
    "cost": "6600.00",
    "cost_with_vat": "7920.00",
    "currency": "RUB",
    "vat": "0.20"
  },
  "service": "taxi",
  "status": "creation_success",
  "value": 220,
  "revoke_count": 0
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `404` — заказ не найден.
