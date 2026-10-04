---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/users-spending-details.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/users-spending-details.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/users-spending-details.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Детализация затрат сотрудников

Запрос позволяет получить детализацию затрат сотрудников, совершенных в рамках их лимитов. Если на момент совершения траты для сотрудника не был установлен лимит, информация по данной трате не будет передана.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/users-spending-details
```

**Заголовки запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->
 

**Тело запроса**

Список сотрудников, по которым запрашивается детализация затрат, передается в теле запроса в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `user_ids` | Массив с идентификаторами сотрудников (не более 100) | Массив строк | Да||
|#

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

#|
||**Поле** | **Описание** | **Формат**||
||`users` | [Список сотрудников](#users). | Массив||
|#

Структура элемента массива `users`: {#users}

#|
||**Поле** | **Описание** | **Формат**||
||`limits` | [Информация о лимитах](#limits). | Массив||
||`user_id` | Идентификатор сотрудника. | Строка||
|#

Структура элемента массива `limits`: {#limits}

#|
||**Поле** | **Описание** | **Формат**||
||`limit_id` | Идентификатор лимита.| Строка ||
||`service` | Название сервиса лимита. Возможные значения: `taxi`, `eats2`, `drive`, `tanker`, `grocery`.| Строка ||
||`spending_details` | [Данные по тратам сотрудников](#spending-details). | Объект ||
|#

Объект `spending_details`: {#spending-details}

#|
||**Поле** | **Описание** | **Формат**||
||`orders_cost` | Ограничения лимита по тратам. | Строка||
||`spent` | Сумма, потраченная сотрудником по данному лимиту за текущий период. | Строка||
||`orders_amount` | Ограничение на количество поездок, которые сотрудник может совершить за период. Указывается только для сервиса `taxi`.| Целое число||
||`orders_spent` | Количество совершенных заказов за текущий период. | Целое число||
||`nested_spendings` | Траты по вложенным лимитам. Ключ объекта — идентификатор сервиса; значение содержит поля `spent` и `orders_spent`. | Объект||
|#

## Примеры запросов {#request-example}

```
POST url https://b2b-api.go.yandex.ru/integration/2.0/users-spending-details 
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

  { "user_ids": [
      "26e8...3f62", 
      "5758...0ede"
    ]
  }
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
  "users": [
    {
      "limits": [
        {
          "limit_id": "f81ea...9c6a2",
          "service": "drive",
          "spending_details": {
            "orders_cost": "10000",
            "spent": "0",
            "orders_spent": 0
          }
        },
        {
          "limit_id": "64f1...3fb8",
          "service": "eats2",
          "spending_details": {
            "orders_cost": "147614.40",
            "spent": "0",
            "orders_spent": 0
          }
        }
      ],
      "user_id": "26e8...3f62"
    },
    {
      "limits": [
        {
          "limit_id": "8062...d071",
          "service": "taxi",
          "spending_details": {
            "orders_cost": "10000",
            "spent": "3894",
            "orders_amount": 5,
            "orders_spent": 2
          }
        },
        {
          "limit_id": "794e...30c4",
          "service": "eats2",
          "spending_details": {
            "orders_cost": "3600",
            "spent": "0",
            "orders_spent": 0
          }
        },
        {
          "limit_id": "1cd7...33cc",
          "service": "drive",
          "spending_details": {
            "orders_cost": "12331",
            "spent": "10000",
            "orders_spent": 8
          }
        },
        {
          "limit_id": "7f5d...282c",
          "service": "tanker",
          "spending_details": {
            "orders_cost": "8765",
            "spent": "5478",
            "orders_spent": 3
          }
        }
      ],
      "user_id": "5758...0ede"
    }
  ]
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
