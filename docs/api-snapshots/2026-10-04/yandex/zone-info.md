---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/zone-info.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/zone-info.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/zone-info.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Получение информации о зоне

Получение информации о тарифах и дополнительных опциях в конкретной зоне. 

Информация о зоне передается в виде координат в `lat` и `lon`. При невалидных координатах выдается ошибка "Zone not found". 

Язык можно сменить параметром `Accept-Language`.

## Синтаксис запроса {#request-syntax}

```
GET http://b2b-api.go.yandex.ru/integration/2.0/zoneinfo?lat=<широта>&lon=<долгота>
```

**Заголовки запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->
 
- `X-Request-Language: en`

**Параметры запроса**

Запрос должен содержать следующие обязательные параметры:
    
- `lat` — широта точки, принадлежащей зоне.
    
- `lon` — долгота точки, принадлежащей зоне.


## Описание полей ответа {#response-description}

В ответе содержатся поля:

Поле | Описание | Формат
----- | ----- | -----
`tariff_classes` | [Массив тарифов](#tariff_classes). | Массив объектов

Структура элемента массива `tariff_classes`: {#tariff_classes}

Поле | Описание | Формат
----- | ----- | -----
`name` | Название тарифа латинскими буквами. | Строка
`name_translate` | Локализованное название тарифа. | Строка
`supported_requirements` | [Массив требований](#supported_requirements). | Массив объектов

Структура элемента массива `supported_requirements`: {#supported_requirements}

Поле | Описание | Формат
----- | ----- | -----
`name` | Нззвание требования (латинскими буквами). | Строка
`label` | Название требования. | Строка
`glued` | Применяется к пожеланиям типа `select` в тарифах. Если равно `true`,то  пожелание прикрепляется к верхней части карточки саммари и становится обязательным для выбора перед созданием заказа. Локально блокируется кнопка **Заказать**, пока пользователь не выберет значение. Поле не обязательно для заполнения, если задано `optional_glued: true`.| Булево
`type` | Тип требования. Возможные значения: `select`, `boolean`. | Строка
`multiselect` | Используется для пожеланий в тарифах, где требуется множественный выбор. Если значение равно `true`, пользователь может выбрать несколько опций из списка. Также задает ограничение на максимальный вес выбранных опций (`max_weight`) и количество выбранных опций (`max_count`). | Булево
`max_weight` |  Максимальный суммарный вес выбранных опций. Используется для ограничения выбора, если опции имеют вес. Например, для детских кресел: <br/>- Кресло "infant" может иметь вес 2.<br/>- Кресло "chair" может иметь вес 2.<br/>- Бустер "booster" может иметь вес 1.<br/>Суммарный вес выбранных опций не должен превышать значение `max_weight`. | Число
`select` | [Описание требования](#select). Указывается только для требований с типом `select`.| Объект

Структура объекта `select`: {#select}

Поле | Описание | Формат
----- | ----- | -----
`options` | [Массив доступных опций](#options). | Массив объектов
`type` | Тип значения. | Строка

Структура элемента массива `options`: {#options}

Поле | Описание | Формат
----- | ----- | -----
`name` | Название опции латинскими буквами. | Строка
`label` | Название требования, к которому относится опция. | Строка
`title` | Локализованное название опции. | Строка
`weight` | Вес опции. | Число
`max_count` | Максимальное количество опций, которые можно выбрать. | Целое число
`value` | Значение опции. | Число

## Пример запроса {#request-example}

```
GET http://b2b-api.go.yandex.ru/integration/2.0/zoneinfo?lat=32.093320&lon=34.798363
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
```

## Пример ответа {#response-example}

Пример ответа на данный запрос выглядит следующим образом:

```json
{
  "tariff_classes": [
    {
      "name": "business",
      "name_translate": "Бизнес",
      "supported_requirements": [
        {
          "name": "quiet_ride",
          "label": "Поездка в тишине",
          "glued": false,
          "type": "boolean"
        },
        {
          "name": "childchair_v2",
          "label": "Детское кресло",
          "glued": false,
          "type": "select",
          "multiselect": true,
          "max_weight": 2,
          "select": {
            "options": [
              {
                "name": "booster",
                "label": "22–36 кг",
                "title": "Бустер, 6–12 лет",
                "weight": 1,
                "max_count": 2,
                "value": 7
              }
            ],
            "type": "number"
          }
        }
      ]
    }
  ]
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
- `404` — зона не найдена, проблема на стороне клиента.
