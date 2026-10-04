---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/user-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Список сотрудников клиента

Запрос позволяет получить список сотрудников клиента.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/users?
limit=<количество записей>
&cursor=<отметка от предыдущего запроса>
```

{% note warning %}

Список сотрудников сортируется по времени создания, порядок сортировки — возрастающий (на первой странице всегда будут сотрудники с самой ранней датой создания).

{% endnote %}

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
    
## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`items` | [Список сотрудников клиента](#items). | Массив
`cursor`| Отметка текущего запроса. | Строка
`next_cursor`| Отметка для следующего запроса. Для получения следующей страницы нужно передать значение из поля `next_cursor` в GET-параметр `cursor`. Если ответ пустой, поле `next_cursor` отсутствует. | Строка
`limit` | Максимальное количество возвращаемых записей. | Число
`total_amount` | Количество найденных записей. | Число

Структура элемента массива `items`: {#items}

Поле | Описание | Формат
----- | ----- | -----
`client_id` | Идентификатор клиента (кабинета). | Строка
`id` | Идентификатор сотрудника. | Строка
`is_deleted` |  Признак удаленности сотрудника (виден ли в интерфейсе), удаленный сотрудник не может быть активным. | Логическое
`cost_center` | Название центра затрат клиента. | Строка
`department_id` | Идентификатор департамента. | Строка
`phone` | Телефонный номер сотрудника. | Строка
`email` | Адрес электронной почты сотрудника. | Строка
`nickname` | Краткое имя сотрудника. | Строка
`limits` | Информация о лимитах. | Массив
`is_active` | Признак активности сотрудника. Неактивный пользователь не имеет возможности самостоятельного заказа. | Логическое
`cost_centers_id` | Идентификатор набора настроек центров затрат | Строка
`fullname` | Полное имя сотрудника. | Строка

Структура элемента массива `limits`: {#limits}

Поле | Описание | Формат
----- | ----- | -----
`limit_id` | Идентификатор лимита.| Строка 
`service` | Название сервиса лимита. Возможные значения: `taxi`, `eats2`, `drive`, `tanker`, `grocery`.| Строка 

## Примеры запросов {#request-example}

Первый запрос:

```
GET https://b2b-api.go.yandex.ru/integration/2.0/users?limit=100
...
Authorization: <OAuth-токен>
```

Последующие запросы:

```
GET https://b2b-api.go.yandex.ru/integration/2.0/users?limit=100&cursor=djEgMTY2MjcyMzI2MS4yMzEgYWE4NDBhMTE0MGFjNDMzYmI5NDJiNDYzZjA5MGM3OTE=
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
            "cost_centers_id": "4d6ffae7af844b…",
            "is_active": true,
            "email": "email1@email.ru",
            "limits": [
              {
                "limit_id": "e31cc52437…",
                "service": "eats2"
              },
              {
                "limit_id": "4afef98…..20569bb9d",
                "service": "drive"
              }
            ],
            "client_id": "1f300a6…..edf867021c",
            "department_id": "9080a2……208a1856",
            "fullname": "Имя Фамилия ",
            "cost_center": "",
            "phone": "+79999999996",
            "nickname": "id1234572",
            "id": "0516587…..c5a8adb58",
            "is_deleted": false
        }
    ],
    "limit": 10,
    "total_amount": 28,
    "cursor": "djEgMTY2Mjcy4yMz…..DMzYmI5NDJiNDYzZjA5MGM3OTE=",
    "next_cursor": "djEgMTY2NjA3OTAN….GM4MTgwMDFlNTAzYjg3NTQ="
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
