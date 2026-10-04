---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/cost-center-update.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/cost-center-update.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/cost-center-update.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Обновление центра затрат

Запрос позволяет изменить параметры центра затрат.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/cost_centers/update?id=<идентификатор_центра_затрат>
```

**Заголовок запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->
 
**Параметры запроса**

Запрос содержит следующий параметр:

- `id` — идентификатор центра затрат. 

**Тело запроса**

Данные о заказе передаются в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `name` | Название центра затрат. | Строка | Да ||
|| `default` | Признак, используется ли данный центр затрат по умолчанию (задан при активации сервиса клиенту). | Булево | Да ||
|| `field_settings` | [Список настроек](#field-settings) для каждого поля центров затрат. | Массив объектов | Да ||
|#

Структура элемента массива `field_settings`: {#field-settings}

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
||`id` | id поля.| Строка| Нет||
||`hidden` | Не показывать и не использовать это поле при заказе. | Логическое| Нет||
||`title` | Название поля. | Строка | Да ||
||`required` | Обязательно ли заполнять это поле при заказе. | Логическое| Да||
||`services` | Идентификаторы сервисов, в которых можно использовать это поле при заказе. Возможные значения: 

* `taxi`: Яндекс Go;

* `eats2`: [Яндекс Еда и Яндекс Лавка](*comb);

* `grocery`: [Яндекс Лавка](*lavka);

* `drive`: Каршеринг;

* `tanker`: Яндекс Заправки;

* `cargo`: Грузоперевозки;

* `travel`: [Яндекс Путешествия](*travel);

* `scooters`: Яндекс Самокаты. | Массив строк| Да||
||`format` | Возможные значения: 

- `select` — сотрудник выбирает кост-центр из списка;

- `text` — сотрудник самостоятельно указывает кост-центр в текстовом поле;

- `mixed` — сотруднику доступны выбор кост-центра из списка и свободный ввод в текстовом поле. | Строка| Да||

||`values` | Cписок кост-центров, доступных для сотрудника. Формат списка "кост_центр1","кост_центр2", .... | Массив строк| Да||
|#

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

Поле | Описание | Формат
----- | ----- | -----
`id` | Идентификатор центра затрат. | Строка

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/cost_centers/update?id=2983...3ecf
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>

  {
    "id": "87587...16e6b",
    "name": "Cost center to update",
    "default": false,
    "field_settings": [
      {
        "title": "Центр затрат",
        "required": true,
        "services": [
          "taxi",
          "eats2",
          "cargo"
        ],
        "format": "select",
        "values": [
          "По работе",
          "Не по работе"
        ],
        "id": "cost_center",
        "hidden": true
      },
    ...,
      {
        "title": "Параметр123",
        "required": false,
        "services": [
          "taxi"
        ],
        "format": "text",
        "values": [],
        "id": "d9b2cf97-...-7dbfd2524699",
        "hidden": true
      }
    ]
  }
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
    "id": "2983...3ecf"
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.

- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.

- `403`:

  - SELECT_CLIENT_HEADER_REQUIRED — в запросе не передан заголовок `X-YaTaxi-Selected-Corp-Client-Id` (возвращается в случае, если для токена доступно более одного клиента).  

  - SELECTED_CLIENT_ACCESS_DENIED — в заголовке `X-YaTaxi-Selected-Corp-Client-Id` передан ID клиента, к которому нет доступа у этого логина.

- `404` — объект не найден.

- `406` — обновление центра затрат с переданными параметрами недоступно.

- `409` — конфликт при обновлении центра затрат.

[*comb]: комбинированный сервис

[*lavka]: сервис устарел, используйте `eats2`

[*travel]: Отели