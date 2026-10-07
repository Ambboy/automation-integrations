---
metadata:
  - name: generator
    content: Diplodoc Platform v5.61.0
alternate:
  - https://taxi__business-api.docs-viewer.yandex.ru/en/concepts/api20/roles.md
  - https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/roles.md
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/roles.md
    type: text/markdown
    title: Markdown version
  - href: https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt
    rel: describedby
---
> **Documentation Index:** Fetch the complete configuration index at https://taxi__business-api.docs-viewer.yandex.ru/ru/llms.txt

# Роли

Роль определяет уровень доступа к управлению и редактированию подразделения.

В Личном кабинете поддерживаются три роли:

- **Менеджер департамента**

    В пределах доверенного ему подразделения может:
    - управлять сотрудниками и поездками;
    - выгружать отчеты;
    - добавлять вложенные подразделения и роли.

    Не может:
    - видеть подразделения, которые находятся выше или в параллельной ветке организационной структуры;
    - добавлять центры затрат;
    - редактировать комментарий водителю;
    - просматривать баланс при внесенной предоплате;
    - просматривать финансовые документы.

- **Секретарь департамента**

    - Может просматривать вкладки «Поездки» и «Заказ».
    - В рамках доверенного ему подразделения может:
        - заказывать такси;
        - просматривать карточки заказов;
        - отменять заказ.

- **Клиентский менеджер**

    Может выполнять в Личном кабинете те же действия, что и администратор, но не имеет доступа в раздел «Баланс».
