---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/department-archive.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/department-archive.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/department-archive.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Удаление департамента

Запрос позволяет удалить департамент и все подчиненные (дочерние) департаменты.

Удаляемый департамент и подчиненные департаменты:
- могут содержать только архивированных сотрудников;
- не должны иметь привязанных к ним ролей — секретарей и менеджеров департамента. 
Иначе удаление не поизойдет, и запрос вернет ошибку с [кодом 400](#response-codes).

При удалении департамент пропадает из личного кабинета.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/departments/archive?department_id={идентификатор департамента}
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
    
- `department_id` — идентификатор департамента, по которому архивируется информация.

## Описание полей ответа {#response-description}

В ответе содержится поле:

Поле | Описание | Формат
----- | ----- | -----
`deleted_ids` | Идентификаторы всех удаленных департаментов. | Массив строк

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/departments/archive?department_id=87e8...646c
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
  "deleted_ids": ["87e8...646c", "2f53...4bca"]
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
- `404` — запрашиваемая запись не найдена.
