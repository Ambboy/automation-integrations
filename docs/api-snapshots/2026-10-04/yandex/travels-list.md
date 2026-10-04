---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/travels-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/travels-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/travels-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получение списка командировок

Запрос позволяет получить список командировок.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/travels/list
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

Данные о заказе передаются в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `name` | Фильтр по названию командировки. | Строка | Нет ||
|| `date_from` | Дата начала периода фильтрации в формате `YYYY-MM-DD`. Например, `2025-12-01` (1 декабря 2025), `2025-10-31` (31 октября 2025). | Строка | Нет ||
|| `date_to` |Дата окончания периода фильтрации в формате `YYYY-MM-DD`. Например, `2025-12-01` (1 декабря 2025), `2025-10-31` (31 октября 2025). | Строка | Нет ||
|| `cursor` | Курсор для следующей страницы. | Строка | Нет ||
|| `limit` | Максимальное количество возвращаемых записей. Значение от 1 до 10. По умолчанию 10. | Число | Нет ||
|| `updated_at_from` | Нижняя граница времени последнего изменения командировки (включительно) в формате ISO 8601. Возвращаются командировки, которые изменены, начиная с указанного момента. Например, `2025-08-13T09:00:00+00:00`.| Строка | Нет ||
|| `updated_at_to` | Верхняя граница времени последнего изменения командировки (включительно) в формате ISO 8601. Возвращаются командировки, измененные до указанного момента. Например, `2025-08-14T18:30:00+00:00`. | Строка | Нет ||
|#

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`travel_items`|Список командировок — массив объектов [TravelItem](#travel-item). В ответе возвращаются только подтвержденные и оплаченные элементы, отмененные и возвращенные не возвращаются.| Массив| Да||
||`next_cursor`|Курсор для следующей страницы. Для получения следующей страницы надо передать этот курсор в следующем запросе в поле `cursor`.| Строка| Нет||
|#

Структура объекта `TravelItem`: {#travel-item}

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`id`|Уникальный идентификатор командировки.| Строка| Да||
||`name`|Название командировки.| Строка| Да||
||`date_from`|Дата начала командировки в формате `YYYY-MM-DD`. Например, `2025-12-01` (1 декабря 2025), `2025-10-31` (31 октября 2025).| Строка| Нет||
||`date_to`|Дата окончания командировки в формате `YYYY-MM-DD`. Например, `2025-12-01` (1 декабря 2025), `2025-10-31` (31 октября 2025).| Строка| Нет||
||`created_at`|Дата и время создания записи в формате `YYYY-MM-DD`. Например, `2025-12-01` (1 декабря 2025), `2025-10-31` (31 октября 2025).| Строка| Да||
||`hotel_reservations`|Бронирования отелей — массив объектов [HotelReservationItem](#hotel-reservation-item).| Массив объектов| Да||
||`train_trips`|Поездки на поезде — массив объектов [TrainsTrip](#trains-trip).| Массив| Да||
||`avia_reservations`|Бронирования авиабилетов — массив объектов [AviaReservationItem](#avia-reservation-item).| Массив объектов| Да||
|#

Структура объекта `HotelReservationItem`: {#hotel-reservation-item}

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`id`| Идентификатор брони. | Строка | Да||
||`external_id`| Идентификатор брони на стороне поставщика. Этот идентификатор отображается на странице «Заказы и отчеты». | Строка | Нет||
||`country`| Страна. | Строка | Да||
||`city`| Город. | Строка | Да||
||`hotel_address`| Адрес отеля. | Строка | Да||
||`hotel_name`| Название отеля. | Строка | Да||
||`room_name`| Тип номера. | Строка | Да||
||`price`| Стоимость — объект [Price](#price). | Объект| Да ||
||`stars`| Количество звезд. | Целое число | Нет||
||`users`| Участники бронирования — массив объектов [HotelReservationUserItem](#HotelReservationUserItem). | Массив | Да||
||`date_from`| Дата заезда в формате `YYYY-MM-DD`. Например, `2025-12-01` (1 декабря 2025), `2025-10-31` (31 октября 2025). | Строка | Да||
||`date_until`| Дата выезда в формате `YYYY-MM-DD`. Например, `2025-12-01` (1 декабря 2025), `2025-10-31` (31 октября 2025). | Строка | Да||
||`voucher_url`| Ссылка на ваучер. Ссылка действует ограниченное время, рекомендуется скачать файл при получении и сохранить у себя. | Строка | Нет||
|#

Структура объекта `HotelReservationUserItem`: {#hotel-reservation-user-item}

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`id`| Идентификатор пользователя, на которого забронирован отель. | Строка | Да||
||`fullname`| ФИО пользователя, на которого забронирован отель.| Строка | Да||
|#

Структура объекта `AviaReservationItem`: {#avia-reservation-item}

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`id`| Идентификатор брони. | Строка | Да||
||`cost`| Стоимость перелета — объект [Price](#price). | Объект | Нет||
||`extra_charge_cost`| Дополнительные сборы — объект [Price](#price). | Объект  | Нет||
||`forward_trip`| Перелет туда — объект [AviaTripInfo](#avia-trip-info). | Объект  | Да||
||`backward_trip`| Перелет обратно — объект [AviaTripInfo](#avia-trip-info). | Объект  | Нет||
||`users`| Участники перелета — массив объектов [AviaReservationUserItem](#avia-reservation-user-item). | Массив | Да||
|#

Структура объекта `AviaReservationUserItem`: {#avia-reservation-user-item}

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`id`| Идентификатор пользователя, на которого приобретен билет. | Строка  | Да||
||`fullname`| ФИО пользователя, на которого приобретен билет. | Строка  | Да||
||`price`|Стоимость билета — объект [Price](#price). | Объект  | Да||
||`ticket_number`| Номер авиабилета. | Строка  | Нет||
|#

Структура объекта `AviaTripInfo`: {#avia-trip-info}

Перелет в одну сторону. Может включать пересадки.

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`departure_city`| Город вылета. | Строка  | Да||
||`departure_airport`| Аэропорт вылета. | Строка  | Да||
||`departure_time`| Время вылета. | Строка  | Да||
||`arrival_city`| Город прилета. | Строка  | Да||
||`arrival_airport`| Аэропорт прилета. | Строка  | Да||
||`arrival_time`| Время прилета. | Строка  | Да||
||`total_duration`| Общая продолжительность (минуты). | Число  | Да||
||`flights`| Сегменты перелета — массив объектов [AviaFlightInfo](#avia-flight-info). | Массив  | Да||
|#

Структура объекта `AviaFlightInfo`: {#avia-flight-info}

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`airline`| Авиакомпания. | Строка | Да||
||`airline_code`| Код авиакомпании. | Строка | Нет||
||`flight_number`| Номер рейса. | Строка | Нет||
||`departure_city`| Город вылета. | Строка | Да||
||`departure_airport`| Аэропорт вылета. | Строка | Да||
||`departure_airport_code`| Код аэропорта вылета. | Строка | Да||
||`departure_time`| Время вылета. | Строка | Да||
||`arrival_city`| Город прилета. | Строка | Да||
||`arrival_airport`| Аэропорт прилета. | Строка | Да||
||`arrival_airport_code`| Код аэропорта прилета. | Строка | Да||
||`arrival_time`| Время прилета. | Строка | Да||
||`total_duration`| Длительность перелета (минуты). | Число | Да||
||`baggage_info`| Информация о багаже — массив объектов [AviaBaggageInfo](#avia-baggage-info). | Массив | Нет||
|#

Структура объекта `AviaBaggageInfo`: {#avia-baggage-info}

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`pieces` | Количество мест багажа. | Целое число| Да||
||`weight` | Вес багажа (кг). | Целое число| Да||
||`size` | Размер багажа (см). | Целое число| Да||
||`is_cabin`| Ручная кладь (`true`/`false`). | Булево| Да||
|#

Структура объекта `TrainsTrip`: {#trains-trip}

Поездка на поезде.

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`id`| Идентификатор поездки. | Строка | Да||
||`trip_parts`| Части маршрута — массив объектов [TrainsTripPart](#trains-trip-part). | Массив | Да||
||`blank_url`| Ссылка на бланк билета. Ссылка действует ограниченное время, рекомендуется скачать файл при получении и сохранить у себя. | Строка | Да||
|#

Структура объекта `TrainsTripPart`: {#trains-trip-part}

Одна часть маршрута переезда на поезде. Содержит информацию о направлении, поезде и т.п.

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`trip_part_id` |Идентификатор части маршрута.| Строка | Да||
||`departure_city` |Город отправления.| Строка | Да||
||`departure_station_code`| Код станции отправления.| Строка | Да||
||`departure_station_name`| Название станции отправления.| Строка | Да||
||`arrival_city`| Город назначения.| Строка | Да||
||`arrival_station_code`| Код станции назначения.| Строка | Да||
||`arrival_station_name`| Название станции назначения.| Строка | Да||
||`departure_time`| Время отправления.| Строка | Да||
||`arrival_time`| Время прибытия.| Строка | Да||
||`total_duration`| Продолжительность (минуты).| Число | Да||
||`direction`| Направление. Возможные значения: `forward` — туда, `backward` — обратно.| Строка | Да||
||`train_number`| Номер поезда.| Строка | Да||
||`train_name`| Название поезда.| Строка | Нет||
||`train_description`| Описание поезда.| Строка | Нет||
||`is_ticket_print_required`| Требуется печать билета.| Булево | Нет||
||`reservations`| Список броней — массив объектов [TrainsReservation](#trains-reservation). |Массив | Да||
|#

Структура объекта `TrainsReservation`: {#trains-reservation}

Содержит информацию о вагоне, месте и т.п.

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`id`| Идентификатор брони.| Строка | Да||
||`booking_number`| Номер бронирования РЖД.| Строка | Нет||
||`total_cost`| Общая стоимость — объект [Price](#price). | Объект | Да||
||`total_paid`| Фактически оплаченная стоимость — объект [Price](#price). | Объект | Нет||
||`refund_cost`| Сумма возврата — объект [Price](#price). | Объект | Нет||
||`users`|Пассажиры  — массив объектов [TrainsReservationUserInfo](#trains-reservation-user-info). |Массив | Да||
||`place_type`| Тип места. Возможные значения:
  - `NoValue`
  - `SeparateCompartment`
  - `SideLowerNearRestroom`
  - `SideUpperNearRestroom`
  - `ThirdShelf`
  - `Foldable`
  - `Upper`
  - `Lower`
  - `Usual`
  - `LastKupeLower`
  - `LastKupeUpper`
  - `Middle`
  - `WithBicycle`
  - `SideLower`
  - `SideUpper`
  - `NearPlayground`
  - `NearTablePlayground`
  - `NearTable`
  - `WithPets`
  - `MotherAndBaby`
  - `WithChild`
  - `NearPassengersWithPets`
  - `Invalids`
  - `InvalidsLower`
  - `InvalidsUpper`
  - `Negotiations`
  - `NearTableForward`
  - `NearTableBackward`
  - `NoTableForward`
  - `NoTableBackward`
  - `NoWindowForward`
  - `NoWindowBackward`
  - `SingleForward`
  - `NearRestroom`
  - `FoldableNearRestroom`
  - `NearRestroomAndBackward`
  - `NearRestroomAndForward`
  - `NoTableAndNoWindow`
  - `Side`
  - `WithoutPlace`
  - `WithHigherLevelOfNoise`
  - `FoldableOrWithHigherLevelOfNoise`
  - `SideLowerWithHigherLevelOfNoise`
  - `SideUpperWithHigherLevelOfNoise`
  - `AisleSeat`
  - `AisleSeatWithHigherLevelOfNoise`
  - `UpperInTwoPlaceCompartment`
  - `LowerInTwoPlaceCompartment`
  - `LastCompartmentLowerWithHigherLevelOfNoise`
  - `LastCompartmentUpperWithHigherLevelOfNoise`
| Строка | Нет||
||`service_class`| Класс обслуживания.| Строка | Да||
||`car_number`| Номер вагона.| Строка | Да||
||`car_description`| Описание вагона.| Строка | Да||
||`car_type`| Тип вагона. Возможные значения:
  - `Shared` — Общий
  - `Soft` — Люкс
  - `Luxury` — СВ
  - `Compartment` — Купе
  - `ReservedSeat` — Плацкарт
  - `Sedentary` — Сидячий
  - `Baggage` — Багажный
| Строка | Да||
||`cabin_gender_type`| Пол в купе. Возможные значения:
  - `male`
  - `female`
  - `combined`
  - `nondef`
  - `none`
| Строка | Нет||
||`is_bedding_included`| Включено постельное белье.| Булево | Нет||
||`service_cost`| Стоимость дополнительных услуг — объект [Price](#price). | Объект | Да||
||`car_services`| Дополнительные услуги в вагоне. Массив строк. Возможные значения:
  - `Bedclothes` — Постельное белье
  - `Meal` — Питание
  - `Wifi` — Wifi
  - `Tv` — Телевизор
  - `HygienicKit` — Санитарно-гигиенический набор
  - `Press` — Пресса
  - `AirConditioning` — Кондиционер
  - `BioToilet` — Биотуалет
  - `Plaid` — Плед
  - `WashbasinInCompartment` — Умывальник
  - `ShowerRoomInCompartment` — Душевая
  - `HygienicShower` — Гигиенический душ
  - `Socket220V` — Розетка 220В
  - `Slippers` — Тапочки
  - `PetsCarriage` — провоз домашних животных
  - `PlacesForPassengerWithBaby` — Места для пассажиров с детьми
  - `Transfer` — Трансфер
  - `RestaurantCarOrBuffet` — Вагон-ресторан или купе-буфет
  - `LuggageCompartment` — Купе для багажа
  - `ShowerRoomInTrain` — Душевая в поезде
  - `Safe` — Сейф
  - `ImprovedServices` — Вагон с улучшенными характеристиками
  - `HighComfortWaitingRoomServices` — Услуги залов повышенной комфортности
  - `InfotainmentService` — Информационно-развлекательный сервис
  - `HotDrink` - Горячие напитки
  - `UsbSocket` - Usb розетка
  - `ExcursionService` - Экскурсионное обслуживание
  - `PanoramicSalon` - Панорамный салон
  - `MediaPlayer` - Медиапроигрыватель
  - `Iron` - Утюг
  - `IroningBoard` - Гладильная доска

|Массив | Нет||
||`place_reservation_type`| Тип выкупа мест. Возможные значения:
  - `Usual`
  - `TwoPlacesAtOnce`
  - `ThreePlacesAtOnce`
  - `FourPlacesAtOnce`
  - `SixPlacesAtOnce`
| Строка | Нет||
||`compartment_number`| Номер купе.| Строка | Нет||
||`arrival_time`| Время прибытия.| Строка | Нет||
||`additional_information`| Дополнительная информация.| Строка | Нет||
||`carrier`| Перевозчик.| Строка | Нет||
|#

Структура объекта `TrainsReservationUserInfo`: {#trains-reservation-user-info}

Содержит информацию о пассажире поезда.

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`id`| Идентификатор пользователя. | Строка | Да||
||`fullname`| ФИО пользователя.|Строка | Да||
||`places`| Номера мест.| Массив целых чисел | Да||
||`cost`| Стоимость за место — объект [Price](#price). | Объект | Да||
|#

Структура объекта `Price`: {#price}

Цена с валютой.

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`value`| Сумма. Например: `1000.00`, `150.50`.|Строка | Да||
||`currency`| Код валюты (например, RUB, USD).| Строка | Да||
|#


## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/travels/list
...
Authorization: Bearer <OAuth-токен>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

  {
    "name": "Москва 13.08.2025 - 14.08.2025"
  }
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
  "travel_items": [
    {
      "id": "0507669f-0387-41ac-9f4d-a4514a5739f0",
      "name": "Москва 13.08.2025 - 14.08.2025",
      "created_at": "2025-07-02T13:48:40.862011+00:00",
      "hotel_reservations": [
        {
          "id": "02a4add7-d052-4c7f-a957-e5572f5785fe",
          "external_id": "12345678",
          "country": "Россия",
          "city": "Москва",
          "hotel_address": "улица Пушкина, дом 1, Москва",
          "hotel_name": "Мини-Отель на улице Пушкина",
          "room_name": "БЮДЖЕТНЫЙ ДВУХМЕСТНЫЙ НОМЕР С 1 КРОВАТЬЮ БЕЗ ОКНА (ДВУХЪЯРУСНАЯ КРОВАТЬ, УДОБСТВА НА ЭТАЖЕ)",
          "price": {
            "value": "2766.06",
            "currency": "RUB"
          },
          "users": [
            {
              "id": "098bfbffb02648c88caccc047def2446",
              "fullname": "Иванов Иван"
            }
          ],
          "date_from": "2025-08-13",
          "date_until": "2025-08-14",
          "stars": 2,
          "voucher_url": "VOUCHER_URL"
        }
      ],
      "train_trips": [
        {
          "id": "16b0b75b-60e5-4df3-8d78-7c342f2725ab",
          "trip_parts": [
            {
              "trip_part_id": "de412d52-bf38-463e-901a-946c8be79752",
              "departure_city": "САНКТ-ПЕТЕРБУРГ",
              "departure_station_code": "2004001",
              "departure_station_name": "САНКТ-ПЕТЕРБУРГ-ГЛАВН.",
              "arrival_city": "МОСКВА",
              "arrival_station_code": "2006004",
              "arrival_station_name": "МОСКВА ОКТЯБРЬСКАЯ",
              "departure_time": "2025-08-13T09:00:00+00:00",
              "arrival_time": "2025-08-13T12:58:00+00:00",
              "total_duration": 238,
              "direction": "forward",
              "train_number": "759А",
              "reservations": [
                {
                  "id": "20b4d5b7-83a1-4b42-aecd-0d233b8ba43e",
                  "total_cost": {
                    "value": "5031.20",
                    "currency": "RUB"
                  },
                  "users": [
                    {
                      "id": "098bfbffb02648c88caccc047def2446",
                      "fullname": "Иванов Иван",
                      "places": [
                        49
                      ],
                      "cost": {
                        "value": "5031.20",
                        "currency": "RUB"
                      }
                    }
                  ],
                  "service_class": "2С",
                  "car_number": "06",
                  "car_description": "У0",
                  "car_type": "Sedentary",
                  "service_cost": {
                    "value": "117.60",
                    "currency": "RUB"
                  },
                  "car_services": [],
                  "booking_number": "75600963602640",
                  "place_type": "NoWindowBackward",
                  "cabin_gender_type": "none",
                  "place_reservation_type": "Usual",
                  "compartment_number": "23"
                }
              ],
              "train_name": "САПСАН",
              "is_ticket_print_required": false
            }
          ],
          "blank_url": "BLANK_URL"
        }
      ],
      "avia_reservations": [
        {
          "id": "66592711-51fc-4dd6-80ba-722d8f00fbe7",
          "forward_trip": {
            "departure_city": "Москва",
            "departure_airport": "Аэропорт Домодедово",
            "departure_time": "2025-08-14T17:00:00+00:00",
            "arrival_city": "Санкт-Петербург",
            "arrival_airport": "Аэропорт Пулково",
            "arrival_time": "2025-08-14T18:30:00+00:00",
            "total_duration": 90,
            "flights": [
              {
                "airline": "Уральские авиалинии",
                "departure_city": "Москва",
                "departure_airport": "Аэропорт Домодедово",
                "departure_airport_code": "DME",
                "departure_time": "2025-08-14T17:00:00+00:00",
                "arrival_city": "Санкт-Петербург",
                "arrival_airport": "Аэропорт Пулково",
                "arrival_airport_code": "LED",
                "arrival_time": "2025-08-14T18:30:00+00:00",
                "total_duration": 90,
                "airline_code": "U6",
                "flight_number": "124",
                "baggage_info": [
                  {
                    "pieces": 1,
                    "weight": 10,
                    "size": 0,
                    "is_cabin": true
                  }
                ]
              }
            ]
          },
          "users": [
            {
              "id": "098bfbffb02648c88caccc047def2446",
              "fullname": "Иванов Иван",
              "price": {
                "value": "3897.00",
                "currency": "RUB"
              }
            }
          ],
          "cost": {
            "value": "3797.00",
            "currency": "RUB"
          },
          "extra_charge_cost": {
            "value": "100.00",
            "currency": "RUB"
          }
        }
      ],
      "date_from": "2025-08-13",
      "date_to": "2025-08-14"
    }
  ]
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `403` — у клиента не хватает прав на выполнение данного запроса.
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `429` — превышен лимит запросов.
