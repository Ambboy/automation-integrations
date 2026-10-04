---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/vehicles-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/vehicles-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/vehicles-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получение списка автомобилей

Запрос позволяет получить список зарегистрированных автомобилей клиента с возможностью фильтрации по пользователю и другими параметрами. Поддерживает постраничную навигацию и опцию включения удаленных машин.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/vehicles/list?limit=<количество записей>
&cursor=<отметка от предыдущего запроса>
&user_id=<идентификатор пользователя>
&include_deleted=false
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

- `limit` — количество выводимых записей. При отсутствии данного параметра возвращается информация о первых 100 записях.
- `cursor` — отметка запроса (возвращается в теле ответа на предыдущий запрос). Для запроса первой страницы параметр указывать не нужно, для запросов последующих страниц — обязательно.
- `user_id` — идентификатор пользователя (для фильтрации).
- `include_deleted` — включать удаленные (архивированные) автомобили. По умолчанию `false`.  

## Описание полей ответа {#response-description}

Ответ возвращается в формате JSON и содержит постраничный список автомобилей.

Поле | Описание | Формат
----- | ----- | -----
`items` | Массив объектов с данными по каждому автомобилю. | Массив
`limit` | Лимит, запрошенный на страницу. | Число
`cursor` | Курсор для следующей страницы (если есть). | Строка
`total_amount` | Общее количество подходящих автомобилей. | Число
`all_client_vehicles` | Общее количество автомобилей у клиента. | Число

Структура элемента массива `items`: {#items}

Поле | Описание | Формат
----- | ----- | -----
`vehicle_id` | Идентификатор автомобиля. | Строка
`license_plate` | Государственный номер. | Строка
`model` | Модель автомобиля. | Строка
`limit` | Лимит автомобиля. | Объект
`is_deleted` | Признак архивного автомобиля. | Булево
`created_at` | Дата и время создания. | Строка
`deleted_at` | Дата и время архивирования. | Строка
`access_type` | Тип доступа. | Строка
`drivers` | Пользователи и департаменты с доступом. | Объект

Структура объекта `limit`: {#limit}

Поле | Описание | Формат
----- | ----- | -----
`limit_id` | Идентификатор лимита. | Строка
`service` | Сервис лимита. | Строка
`title` | Название лимита. | Строка
`fuel_types` | Доступные виды топлива. | Массив строк
`limits` | Ограничения лимита. | Объект

Структура объекта `limits`: {#limits}

Поле | Описание | Формат
----- | ----- | -----
`orders_cost` | Ограничение стоимости заказов. | Объект

Структура объекта `orders_cost`: {#orders-cost}

Поле | Описание | Формат
----- | ----- | -----
`value` | Значение ограничения. | Строка
`period` | Период ограничения. | Строка
`kind` | Вид ограничения. | Строка

Структура объекта `drivers`: {#drivers}

Поле | Описание | Формат
----- | ----- | -----
`total_count` | Общее количество пользователей с доступом. | Целое число
`users` | Пользователи с доступом. | Массив объектов
`departments` | Идентификаторы департаментов с доступом. | Массив строк

Структура элемента массива `users`: {#drivers-users}

Поле | Описание | Формат
----- | ----- | -----
`user_id` | Идентификатор пользователя. | Строка
`department_id` | Идентификатор департамента пользователя. | Строка

## Пример запроса {#request-example}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/vehicles/list?limit=10&include_deleted=false
Authorization: Bearer <OAuth-токен>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#response-example}

```json
{
  "items": [
    {
      "vehicle_id": "7ea0b....75e9",
      "license_plate": "М200ММ199",
      "model": "Газель Next",
      "limit": {
        "limit_id": "7715b673f2....39c9b0d4b6",
        "service": "tanker",
        "title": "Ежедневные лимиты",
        "fuel_types": [
            "metan"
        ],
        "limits": {
            "orders_cost": {
                "value": "1000",
                "period": "month",
                "kind": "money"
            }
        }
      },
      "created_at": "2022-11-21T14:36:27.369997+00:00",
      "access_type": "custom",
      "is_deleted": false,
      "drivers": {
        "total_count": 0,
        "users": [],
        "departments": []
      }
    }
  ],
  "limit": 10,
  "total_amount": 1,
  "all_client_vehicles": 1
}
```

## Возможные коды ответа {#response-codes}

- `200` — успешно
- `400` — ошибка параметров запроса
- `403` — доступ запрещен
