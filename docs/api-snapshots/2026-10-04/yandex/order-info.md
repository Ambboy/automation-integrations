---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/order-info.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-info.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-info.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Информация о заказе

Запрос позволяет получить информацию о заказе.

## Синтаксис запроса {#request-syntax}

```
GET http://b2b-api.go.yandex.ru/integration/2.0/orders/info?order_id={идентификатор заказа}
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
    
- `order_id` — идентификатор заказа, по которому предоставляется информация.

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`id` | Идентификатор заказа. | Строка
`user_id` | Идентификатор пользователя. | Строка
`class` | Наименование тарифа. | Строка
`status` | Статус заказа. | Строка
`due_date` | Дата и время начала поездки. Формат значения: `YYYY-MM-DDThh:mm:ss±hh:mm` | Строка
`finished_date` | Дата и время окончания поездки. Возвращается только для завершенного заказа. Формат значения: `YYYY-MM-DDThh:mm:ss±hh:mm` | Строка
`performer` | [Информация о машине и водителе](#performer). | Объект
`source` | [Начальная точка маршрута](#source-destination). | Объект
`interim_destinations` | [Промежуточные точки маршрута](#source-destination). | Массив объектов
`destination` | [Конечная точка маршрута](#source-destination). | Объект
`cancel_rules` | [Правила отмены заказа](#cancel_rules). | Объект
`cost` | Стоимость поездки и проезда по платной дороге (если таковая была в заказе) без НДС. Возвращается только для завершенного заказа. | Число
`cost_with_vat` | Стоимость поездки и проезда по платной дороге (если таковая была в заказе) с НДС.  Возвращается только для завершенного заказа. | Число
`cost_center_values` | [Новые поля центров затрат](#cost_center_values). | Массив объектов 
`toll_roads` | [Платные дороги](#toll_roads). | Объект 

Структура элемента массива `performer`: {#performer}

Поле | Описание | Формат
----- | ----- | -----
`vehicle` | [Информация об автомобиле](#vehicle). | Объект
`fullname` | ФИО водителя. | Строка
`phone` | Номер телефона водителя. | Строка

Структура объекта `vehicle`: {#vehicle}

Поле | Описание | Формат  
----- | ----- | -----
`model` | Наименование модели автомобиля. | Строка 
`number` | Номер автомобиля. | Строка 
`color` | Цвет автомобиля. | Строка 

Структура объекта `source-destination`: {#source-destination}

Поле | Описание | Формат
----- | ----- | -----
`fullname` | Название точки. | Строка
`geopoint` | Массив из двух значений, задающих долготу и широту точки. | Массив
`porchnumber` | Номер подъезда. | Строка
`locale` | Локаль адреса. | Строка

Структура объекта `cancel_rules`: {#cancel_rules}

Поле | Описание | Формат  
----- | ----- | -----
`can_cancel` | Наличие или отсутствие возможности отмены заказа. | Логическое
`message` | Текстовое описание правил отмены заказа. | Строка 
`state` | Актуальный статус возможности отмены заказа. | Строка 
`title` | Название правила отмены. | Строка 

Структура элемента массива `cost_center_values`: {#cost_center_values}

Поле | Описание | Формат  
----- | ----- | -----
`id` | id поля центра затрат. | Строка 
`title` | Название поля центра затрат. | Строка 
`value` | Новое значение поля. | Строка 

Структура объекта `toll_roads`: {#toll_roads}

Поле | Описание | Формат  
----- | ----- | -----
`user_chose_toll_road` | Пользователь выбрал платную дорогу. | Логическое 
`user_had_choice` | Пользователь имел выбор (была бесплатная альтернатива). | Логическое 
`auto_payment` | Оплата платной дороги за корпоративный счет. | Логическое 

## Пример запроса {#request-example}

```
GET http://b2b-api.go.yandex.ru/integration/2.0/orders/info?order_id=885...7f2e
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#response-example}

Пример ответа для активного заказа:

```json
{
  "id": "885e440dc70acc3bb6ce0cc5c67d7f2e",
  "user_id": "5769a1d0ed084122a5ff50d67941edc8",
  "class": "econom",
  "status": "driving",
  "due_date": "2023-02-10T10:54:55+03:00",
  "performer": {
    "vehicle": {
      "model": "Nissan Qashqai",
      "number": "В746УО777",
      "color": "зеленый"
    },
    "fullname": "Сазонов Станимир Матвеевич",
    "phone": "+79120995513,,95576"
  },
  "source": {
    "fullname": "Москва, Зоологическая улица, 28с1",
    "geopoint": [
      37.58508433837886,
      55.76631637044709
    ]
  },
  "destination": {
    "fullname": "Москва, улица Годовикова, 9с1",
    "geopoint": [
      37.62525310058589,
      55.80713497241309
    ]
  },
  "cancel_rules": {
    "can_cancel": true,
    "message": "Сейчас отмена бесплатна. После приезда водителя за нее, возможно, придется заплатить",
    "state": "free",
    "title": "Бесплатная отмена"
  },
  "cost_center_values": [
    {
      "id": "cost_center",
      "title": "Цель поездки",
      "value": ""
    }
  ],
  "toll_roads": {
    "user_chose_toll_road": true,
    "user_had_choice": true,
    "auto_payment": true
  }
}
```
Пример ответа для завершенного заказа:

```json
{
  "id": "885e440dc70acc3bb6ce0cc5c67d7f2e",
  "user_id": "5769a1d0ed084122a5ff50d67941edc8",
  "class": "econom",
  "status": "complete",
  "due_date": "2023-02-10T10:54:55+03:00",
  "finished_date": "2023-02-10T11:14:16.037000+03:00",
  "performer": {
    "vehicle": {
      "model": "Nissan Qashqai",
      "number": "В746УО777",
      "color": "зеленый"
    },
    "fullname": "Сазонов Станимир Матвеевич"
  },
  "source": {
    "fullname": "Москва, Зоологическая улица, 28с1",
    "geopoint": [
      37.58508433837886,
      55.76631637044709
    ]
  },
  "destination": {
    "fullname": "Москва, улица Годовикова, 9с1",
    "geopoint": [
      37.62525310058589,
      55.80713497241309
    ]
  },
  "cost": 2188,
  "cost_with_vat": 2625.6,
  "cost_center_values": [
    {
      "id": "cost_center",
      "title": "Цель поездки",
      "value": ""
    }
  ],
  "toll_roads": {
    "user_chose_toll_road": true,
    "user_had_choice": true,
    "auto_payment": true
  }
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `404` — запрашиваемая запись не найдена.
