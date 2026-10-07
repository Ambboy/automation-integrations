---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/promocodes-codes-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/promocodes-codes-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/promocodes-codes-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Список промокодов в заказе

Запрос позволяет получить список промокодов по конкретному заказу.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/promocodes/orders/codes/list?order_id=<идентификатор заказа>
&limit=<количество записей> 
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

Запрос содержит обязательный параметр:

- `order_id` — идентификатор заказа.

Запрос может содержать следующие необязательные параметры:

- `limit` — количество выводимых записей. При отсутствии данного параметра возвращается информация о первых 100 записях.
- `cursor` — отметка запроса (возвращается в теле ответа на предыдущий запрос). Для запроса первой страницы параметр указывать не нужно, для запросов последующих страниц — обязательно.

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

#| 
|| **Поле** | **Описание** | **Формат** ||
|| `codes` | Список [промокодов](#codes) в одном конкретном заказе. | Массив объектов ||
|| `next_cursor` | Курсор следующей страницы. | Строка ||
|#

Структура элементов массива `codes`: {#codes}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `code` | Промокод. | Строка ||
|| `id` | Идентификатор промокода. | Строка ||
|| `status` | Статус промокода. | Строка ||
|| `is_revoked` | Признак того, что промокод был отозван. | Булево ||
|| `usages` | Список [использований](#usages). | Массив объектов ||
|#

Структура элементов массива `usages`: {#usages}

#|
|| **Поле** | **Описание** | **Формат** ||
|| `used_at` | Дата использования промокода в формате `datetime`. | Строка ||
|#

## Пример запроса {#request-example}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/promocodes/orders/codes/list?order_id=fa0...6f3
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#response-example}

```json
{
  "codes": [
    {
      "code": "b2b...862",
      "id": "e6z...60b",
      "status": "used",
      "usages": [
        {
          "used_at": "2024-10-29T14:31:57.803131Z"
        }
      ]
    },
    {
      "code": "b2b...397",
      "id": "ca5...b30",
      "status": "active",
      "usages": []
    }
  ]
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `403` — у клиента не хватает прав на выполнение данного запроса. 
  - SELECT_CLIENT_HEADER_REQUIRED: в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED: в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `404` — заказ не найден.
