# Open WebUI: ассистенты БП и 1С

Карточки создаются на https://chatgpt.iek.local/workspace/models  
(имена `*-web-helper` **не** передаются в `llm.iek.local/v1` — только UI).

**API (автоматически):** `IEK_LLM_API_KEY` → `POST https://chatgpt.iek.local/api/v1/models/create`

```powershell
python chatbot_intraservice/scripts/create_owui_bp_1c_models.py
python chatbot_intraservice/scripts/create_owui_bp_1c_models.py --dry-run
```

`IEK_LLM_TOKEN` — другой ключ: LiteLLM `llm.iek.local` (`GET /v1/models`, `POST /model/new` для backend-деплоев).
`IEK_LLM_API_KEY` как Bearer на `llm.iek.local` **не работает** (401).

**Важно:** «помощник партнёра ЛК» (`partner-lk-web-helper`) создавался так же через Open WebUI API/Knowledge, не через LiteLLM.
Чатбот HD использует профили `bp_tickets` / `onec_tickets` с локальными корпусами + `iek/confluence-agent`.

Чатбот IntraService ходит в API-модели (`iek/confluence-agent` и т.д.) и подставляет
`openwebui_hint` в историю вызовов для сверки с UI.

## 1. Knowledge

| Name | Содержание |
|:--|:--|
| `support-bp-webkb-safe` | Обезличенный `knowledge/bp/corpus.md` + быстрые ответы БП |
| `support-1c-webkb-safe` | `knowledge/1c/corpus.md` + статьи WEBKB про резерв в пути |

Access: Private. Без ПДн из заявок.

## 2. Models

### БП

| Поле | Значение |
|:--|:--|
| Name | `Разбор заявок БП` |
| Model ID | `support-dep-bp-web-helper` |
| Base Model | как у `support-dep-lk-web-helper` |
| Knowledge | `support-bp-webkb-safe` |
| System | `docs/правила/разбор_заявки_для_исполнителя.md` + блок adm.bp |

URL: https://chatgpt.iek.local/?model=support-dep-bp-web-helper

### 1С

| Поле | Значение |
|:--|:--|
| Name | `Разбор заявок 1С` |
| Model ID | `support-dep-1c-web-helper` |
| Base Model | тот же Base |
| Knowledge | `support-1c-webkb-safe` |
| System | правила 1С: галка «в пути», номера заказа/счёта/эл.заявки |

URL: https://chatgpt.iek.local/?model=support-dep-1c-web-helper

**Не менять** существующие `support-dep-lk-web-helper` и `partner-lk-web-helper`.

## 3. Самообучение (n8n, опционально)

Закрытые заявки → локальный watch → черновик AI-KB → (после ревью) Confluence → обновить Knowledge.

| Шаг | Где |
|:--|:--|
| Watch закрытых | `scripts/pipeline_watch.py` (Task Scheduler) |
| Watch «До просрочки» | `scripts/watch_overdue.py` |
| Черновики | `docs/черновики_статей/` + `knowledge/learned/index.json` |
| n8n webhook | `N8N_WEBHOOK_HELPDESK` в `.env` (если ДИТ заведёт workflow) |

Поток n8n (предложение): IntraService webhook / cron → POST на ноутбук **не нужен**;
ноутбук сам опрашивает HelpDesk. n8n может дергать `publish_kb_draft_confluence`
после approve в Confluence — отдельный workflow.

## 4. Env подсказки

```
IEK_LLM_BP_OWUI_ID=support-dep-bp-web-helper
IEK_LLM_1C_OWUI_ID=support-dep-1c-web-helper
```

## 5. Knowledge в карточках (RAG, не fine-tune)

| Карточка | Knowledge | Источник |
|:--|:--|:--|
| `support-dep-bp-web-helper` | `support-bp-webkb-safe` | `knowledge/bp/corpus.md` |
| `support-dep-1c-web-helper` | `support-1c-webkb-safe` | `knowledge/1c/corpus.md` |
| `support-dep-lk-web-helper` | ФЗ ЛК (ДИТ) | не меняем |
| `partner-lk-web-helper` | `partner-lk-howtos` | P-00…P-17 |

Чатбот HelpDesk вызывает `iek/confluence-agent` + локальный корпус, не id `*-web-helper`.  
После ревью черновика: `python scripts/sync_kb_after_review.py --task-id <id>`.
