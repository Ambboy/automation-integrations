---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/role-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/role-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/role-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Список ролей менеджеров подразделения

Запрос позволяет получить список ролей менеджеров подразделения. [Подробнее о ролях](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/roles.md).

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/managers/list?
department_id=<ID подразделения>
&roles=<список ролей, разделенных запятыми>
&limit=<количество записей>
&cursor=<отметка от предыдущего запроса>
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

- `department_id` — идентификатор департамента.

- `roles` — список ролей, которые нужно вывести. Возможные значения: `department_manager`, `department_secretary`, `client_manager`.
    
- `limit` — количество выводимых записей. Значение от 1 до 100. При отсутствии данного параметра возвращается информация о первых 10 записях.
    
- `cursor` — отметка запроса (возвращается в теле ответа на предыдущий запрос). Для запроса первой страницы параметр указывать не нужно, для запросов последующих страниц — обязательно. 

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`items` | [Список менеджеров](#items). | Массив
`total_amount` | Количество найденных записей | Число
`cursor`| Отметка текущего запроса. | Строка
`next_cursor`| Отметка для следующего запроса. Для получения следующей страницы нужно передать значение из поля `next_cursor` в GET-параметр `cursor`. Если ответ пустой, поле `next_cursor` отсутствует. | Строка
`limit` | Максимальное количество возвращаемых записей. | Число

Структура элемента массива `items`: {#items}

Поле | Описание | Формат
----- | ----- | -----
`id` | Идентификатор менеджера. | Строка
`email` | Электронная почта менеджера. | Строка
`fullname` | Полное имя менеджера. | Строка
`phone` | Телефонный номер менеджера. | Строка
`yandex_login` | Логин менеджера. | Строка
`department_id` | Идентификатор подразделения. | Строка
`role` | Роль менеджера. | Строка

## Примеры запросов {#request-example}

Первый запрос:

```
GET https://b2b-api.go.yandex.ru/integration/2.0/managers/list?limit=20&roles=department_manager,department_secretary
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

Последующие запросы:

```
GET https://b2b-api.go.yandex.ru/integration/2.0/users?limit=20&cursor=djEgMTY2MjcyMzI2MS4yMzEgYWE4NDBhMTE0MGFjNDMzYmI5NDJiNDYzZjA5MGM3OTE==&roles=department_manager,department_secretary
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
      "email": "email@example.com",
      "fullname": "Иванов Илья",
      "phone": "+799900000000",
      "yandex_login": "sample_yandex_login",
      "department_id": "3648...396b",
      "role": "department_manager",
      "id": "07e4...b2f4"
    },
    ...
  ],
  "total_amount": 42,
  "next_cursor": "djEgMjAyNC0wNy0yMl...GM4MTgwMDFlNTAzYjg3NTQ=",
  "limit": 10
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
- `404` — указанного `department_id` не существует.
