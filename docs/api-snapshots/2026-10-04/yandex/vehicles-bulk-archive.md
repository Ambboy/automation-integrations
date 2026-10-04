---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/vehicles-bulk-archive.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/vehicles-bulk-archive.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/vehicles-bulk-archive.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Массовое удаление автомобилей

Запрос позволяет логически удалить (архивировать) несколько автомобилей по их идентификаторам.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/vehicles/bulk-archive
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
`vehicle_ids` | Список идентификаторов автомобилей. | Массив | Да

## Описание полей ответа {#response-description}

Успешный ответ не содержит тела (возвращается статус `200 OK`).

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/vehicles/bulk-archive
Authorization: Bearer <OAuth-токен>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
X-Idempotency-Token: <токен>

  {
    "vehicle_ids": [
      "vehicle-abc-123",
      "vehicle-def-456"
    ]
  }
```

## Пример ответа {#response-example}

```json
{ }
```

## Возможные коды ответа {#response-codes}

- `200` — машины успешно удалены
- `400` — ошибка валидации параметров
- `404` — одна или несколько машин не найдены
- `503` — ошибка сервера