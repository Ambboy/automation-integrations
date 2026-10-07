---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/change-destinations.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/change-destinations.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/change-destinations.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Изменение маршрута

Дает возможность изменить точки маршрута, кроме начальной. Для этого в теле запроса необходимо указать `destinations` (точки маршрута без начальной точки) и `created_time` (UTC-время создания изменения).

## Синтаксис запроса {#request-syntax}

```
POST http://b2b-api.go.yandex.ru/integration/2.0/orders/change-destinations?order_id={идентификатор заказа}
```

**Заголовки запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->

- `Accept-Language` — выбор языка в формате строки (ru, en, fr, hy, he и т.п.).

**Параметры запроса**

Запрос содержит обязательный параметр:
    
- `order_id` — идентификатор заказа, для которого меняется маршрут.

**Тело запроса**

Данные об измененном маршруте передаются в формате JSON:

Поле | Описание | Формат | Обязательность
----- | ----- | ----- | -----
`created_time` | UTC-время создания изменения. Формат значений: `YYYY-MM-DDThh:mm:ss±hh:mm`. | Строка | Да
`destinations` | [Точки измененного маршрута](#destinations), кроме начальной точки. | Массив объектов | Да

Структура элемента массива `destinations`: {#destinations}

Поле | Описание | Формат
----- | ----- | -----
`geopoint` | Массив из двух значений, задающих долготу и широту точки. | Массив 
`fullname` | Адрес точки. | Строка 

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`changed_destinations` | [Измененный маршрут](#changed_destinations). | Массив объектов 

Структура объекта `changed_destinations`: {#changed_destinations}

Поле | Описание | Формат
----- | ----- | -----
`geopoint` | Массив из двух значений, задающих долготу и широту точки. | Массив 
`fullname` | Адрес точки. | Строка 
`country` | Страна. | Строка 
`locality` | Город. | Строка 
`premisenumber` | Номер здания. | Строка 
`thoroughfare` | Улица. | Строка 

## Пример запроса {#request-example}

```
POST http://b2b-api.go.yandex.ru/integration/2.0/orders/change-destinations?order_id=31c...1fc6
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
Accept-Language: ru

  {
    "created_time": "2022-02-09T22:50:34",
    "destinations": [
      {
        "geopoint": [
          37.600296,
          55.750379
        ],
        "fullname": "Гоголевский бульвар, 31с1"
      }
    ]
  }
```

## Пример ответа {#response-example}

Пример ответа  на данный запрос выглядит следующим образом:

```json
{
  "changed_destinations": [
    {
      "fullname": "Москва, Гоголевский бульвар, 31с1",
      "geopoint": [
        37.600296,
        55.750379
      ],
      "country": "Россия",
      "locality": "Москва",
      "premisenumber": "31с1",
      "thoroughfare": "Гоголевский бульвар"
    }
  ]
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `404` — заказ не найден.
- `409` — пункт назначения уже был изменен клиентом (или водителем) с более поздним `created_time`.
