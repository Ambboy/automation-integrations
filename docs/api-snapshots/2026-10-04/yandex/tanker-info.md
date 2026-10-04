---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/tanker-info.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/tanker-info.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/tanker-info.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получение отчетности об операциях в сервисе «Заправки»

Запрос позволяет получить информацию об операциях в сервисе «Заправки».

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/orders/tanker
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
    
- `user_id` — id сотрудника. При отсутствии данного параметра возвращается информация обо всех пользователях.
    
- `limit` — максимальное количество заказов в ответе. Может принимать значение от 1 до 1000. При отсутствии данного параметра возвращается информация о первых 100 записях.

- `since_datetime` — начальная дата периода отчета. Задается в виде строки формата `YYYY-MM-DDThh:mm:ss.sss` в UTC без часового пояса.

- `till_datetime` — конечная дата периода отчета. Задается в виде строки формата `YYYY-MM-DDThh:mm:ss.sss` в UTC без часового пояса.

{% note warning %}

Отчет строится по дате завершения заказа (поле `order.closed_at`). 

Левая граница периода отчета включается в отчет, а правая граница — нет, т.е. `since_datetime <= order.closed_at < till_datetime`.

{% endnote %}

## Описание полей ответа {#response-description}

В ответе содержатся поля:

Поле | Описание | Формат
----- | ----- | -----
`orders` | [Массив заказов](#orders). | Массив
`last_closed_at` | Дата завершения последнего заказа из массива `orders`. Имеет формат `YYYY-MM-DDThh:mm:ss.sss` в UTC без таймзоны. Если массив пустой , `last_closed_at` не возвращается. | Строка

Структура элемента массива `orders`: {#orders}

Поле | Описание | Формат
----- | ----- | -----
`id` | id заказа| Строка
`client_id` | id клиента. | Строка
`user_id` | id сотрудника.| Строка
`created_at` | Дата создания заказа. | Строка
`closed_at` | Дата заверешения заказа.| Строка
`fuel_type` | id топлива. Например, `"a95_premium"`.| Строка
`final_price` | Итоговая стоимость, которую списали с клиента, с учетом скидок.| Строка
`liters_filled` | Фактический объем заправки. Например, `"7.07"`. | Строка
`station_location` | Местоположение станции в формате `[<долгота>,<широта]`| Массив

## Примеры запросов {#request-example}

1. Запрос вернет не более 100 первых заказов клиента:

    ```
    https://b2b-api.go.yandex.ru/integration/2.0/orders/tanker
    ...
    Authorization: Bearer <OAuth-token>
    X-YaTaxi-Selected-Corp-Client-Id: <client-id>
    ```

1. Запрос вернет не более 50 первых заказов сотрудника с `id` равным `some_user_id`:

    ```
    https://b2b-api.go.yandex.ru/integration/2.0/orders/tanker?user_id=some_user_id&limit=50
    ...
    Authorization: Bearer <OAuth-token>
    X-YaTaxi-Selected-Corp-Client-Id: <client-id>
    ```

1. Запрос вернет не более 100 заказов в период `[2022-05-12T13:32:49.123, 2022-05-15T06:11:52.834)`:

    ```
    https://b2b-api.go.yandex.ru/integration/2.0/orders/tanker?since_datetime=2022-05-12T13:32:49.123&since_datetime=2022-05-15T06:11:52.834
    ...
    Authorization: Bearer <OAuth-token>
    X-YaTaxi-Selected-Corp-Client-Id: <client-id>
    ```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
    "orders": [
        {
            "id": "bf8...edf",
            "client_id": "33f...85e2",
            "user_id": "bd0f...015",
            "created_at": "2022-02-25T18:44:06.637000+03:00",
            "closed_at": "2022-02-25T18:45:01.004000+03:00",
            "fuel_type": "a92",
            "final_price": "236.4",
            "liters_filled": "5.0",
            "station_location": [
                37.8636,
                51.341842
            ]
        },
        {
            "id": "f0e...1d8",
            "client_id": "33f...5e2",
            "user_id": "bb6...e45",
            "created_at": "2022-03-11T22:23:35.798000+03:00",
            "closed_at": "2022-03-11T22:25:07.939000+03:00",
            "fuel_type": "a92_premium",
            "final_price": "485.19",
            "liters_filled": "10.55",
            "station_location": [
                37.874212,
                55.822556
            ]
        }
    ],
    "last_closed_at": "2022-03-11T19:25:07.939000"
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
