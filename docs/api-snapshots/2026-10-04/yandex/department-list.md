---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/department-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/department-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/department-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получение списка департаментов клиента

Запрос позволяет получить список департаментов клиента.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/departments/list?
limit=<количество записей>
&offset=<количество пропускаемых записей>
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

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`items` | [Список департаментов](#items). | Массив
`limit` | Максимальное количество возвращаемых записей. | Число
`offset` | Количество пропущенных записей. | Число
`total_amount` | Количество найденных записей. | Число

Структура элемента массива `items`: {#items}

#|
||**Поле** | **Описание** | **Формат**||
||`id` | id департамента. | Строка||
||`name` | Название департамента. | Строка||
||`parent_id` | id родительского департамента. | Строка||
||`limits` | Ограничения по сервисам на сумму, которую пользователи департамента могут потратить суммарно. | Объект||
|#

Структура объекта `limits`: {#limits}

#|
||**Поле** | **Описание** | **Формат**||
||`taxi` | Лимит для сервиса Такси. | Объект||
||`eats2` | Лимит для сервисов Еда и Лавка. | Объект||
||`tanker` | Лимит для сервиса Заправки. | Объект||
||`cargo` | Лимит для сервиса Доставка. | Объект||
||`travel_common` | Лимит для сервиса Командировки. | Объект||
|#

Структура лимита сервиса: {#service-limit}

#|
||**Поле** | **Описание** | **Формат**||
||`budget` | Бюджет сервиса. Значение `null` означает отсутствие лимита. | Число||
||`period` | Период лимита: `month` или `quarter`. Присутствует только при ненулевом значении `budget` (при `budget: null` поле отсутствует). | Строка||
|#

## Пример запроса {#request-example}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/departments/list?limit=100&offset=0
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
      "id": "a8187621244340d890b684иииbf298276",
      "name": "Бухгалтеры",
      "limits": {
        "taxi": {
          "budget": 10000
        },
        "eats2": {
          "budget": null
        },
        "tanker": {
          "budget": null
        }
      },
      "parent_id": null
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
- `403` — у клиента не хватает прав на выполнение данного запроса. 
  - SELECT_CLIENT_HEADER_REQUIRED: в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED: в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
