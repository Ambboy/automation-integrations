---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/user-create.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-create.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-create.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Создание сотрудника

Запрос позволяет создать запись о новом сотруднике клиента.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/users
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

Данные о новом сотруднике передаются в теле запроса в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `fullname` | Полное имя сотрудника. Может быть пустой строкой. | Строка | Да||
|| `phone` | Номер телефона пользователя. Можно указать только номер в международном формате с кодом страны, например `+79001234567`. | Строка | Да||
|| `email` | Адрес электронной почты пользователя. Можно указать только email, который соответствует стандартному формату адреса. | Строка | Нет ||
|| `is_active` | Признак активности сотрудника. Неактивный сотрудник не имеет возможности самостоятельного заказа и на его имя нельзя заказать поездку. | Логическое | Да||
|| `cost_centers_id` | Идентификатор центра затрат. | Строка | Нет||
|| `nickname` | Краткое имя сотрудника. В интерфейсе личного кабинета является полем ID во внешней системе. | Строка | Нет||
|| `department_id` | Идентификатор департамента в личном кабинете. | Строка | Нет||
|| `limits` | Ограничения на сумму, которую сотрудник может потратить на сервисы за календарный месяц. | Массив элементов, содержит отдельный элемент для каждого сервиса. | Нет||
|| `documents` | Документы сотрудника. | Массив объектов | Нет ||
|#

Структура элемента массива `limits`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `limit_id` | Идентификатор ранее созданного лимита, который будет назначен пользователю. | Строка | Да ||
|| `service` | Название сервиса. Возможные значения: 

* `taxi`: Яндекс Go;

* `eats2`: [Яндекс Еда и Яндекс Лавка](*comb);

* `grocery`: [Яндекс Лавка](*lavka);

* `drive`: Каршеринг;

* `tanker`: Яндекс Заправки;

* `cargo`: Грузоперевозки;

* `travel`: [Яндекс Путешествия](*travel);

* `scooters`: Яндекс Самокаты. | Строка | Да||
|#

Структура элемента массива `documents`:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `document_type` | Тип документа: `passport_rus`, `birth_certificate`, `seafarer_passport`, `foreign_passport_rus`, `foreign_document`, `cosmopolit_certificate`. | Строка | Да ||
|| `citizenship` | Гражданство. | Строка | Нет ||
|| `first_name` | Имя. | Строка | Нет ||
|| `last_name` | Фамилия. | Строка | Нет ||
|| `middle_name` | Отчество. | Строка | Нет ||
|| `first_name_lat` | Имя латиницей. | Строка | Нет ||
|| `last_name_lat` | Фамилия латиницей. | Строка | Нет ||
|| `middle_name_lat` | Отчество латиницей. | Строка | Нет ||
|| `gender` | Пол: `male` или `female`. | Строка | Нет ||
|| `actual_to_str` | Дата окончания действия документа в формате `YYYY-MM-DD`. | Строка | Нет ||
|| `birth_date_str` | Дата рождения в формате `YYYY-MM-DD`. | Строка | Нет ||
|| `number` | Номер документа. | Строка | Нет ||
|#

## Описание полей ответа {#response-description}

В ответе с кодом 200 содержится поле:

Поле | Описание | Формат
----- | ----- | -----
`id` | Идентификационный номер сотрудника. | Строка

### 400

В ответе с кодом 400 содержатся поля:

Поле | Описание | Формат
----- | ----- | -----
`code` | Строковый код ошибки. | Строка
`message` | Человекочитаемое сообщение об ошибке. | Строка
`extra` | Дополнительная информация об ошибке. Необязательное поле. | Объект

Структура объекта `extra`:

Поле | Описание | Формат
----- | ----- | -----
`conflict_user_id` | Идентификатор пользователя, с которым возник конфликт. Возможные причины:

* пользователь с таким номером телефона уже существует;

* пользователь с [таким email](*email) уже существует;

* пользователь с таким значением поля `nickname` уже существует в рамках клиента;

* нарушена уникальность других полей. | Строка

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/users
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

    {
        "fullname": "Иванов Илья",
        "phone": "+79990000000",
        "is_active": true,
        "nickname": "ИИлья",
        "cost_centers_id": "123...fef",
        "department_id": "987...ghj",        
        "limits":[
            { 
                "limit_id": "abcdef_taxi",
                "service": "taxi" 
            },
            {
                "limit_id":"abcdef_eats",
                "service":"eats2"
            },
            {
                "limit_id":"abcdef_drive",
                "service":"drive"
            }
        ]   
     }
```

## Примеры ответа {#response-example}

Пример ответа на данный запрос с кодом 200 выглядит следующим образом:

```json
{
    "id": "3caa...3b05e"
}
```

Пример ответа с кодом 400 выглядит следующим образом:

```json
{
    "code": "USER_IS_DELETED_ERROR",
    "message": "user is deleted",
    "extra": {
        "conflict_user_id": "c3ad...89ad"
    }
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.

- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.

- `401` — был передан неверный [OAuth-токен](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).

- `403` — у клиента не хватает прав на выполнение данного запроса:

  - SELECT_CLIENT_HEADER_REQUIRED: в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента). 

  - SELECTED_CLIENT_ACCESS_DENIED: в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.

- `406` — запись с указанными параметрами уже существует.

[*email]: если указан

[*comb]: комбинированный сервис

[*lavka]: сервис устарел, используйте `eats2`

[*travel]: Отели