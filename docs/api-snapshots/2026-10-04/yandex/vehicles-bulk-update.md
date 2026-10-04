---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/vehicles-bulk-update.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/vehicles-bulk-update.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/vehicles-bulk-update.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Массовое обновление автомобилей

Запрос позволяет обновить информацию о нескольких автомобилях.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/vehicles/bulk-update
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
`vehicles` | Массив объектов [vehicles](#vehicles) с данными по каждому автомобилю. | Массив | Да

Структура элемента массива `vehicles`: {#vehicles}

Поле | Описание | Формат | Обязательность
----- | ----- | ----- | -----
`vehicle_id` | Уникальный идентификатор автомобиля. | Строка | Да
`license_plate` | Новый номер автомобиля. | Строка | Да
`model` | Новая модель автомобиля. | Строка | Да
`limit_id` | Новый лимит на заправку. | Строка | Да
`access_type` | Тип доступа. Возможные значения: `anyone` или `custom`. | Строка | Да
`access` | Массив прав доступа [access](#access). | Массив | Нет

Структура элемента массива `access`: {#access}

Поле | Описание | Формат | Обязательность
----- | ----- | ----- | -----
`entity_type` | Тип субъекта доступа. Возможные значения: `user`, `department`. | Строка | Да
`entity_id` | Идентификатор пользователя или отдела. | Строка | Да

## Описание полей ответа {#response-description}

Успешный ответ не содержит тела (возвращается статус `200 OK`).

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/vehicles/bulk-update
Authorization: Bearer <OAuth-токен>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
X-Idempotency-Token: <токен>

  {
    "vehicles": [
      {
        "vehicle_id": "7ea0b85f04c9469e9fb039b3515975e9",
        "license_plate": "М200ММ199",
        "model": "Газель Next5",
        "limit_id": "7715b673f26a4785bfe11639c9b0d4b6",
        "access_type": "custom",
        "access": []
      }
    ]
  }
```

## Пример ответа {#response-example}

```json
{ }
```

## Возможные коды ответа {#response-codes}

- `200` — успешно обновлено
- `400` — ошибка валидации параметров
- `404` — машина не найдена
- `409` — конфликт (например, дубликат номера машины)
- `503` — ошибка сервера