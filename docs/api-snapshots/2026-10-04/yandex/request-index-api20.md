---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/request-index-api20.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/request-index-api20.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/request-index-api20.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# API 2.0

Для вызова методов API версии 2.0 используйте хост:

```
https://b2b-api.go.yandex.ru/integration/...
```

Ниже приведен список запросов к сервису Яндекс Такси для версии API 2.0:

Адрес запроса | Метод | Описание
----- | ----- | -----
**Сотрудники** | |
`/2.0/users` | POST | [Создание сотрудника](api20/user-create.md)
`/2.0/users?user_id={user_id}` | GET | [Детальная информация о сотруднике](api20/user-info.md)
`/2.0/users?user_id={user_id}` | PUT | [Обновление данных сотрудника (PUT)](api20/user-update-put.md)
`/2.0/users?user_id={user_id}` | PATCH | [Обновление данных сотрудника (PATCH)](api20/user-update-patch.md)
`/2.0/users/by_phone` | POST | [Детальная информация о сотруднике по номеру телефона](api20/user-phone.md)
`/2.0/users/archive?user_id={user_id}` | POST | [Архивирование сотрудника](api20/user-archive.md)
`/2.0/users` | GET | [Получение списка сотрудников](api20/user-list.md)
`/2.0/users-spending-details` | POST | [Детализация затрат сотрудников](api20/users-spending-details.md)
**Роли менеджеров подразделений** | |
`/2.0/managers/create` | POST | [Создание роли](api20/role-create.md)
`/2.0/managers/update?id={manager_id}` | POST | [Обновление данных сотрудника](api20/role-update.md)
`/2.0/managers/delete?id={manager_id}` | POST | [Удаление роли менеджера подразделения](api20/role-delete.md)
`/2.0/managers/list` | GET | [Получение списка ролей менеджеров подразделения](api20/role-list.md)
**Справочники**  | |
&nbsp;&nbsp;&nbsp;**_ЦЗ и лимиты_** | | 
`/2.0/cost_centers/create` | POST | [Создание центра затрат](api20/cost-center-create.md)
`/2.0/cost_centers/update` | POST | [Обновление центра затрат](api20/cost-center-update.md)
`/2.0/cost_centers/list` | GET | [Получение списка центров затрат](api20/cost-center-list.md)
`/2.0/limits/search` | GET | [Получение списка лимитов](api20/limit-list.md)
`/2.0/limits?limit_id={limit_id}` | GET | [Получение информации о лимите](api20/limit-info.md)
`/2.0/limits/personal?user_id={user_id}` | PUT | [Обновление персонального лимита](api20/limit-update.md)
&nbsp;&nbsp;&nbsp;**_Департаменты/Подразделения_** | | 
`/2.0/departments/list` | GET | [Получение списка департаментов](api20/department-list.md)
`/2.0/departments/create` | POST | [Создание нового департаментов](api20/department-create.md)
`/2.0/departments/update?department_id={department_id}` | PUT | [Обновление данных о департаменте](api20/department-update.md)
`/2.0/departments/archive?department_id={department_id}` | POST | [Удаление департамента](api20/department-archive.md)
`/2.0/departments/limits/taxi?department_id={идентификатор департамента}` | GET | [Получение лимита департамента на поездки](api20/department-limits-get.md)
`/2.0/departments/limits/taxi/update?department_id={идентификатор департамента}` | POST | [Изменение лимита департамента на поездки](api20/department-limits-update.md)
&nbsp;&nbsp;&nbsp;**_Районы_**  | |
`/2.0/geo_restrictions/list` | GET | [Список районов](api20/region-list.md)
`/2.0/geo_restrictions/create` | POST | [Создание нового района](api20/region-create.md)
`/2.0/geo_restrictions/update?id={geo_id}` | POST | [Изменение района](api20/region-edit.md)
`/2.0/geo_restrictions/delete?id={geo_id}` | POST | [Удаление района](api20/region-delete.md)
&nbsp;&nbsp;&nbsp;**_Получение информации о зонах для Такси и Доставки_**  | | 
`/2.0/zoneinfo` | GET | [Получение информации о зоне](api20/zone-info.md)
**Промокоды**  | |
`2.0/promocodes/orders/create` | POST | [Создание серии промокодов](api20/promocodes-create.md)
`2.0/promocodes/orders/cancel?order_id={order_id}` | POST | [Отмена заказа промокодов](api20/promocodes-cancel.md)
`2.0/promocodes/orders/list` | GET | [Список заказов промокодов](api20/promocodes-list.md)
`2.0/promocodes/orders/codes/list?order_id={order_id}` | GET | [Список промокодов в заказе](api20/promocodes-codes-list.md)
`2.0/promocodes/orders/info?order_id={order_id}` | GET | [Получение информации о заказе промокодов](api20/promocodes-info.md)
**Такси**  | |
&nbsp;&nbsp;&nbsp;**_Управление заказом_** | | 
`/2.0/orders/create` | POST | [Создание заказа](api20/order-create.md)
`/2.0/orders/routestats` | POST | [Получение информации о предстоящей поездке](api20/routestats.md)
`/2.0/orders/progress?order_id={order_id}` | GET | [Отслеживание заказа](api20/order-progress.md)
`/2.0/orders/change-destinations?order_id={order_id}` | POST | [Изменение маршрута](api20/change-destinations.md)
`/2.0/orders/cancel?order_id={order_id}` | POST | [Отмена заказа](api20/order-cancel.md)
`/2.0/orders/feedback?order_id={order_id}` | POST | [Отзыв о водителе](api20/order-feedback.md)
&nbsp;&nbsp;&nbsp;**_Информация о заказах_** | | 
`/2.0/orders/info?order_id={order_id}` | GET | [Информация о заказе](api20/order-info.md)
`/2.0/orders/list` | GET | [Список заказов клиента](api20/order-list.md)
`/2.0/orders/active?user_id={user_id}` | GET | [Список активных заказов](api20/order-active.md)
`/2.0/orders/taxi/report` | POST | [Информация о заказах такси для отчета](api20/taxi-report.md)
**Автопарк**  | |
`/2.0/vehicles/bulk-create` | POST | [Массовое создание автомобилей](api20/vehicles-bulk-create.md)
`/2.0/vehicles/bulk-update` | POST | [Массовое обновление автомобилей](api20/vehicles-bulk-update.md)
`/2.0/vehicles/bulk-archive` | POST | [Массовое удаление автомобилей](api20/vehicles-bulk-archive.md)
`/2.0/vehicles/list` | GET | [Получение списка автомобилей](api20/vehicles-list.md)
**Другие сервисы**  | |
`/2.0/orders/tanker` | GET | [Получение списка операций в сервисе "Заправки"](api20/tanker-info.md)
`/2.0/orders/eats/list` | POST | [Получение списка заказов в сервисе "Еда"](api20/food-list.md)
`/2.0/orders/travels/list` | POST | [Получение списка командировок](api20/travels-list.md)
**Список доступных клиентов** | |
`/2.0/auth/list` | GET | [Список доступных клиентов по токену](api20/auth-list.md)

