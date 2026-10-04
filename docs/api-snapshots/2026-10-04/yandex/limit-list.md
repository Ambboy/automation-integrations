---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/limit-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/limit-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/limit-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получение списка лимитов клиента

Запрос позволяет получить список существующих лимитов.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/limits/search?
department_id=<ID подразделения>
&limit=<количество записей>
&offset=<количество пропускаемых записей>
&search=<поиск по названию>
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
    
- `offset` — количество пропускаемых записей. При отсутствии данного параметра возвращается информация начиная с первой записи.

- `search` — дополнительный фильтр лимитов (по полному совпадению в поле `title`).

- `department_id` — идентификатор департамента.

- `user_id` — идентификатор сотрудника, которому назначен лимит.

- `service` — сервис: `taxi`, `eats2`, `grocery`, `drive`, `tanker`, `cargo` или `travel`.

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`items` | [Список лимитов](#items). | Массив
`limit` | Максимальное количество возвращаемых записей. | Число
`offset` | Количество пропущенных записей. | Число
`total_amount` | Количество найденных записей. | Число

Структура элемента массива `items`: {#items}

Поле | Описание | Формат
----- | ----- | -----
`id` | Идентификатор лимита. | Строка
`title` | Название лимита. | Строка
`client_id` | Идентификатор клиента. | Строка
`department_id`| Идентификатор департамента, к которому относится лимит. Если департамент отсутствует, значит, это корневой департамент. | Строка
`categories` | Cписок доступных тарифных категорий. Указывается только для сервисов `taxi` и `cargo`. Формат списка "категория1","категория2", .... | Массив строк
`fuel_types` | Список доступных видов топлива. Указывается только для сервиса `tanker`. Формат списка "вид1","вид2", .... | Массив строк
`limits` | [Ограничения](#limits) | Объект
`geo_restrictions` | [Блок с информацией](#geo-restrictions) о разрешенных районах поездок. | Массив объектов
`time_restrictions` | [Блок с информацией](#time-restriction) о временных ограничениях. | Массив объектов 
`can_edit` | Признак, может ли пользователь изменить или удалить данный лимит. | Логическое
`counters` | Количество сотрудников с данным лимитом. Объект со структурой `{"users": <число>}`. | Объект
`is_default` | Признак, используется ли данный лимит по умолчанию (задан при активации сервиса клиенту). | Логическое
`service` | Идентификатор сервиса, для которого задается лимит. | Строка
`travel_policy_id` | Идентификатор политики командировок. |
`allow_reservations_without_approve` | Разрешение на бронирование без одобрения. |
`approve_role` | Роль для одобрения заказов. |
`approve_roles` | Список ролей для одобрения заказов. |
`is_qr_enabled` | Разрешена ли оплата по QR-коду в вендоматах. |

Структура объекта `limits`: {#limits}

#|
||**Поле** | **Описание** | **Формат**||
||`orders_amount` | Ограничение на число поездок, которые клиент может совершить за период. Указывается только для сервисов `taxi` и `cargo`.
Объект со структурой `{"value": <число>, "period": <период>}`.
Период задается в виде строки, например, `"month"`. | Объект||
||`orders_cost` | Ограничение на сумму, которую клиент может потратить за период.<br/><br/>Объект со структурой `{"value": <число>, "period": <период>}`.
Период задается в виде строки, например, `"month"`. | Объект||
|#

Структура элемента массива `geo_restrictions`: {#geo-restrictions}

#|
||**Поле** | **Описание** | **Формат**||
||`source` | Идентификатор района начала поездки.
Если поле не задано, то разрешен любой район.
Должно быть задано хотя бы одно из полей `source` и `destination`. | Строка||
||`destination` | Идентификатор района конца поездки.
Если поле не задано, то разрешен любой район.
Должно быть задано хотя бы одно из полей `source` и `destination`. | Строка||
|#

Структура элемента массива `time_restrictions`: {#time-restrictions}

#|
||**Поле** | **Описание** | **Формат**||
||`type` | Тип ограничения. Возможные значения:
- `weekly_date` — ограничения по дням недели.
- `range_date` — ограничения по дате. | Строка||
||`days` | Дни недели, в которые доступен заказ поездки. Возможные значения:
- `mo` — понедельник.
- `tu` — вторник.
- `we` — среда.
- `th` — четверг.
- `fr` — пятница.
- `sa` — суббота.
- `su` — воскресенье.
Поле используется только для ограничения с типом `weekly_date`. | Массив строк||
||`start_time` | Время, начиная с которого будет доступен заказ. Формат значений: `ЧЧ:ММ:СС`.
Поле используется только для ограничения с типом `weekly_date`. | Строка||
||`end_time` | Время, до которого будет доступен заказ. Формат значений: `ЧЧ:ММ:СС`.
Поле используется только для ограничения с типом `weekly_date`. | Строка||
|#

## Пример запроса {#request-example}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/limits/search?limit=100&offset=0&search=Такси - 5000
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
  "items": [
    {
      "geo_restrictions": [
        {
          "source": "50d17034e0ebаааd952d2dad4bbbabcf",
          "destination": "62b9160b33ааа4548e11bbb736bde8b"
        }
      ],
      "id": "9acfdf0a7c9a4dbb85c0601e422f25d9",
      "client_id": "9acfdf0a7c9a4dbb85c0601e422f25d9",
      "categories": [
        "maybach",
        "start",
        "comfortplus",
        "courier",
        "child_tariff",
        "express",
        "cargo",
        "vip",
        "minivan",
        "econom",
        "business",
        "premium_van"
      ],
      "limits": {
        "orders_amount": {
          "value": 50,
          "period": "month"
        },
        "orders_cost": {
          "value": "5000",
          "period": "month"
        }
      },
      "title": "Такси - 5000",
      "time_restrictions": [
        {
          "type": "weekly_date",
          "start_time": "00:59:00",
          "end_time": "02:00:00",
          "days": ["mo","tu","we","th","fr","sa","su"]
        }
      ],
      "can_edit": true,
      "counters": {
        "users": 3
      },
      "service": "taxi"
    }
  ], 
  "limit": 100,
  "offset": 0,
  "total_amount": 1
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.

- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.

- `401` — был передан неверный [OAuth-токен](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).

- `403` — у клиента не хватает прав на выполнение данного запроса:

  - SELECT_CLIENT_HEADER_REQUIRED: в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  

  - SELECTED_CLIENT_ACCESS_DENIED: в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
