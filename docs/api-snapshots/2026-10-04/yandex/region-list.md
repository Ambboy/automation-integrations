---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/region-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/region-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/region-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Список районов

Запрос позволяет получить информацию обо всех доступных районах поездок клиента.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/geo_restrictions/list? 
limit=<количество записей>
&offset=<количество пропускаемых записей>
```

{% cut "Устаревший метод" %}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/geo_restrictions? 
limit=<количество записей>
&offset=<количество пропускаемых записей>
```

{% endcut %}

**Заголовки запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->
 

**Параметры запроса**

Запрос может содержать следующие необязательные аргументы:

- `limit` — количество выводимых записей. При отсутствии данного параметра возвращается информация о первых 100 записях.
    
- `offset` — количество пропускаемых записей. При отсутствии данного параметра возвращается информация начиная с первой записи.
    
Записи в ответе сортируются по дате и времени последнего обновления.

Максимальный рекомендованный размер справочника — до 10 000 записей.

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`items` | Список районов. | Массив объектов
`amount` | Общее количество районов. | Целое число
`limit` | Максимальное количество возвращаемых районов. | Целое число
`offset` | Количество пропущенных районов. | Целое число

Структура элемента массива `items`: {#items}

Поле | Описание | Формат
----- | ----- | -----
`id` | Идентификатор. | Строка
`name` | Имя. | Строка
`geo_type` | Тип гео ограничения. Сейчас поддерживается только `circle`. | Строка
`geo` | Описание гео ограничения. Содержит следующие поля:<br/>- `center` — координаты центра;<br/>- `radius` — расстояние от центра (в метрах). | Объект

Структура объекта `geo`: {#geo}

Поле | Описание | Формат
----- | ----- | -----
`center` | Координаты центра окружности: долгота и широта. | Массив чисел
`radius` | Радиус окружности в метрах. | Целое число

## Пример запроса {#request-example}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/geo_restrictions/list?limit=50
...
Authorization: <OAuth-токен>
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```
{
    "limit": 50,
    "amount": 2,
    "offset": 0,
    "items": [
      {
        "id": "0081...6917",
        "geo": {
          "center": [
            72.368212,
            54.989342
          ],
          "radius": 500
        },
        "geo_type": "circle",
        "name": "Офис 1"
      },
      {
        "id": "b45e...f0de",
        "geo": {
          "center": [
            37.642639,
            55.734894
          ],
          "radius": 200
        },
        "geo_type": "circle",
        "name": "Офис 2"
      }
    ]
  }
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр.
- `401` — был передан неверный [OAuth-токен](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
- `403` — у клиента не хватает прав на выполнение данного запроса. 
  - SELECT_CLIENT_HEADER_REQUIRED: в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED: в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
