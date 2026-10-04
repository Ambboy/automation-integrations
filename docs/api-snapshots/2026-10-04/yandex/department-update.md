---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/department-update.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/department-update.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/department-update.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Редактирование департамента

Запрос позволяет редактировать департамент.

## Синтаксис запроса {#request-syntax}

```
PUT https://b2b-api.go.yandex.ru/integration/2.0/departments/update?department_id={идентификатор департамента}
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

Запрос содержит обязательный параметр:
    
- `department_id` — идентификатор департамента, по которому обновляется информация.

**Тело запроса**

{% note warning %}

В данном запросе необходимо тело (body) запроса!

{% endnote %}

Данные о департаменте передаются в теле запроса в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `parent_id` | Id родительского подразделения, к которому мы хотим прикрепить департамент. 

`parent_id` не может быть `null`. Запросы с `parent_id: null` воспринимаются как не изменяющие `parent_id`. | Строка | Нет ||
|| `name` | Название департамента. | Строка | Нет ||
|#

Изменяются только те поля, для которых переданы соответствующие параметры в теле запроса. Например, можно поменять только название, при этом `parent_id` можно не передавать. 

## Пример запроса {#request-example}

```
PUT https://b2b-api.go.yandex.ru/integration/2.0/departments/update?department_id=87e8...f646c
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

    { 
        "parent_id": "63e8...5d8c",
        "name": "Маркетинг B2B"
    }
```

## Пример ответа {#response-example}

В случае успешного запроса будет возвращен пустой ответ с кодом 200.

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `401` — был передан неверный [OAuth-токен](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
- `403` — у клиента не хватает прав на выполнение данного запроса. 
  - SELECT_CLIENT_HEADER_REQUIRED: в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED: в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `406` — запись с указанными параметрами уже существует.
- `409` — циклическая иерархия.
