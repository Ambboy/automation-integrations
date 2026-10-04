---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/order-active.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-active.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-active.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Список активных заказов

Получает список активных заказов со статусами.

## Синтаксис запроса

```
GET http://b2b-api.go.yandex.ru/integration/2.0/orders/active?user_id={идентификатор пользователя}
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
    
- `user_id` — идентификатор сотрудника, чьи заказы нужно посмотреть.

## Описание полей ответа

В ответе содержится поле:

Поле | Описание | Формат
----- | ----- | -----
`items` | Массив с данными о [маршрутах](#items). | Массив объектов

Структура элемента массива `items`: {#items}

#|
|| **Поле** | **Описание** | **Формат** ||
||`id` | Идентификатор заказа. | Строка||
||`status` | Статус заказа. Возможные значения:
- `search` — заказ создан и осуществляется поиск водителя.
- `driving` — водитель найден и едет к месту подачи автомобиля.
- `waiting` — водитель прибыл и ожидает сотрудника.
- `transporting` — сотрудник сел в машину и находится в пути.
- `complete` — заказ завершен успешно.
- `cancelled` — заказ отменен по инициативе клиента или его сотрудника.
- `failed` — заказ отменен таксопарком, так как водитель не может его выполнить.
- `expired` — статус заказа неизвестен. Данный статус может возвращается, если таксопарк вовремя не прислал данные о состоянии заказа.
- `scheduling` — заказ создан, поиск водителя будет начат за некоторое время до подачи автомобиля.
- `scheduled` — заказ создан, водитель назначен и выедет к сотруднику согласно времени подачи. Заказ в этом статусе может быть изменен. | Строка||
|#

## Пример запроса

```
GET http://b2b-api.go.yandex.ru/integration/2.0/orders/active?user_id=0354...3c71
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа

Пример ответа на данный запрос выглядит следующим образом:

```json
{
  "items": [
    {
      "id": "8f7...c83",
      "status": "driving"
    },
    {
      "id": "71e...05c",
      "status": "transporting"
    }
  ]
}
```

## Возможные коды ответа

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
