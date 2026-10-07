---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/order-feedback.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-feedback.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-feedback.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Оставить отзыв водителю

Есть возможность поставить оценку и оставить комментарий на заказ, которому меньше суток. В ином случае появится ошибка `Feedback has expired`.

## Синтаксис запроса {#request-syntax}

```
POST http://b2b-api.go.yandex.ru/integration/2.0/orders/feedback?order_id={идентификатор заказа}
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

**Тело запроса**

Данные передаются в формате JSON:

Поле | Описание | Формат | Обязательность
----- | ----- | ----- | -----
`rating` | Оценка выполнения заказа. Целое число от 1 до 5. | Число | Да
`msg` | Комментарий к выполненному заказу. | Строка | Нет

## Пример запроса {#request-example}

```
POST http://b2b-api.go.yandex.ru/integration/2.0/orders/feedback?order_id=191...280'
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

  {
    "rating": 5,
    "msg": "хороший водитель"
  }
```

## Пример ответа {#response-example}

В случае успешного запроса будет возвращен пустой ответ с кодом 200.

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `404` — заказ не найден.
- `409` — произошел конфликт при сохранении оценки.
- `410` — заказ был сделан более суток назад, оставить отзыв нельзя.
