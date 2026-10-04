---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/quickstart.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/quickstart.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Начало работы

Чтобы начать работать с Яндекс Такси:

1. Получите токен для отправки запросов к API:

    1. Войдите в [Кабинет Корпоративного Клиента Яндекс&#160;Такси](https://business.taxi.yandex.ru/) с помощью почты, к которой привязан аккаунт в Яндекс Go для бизнеса.

    2. Перейдите на вкладку **Профиль компании**.

    3. Нажмите кнопку **Получить токен**.

    4. На странице oauth.yandex.ru нажмите кнопку **Войти как <ваш логин>**. Вы будете перенаправлены в Кабинет Корпоративного Клиента Яндекс&#160;Такси.

    5. В блоке **Токен сгенерирован** будет отображен ваш OAuth-токен.
    
2. Токены для доступа к API действуют ограниченное время, после которого становятся недействительными. Если время жизни токена истекло — получите новый токен в [Кабинете Корпоративного Клиента Яндекс&#160;Такси](https://business.taxi.yandex.ru/).
    
    {% note info %}
    
    Если токен утерян, для перевыпуска обратитесь в [Яндекс&#160;Паспорт](https://passport.yandex.ru).
    
    {% endnote %}
    
3. Используйте OAuth-токен во всех запросах к API. Передавайте токен в заголовке: `Authorization: Bearer <значение вашего токена>`.
    
    {% note info %}
    
    Для работы с API 2.0 используйте хост `http://b2b-api.go.yandex.ru`.
    
    {% endnote %}
    
4. Если один аккаунт в Яндекс ID имеет доступ к нескольким личным кабинетам, для всех запросов нужно указывать заголовок `X-YaTaxi-Selected-Corp-Client-Id` следующим образом:
  
   1. В личном кабинете перейдите на вкладку **Профиль компании**.
   
   2. Передайте в заголовок ID клиента.

5. [Укажите информацию о кост-центрах](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/cost-center-create.md).

6. Создайте [роли пользователей](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/role-create.md).

7. Заведите [учетные записи пользователей](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/user-create.md).

## Заказ поездки {#section_gyz_b4t_5hb}

После того, как вы получили токен и указали информацию о ваших пользователях, вы можете использовать API Яндекс&#160;Такси для заказа поездок.

Процедура заказа выглядит следующим образом:

1. [Узнайте цену и условия предстоящей поездки](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/routestats.md).

2. Создайте [заказ](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-create.md).

3. При необходимости [отмените заказ](https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/order-cancel.md).
