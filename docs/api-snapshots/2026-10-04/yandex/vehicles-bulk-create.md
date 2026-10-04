---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/vehicles-bulk-create.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/vehicles-bulk-create.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/vehicles-bulk-create.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Массовое создание автомобилей

Запрос позволяет создать сразу несколько автомобилей, указав их данные в теле запроса.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/vehicles/bulk-create
```

**Заголовки запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->

<!-- source: ru/_includes/concepts/api20/idempotency.md -->
- `X-Idempotency-Token` — токен идемпотентности, строка [формата UUID](https://ru.wikipedia.org/wiki/UUID#Формат). Одному токену идемпотентности соответствует один заказ, для нового заказа нужно сгенерировать новый токен. Обязательный заголовок.
<!-- endsource: ru/_includes/concepts/api20/idempotency.md -->

**Тело запроса**

Данные передаются в формате JSON:

Поле | Описание | Формат | Обязательность
----- | ----- | ----- | -----
`vehicles` | Массив описаний автомобилей [vehicles](#vehicles). | Массив | Да

Структура элемента массива `vehicles`: {#vehicles}

Поле | Описание | Формат | Обязательность
----- | ----- | ----- | -----
`license_plate` | Номер автомобиля. | Строка | Да
`model` | Модель автомобиля. | Строка | Да
`limit_id` | Идентификатор лимита на заправку. | Строка | Да
`access_type` | Тип доступа. Возможные значения: `anyone` или `custom`. | Строка | Да
`access` | Массив прав доступа [access](#access). | Массив | Нет

Структура элемента массива `access`: {#access}

Поле | Описание | Формат | Обязательность
----- | ----- | ----- | -----
`entity_type` | Тип субъекта доступа. Возможные значения: `user`, `department`. | Строка | Да
`entity_id` | Идентификатор пользователя или отдела. | Строка | Да

## Описание полей ответа {#response-description}

Возвращает список идентификаторов созданных машин.

Поле | Описание | Формат
----- | ----- | -----
`ids` | Идентификаторы созданных машин. | Массив строк

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/vehicles/bulk-create
Authorization: Bearer <OAuth-токен>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
X-Idempotency-Token: <токен>

  {
    "vehicles": [
      {
        "license_plate": "Е768КК58",
        "model": "Haval-5",
        "limit_id": "7715b67....c9b0d4b6",
        "access_type": "custom",
        "access": [
          {
            "entity_type": "department",
            "entity_id": "6ddfc4...ec77b135f"
          }
        ]
      }
    ]
  }
```

## Пример ответа {#response-example}

```json
{
  "ids": [
    "4cd981dc5....805500202"
  ]
}
```

## Возможные коды ответа {#response-codes}

- `200` — успешно создано
- `400` — ошибка валидации параметров
- `404` — клиент не найден
- `409` — конфликт (например, дубликат номера машины)
- `503` — временная ошибка сервера
