# BPMN / flowchart — чатбот L1 IEK

## Основной поток

```mermaid
flowchart TD
  Start([Пользователь открыл чат]) --> Greet[Приветствие и быстрые подсказки]
  Greet --> Ask[Вопрос пользователя]
  Ask --> Search{Есть ответ в AI-Библиотеке или WEBKB?}
  Search -->|Да| Answer[Пошаговый ответ и ссылки]
  Answer --> Feedback{Помогло?}
  Feedback -->|Да| EndOk([Вопрос решён])
  Feedback -->|Не помогло| Route
  Search -->|Нет| Route

  Route{URL/контур ясен?}
  Route -->|Нет, ЛК или API| LkVsBp[Уточнить: lk.iek.ru или bp.iek.ru?]
  Route -->|Нет, иное| WhichSvc[Какой сервис и URL?]
  Route -->|Да| Cat
  LkVsBp --> Cat
  WhichSvc --> Cat

  Cat[Определить категорию проблемы]
  Cat --> Cycle[Цикл уточнений: шаг 1..N по матрице]
  Cycle --> Enough{Обязательные поля есть?}
  Enough -->|Нет и шаги не исчерпаны| Cycle
  Enough -->|Да или пользователь согласен| Draft[Черновик заявки Name Description ServiceKey]
  Draft --> Confirm{Подтверждение создания?}
  Confirm -->|Отмена| Ask
  Confirm -->|Создать| Map[Маппинг ServiceKey в ServiceId]
  Map --> ApiGet[GET api/newtask]
  ApiGet --> ApiPost[POST api/task с UserEmail]
  ApiPost --> Created[Номер заявки и ссылка HelpDesk]
  Created --> EndTicket([Заявка в IntraService])

  Ask --> TicketBtn[Кнопка Создать заявку из чата]
  TicketBtn --> Route
```

## Длина цикла по сервису

| ServiceKey | Типичные категории | Шагов | Вопросов |
|:--|:--|:--:|:--:|
| kp | AUTH, ACCESS, SMS_2FA | 2 | 2–4 |
| lk | AUTH, ORDERS, API_LK, NS_RESERVE, DOCS_UPD | 2–3 | 2–5 |
| bp | AUTH_KEY, API_BP | 2–3 | 2–5 |
| vpn / mail / other | CONNECT, DISKS, DELIVERY… | 2 | 2–4 |

Детали вопросов: `prompts/матрица_уточнений.md`.
