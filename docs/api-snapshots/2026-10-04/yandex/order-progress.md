---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/order-progress.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-progress.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-progress.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Отслеживание заказа

Запрос позволяет узнать статус заказа и местонахождение машины, которая была назначена заказу.

## Синтаксис запроса {#request-syntax}

```
GET http://b2b-api.go.yandex.ru/integration/2.0/orders/progress?order_id={идентификатор заказа}
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
    
- `order_id` — идентификатор отменяемого заказа.

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`status` | Статус заказа. | Строка
`time_left_raw` | Время до прибытия водителя или до окончания заказа в секундах. | Число
`vehicle` | Информация о местоположении машины. | Объект

Структура объекта `vehicle`: {#vehicle}

Поле | Описание | Формат
----- | ----- | -----
`location` | Координаты машины: широта и долгота. | Массив чисел

## Пример запроса {#request-example}

```
GET http://b2b-api.go.yandex.ru/integration/2.0/orders/progress?order_id=191...280'
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
  "status": "finished",
  "vehicle": {
    "location": [55.749884, 37.589688]
  }
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `404` — заказ не найден.
