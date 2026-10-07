---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/food-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/food-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/food-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получить список заказов в сервисе «Еда»

Запрос позволяет получить список заказов в сервисах «Еда» и «Лавка» с фильтрацией и пагинацией.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/orders/eats/list?limit=<количество заказов>&cursor=<курсор>
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

- `limit` — количество выводимых заказов. При отсутствии данного параметра возвращается информация о первых 150 заказах.
- `cursor` — отметка запроса (возвращается в теле ответа на предыдущий запрос). Для запроса первой страницы параметр указывать не нужно, для запросов последующих страниц — обязательно

**Тело запроса**

Данные передаются в теле запроса в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `user_ids` | Массив идентификаторов сотрудников, сделавших заказы. | Массив | Нет||
|#
    
## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`cursor` | Отметка текущего запроса. | Строка
`limit` | Максимальное количество возвращаемых записей.	 | Число
`orders`| [Список заказов](#orders) с их описанием. | Массив объектов
`sorting_order` | Направление сортировки массива заказов (по дате создания заказа). | Строка

Структура элемента массива `orders`: {#orders}

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `id` | Идентификатор заказа. | Строка | Да ||
|| `user_id` | Идентификатор пользователя. | Строка | Да ||
|| `department_id` | Идентификатор департамента. | Строка | Нет ||
|| `status` | Статус заказа. | Строка | Да ||
|| `created_at` | Дата и время создания заказа. | Строка в формате даты и времени | Да ||
|| `closed_at` | Дата и время завершения заказа. | Строка в формате даты и времени | Нет ||
|| `restaurant_name` | Название ресторана. | Строка | Нет ||
|| `destination_address` | Адрес доставки. | Строка | Нет ||
|| `destination_city` | Город доставки. | Строка | Нет ||
|| `order_calculation` | Состав и расчет заказа. | Массив объектов | Нет ||
|| `final_cost` | Итоговая стоимость заказа в ресторане/магазине без НДС. | Строка | Нет ||
|| `vat` | НДС стоимости заказа в ресторане/магазине. | Строка | Нет ||
|| `final_cost_with_vat` | Итоговая стоимость заказа в ресторане/магазине с НДС. | Строка | Нет ||
|| `corp_discount` | Корпоративная скидка. | Объект | Нет ||
|| `corp_discount_reverted` | Признак отмены корпоративной скидки. | Булево | Нет ||
|| `currency` | Валюта. | Строка | Нет ||
|| `eats_cost_centers` | Значения центров затрат. | Массив объектов | Нет ||
|| `commission` | Комиссия без НДС. | Строка | Нет ||
|| `commission_vat` | НДС комиссии. | Строка | Нет ||
|| `commission_with_vat` | Комиссия с НДС. | Строка | Нет ||
|#

Структура элемента массива `order_calculation`: {#order-calculation}

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `name` | Название позиции. | Строка | Да ||
|| `cost` | Стоимость без НДС. | Строка | Да ||
|| `vat` | НДС. | Строка | Да ||
|| `cost_with_vat` | Стоимость с НДС. | Строка | Да ||
|| `modifiers` | Модификаторы позиции. | Массив объектов | Нет ||
|| `count` | Количество. | Целое число | Нет ||
|#

Структура элемента массива `modifiers`: {#modifiers}

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `name` | Название модификатора. | Строка | Да ||
|| `cost` | Стоимость без НДС. | Строка | Да ||
|| `vat` | НДС. | Строка | Да ||
|| `cost_with_vat` | Стоимость с НДС. | Строка | Да ||
|| `count` | Количество. | Целое число | Нет ||
|#

Структура объекта `corp_discount`: {#corp-discount}

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `sum` | Сумма скидки без НДС. | Строка | Да ||
|| `vat` | НДС скидки. | Строка | Да ||
|| `with_vat` | Сумма скидки с НДС. | Строка | Да ||
|| `sales_tax` | Налог с продаж. | Строка | Нет ||
|| `total` | Итоговая сумма скидки. | Строка | Нет ||
|#

Структура элемента массива `eats_cost_centers`: {#eats-cost-centers}

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `id` | Идентификатор поля центра затрат. | Строка | Да ||
|| `title` | Название поля центра затрат. | Строка | Да ||
|| `value` | Значение поля центра затрат. | Строка | Да ||
|#

## Пример запроса {#request-example}

Первый запрос:

```
POST https://b2b-api.go.yandex.ru/integration/2.0/orders/eats/list?limit=2
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

  {
    "user_ids": [
        "b201...a4bc"
    ]
  }
```

Последующие запросы:

```
POST https://b2b-api.go.yandex.ru/integration/2.0/orders/eats/list?limit=2&cursor=djEg...M3OT
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

  {
    "user_ids": [
        "b201...a4bc"
    ]
  }
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
    "cursor": "1676209440.0-230212-6600939",
    "limit": 2,
    "orders": [
        {
            "id": "230218-1509473",
            "user_id": "b201...a4bc",
            "status": "delivered",
            "created_at": "2023-02-18T11:42:10+03:00",
            "closed_at": "2023-02-18T12:42:45+03:00",
            "restaurant_name": "Zotman Pizza",
            "destination_address": "Мясницкая улица, 40А",
            "order_calculation": [
                {
                    "name": "Цыпленок с песто",
                    "cost": "590.",
                    "vat": "118.0000",
                    "cost_with_vat": "708.0000",
                    "modifiers": [],
                    "count": 1
                },
                {
                    "name": "Доставка",
                    "cost": "59.",
                    "vat": "11.8000",
                    "cost_with_vat": "70.8000"
                }
            ],
            "final_cost": "688.0000",
            "vat": "137.6000",
            "final_cost_with_vat": "825.6000",
            "currency": "RUB"
        },
        {
            "id": "230212-6600939",
            "user_id": "b201...a4bc",
            "status": "delivered",
            "created_at": "2023-02-12T19:44:00+03:00",
            "closed_at": "2023-02-12T20:59:54+03:00",
            "restaurant_name": "Лепим и варим",
            "destination_address": "Мясницкая улица, 40А",
            "order_calculation": [
                {
                    "name": "Классика жанра большая порция",
                    "cost": "430.",
                    "vat": "86.0000",
                    "cost_with_vat": "516.0000",
                    "modifiers": [],
                    "count": 1
                },
                {
                    "name": "Доставка",
                    "cost": "223.",
                    "vat": "44.6000",
                    "cost_with_vat": "267.6000"
                }
            ],
            "final_cost": "692.0000",
            "vat": "138.4000",
            "final_cost_with_vat": "830.4000",
            "currency": "RUB"
        }
    ],
    "sorting_order": "desc"
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
