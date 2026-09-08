# Интеграция с HelpDesk IntraService (helpdesk.iek.local)

**Документация вендора:** [IntraService API v5.42 (PDF)](https://intraservice.ru/upload/iblock/1ea/ktnvaryw9iceol8dz0cao6hhlnjgq8rj/IntraService_API_v5_42.pdf)  
**Обзор API:** https://intraservice.ru/overview/integration-api/  
**Типовой IT-процесс:** https://intraservice.ru/examples/it/

## Есть ли API для автосоздания заявки?

**Да.** IntraService предоставляет REST API.

| Операция | Метод | Endpoint |
|:--|:--|:--|
| Список сервисов (для создания) | GET | `/api/service?for=createtask&fields=Id,Name,Code` |
| Шаблон заявки (defaults) | GET | `/api/newtask?serviceid={id}&tasktypeid={id}` |
| **Создать заявку** | **POST** | **`/api/task`** |
| Получить заявку | GET | `/api/task/{id}` |
| **Изменить заявку (статус)** | **PUT** | **`/api/task/{id}`** |
| Справочник статусов | GET | `/api/taskstatus` |
| Текущий пользователь API | GET | `/api/user?getcurrentuserinfo=true` |
| Комментарий | поле `Comment` в POST/PUT | (см. PDF) |

**Авторизация:** HTTP Basic (логин/пароль сервисной УЗ API).  
**Формат POST/PUT:** только JSON, `Content-Type: application/json`.

База для IEK: `https://helpdesk.iek.local` → API base обычно `https://helpdesk.iek.local/api`.

### Чтение заявки из репозитория

В корневом `.env`:

```
INTRASERVICE_BASE_URL=https://helpdesk.iek.local
INTRASERVICE_USER=login_without_domain
INTRASERVICE_PASSWORD=***
```

```bash
python scripts/intraservice_get_task.py 693437
python scripts/intraservice_get_task.py 693437 --raw
```

Логин для Basic Auth — обычно **без** `@iek.ru`. Windows SSO на `/api` не работает.

## Обязательные поля создания (из API)

| Поле | Обяз. | Назначение |
|:--|:--|:--|
| `Name` | + | Название заявки |
| `ServiceId` | + | Сервис (ветка каталога HelpDesk) |
| `StatusId` | + | Обычно «Открыта» (из шаблона `/api/newtask`) |
| `PriorityId` | + | Приоритет |
| `TypeId` | + | Тип заявки (инцидент / запрос / …) |
| `Description` | рек. | Описание |
| `UserEmail` | +* | Email заявителя (*для создания «от лица») |

Рекомендуемый алгоритм вендора:

1. `GET /api/newtask?serviceid=…&tasktypeid=…` — значения по умолчанию.
2. Подставить `Name`, `Description`, `UserEmail`, приоритет, вложения.
3. `POST /api/task` с полями Task (не оборачивать в `{ "Task": … }`).

Доп. поля: `Field{id}` (например `Field8`), `FileTokens` после загрузки файлов, `ExecutorIds`, `ObserverIds`.

### Связанные / подчинённые заявки

- Поиск: `GET /api/task?search={заказ|счёт|GUID}&pagesize=20`
- Подчинить: `PUT /api/task/{childId}` с телом `{"ParentId": <id более ранней>}`
- Наблюдатели: `PUT /api/task/{id}` с `{"ObserverIds": "id1, id2, …"}` (полный список, не затирать существующих)
- Пайплайн: при совпадении по заказу/счёту/эл.заявке/GUID более поздняя → child; Creator ранней → Observer поздней (`src/related_tasks.py`).

### События / webhook просрочки — **нет в API IEK**

Проверено на `helpdesk.iek.local/api`: `/webhook`, `/webhooks`, `/event(s)`, `/subscription`, `/escalation`, `/automation` → **404**.  
Робот «До просрочки» пишет **в lifetime заявки** (Comments) и шлёт **email** — это не push в наш чатбот.

Варианты без poll каждые 5 мин на ноутбуке:

1. **Правило IntraService** (админы HD): второе действие эскалации — email на mailbox → **n8n** парсит номер заявки → HTTP на агент / очередь.
2. **n8n / сервер** внутри сети: cron раз в 10–15 мин дергает `watch_overdue.py` (не ноутбук).
3. Локально: Task Scheduler с **`pythonw.exe` + Hidden** (`scripts/install_scheduler.ps1`, интервал по умолчанию 15 мин) — без окна CMD.


## Создание от сотрудника по email

В теле POST дополнительно:

- `UserEmail` — всегда;
- если пользователя нет в IntraService — также `UserPassword`, `UserConfirmPassword` (и опционально ФИО, компания) **или** лучше заранее иметь УЗ и передавать только `UserEmail` / `CreatorId`.

Для чатбота на corp.iek.ru: брать email из SSO-сессии; создавать заявку сервисной УЗ с `UserEmail` заявителя.

## Что нужно системе HelpDesk для автосоздания (чеклист IEK)

1. **Сервисная учётка API** с правом создавать заявки в нужных сервисах.
2. **Справочник маппинга** `ServiceKey → ServiceId, TypeId, default PriorityId, StatusId` (заполнить с стенда).
3. Каталог сервисов: `GET /api/service?for=createtask`.
4. Решение по файлам: upload → `FileTokens` в заявку (скриншоты из чата).
5. URL карточки: `https://helpdesk.iek.local/Task/View/{Id}`.
6. «Мои заявки»: deep-link фильтра по заявителю (как в текущем ассистенте).

## Пример тела POST (черновик)

```http
POST https://helpdesk.iek.local/api/task
Authorization: Basic ***
Content-Type: application/json

{
  "Name": "ЛК: ошибка 502 на lk.iek.ru с 14:05 МСК",
  "ServiceId": 123,
  "TypeId": 1,
  "StatusId": 1,
  "PriorityId": 2,
  "Description": "## Суть\nНе открывается ЛК...\n## Чат\n...",
  "UserEmail": "ivanov@iek.ru"
}
```

*(ServiceId/TypeId/StatusId/PriorityId — подставить из вашего IntraService.)*

## Маппинг ServiceKey → логика (заполнить Id на стенде)

| ServiceKey | Когда | ServiceId | TypeId | Примечание |
|:--|:--|:--|:--|:--|
| `kp` | corp/kp вход, права КП | TBD | TBD | WEB — КП |
| `lk` | lk.iek.ru, заказы, НС, УПД | TBD | TBD | WEB — ЛК |
| `bp` | bp.iek.ru API | TBD | TBD | Перепелкин / WEB |
| `vpn` | VPN, Ideco | TBD | TBD | IT |
| `mail` | Exchange | TBD | TBD | IT |
| `other` | не классифицировано | TBD | TBD | общий WEB/IT |

Сохранить актуальные Id в `service_catalog.json` после опроса API.

## Связь с процессом IT (examples/it)

Типовой lifecycle IntraService:

1. Клиент создаёт (статус Открыта) ← **чатбот**
2. Исполнитель → В работе
3. Выполнена
4. Клиент закрывает / возвращает

При нехватке данных исполнитель может вернуть «Требует уточнения» — поэтому бот должен собрать минимум **до** создания.

## Взятие в работу и смена статуса (чатбот)

`PUT /api/task/{id}` с полем `StatusId`. В справочнике IEK **нет** статуса «В работе».

| Ключ в коде | StatusId | Имя в HelpDesk |
|:--|:--|:--|
| `open` | 31 | Открыта |
| `in_progress` | **27** | **В процессе** (эквивалент «взять в работу») |
| `transferred` | 38 | Передана исполнителю |
| `awaiting_reply` | **46** | **Ожидание ответа пользователя** (нужен Comment) |
| `awaiting_reply_autoclose` | 120 | Ожидание ответа с автозакрытием |
| `done` | 29 | Выполнена |
| `closed` | 28 | Закрыта |
| `l1` | 121 | 1 Линия ТП |

Взятие в работу: `StatusId=27` + `ExecutorIds` с Id текущего API-пользователя (`GET /api/user?getcurrentuserinfo=true`).

```bash
python scripts/take_task.py 123456
python scripts/take_task.py 123456 --awaiting-reply --comment "Уточните URL и время МСК"
python scripts/take_task.py --list-statuses
```

Переход может быть запрещён бизнес-процессом сервиса — тогда API вернёт ошибку; бот должен показать её оператору.
