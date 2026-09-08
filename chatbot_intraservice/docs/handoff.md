# Handoff — последняя сессия

Шаблон для смены контекста (человек ↔ агент). Обновлять в конце содержательной сессии.

## Goal

Управление разросшимся проектом: vibe-coding практики (AGENTS.md, архитектура, roadmap, speка L0).

## Done

- Root + `chatbot_intraservice/AGENTS.md`
- `docs/ARCHITECTURE.md`, `ROADMAP.md`, `specs/L0_employee_chatbot.md`
- `docs/scripts_map.md`, `.cursor/rules/chatbot-intraservice.mdc`
- README: блок «С чего начать»
- **CRM самообучение:** `knowledge/crm/qa.md` (14 Q&A), `build_crm_corpus.py`, WEBKB [124642008](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642008) — Expand+Code для копирования ответов; `docs/pipeline/самообучение_crm.md`
- **1С Солярис:** база в пространстве **1C** под [Первая линия](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=39887131) — хаб [124642089](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642089); `publish_1c_l1_confluence.py`; Promote → pageId **124642091**
- **Закрытие HD:** `error_stage_ru` + `root_cause_ru`; Field2229/3061 (`closure_taxonomy.py`)
- **1С ТН ОП-2765:** профиль `onec_logistics_tn`, `onec_analyze_scope` (было `logistics_tn`) (#699796, #699810); Confluence [124642131](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642131) · `publish_1c_logistics_tn_confluence.py`
- **L0 (встречающий чат), часть 1:** спека `docs/specs/L0_employee_chatbot.md` — selectservice **не** запускает бота; заявка через `POST /api/task`. Каталог WEB leaf (715/732/833/714…). CLI: `python scripts/l0_ask.py "…"`. Streamlit: вкладка **«L0 чат (сотрудник)»** в `app.py`. Модуль `src/l0_chat.py`.
- **VLAN/VM чеклист для ДИТ:** [124642475](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642475) — expand: чеклист + спека L0 + черновик `дит_деплой_чатбота_n8n.md`; git: `docs/заявки/vlan_vm_l0_checklist.md`, `publish_vlan_l0_confluence.py`.
- **Преданализ (Качанов Ю.А.):** тип HD + сервис + важность в строке скрытого комментария; важность авто-повышение при `--post`. `service_routing.check_service(prior=)`.
- **Learn #699802:** reject галлюцинаций LK-15-SUP; черновик LK-16; `pick_resolution` не берёт текст заявителя.
- **L0 + разбор заявки:** `l0_chat.review_ticket` / UI «Разобрать + уточнить» — L1 preview без поста + уточнения в чате; «Запуск» остаётся для post/take/learn.
- **watch_user_reply (2026-09-04):** подтверждение («спасибо/можно закрывать») → **29** + скрытый; доп. вопрос из 46/120 → **38** + скрытый с правилом; nudge исполнителя (≥20 ч) → **120** + скрытый. Примеры #700891/#701113/#700844/#700796.
- **1С scope `all` + жёсткие пропуски (2026-09-07):** `onec_analyze_scope=all` (default+local); `assistants.skip_onec_task()` — предразбор не делается для «запрос на изменение» (TypeId 1010) и «в работе» (StatusId 27). UI: тумблер «1С: разбирать все заявки».
- **Автообучение — решение исполнителя (2026-09-07):** при `require_closed_for_auto_learn` в `learn_from_task_data` требуется публичный ответ исполнителя (`performer_resolution_present`), не fallback на summary/название.
- **watch_user_reply статусы (2026-09-07):** «уточняющий вопрос» больше не возвращает в 38 (только «проблема не решена»); отдельный тумблер `watch_user_reply_crm_status_changes` (default false) — бот не меняет статусы CRM.
- **Streamlit bug (2026-09-07):** `l0_email` — pending-ключ, чтобы не падать на `StreamlitAPIException`.

- **Преданализ — компактный формат + short URL (2026-09-07):** Предзаголовок -> награтив -> Ранее от заявителя {lesson} {short_url} | Похожее: до 3 (без дубля контекста) -> Этап/Причина -> проверки -> Комментарий -> Рекомендации (только при mismatch). short url через INTRASERVICE_SHORT_TASK_URL_TEMPLATE. Unit test_hidden_comment_format + smoke 701453 pass; --dry-run требует llm_client.py + LLM.
## Current state

- **Планировщик Windows (основной контур):** задачи `IEK-IntraService-Watch*` / GapDigest / DraftsReview — Ready. UI: `IEK-IntraService-StreamlitUI` (AtLogOn) + скрипт `scripts/start_streamlit_ui.ps1`. Порт **8502** проверен HTTP 200.
- **n8n:** опционален; `ECONNREFUSED :8765` если нет `n8n_http_server` / устарел IP ноутбука. Не нужен, пока крутит Scheduler.
- **Этап деки:** IntraService L1 HD + AI-KB. L0 MVP: вкладка Streamlit + `l0_ask.py`.
- Learn: `iek/gpt-oss-120b` (confluence-agent снят с `/v1/models`).

## Next step

1. Журнал багов на Confluence обновлён (124642389, 2026-09-04 watch_user_reply).
2. Открыть http://localhost:8502/ — панель + вкладка L0.
3. Probe `_*.py` не тащить в коммит без нужды.

## Blockers / decisions needed

- Нужно ли синхронизировать ROADMAP на Confluence page `124640056`?
- n8n workflow оставить выключенным / поправить IP, раз основной контур — Scheduler?

## Tried / pitfalls

- PPTX «ИИ в поддержке 2026» не использует слово L0 — там L1 консультант/диспетчер и L2.
- OWUI MCP ≠ LiteLLM API для HD-бота.
- n8n только шлёт HTTP POST; без `n8n_http_server :8765` на хосте бота — `connection refused` (не баг LLM).
