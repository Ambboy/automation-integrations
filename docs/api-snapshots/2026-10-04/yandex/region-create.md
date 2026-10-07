---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/region-create.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/region-create.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/region-create.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Создание нового района

Запрос позволяет создать новый район поездок клиента.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/geo_restrictions/create
```

{% cut "Устаревший метод" %}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/geo_restrictions
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
 

**Тело запроса**

Данные о новом районе передаются в теле запроса в формате JSON:

Поле | Описание | Формат | Обязательность
----- | ----- | ----- | -----
`name` | Имя. | Строка | Да 
`geo_type` | Тип гео ограничения. Сейчас поддерживается только `circle`. | Строка | Да 
`geo` | Описание гео ограничения. Содержит следующие поля:<br/>- `center` — координаты центра;<br/>- `radius` — расстояние от центра (в метрах). | Объект | Да 

Структура объекта `geo`: {#geo}

Поле | Описание | Формат | Обязательность
----- | ----- | ----- | -----
`center` | Координаты центра окружности: долгота и широта. | Массив чисел | Да
`radius` | Радиус окружности в метрах. | Целое число | Да


## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`id` | Идентификационный номер района поездок. | Строка


## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/geo_restrictions/create
  {
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
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```
  {
      "id": "b45efcaa04014fff997c2683ef91f0de"
  }
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением. Например, запись с указанными данными уже существует.
- `401` — был передан неверный [OAuth-токен](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
- `403` — у клиента не хватает прав на выполнение данного запроса. 
  - SELECT_CLIENT_HEADER_REQUIRED: в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED: в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
