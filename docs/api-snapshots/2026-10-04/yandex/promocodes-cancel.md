---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/promocodes-cancel.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/promocodes-cancel.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/promocodes-cancel.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Отмена заказа промокодов

Запрос позволяет отменить заявку на создание серии промокодов.

{% note info %}

Отменить серию промокодов можно только в том случае, если не один промокод из этого заказа не был использован.

{% endnote %}

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/promocodes/orders/cancel?order_id={идентификатор заказа}
```

**Заголовок запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->
 

**Параметры запроса**

Запрос содержит обязательный параметр:

- `order_id` — идентификатор отменяемого заказа. 

## Описание полей ответа {#response-description}

В ответе содержится поле:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `status` | Статус заказа. | Строка ||
|#

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/promocodes/orders/cancel?order_id=099...4e48
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#response-example}

```json
{
    "status": "cancelled"
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
- `409` — произошел конфликт.