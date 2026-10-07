---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/order-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Список заказов клиента

Запрос позволяет получить список заказов клиента. Список можно отфильтровать по идентификатору пользователя.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/orders/list?
limit=<количество записей>
&offset=<количество пропускаемых записей>
&user_id=<идентификатор пользователя>
&sorting_field={due_date|finished_date}
&sorting_direction={1|-1}
&since_datetime=<начальная_дата>
&till_datetime=<конечная_дата>
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

Запрос может содержать следующие необязательные параметры:
    
- `limit` — количество выводимых записей. При отсутствии данного параметра возвращается информация о первых 100 записях.

- `offset` — количество пропускаемых записей. При отсутствии данного параметра возвращается информация начиная с первой записи.

- `user_id` — идентификатор пользователя, по которому фильтруется список заказов. Если параметр не передан, возвращаются заказы всех пользователей выбранного клиента.

- `sorting_field` — поле, по которому сортируется возвращаемый список заказов. Может принимать значения: `due_date` - по дате начала заказа (значение по умолчанию), `finished_date` - по дате окончания заказа. 

- `sorting_direction` — направление сортировки возвращаемого списка заказов. Может принимать значения: 1 - по возрастанию, -1 - по убыванию (значение по умолчанию).

- `since_datetime` — Начальное время для фильтрации. Формат значений: `YYYY-MM-DDThh:mm:ss±hh:mm`.

- `till_datetime` — Конечное время для фильтрации. Формат значений: `YYYY-MM-DDThh:mm:ss±hh:mm`.

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`items` | [Список заказов клиента](#items). | Массив объектов
`limit` | Максимальное количество возвращаемых записей. | Число
`offset` | Количество пропускаемых записей. | Число
`total_amount` | Общее количество заказов, соответствующих параметрам запроса. | Число

Структура элемента массива `items`: {#items}

Поле | Описание | Формат
----- | ----- | -----
`id` | Идентификатор заказа. | Строка
`user_id` | Идентификатор пользователя. | Строка
`class` | Наименование тарифа. | Строка
`status` | Статус заказа. | Строка
`source` | [Начальная точка маршрута](#source-destination). | Объект
`interim_destinations` | [Промежуточные точки маршрута](#source-destination). | Массив объектов
`destination` | [Конечная точка маршрута](#source-destination). | Объект
`cost_center_values` | Новые поля центра затрат. | Массив объектов 
`due_date` | Время начала заказа. Формат значения: `YYYY-MM-DDThh:mm:ss±hh:mm` | Строка
`finished_date` | Время окончания заказа. Возвращается только для завершенного заказа. Формат значения: `YYYY-MM-DDThh:mm:ss±hh:mm` | Строка
`cost` | Стоимость без НДС.  Возвращается только для завершенного заказа. | Число
`cost_with_vat` | Стоимость с НДС.  Возвращается только для завершенного заказа. | Число

Структура объекта `source-destination`: {#source-destination}

Поле | Описание | Формат
----- | ----- | -----
`fullname` | Название точки. | Строка
`geopoint` | Массив из двух значений, задающих долготу и широту точки. | Массив
`porchnumber` | Номер подъезда. | Строка
`locale` | Локаль адреса. | Строка

Структура элемента массива `cost_center_values`: {#cost_center_values}

Поле | Описание | Формат  
----- | ----- | -----
`id` | id поля центра затрат. | Строка 
`title` | Название поля центра затрат. | Строка 
`value` | Новое значение поля. | Строка 

## Пример запроса {#request-example}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/orders/list?limit=5&offset=0&sorting_field=due_date&sorting_direction=1
...
Authorization: <OAuth-токен>
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
  "items": [
    {
      "id": "507...1db",
      "user_id": "035...c71",
      "status": "cancelled",
      "class": "business",
      "source": {
        "fullname": "Москва, улица Новая Башиловка, 10",
        "geopoint": [
          37.56997813720699,
          55.78798846490584
        ]
      },
      "destination": {
        "fullname": "Москва, Садовая-Кудринская улица, 15с9",
        "geopoint": [
          37.58542766113278,
          55.76496146265227
        ]
      },
      "cost_center_values": [
        {
          "id": "cost_center",
          "title": "Цель поездки",
          "value": ""
        }
      ],
      "due_date": "2023-02-08T10:54:41+03:00",
      "finished_date": "2023-02-08T10:51:37.759000+03:00",
      "cost": 0,
      "cost_with_vat": 0
    },
    {
      "id": "b99...dc17",
      "user_id": "035...c71",
      "status": "complete",
      "class": "business",
      "source": {
        "fullname": "Москва, Большая Садовая улица, 14с9",
        "geopoint": [
          37.59538402099606,
          55.76728413277445
        ]
      },
      "destination": {
        "fullname": "Москва, Коробейников переулок, 1",
        "geopoint": [
          37.5998472167968,
          55.73785337560665
        ]
      },
      "cost_center_values": [
        {
          "id": "9af...12a",
          "title": "Цель поездки",
          "value": "по работе"
        }
      ],
      "due_date": "2023-02-08T17:50:36+03:00",
      "finished_date": "2023-02-08T17:56:17.442000+03:00",
      "cost": 345,
      "cost_with_vat": 414
    }
  ],
  "limit": 5,
  "offset": 0,
  "total_amount": 2
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `403` — недостаточно данных или прав для выбора клиента:
  - `SELECT_CLIENT_HEADER_REQUIRED` — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - `SELECTED_CLIENT_ACCESS_DENIED` — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
