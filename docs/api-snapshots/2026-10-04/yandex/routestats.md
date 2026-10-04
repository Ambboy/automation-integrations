---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/routestats.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/routestats.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/routestats.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получить информацию о предстоящей поездке

Запрос позволяет узнать предварительную стоимость поездки для разных тарифов и создать оффер на поездку. Передаются координаты точек маршрута `routes`, id сотрудника `user_id`, дополнительные условия `requirements`.
Если передан `user_id` и длина `route` >= 2, то должен вернуться оффер, который далее будет передаваться в запрос на [создание заказа](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-create.md).

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/orders/routestats
```

**Заголовки запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->
 
- `Accept-Language` — выбор языка в формате строки (ru, en, fr, hy, he и т.п.)

**Тело запроса**

Данные передаются в теле запроса в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `route` | Блок информации о маршруте поездки. Координаты поездки указываются в формате: 
```
[
  [<долгота точки отправления>,<широта точки отправления>],
  [<долгота точки назначения>,<широта точки назначения>]
]
```
| Массив | Да||
|| `requirements` | Список требований к поездке. Может варьироваться в зависимости от города. Чтобы узнать поддерживаемые требования, воспользуйтесь запросом [GET /zoneinfo](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/zone-info.md). В ответе в массиве `supported_requirements` будут перечислены варианты, доступные для этой геозоны. | Объект | Нет||
|| `user_id` | Идентификатор сотрудника. | Строка | Нет||
|| `use_toll_roads` | Возможность использовать платные дороги. По умолчанию `false`. | Логическое | Нет||
|#
    
## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`offer` | Идентификатор оффера. | Строка
`service_levels`| [Список тарифов](#service_levels) с их описанием. | Массив объектов
`toll_roads`| [Платные дороги](#toll_roads). | Объект

Структура элемента массива `service_levels`: {#service_levels}

Поле | Описание | Формат
----- | ----- | -----
`class` | Категория тарифа. | Строка
`is_fixed_price` | Признак фиксированной цены. | Логическое
`price` | Ориентировочная стоимость поездки. | Строка
`estimated_waiting`| [Предполагаемое ожидание](#estimated_waiting). | Объект
`details_tariff` |  [Описание](#details_tariff) составляющих минимального тарифа.  | Массив объектов

Структура объекта `estimated_waiting`: {#estimated_waiting}

Поле | Описание | Формат
----- | ----- | -----
`seconds` | Время ожидания в секундах. | Число
`message` | Время в текстовом формате. | Строка

Структура элемента массива `details_tariff`: {#details_tariff}

Поле | Описание | Формат
----- | ----- | -----
`type` | Тип составляющей. | Строка
`value` | Описание составляющей. | Строка
`type_details` | Детали о типе составляющей (например, название опции). | Строка

Структура объекта `toll_roads`: {#toll_roads}

Поле | Описание | Формат
----- | ----- | -----
`has_tolls` | Наличие платных дорог в маршруте. |  Логическое
`auto_payment` | Автоматическое списание оплаты за проезд по платной дороге. Равно `true`, если платная дорога доступна для автооплаты и у клиента включена возможность оплаты платных дорог. |  Логическое
`price` | Приблизительная стоимость проезда по платной дороге, если ее удалось рассчитать. | Строка

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/orders/routestats
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

  {
    "route": [
        [
          37.593983,
          55.738759
        ],
        [
          37.609479,
          55.746943
        ]
    ],
    "user_id": "035...3c71",
    "use_toll_roads": true,
    "requirements": {
      "conditioner": true, 
      "yellowcarnumber": true
    }
  }
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
  "offer": "06f...f7da",
  "service_levels": [
    {
      "class": "comfortplus",
      "is_fixed_price": true,
      "price": "290 руб.",
      "details_tariff": [
        {
          "type": "price",
          "value": "от 219 руб."
        },
        {
          "type": "icon",
          "value": "от 219 руб."
        },
        {
          "type": "comment",
          "value": "включено 5 мин., далее 14,3 руб./мин."
        },
        {
          "type": "comment",
          "value": "включено 0 км, далее 14,3 руб./км"
        }
      ]
    },
    {
      "class": "cargo",
      "is_fixed_price": true,
      "price": "1120 руб.",
      "estimated_waiting": {
        "seconds": 300,
        "message": "5 мин"
      },
      "details_tariff": [
        {
          "type": "price",
          "value": "от 1044 руб."
        },
        {
          "type": "icon",
          "value": "от 1044 руб."
        },
        {
          "type": "comment",
          "value": "включено 5 мин., далее 14,3 руб./мин."
        },
        {
          "type": "comment",
          "value": "включено 0 км, далее 14,3 руб./км"
        }
      ]
    },
    {
      "class": "econom",
      "is_fixed_price": true,
      "price": "250 руб.",
      "estimated_waiting": {
        "seconds": 240,
        "message": "4 мин"
      },
      "details_tariff": [
        {
          "type": "price",
          "value": "от 166 руб."
        },
        {
          "type": "icon",
          "value": "от 166 руб."
        },
        {
          "type": "comment",
          "value": "включено 2 мин., далее 9,9 руб./мин."
        },
        {
          "type": "comment",
          "value": "включено 1 км, далее 9,9 руб./км"
        }
      ]
    },
    {
      "class": "maybach",
      "is_fixed_price": true,
      "price": "2030 руб.",
      "estimated_waiting": {
        "seconds": 240,
        "message": "4 мин"
      },
      "details_tariff": [
        {
          "type": "price",
          "value": "от 1100 руб."
        },
        {
          "type": "icon",
          "value": "от 1100 руб."
        },
        {
          "type": "comment",
          "value": "включено 1 мин., далее 110 руб./мин."
        },
        {
          "type": "comment",
          "value": "включено 1 км, далее 110 руб./км"
        }
      ]
    },
    {
      "class": "express",
      "is_fixed_price": true,
      "price": "210 руб.",
      "estimated_waiting": {
        "seconds": 300,
        "message": "5 мин"
      },
      "details_tariff": [
        {
          "type": "price",
          "value": "от 175 руб."
        },
        {
          "type": "icon",
          "value": "от 175 руб."
        },
        {
          "type": "comment",
          "value": "включено 5 мин., далее 9,9 руб./мин."
        },
        {
          "type": "comment",
          "value": "включено 3 км, далее 11 руб./км"
        }
      ]
    },
    {
      "class": "business",
      "is_fixed_price": true,
      "price": "260 руб.",
      "estimated_waiting": {
        "seconds": 240,
        "message": "4 мин"
      },
      "details_tariff": [
        {
          "type": "price",
          "value": "от 219 руб."
        },
        {
          "type": "icon",
          "value": "от 219 руб."
        },
        {
          "type": "comment",
          "value": "включено 5 мин., далее 13,2 руб./мин."
        },
        {
          "type": "comment",
          "value": "включено 2 км, далее 13,2 руб./км"
        }
      ]
    },
    {
      "class": "child_tariff",
      "is_fixed_price": true,
      "price": "180 руб.",
      "details_tariff": [
        {
          "type": "price",
          "value": "от 109 руб."
        },
        {
          "type": "icon",
          "value": "от 109 руб."
        },
        {
          "type": "comment",
          "value": "включено 1 мин., далее 12,1 руб./мин."
        },
        {
          "type": "comment",
          "value": "включено 2 км, далее 12,1 руб./км"
        }
      ]
    },
    {
      "class": "vip",
      "is_fixed_price": true,
      "price": "230 руб.",
      "details_tariff": [
        {
          "type": "price",
          "value": "от 110 руб."
        },
        {
          "type": "icon",
          "value": "от 110 руб."
        },
        {
          "type": "comment",
          "value": "подача,"
        },
        {
          "type": "comment",
          "value": "далее 11 руб./км и 12,1 руб./мин."
        }
      ]
    },
    {
      "class": "ultimate",
      "is_fixed_price": true,
      "price": "120 руб.",
      "details_tariff": [
        {
          "type": "price",
          "value": "от 110 руб."
        },
        {
          "type": "icon",
          "value": "от 110 руб."
        },
        {
          "type": "comment",
          "value": "подача,"
        },
        {
          "type": "comment",
          "value": "далее 1,1 руб./км и 1,1 руб./мин."
        }
      ]
    }
  ],
  "toll_roads": {
    "has_tolls": true,
    "auto_payment": false
  }
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `404` — зона не найдена.
