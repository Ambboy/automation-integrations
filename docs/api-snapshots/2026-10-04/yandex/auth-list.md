---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/auth-list.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/auth-list.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/auth-list.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получение списка доступных клиентов по токену

Запрос позволяет получить список клиентов, доступных по токену.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/auth/list
```

**Заголовки запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`clients` | Массив [clients](#clients) объектов с информаций о клиентах. | Массив объектов

Структура элемента массива `clients`: {#clients}

Поле | Описание | Формат
----- | ----- | -----
`client_id` | Идентификатор клиента. | Строка
`name` | Имя клиента. | Строка
`role` | Роль клиента. | Строка

## Пример запроса {#request-example}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/auth/list
...
Authorization: Bearer <OAuth-token>
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
  "clients": [
    {
      "client_id": "beed...e542c",
      "name": "user-name",
      "role": "client"
    }
  ]
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `401` — был передан неверный [OAuth-токен](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
