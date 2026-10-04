---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/promocodes-create.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/promocodes-create.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/promocodes-create.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Создание серии промокодов

Запрос позволяет создать заявку на выпуск новой серии промокодов.

## Синтаксис запроса {#request-syntax}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/promocodes/orders/create
```

**Заголовки запроса**

<!-- source: ru/_includes/concepts/api20/authorization.md -->
- `Authorization: Bearer <OAuth-токен>` 
  Процесс получения токена описан в разделе [Начало работы](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md).
<!-- endsource: ru/_includes/concepts/api20/authorization.md -->

<!-- source: ru/_includes/concepts/api20/client-id.md -->
- `X-YaTaxi-Selected-Corp-Client-Id` — ID клиента из Личного кабинета. Обязателен, если по токену доступно несколько клиентов.
<!-- endsource: ru/_includes/concepts/api20/client-id.md -->
 
<!-- source: ru/_includes/concepts/api20/idempotency.md -->
- `X-Idempotency-Token` — токен идемпотентности, строка [формата UUID](https://ru.wikipedia.org/wiki/UUID#Формат). Одному токену идемпотентности соответствует один заказ, для нового заказа нужно сгенерировать новый токен. Обязательный заголовок.
<!-- endsource: ru/_includes/concepts/api20/idempotency.md -->

**Тело запроса**

Данные о новом заказе промокодов передаются в теле запроса в формате JSON:

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `name` | Имя заказа. | Строка | Нет ||
|| `value` | Номинал одного промокода. | Число | Да ||
|| `count` | Количество промокодов. | Число | Да ||
|| `service` | Сервис, для которого создаются промокоды. Возможные значения: 
- `taxi`: Такси
- `grocery`: Лавка
- `eats`: Еда
- `fuel`: Заправки
- `cargo`: Карго

По умолчанию `taxi`. | Строка | Нет ||
|| `active_from` | Начало действия промокода в формате `ГГГГ-ММ-ДД`. По умолчанию — дата запроса. | Строка | Нет ||
|| `active_until` | Конец действия промокода в формате `ГГГГ-ММ-ДД`. | Строка | Да ||
|| `bin_ranges` | Массив диапазонов BIN-кодов. Массив элементов, где каждый элемент — пара из начального и конечного значений.| Массив | Нет ||
|| `bank_name` | Словарь наименований банка. Список в формате JSON, где ключ — это язык, а значение — наименование банка на этом языке. | Объект | Нет ||
|| `geo_restrictions` | Географические ограничения. | Массив объектов | Нет ||
|| `classes` | Тарифные классы, на которые распространяется промокод. | Массив строк | Нет ||
|#

Структура объекта `bank_name`: {#bank-name}

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `ru` | Название банка на русском языке. | Строка | Да ||
|| `en` | Название банка на английском языке. | Строка | Да ||
|#

Структура элемента массива `geo_restrictions`: {#geo-restrictions}

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `source` | Ограничение для точки отправления. | Объект | Нет ||
|| `destination` | Ограничение для точки назначения. | Объект | Нет ||
|| `max_intermediate_points` | Максимальное количество промежуточных точек. | Число | Нет ||
|#

Структура объектов `source` и `destination`: {#geo-restriction-point}

#|
|| **Поле** | **Описание** | **Формат** | **Обязательность** ||
|| `geo_restriction_id` | Идентификатор геозоны. | Строка | Да ||
|#

Ограничения и их значения:

#|
|| Ограничение | **Такси** | **Заправки**, **Карго** | **Лавка**, **Еда** ||
|| `service` | "taxi" | "fuel", "cargo" | "grocery", "eats" ||
|| `value` | 
Максимальное: 5 000
Минимальное: 100
|
Максимальное: 5 000
Минимальное: 100
|
Максимальное: 30 000
Минимальное: 100 
||
|| `count` |
Максимальное: 1 000
Минимальное: 5
| 
Максимальное: 1 000
Минимальное: 5
| 
Максимальное: 1 000
Минимальное: 5
||
|| `active_until` | Не более 90 дней. Отсчет идет от даты запроса на создание промокодов. {.cell-align-center} | > | > ||
|| `name` |
Максимум: 256
Минимум: 1 
| 
Максимум: 256
Минимум: 1 
| 
Максимум: 256
Минимум: 1 
||
|#

## Описание полей ответа {#response-description}

В ответе могут содержаться следующие поля:

#|
|| **Поле** | **Описание** | **Формат** ||
|| `order_id` | Идентификатор заказа промокодов. | Строка ||
|#

## Пример запроса {#request-example}

```
POST https://b2b-api.go.yandex.ru/integration/2.0/promocodes/orders/create
...
Authorization: Bearer <OAuth-token>
X-YaTaxi-Selected-Corp-Client-Id: <client-id>
X-Idempotency-Token: <токен>

{
  "name": "Новый заказ",
  "value": 220,
  "count": 31,
  "service": "taxi",
  "active_from": "2024-11-22",
  "active_until": "2024-12-01",
  "bin_ranges": [
    ["123400", "123499"],
    ["555000", "555123"]
  ],
  "bank_name": { 
    "ru": "Банк", 
    "en": "The Bank" 
  }
}
```

## Пример ответа {#response-example}

```json
{
  "order_id": "15с...83d"
}
```

## Возможные коды ответа {#response-codes}

Ответ на данный запрос может содержать следующие стандартные HTTP-коды:

- `200` — запрос выполнен успешно.
- `400` — в запросе был передан неизвестный параметр или параметр с недопустимым значением.
