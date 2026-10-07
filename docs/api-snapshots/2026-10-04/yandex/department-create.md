---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/department-create.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/department-create.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/department-create.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Создание департамента

Запрос позволяет создать департамент.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/departments/create
```

**Заголовки запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->
 

**Тело запроса**

{% note warning %}

В данном запросе необходимо тело (body) запроса!

{% endnote %}

Данные о новом департаменте передаются в теле запроса в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `parent_id` | Id родительского подразделения, к которому мы хотим прикрепить новый департамент. 

Если в качестве `parent_id` передается `null`, то департамент прикрепляется к корневому подразделению. | Строка | Да ||
|| `name` | Название нового департамента. | Строка | Да ||
|#

## Описание полей ответа {#response-description}

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `_id` | Идентификатор созданного департамента. | Строка | Нет ||
|#

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/departments/create

Body 
{ 
    "parent_id": null,
    "name": "Отдел маркетинга"
}
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
    "_id": "63e823515f8a4f5a93dab0298c0f5d8c"
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
- `406` — запись с указанными параметрами уже существует.
