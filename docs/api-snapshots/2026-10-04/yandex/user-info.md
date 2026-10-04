---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/user-info.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-info.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-info.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Детальная информация о сотруднике

Запрос позволяет получить подробную информацию о сотруднике клиента.

## Синтаксис запроса {#request-syntax}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/users?user_id={идентификатор сотрудника}
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
    
- `user_id` — идентификатор сотрудника, по которому предоставляется информация.

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`fullname` | Полное имя сотрудника. | Строка
`is_active` | Признак активности сотрудника. Неактивный сотрудник не имеет возможности самостоятельного заказа и на его имя нельзя заказать поездку. | Логическое
`phone` | Телефонный номер сотрудника. | Строка
`id` | Идентификатор сотрудника. | Строка
`is_deleted` | Признак [архивированного сотрудника](user-archive.md). | Логическое
`cost_center` | Название центра затрат клиента. | Строка
`cost_centers_id` | Идентификатор набора настроек центров затрат при наличии у клиента новых центров затрат. Необязательное поле. | Строка
`department_id` | Идентификатор департамента в личном кабинете. | Строка
`limits` | Ограничения на сумму, которую сотрудник может потратить на определенный сервис за календарный месяц. | Массив элементов, содержит отдельный элемент для каждого сервиса.
`nickname` | Краткое имя сотрудника. В интерфейсе личного кабинета является полем ID во внешней системе. | Строка
`email` | Адрес электронной почты сотрудника. | Строка
`client_id` | Идентификатор клиента. | Строка
`documents` | Документы сотрудника. | Массив объектов

Структура элемента массива `limits`:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `limit_id` | Идентификатор ранее созданного лимита, который будет назначен пользователю. | Строка ||
|| `service` | Название сервиса. Возможные значения: 
* `taxi`: Яндекс Go;
* `eats2`: [Яндекс Еда и Яндекс Лавка](*comb);
* `grocery`: [Яндекс Лавка](*lavka);
* `drive`: Каршеринг;
* `tanker`: Яндекс Заправки;
* `cargo`: Грузоперевозки;
* `travel`: [Яндекс Путешествия](*travel);
* `scooters`: Яндекс Самокаты. | Строка ||
|#

Структура элемента массива `documents`:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `id` | Идентификатор документа. | Строка ||
|| `user_id` | Идентификатор сотрудника. | Строка ||
|| `document_type` | Тип документа: `passport_rus`, `birth_certificate`, `seafarer_passport`, `foreign_passport_rus`, `foreign_document`, `cosmopolit_certificate`. | Строка ||
|| `citizenship` | Гражданство. | Строка ||
|| `first_name` | Имя. | Строка ||
|| `last_name` | Фамилия. | Строка ||
|| `middle_name` | Отчество. | Строка ||
|| `first_name_lat` | Имя латиницей. | Строка ||
|| `last_name_lat` | Фамилия латиницей. | Строка ||
|| `middle_name_lat` | Отчество латиницей. | Строка ||
|| `gender` | Пол: `male` или `female`. | Строка ||
|| `actual_to_str` | Дата окончания действия документа в формате `YYYY-MM-DD`. | Строка ||
|| `birth_date_str` | Дата рождения в формате `YYYY-MM-DD`. | Строка ||
|| `number` | Номер документа. | Строка ||
|#

## Пример запроса {#request-example}

```
GET https://b2b-api.go.yandex.ru/integration/2.0/users?user_id=f65...c57d
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
  "fullname": "Иванов Илья",
  "is_active": true,
  "phone": "+79262770203",
  "id": "2e….b6",
  "is_deleted": false,
  "cost_center": "",
  "cost_centers_id": "2c53…1",
  "department_id": "b617…4",
  "limits": [
     {
       "limit_id": "d4c...8",
       "service": "taxi"
     },
     {
       "limit_id": "473…8",
       "service": "eats2"
     },
     {
       "limit_id": "df…f",
       "service": "cargo"
     }
     ],
  "nickname": "",
  "client_id": "bee…c"
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.

- `401` — был передан неверный [OAuth-токен](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).

- `403` — у клиента не хватает прав на выполнение данного запроса: 

  - SELECT_CLIENT_HEADER_REQUIRED: в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  

  - SELECTED_CLIENT_ACCESS_DENIED: в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.

- `404` — запрашиваемая запись не найдена.

[*comb]: комбинированный сервис

[*lavka]: сервис устарел, используйте `eats2`

[*travel]: Отели