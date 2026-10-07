---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/user-archive.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-archive.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-archive.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Архивирование сотрудника

Запрос позволяет архивировать сотрудника клиента. При архивации сотрудник пропадает из личного кабинета. Сотрудник не может пользоваться сервисами, и его нельзя найти в личном кабинете.

При попытке создать сотрудника с таким же номером телефона, как и у архивированного сотрудника, возникнет ошибка. 
В этом случае вместо создания нового сотрудника следует [восстановить сотрудника из архива](#restore) с обновленными данными.

<!-- source: ru/_includes/concepts/api20/do-not-delete-user.md -->
{% note info %}

Крайне не рекомендуется менять номер телефона сотрудника. Вместо этого лучше [создать нового сотрудника](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-create.md).

{% endnote %}
<!-- endsource: ru/_includes/concepts/api20/do-not-delete-user.md -->

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/users/archive?user_id={идентификатор сотрудника}
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
    
- `user_id` — идентификатор сотрудника, информация по которому архивируется.

## Описание полей ответа {#response-description}

В ответе содержится поле:

Поле | Описание | Формат
----- | ----- | -----
`status` | Статус выполнения запроса. | Строка

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/users/archive?user_id=f65...c57d
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
    "status": "OK"
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `401` — был передан неверный [OAuth-токен](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
- `403` — у клиента не хватает прав на выполнение данного запроса. 
  - SELECT_CLIENT_HEADER_REQUIRED: в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED: в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `404` — запрашиваемая запись не найдена.


## Восстановление архивированного сотрудника {#restore}

Для восстановления нужно отправить запрос на [редактирование сотрудника](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-update-put.md) с добавлением флага `is_deleted: false`.

