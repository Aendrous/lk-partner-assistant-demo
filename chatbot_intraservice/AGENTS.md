# AGENTS.md — chatbot_intraservice

Операционная памятка для агента и человека. Держать **коротко**; детали — в `docs/`.

## Overview

Пакет **«IEK: Помощник сотрудника»** внутри монорепо.

| Сейчас (этап по деке «ИИ в поддержке 2026») | Дальше |
|---------------------------------------------|--------|
| **Внедрение в IntraService**: бот разбирает заявки для **исполнителя** (скрытый комментарий, watch, AI-KB) | **Чатбот, встречающий пользователей**: вопрос → KB → если не смог → создаёт заявку в нужном сервисе со скринами и описанием |

Оба — один продукт «Помощник сотрудника»; разные точки входа. Не путать с помощником партнёра ЛК в корне репо.

Карта продукта: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · итерации: [`docs/ROADMAP.md`](docs/ROADMAP.md) · старт человека: [`README.md`](README.md).

## Структура кода

```
chatbot_intraservice/
  app.py                 # Streamlit — панель оператора (не чат сотрудника)
  config/                # settings.default.json + local (не в git секреты)
  src/                   # ядро (импортируется scripts/)
  scripts/               # CLI / watch / publish / тесты — см. docs/scripts_map.md
  knowledge/             # corpus ЛК/БП/1С + learned/
  docs/                  # правила, prompts, pipeline, specs
  pipeline/              # runs/, digests/, IDEA_RAG_LEARNING.md
  debug/                 # артефакты разбора (_analysis_*.json) + probe файлы
```

### Ключевые модули `src/`

| Модуль | Зачем |
|--------|--------|
| `intraservice.py` | API HelpDesk |
| `assistants.py` | роутер профилей / моделей |
| `attachments.py` | скрин / msg / PDF·DOC → смысл |
| `analyze` через `scripts/analyze_and_comment.py` | ядро разбора заявки |
| `debug_artifacts.py` | централизованные пути к артефактам разбора в debug/ |
| `analysis_artifact.py` | чтение артефактов (debug/ → root → pipeline/) |
| `pipeline.py` | прогон + артефакты |
| `kb_learning.py` + `learn_*` / `kb_gap*` / `kb_dedup` | самообучение AI-KB |
| `confluence_client.py` | REST Confluence (не MCP OWUI) |
| `confluence_tools.py` | REST prefetch (аналог MCP search/get_page) |
| `prompt_store.py` | редактируемые промпты + корпуса (UI Streamlit) |
| `service_filter.py` / `service_routing.py` | контуры ЛК/БП/CRM |

## Команды

```powershell
cd chatbot_intraservice
pip install -r requirements.txt
copy .env.example .env   # или из корня монорепо

streamlit run app.py --server.port 8502
python scripts/analyze_and_comment.py <task_id> [--post] [--learn]
python scripts/watch_new.py
python scripts/n8n_run.py watch_new          # то же для n8n Execute Command
python scripts/n8n_http_server.py            # HTTP API для n8n
python scripts/pipeline_watch.py --dry-run
python scripts/test_kb_draft_quality.py
python scripts/test_attachments_extract.py
python scripts/test_learn_llm.py
```

Секреты: `IEK_LLM_TOKEN`, `INTRASERVICE_*`, `CONFLUENCE_*` — в `.env`, не в git.

LLM API: `https://llm.iek.local/v1` (`iek/gpt-oss-120b` + REST prefetch Confluence; fallback тот же).  
Имена `*-web-helper` из chatgpt.iek.local **нельзя** передавать как `model` в LiteLLM.  
`iek/confluence-agent` снят с прокси (2026-09) — `llm_client.resolve_model()` подставляет доступную модель.

## Правила кодирования

- Правки минимальные и по задаче; не рефакторить «заодно» весь пакет.
- Новые скрипты: ясное имя; одноразовые зонды — префикс `_` или в `scripts/` с комментарием «probe».
- AI-KB: в боевую KB только блок `KB_INSERT`; человек апрувит в Streamlit.
- Learn-модели: `learn_llm.learn_kb_model()` → `confluence-agent`, не молча `gpt-oss`.
- Контуры: уважать `contour_enabled` / `disabled_service_ids`.
- Документацию обновлять вместе с поведением пайплайна (`docs/pipeline/решения.md`).

## Do Not

- Не публиковать черновики AI-KB в «Быстрые ответы» без Promote / ревью.
- Не слать PII (email) в `KB_INSERT` / корпус.
- Не включать `auto_learn_kb` в defaults без явного решения оператора.
- Не смешивать API каталога ЛК с API-ключом bp.iek.ru.
- Не подключать OWUI MCP «как есть» в HD-пайплайн — prefetch через `confluence_tools.py` + LiteLLM; полный tool loop — после стабильного `/v1` tools execution.
- Не раздувать этот файл > ~200 строк — выносить в `docs/`.

## Known pitfalls

- Длинный промпт → `confluence-agent` отвечает «слишком длинный» → fallback на `gpt-oss` (часто в `_analysis_*.json`).
- `auto_push_confluence_draft: false` по умолчанию — ревью в Streamlit; Confluence опционально.
- Reject пишет `rejection_reason` в index; учитывается в learn (`learn_llm.rejection_context`).
- Watch_new антипетля: пост бота обновляет `Changed` — см. `docs/pipeline/решения.md`.
- Артефакты разбора (`_analysis_*.json`) пишутся в `debug/`; старые из корня читаются для совместимости.

## Спеки и handoff

- Активные спеки: `docs/specs/` (сейчас L0 — `L0_employee_chatbot.md`).
- Конец сессии: обновить `docs/handoff.md` (что сделано / блокер / следующий шаг).
