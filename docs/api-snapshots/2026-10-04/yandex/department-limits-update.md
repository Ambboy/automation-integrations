---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/department-limits-update.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/department-limits-update.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/department-limits-update.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Изменение лимита департамента на поездки

Запрос позволяет изменить лимит департамента на поездки в сервисе Такси.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/departments/limits/taxi/update?department_id={идентификатор департамента}
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
    
- `department_id` — идентификатор департамента, по которому запрашивается лимит.

**Тело запроса**

{% note warning %}

В данном запросе необходимо тело (body) запроса!

{% endnote %}

Данные передаются в теле запроса в формате JSON:

#|
||**Поле** | **Описание** | **Формат**| **Обязательность**||
||`budget` | Сумма, которую департамент может потратить в месяц на поездки в сервисе Такси. Неотрицательное число или `null`. Значение `null` означает, что лимита на стоимость поездок в месяц нет.  | Число | Да||
||`period` | Период лимита: `month` или `quarter`. Устанавливается, если `budget` не равен `null`. | Строка | Нет ||
|#

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/departments/limits/taxi/update?department_id=87e8...f646c
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

    { 
        "budget": 1000
    }
```

## Пример ответа {#response-example}

В случае успешного запроса будет возвращен пустой ответ с кодом 200.

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.
- `401` — был передан неверный [OAuth-токен](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
- `403`:
  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  
  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.
- `404` — департамента с указанным `department_id` не существует.
