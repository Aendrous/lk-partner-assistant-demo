# Spec: чатбот, встречающий пользователей (L0)

Статус: **in progress (часть 1 — KB-ответ)** · Iteration 3 в [`../ROADMAP.md`](../ROADMAP.md)

**Контекст деки:** сейчас этап **чатбот в IntraService** (разбор заявок). Этот документ — следующий слой: чат **до** заявки, чтобы часть обращений закрывалась консультацией, а остальное попадало в IntraService уже «собранным».

## Background

Сейчас в коде — ассистент **исполнителя** по уже созданной заявке (этап IntraService).  
Продуктовые docs (`docs/README.md`, prompts) уже описывают путь «вопрос → KB → заявка».  
**L0 / встречающий чат** = сотрудник ещё не обязан открывать HelpDesk сам.

## Goals

1. Сотрудник задаёт вопрос в чате (канал MVP: Streamlit L0 / internal WEB).
2. Бот ищет ответ в WEBKB «быстрые ответы» + локальный corpus (те же источники, что L1).
3. Если уверенный ответ — текст + ссылки.
4. Если не смог / «не помогло» — **создаёт заявку** в IntraService:
   - правильный **ServiceId** (лист каталога WEB, см. § Сервисы);
   - понятное **Name/Description** из истории чата;
   - **вложения** (скриншоты) — часть 2;
   - возврат номера и URL `Task/View/{id}`.
5. Опционально: цикл уточнений по `docs/prompts/матрица_уточнений.md`.

## Non-Goals (MVP)

- Замена всего диспетчера и L2 CRM.
- Авто-take и скрытые комментарии L1 HD (это другой контур).
- Встройка JS-виджета **внутрь** страниц IntraService без доработки вендора.
- MCP Confluence из OWUI как единственный транспорт.

## Интеграция с IntraService: что возможно

### API (уже есть в репо)

| Операция | Endpoint | Код |
|----------|----------|-----|
| Каталог сервисов для создания | `GET /api/service?for=createtask` | `intraservice.list_services_for_create` |
| Defaults формы | `GET /api/newtask?serviceid=` | `newtask_defaults` |
| **Создать заявку** | `POST /api/task` | `create_task` (+ `UserEmail`) |
| Вложения | upload → `FileTokens` | часть 2 |

Создание заявки **не требует** UI `selectservice` — бот сам выбирает `ServiceId` и шлёт POST.

### Можно ли «запускать чатбот» на `…/task/selectservice?…create=true`?

**Нет, бесшовно из коробки — нельзя.**

Страница выбора сервиса — штатный UI IntraService. У API IEK **нет**:

- hook / webhook «перед созданием заявки»;
- iframe/embed slot в `selectservice`;
- события «открыли форму создания».

Поэтому чатбот **не стартует сам** при открытии `selectservice`. Варианты:

| Вариант | UX | Сложность | Рекомендация |
|---------|-----|-----------|--------------|
| **A. Чат вместо selectservice** | Кнопка «Спросить помощника» / «Создать заявку» ведёт на наш чат; если KB не помогла — бот создаёт заявку через API | Средняя | **MVP** |
| **B. Deep-link после чата** | Из чата: «Создать самому» → `selectservice` или сразу `Task/View` после API-create | Низкая | Дополнение к A |
| **C. Кастомизация IntraService** | Вендор/админы вставляют виджет или редирект с `selectservice` | Высокая, зависит от HD | Позже, если ДИТ договорится |
| **D. Bookmarklet / browser extension** | Перехват create=true | Хрупко | Не для прода |

**Решение для части 1–2:** вариант **A** — отдельный L0-чат (Streamlit/WEB). Заявка создаётся **API**, минуя `selectservice`. Страница selectservice остаётся для ручного пути «я знаю сервис».

Опционально позже: на портале / в HD кнопку «Новая заявка» заменить ссылкой на L0 (редирект) — это уже орг. решение, не API.

## Сервисы WEB (как на скрине selectservice)

Дерево HelpDesk (проверено `GET /api/service?for=createtask`, 2026-09):

```
800 … → 712 WEB - сервисы и сайты
         ├─ 715 Корпоративный портал (corp.iek.ru)     → ServiceKey kp
         ├─ 713 Личный кабинет партнера (lk.iek.ru)
         │     ├─ 731 Инцидент                          → lk (инцидент)
         │     └─ 732 Запрос на обслуживание            → lk (по умолчанию)
         ├─ 827 Бизнес платформа (Портал ЦКГ)
         │     └─ 833 Запрос на обслуживание            → bp
         ├─ 714 Портал перевозчиков (logistic.iek.ru) → logistics
         ├─ 850 Портал экспедиторов                   → expeditors
         ├─ 716 QUART (ТКП, база испытаний)           → quart
         └─ 740 iPrice                                → iprice
```

Для L0 создавать заявку на **листовой** сервис (731/732, 833, 715, 714…), не на папку 712.

Маппинг: `docs/интеграции/service_catalog.json` + `src/service_routing.py`.

## Часть 1 (сейчас) — объём

1. Модуль `src/l0_chat.py`: вопрос → REST prefetch + corpus → ответ / «не знаю».
2. CLI `scripts/l0_ask.py`: smoke без UI.
3. Черновик заявки (JSON) при низком confidence — **без** POST по умолчанию (`--create` отдельно).
4. Обновление этой спеки + каталога сервисов.
5. **Разбор существующей заявки HD** в L0: `review_ticket` / UI «Разобрать + уточнить» — dry-run L1 (без поста) + уточняющие вопросы по матрице; чат продолжает диалог в контексте заявки. Пост / take / learn — вкладка «Запуск».

## Technical plan

| Компонент | Подход |
|-----------|--------|
| Оркестрация | `src/l0_chat.py` — **не** раздувать `analyze_and_comment.py` |
| KB | `confluence_tools.prefetch` + `assistants.load_corpus` + LLM краткий ответ |
| Уточнения | `docs/prompts/уточняющие_вопросы.md` + матрица в промпте L0 |
| Разбор HD | `review_ticket` → `pipeline.run_ticket_pipeline(post=False)` + `ask(ticket_context=…)` |
| Роутинг сервиса | `service_routing.infer_contour` + `service_catalog.json` |
| Создание заявки | `intraservice.create_task` (часть 2: вложения) |
| UI MVP | Streamlit вкладка **«L0 чат (сотрудник)»** в `app.py` (+ CLI `l0_ask.py`) |

## Acceptance criteria

### Часть 1
- [x] Вопрос с ответом в corpus/WEBKB → текст + ссылки, заявка **не** создана.
- [x] Нет ответа → черновик Name/Description/ServiceId (dry-run).
- [x] Каталог WEB leaf ServiceId заполнен в `service_catalog.json`.
- [x] Streamlit вкладка **«L0 чат (сотрудник)»** — чат + кнопка создания заявки.
- [x] L0: номер заявки → преданализ + уточняющие вопросы в чате (`--task-id` / UI).

### Часть 2
- [ ] `--create` / кнопка → реальная заявка + URL.
- [ ] Скрин пользователя → вложение.
- [ ] SSO / UserEmail заявителя.
- [ ] Документация: ARCHITECTURE + Confluence project page § L0.

## Open decisions

1. Канал MVP: **Streamlit L0** (внутр.) → позже corp/TG.
2. SSO: для CLI — `UserEmail` аргументом; для WEB — из сессии.
3. Создавать заявку только по явному «Создать заявку» (не молча).

## References

- Confluence (VLAN/VM + L0, expand): [pageId 124642475](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642475) · `docs/заявки/vlan_vm_l0_checklist.md`
- `docs/README.md` — ключевой сценарий продукта  
- `docs/prompts/формирование_заявки.md`, `матрица_уточнений.md`  
- `docs/интеграции/intraservice_api.md`  
- `docs/схемы/bpmn_чатбот_l1.md` — flowchart вопрос → KB → заявка  
- Презентация: `ИИ в поддержке 2026 v2.pptx`
