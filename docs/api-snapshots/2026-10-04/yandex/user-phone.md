---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/user-phone.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-phone.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-phone.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получение информации о сотруднике по номеру телефона

Запрос позволяет получить подробную информацию о сотруднике клиента по номеру его телефона.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/users/by_phone
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

Данные о заказе передаются в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `phone` | Номер телефона сотрудника в формате `+7ХХХХХХХХХХ`. | Строка | Да ||
|#

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`items` | Сотрудники с переданным номером телефона. | Массив объектов

Структура элемента массива `items`:

Поле | Описание | Формат
----- | ----- | -----
`id` | Идентификатор сотрудника. | Строка
`fullname` | Полное имя сотрудника. | Строка
`nickname` | Краткое имя сотрудника. В интерфейсе личного кабинета является полем ID во внешней системе. | Строка
`is_active` | Признак активности сотрудника. Неактивный сотрудник не имеет возможности самостоятельного заказа и на его имя нельзя заказать поездку. | Логическое
`is_deleted` | Признак [архивированного сотрудника](user-archive.md). | Логическое
`email` | Адрес электронной почты сотрудника. | Строка
`cost_centers_id` | id набора настроек центров затрат (при наличии у клиента новых центров затрат). Необязательное поле. | Строка
`limits` | Ограничения на сумму, которую сотрудник может потратить на определенный сервис за календарный месяц. | Массив элементов, содержит отдельный элемент для каждого сервиса.

Структура элемента массива `limits`:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `limit_id` | Идентификатор ранее созданного лимита, который будет назначен пользователю. | Строка ||
|| `service` | Название сервиса. Возможные значения: 

* `taxi`: Яндекс Go;

* `eats2`: [Яндекс Еда и Яндекс Лавка](*comb);

* `drive`: Каршеринг;

* `tanker`: Яндекс Заправки;

* `cargo`: Грузоперевозки;

* `travel`: [Яндекс Путешествия](*travel);

* `scooters`: Яндекс Самокаты. | Строка ||
|#

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/users/by_phone
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

  {
      "phone": "+79011111111"
  }
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
  "items": [
    {
      "id": "43ed...09f0",
      "fullname": "Иванов Иван Иванович",
      "is_deleted": false,
      "is_active": true,
      "limits": [
        {
          "limit_id": "d4c9...6c58",
          "service": "taxi"
        },
        {
          "limit_id": "473e...23f8",
          "service": "eats2"
        },
        {
          "limit_id": "3359...1048",
          "service": "drive"
        },
        {
          "limit_id": "ef72...859b",
          "service": "cargo"
        },
        {
          "limit_id": "0431...dbf6",
          "service": "travel"
        }
      ],
      "email": "email",
      "cost_centers_id": "2c53...6911",
      "nickname": ""
    }
  ]
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.

- `401` — был передан неверный [OAuth-токен](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).

- `403` — у клиента не хватает прав на выполнение данного запроса:

  - SELECT_CLIENT_HEADER_REQUIRED: в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  

  - SELECTED_CLIENT_ACCESS_DENIED: в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.

[*comb]: комбинированный сервис

[*travel]: Отели