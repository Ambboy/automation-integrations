---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/taxi-report.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/taxi-report.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/taxi-report.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Информация о заказах такси для отчета

Запрос позволяет получить информацио о заказах такси для формирования отчета.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/orders/taxi/report
```

**Заголовки запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->
 
- `Accept-Language` — выбор языка в формате строки (ru-RU, en-US и т.п.).

**Тело запроса**

Данные передаются в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `ids` | Массив идентификаторов заказов, по которым нужна информация. Не более 100 элементов. | Массив строк | Да ||
|#

## Описание полей ответа {#response-description}

В отчете возвращается поле:

Поле | Описание | Формат
----- | ----- | -----
`orders` | Массив объектов [TaxiOrderInfo](#taxi-order-info), каждый объект содержить информацию о заказе. | Массив объектов

Структура объекта `TaxiOrderInfo`: {#taxi-order-info}

#|
|| **Поле** | **Описание** | **Формат**  ||
|| `id` | Идентификатор заказа.  | Строка  ||
|| `agency_fee_percent` | Агентское вознаграждение, процент.  | Число  ||
|| `agency_to_pay` | Агентское вознаграждение с НДС.  | Число  ||
|| `agency_without_vat_to_pay` | Агентское вознаграждение без НДС.  | Число  ||
|| `booking_actual_hours` | Количество фактических часов.  | Число  ||
|| `booking_hour_price` | Стоимость 1 часа.  | Число  ||
|| `booking_hours` | Количество запланированных часов.  | Число  ||
|| `cancel_reason` | Причина отмены заказа. Объект [CancelReason](#cancel_reason). | Объект  ||
|| `city` | Город.  | Строка  ||
|| `comment` | Комментарий к заказу.  | Строка  ||
|| `cost` | Стоимость заказа без НДС.  | Число  ||
|| `cost_center` | Центр затрат.  | Строка  ||
|| `cost_w_vat` | Стоимость заказа с НДС.  | Число  ||
|| `created_datetime` | Время создания заказа.  | Строка  ||
|| `creator` | Инициатор заказа.  | Строка  ||
|| `department` | Актуальное подразделение.  | Строка  ||
|| `department_path` | Актуальная цепочка подразделений.  | Массив строк  ||
|| `destination` | Координаты точки назначения заказа. Массив из двух чисел. | Массив чисел  ||
|| `destination_fullname` | Адерс назначения.  | Строка  ||
|| `discount` | Процент скидки.  | Число  ||
|| `discounted_cost` | Стоимость со скидкой.  | Число  ||
|| `distance` | Пройденное расстояние.  | Число  ||
|| `due_datetime` | Время заказа. | Строка  ||
|| `finish_datetime` | Фактическое время окончания поездки. | Строка  ||
|| `interim_destinations` | Промежуточные точки маршрута.  Массов объектов [InterimDestinationItem](#interim-destination-item).| Массив объектов  ||
|| `local_created_datetime` | Локальное время создания заказа.  | Строка  ||
|| `local_due_datetime` | Локальное время завершения заказа.  | Строка  ||
|| `old_department` | Подразделение сотрудника на момент заказа.  | Строка  ||
|| `order_method` | Способ заказа. Например, "Личный кабинет". | Строка  ||
|| `order_type` | Тип заказа. Объект [OrderType](#order_type). | Объект  ||
|| `park_name` | Таксопарк.  | Строка  ||
|| `receipt_url` | Ссылки на чеки за поездку.  | Массив строк  ||
|| `requirements` | Дополнительные требования, которые были указаны в заказе. Массив объектов [requirements](#requirements).  | Массив объектов  ||
|| `ride_cost` | Стоимость поездки.  | Число  ||
|| `ride_status` | Статус поездки. Объект [RideStatus](#ride_status). | Объект  ||
|| `sales_tax` | Сумма налога с продажи.  | Число  ||
|| `source_fullname` | Адрес подачи.  | Строка  ||
|| `source_geopoint` | Координаты точки подачи. Массив из двух чисел. | Массив чисел  ||
|| `start_datetime` | Фактическое начало поездки.  | Строка  ||
|| `start_waiting_datetime` | Фактическое время прибытия машины. | Строка  ||
|| `tariff_class` | Тариф.  | Строка  ||
|| `toll_road_cost` | Стоимость проезда по платным дорогам.  | Число  ||
|| `total_cost` | Общая стоимость заказа с НДС.  | Число  ||
|| `user_id` | Идентификатор пользователя.  | Строка  ||
|| `vat` | НДС.  | Число  ||
|| `waiting_cost` | Стоимость ожидания.  | Число  ||
|| `waiting_in_depart_time` | Время ожидания в точке начала поездки.  | Число  ||
|| `waiting_in_transit_time` | Время ожидания в промежуточных точках.  | Число  ||
|#

Структура объекта `CancelReason`: {#cancel_reason}

#|
|| **Поле** | **Описание** | **Формат**  ||
|| `text` | Локализованный текст для отображения.  | Строка  ||
|| `value` | Одно из значений: `client_did_not_come`, `a_lot_of_passengers`, `passenger_with_child`, `wrong_address`, `client_cancelled_driving`, `waiting`, `mistaken`, `wrong_pickup`, `wrong_pickup_driver`, `other`. | Строка  ||
|#

Структура объекта `InterimDestinationItem`: {#interim-destination-item}

#|
|| **Поле** | **Описание** | **Формат**  ||
|| `fullname` | Полный адрес промежуточной точки маршрута.  | Строка  ||
|| `geopoint` | Координаты промежуточной точки. Массив из двух чисел. | Массив чисел  ||
|#

Структура объекта `OrderType`: {#order_type}

#|
|| **Поле** | **Описание** | **Формат**  ||
|| `text` | Локализованный текст для отображения.  | Строка  ||
|| `value` | Одно из значений: `combo_order`, `booking`. | Строка  ||
|#

Структура объекта `requirements`: {#requirements}

#|
|| **Поле** | **Описание** | **Формат**  ||
|| `name` | Описание требований.  | Строка  ||
|#

Структура объекта `RideStatus`: {#ride_status}

#|
|| **Поле** | **Описание** | **Формат**  ||
|| `text` | Локализованный текст для отображения.  | Строка  ||
|| `value` | Одно из значений: `client_cancelled`, `driver_cancelled`, `complete`. | Строка  ||
|#

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/orders/taxi/report
...
Accept-Language: ru-RU
Authorization: <OAuth-токен>

    {
        "ids": [
            "1df3...e600",
            "8d66...2781",
            "1fd4...b9df1"
        ]
    }
```

## Пример ответа {#response-example}

```json
{
    "orders": [
        {
            "id": "1df32d5b8bdcc769b9a2e190933fe600",
            "agency_to_pay": 1.2,
            "agency_without_vat_to_pay": 1.0,
            "cancel_reason": {
                "value": "client_cancelled_driving",
                "text": "Отмена заказа после начала платного времени подачи"
            },
            "city": "Москва",
            "cost": 0.0,
            "cost_center": "новый",
            "cost_w_vat": 0.0,
            "created_datetime": "2022-06-09T18:22:42+03:00",
            "destination": [
                37.58041085337755,
                55.807367818950475
            ],
            "destination_fullname": "Россия, Москва, Бутырская улица, 95",
            "discount": 0.0,
            "discounted_cost": 0.0,
            "due_datetime": "2022-06-09T18:23:52+03:00",
            "local_created_datetime": "2022-06-09T18:22:42+03:00",
            "local_due_datetime": "2022-06-09T18:23:52+03:00",
            "old_department": "траты",
            "order_method": "Мобильное приложение",
            "requirements": [
                {
                    "name": "детское кресло от 3 до 7 лет (15-25 кг)"
                },
                {
                    "name": "Час+"
                }
            ],    
            "ride_cost": 0.0,
            "ride_status": {
                "value": "client_cancelled",
                "text": "Отменена пользователем"
            },
            "sales_tax": 0.0,
            "source_fullname": "Россия, Москва, улица Фонвизина, 18",
            "source_geopoint": [
                37.59143138528312,
                55.82111264677945
            ],
            "tariff_class": "Эконом",
            "total_cost": 0.0,
            "user_id": "4550...ba80",
            "vat": 0
        },
        ...
    ]
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED: в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED: в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
