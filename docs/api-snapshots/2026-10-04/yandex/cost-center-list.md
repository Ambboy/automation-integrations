---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/cost-center-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/cost-center-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/cost-center-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получение списка центров затрат клиента

Запрос позволяет получить список существующих центров затрат.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/cost_centers/list?
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
`items` | [Список центров затрат](#items). | Массив
`limit` | Максимальное количество возвращаемых записей. | Число
`offset` | Количество пропущенных записей. | Число
`total_amount` | Количество найденных записей. | Число

Структура элемента массива `items`: {#items}

Поле | Описание | Формат
----- | ----- | -----
`id` | Идентификатор центра затрат. | Строка
`name` | Название центра затрат. | Строка
`default` | Признак, используется ли данный центр затрат по умолчанию (задан при активации сервиса клиенту). | Логическое
`field_settings` | [Список настроек](#field-settings) для каждого поля центров затрат. | Массив

Структура элемента массива `field_settings`: {#field-settings}

#|
||**Поле** | **Описание** | **Формат**||
||`id` | id поля.| Строка||
||`hidden` | Не показывать и не использовать это поле при заказе. | Логическое||
||`title` | Название поля. | Строка||
||`required` | Обязательно ли заполнять это поле при заказе. | Логическое||
||`services` | Идентификаторы сервисов, в которых можно использовать это поле при заказе. На данный момент поддерживается только `taxi`. | Массив строк||
||`format` | Возможные значения: 

- `select` — сотрудник выбирает кост-центр из списка.
- `text` — сотрудник самостоятельно указывает кост-центр в текстовом поле.
- `mixed` — сотруднику доступны выбор кост-центра из списка и свободный ввод в текстовом поле. | Строка||
||`values` | Cписок кост-центров, доступных для сотрудника. Формат списка "кост_центр1","кост_центр2", .... | Массив строк||
|#

## Пример запроса {#request-example}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/cost_centers/list?limit=100&offset=0
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
      "id": "1234567890abcdef1234567890abcdef",
      "name": "Основной центр затрат",
      "default": true,
      "field_settings": [
        {
          "id": "0123456789abcdef0123456789abcde0",
          "hidden": false,
          "title": "Центр затрат",
          "required": true,
          "services": ["taxi"],
          "format": "select",
          "values": ["командировка", "в центральный офис"]
        },
        {
          "id": "0123456789abcdef0123456789abcde1",
          "hidden": false,
          "title": "Цель поездки",
          "services": ["taxi"],
          "required": true,
          "format": "mixed",
          "values": ["цель 1", "цель 2", "особая цель"]
        },
        {
          "id": "0123456789abcdef0123456789abcde2",
          "hidden": true,
          "title": "Номер дела",
          "services": ["taxi"],
          "required": true,
          "format": "text",
          "values": []
        }
      ]
    }
  ],
  "limit": 100,
  "offset": 0,
  "total_amount": 1,
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
