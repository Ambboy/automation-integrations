---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/role-update.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/role-update.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/role-update.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Обновление роли

Запрос позволяет обновить роль менеджера подразделения. [Подробнее о ролях](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/roles.md). Роли, которые могут быть выданы пользователю, можно посмотреть в его Личном кабинете.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/managers/update?id={идентификатор менеджера}
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
    
- `id` — идентификатор менеджера подразделения, для которого обновляется роль.

**Тело запроса**

Данные о роли передаются в теле запроса в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `fullname` | Полное имя менеджера подразделения. | Строка | Да||
|| `email` | Электронная почта менеджера подразделения. | Строка | Да||
|| `phone` | Телефонный номер менеджера подразделения. | Строка | Да||
|| `yandex_login` | Логин менеджера подразделения. | Строка | Да||
|| `role` | Роль менеджера подразделения. Возможные значения: `department_manager`, `department_secretary`, `client_manager`.| Строка| Да||
|| `department_id` | Идентификатор подразделения подразделения. | Строка| Нет||
|#

## Описание полей ответа {#response-description}

В ответе с кодом 200 содержится поле:

Поле | Описание | Формат
----- | ----- | -----
`id` | Идентификационный номер менеджера подразделения. | Строка

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/managers/update?id=07e4...b2f4
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

    {
        "yandex_login": "sample_yandex_login",
        "role": "department_manager",
        "department_id": "3648...396b",
        "phone": "+799900000000",
        "email": "email@example.com",
        "fullname": "Иванов Илья"
    }
```

## Примеры ответа {#response-example}

Пример ответа на данный запрос с кодом 200 выглядит следующим образом:

```json
{
    "id": "07e4...b2f4"
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
- `404` — менеджера с указанным `id` не существует.
- `409` — конфликт одновременного доступа.
