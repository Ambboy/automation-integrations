---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/order-create.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-create.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-create.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Создание заказа

Есть возможность указать оффер, полученный в запросе получения [статистики по маршруту и информации о тарифных категориях](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/routestats.md).

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/orders/create
```

**Заголовки запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->
 

<!-- source: ru/_includes/concepts/api20/idempotency.md -->
- `X-Idempotency-Token` — токен идемпотентности, строка [формата UUID](https://ru.wikipedia.org/wiki/UUID#Формат). Одному токену идемпотентности соответствует один заказ, для нового заказа нужно сгенерировать новый токен. Обязательный заголовок.
<!-- endsource: ru/_includes/concepts/api20/idempotency.md -->

**Тело запроса**

Данные о заказе передаются в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `user_id` | Идентификатор сотрудника. | Строка | Да ||
|| `due_date` | Время, к которому нужно создать заказ. Формат значения: `YYYY-MM-DDThh:mm:ss±hh:mm`. | Строка | Нет ||
|| `route` | [Список координат точек маршрута.](#route). | Массив объектов | Да ||
|| `class` | Тариф поездки. | Строка | Да ||
|| `offer` | Идентификатор оффера, полученного в запросе получения [статистики по маршруту и информации о категориях обслуживания](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/routestats.md). | Строка | Нет ||
|| `requirements` | Список требований к заказу. Может варьироваться в зависимости от города. Чтобы узнать поддерживаемые требования, воспользуйтесь запросом [GET /zoneinfo](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/zone-info.md). В ответе в массиве `supported_requirements` будут перечислены варианты, доступные для этой геозоны. | Объект  | Нет ||
|| `cost_center_values` | Новые поля центров затрат. | Массив объектов  | Нет  ||
|| `comment` | Комментарий водителю. | Строка | Нет ||
|| `order_tag` | Тег, который будет добавлен к заказу. | Строка | Нет ||
|#

Структура элемента массива `route`: {#route}

#|
|| **Поле** | **Описание** | **Формат**  ||
|| `geopoint` | Массив из двух значений, задающих долготу и широту точки. | Массив ||
|| `fullname` | Адрес точки. | Строка ||
|#

Структура элемента массива `cost_center_values`: {#cost_center_values}

#|
|| **Поле** | **Описание** | **Формат**  ||
|| `id` | ID поля центра затрат. | Строка ||
|| `title` | Название поля центра затрат. | Строка ||
|| `value` | Новое значение для поля. | Строка ||
|#

## Описание полей ответа {#response-description}

### 200 {#response-200}

Для актуального оффера в ответе содержится поле:

Поле | Описание | Формат
----- | ----- | -----
`order_id` | Идентификатор созданного заказа. | Строка

### 406 {#response-406}

Для неактуального оффера в ответе содержатся поля:

Поле | Описание | Формат
----- | ----- | -----
`code` | Код отказа. | Строка
`message` | Сообщение, объясняющее причину отказа. | Строка

{% note warning %}

В случае ошибки с кодом 500 заказ все равно мог быть создан. Чтобы не создавать дубликат заказа, нужно сделать запрос заново с тем же `X-Idempotency-Token`.

{% endnote %}

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/orders/create
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
X-Idempotency-Token: <токен>

    {
        "route": [
            {
            "geopoint": [
                37.562394,
                55.792993
            ],
            "fullname": "Москва"
            },
            {
            "geopoint": [
                37.609479,
                55.746943
            ],
            "fullname": "Москва"
            }
        ],
        "user_id": "035...c71",
        "class": "econom",
        "cost_center_values": [
            {
            "id": "9af...12a",
            "title": "Цель поездки",
            "value": "по делам"
            }
        ],
        "offer": "edd...234",
        "requirements": {
            "conditioner": true, 
            "yellowcarnumber": true
        }
    }
```

## Пример ответа {#response-example}

Пример ответа для актуального оффера:

```json
{
    "order_id": "33d...b06"
}
```

Пример ответа для неактуального оффера:

```json
{
    "code": "PRICE_CHANGED",
    "message": "Cannot commit order. Price has been changed"
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `404` — сотрудник не найден.
- `406` — для сотрудника или клиента не доступен корпоративный способ оплаты / цена изменилась.
- `410` — уже был выполнен запрос на этот заказ (срок действия заказа истек).
- `500` — заказ мог быть создан, необходимо повторно отправить запрос с тем же токеном.
