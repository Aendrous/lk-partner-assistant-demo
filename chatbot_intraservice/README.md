# Чатбот IntraService — 1 линия HelpDesk

Отдельный пакет внутри репозитория **AI Assistant IEK** для продукта  
**«IEK: Помощник сотрудника»** (1 линия техподдержки → заявка в IntraService).

**GitHub (standalone):** https://github.com/Aendrous/iek-chatbot-intraservice (private)

Это **не** помощник партнёра ЛК (каталог `/api/products`).  
Партнёрский шлюз остаётся в корне репозитория (`agent.py`, `streamlit_app.py`, …).

---

## С чего начать

| Кто | Читать |
|-----|--------|
| Человек / агент (всегда) | [`AGENTS.md`](AGENTS.md) |
| Карта системы | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| План итераций (L1 → L0) | [`docs/ROADMAP.md`](docs/ROADMAP.md) |
| Что делает каждый скрипт | [`docs/scripts_map.md`](docs/scripts_map.md) |
| Статус последней сессии | [`docs/handoff.md`](docs/handoff.md) |
| Speка будущего L0 | [`docs/specs/L0_employee_chatbot.md`](docs/specs/L0_employee_chatbot.md) |

**Сейчас (по деке — этап IntraService):** бот в HelpDesk для исполнителя + AI-KB.  
**Будет:** чатбот, встречающий пользователей → KB или заявка с сервисом/скринами (ROADMAP Iteration 3).

---

## Как работает чатбот

Чатбот — **ассистент исполнителя HelpDesk**, а не чат для внешнего партнёра.

```
Заявка HelpDesk (#id)
  → watch_* / Streamlit / CLI
  → OCR + вложения (скрин / .msg / PDF·DOC) + номера (заказ/счёт) + связанные / похожие / прошлые заявки инициатора
  → 1С (резерв в пути) · adm.bp (БП)
  → LLM (iek/confluence-agent + локальный corpus ЛК/БП/1С) + CQL Confluence
  → скрытый комментарий исполнителю (факты + ссылки + текст для открытого ответа)
  → ответ заявителя «спасибо/заработало» → статус Выполнена (без скрытого)
  → при просрочке: дедлайн +1 день + краткий открытый ответ (если есть KB)
  → при закрытии + gap в KB → черновик AI-KB → Confluence (ревью) → corpus / OWUI
```

| Режим | Кто запускает | Что делает |
|:--|:--|:--|
| **Автономный** | Windows Task Scheduler / **n8n** / cron | `watch_new`, `watch_user_reply`, `watch_overdue`, `pipeline_watch` |
| **UI** | человек в браузере | настройки, ручной прогон, история, Promote черновиков |
| **CLI** | человек / скрипт | точечный разбор одной заявки |

Модель API для разбора: `iek/confluence-agent` (+ локальный `knowledge/*/corpus.md`).  
Карточки Open WebUI (`*-web-helper`) — для ручного чата на chatgpt.iek.local; HD-бот ходит в LiteLLM напрямую.

Подробнее: `docs/pipeline/README.md`, `docs/pipeline/решения.md`.

---

## Зачем Streamlit

**Streamlit (`app.py`) — панель оператора**, не публичный чат с пользователем.

В UI можно:

- включать/выключать **L1 Simple** (просрочка, скрытый пост, public только при KB, AI-KB);
- в expander — dedup, digests, related;
- запускать разбор заявки по Id; Promote черновиков.

Без Streamlit бот всё равно работает по Scheduler/CLI. UI нужен, чтобы не править JSON руками и видеть статус.

Адрес по умолчанию: http://localhost:8502

С другого ПК в корпсети (ноутбук разработчика, пример LAN): http://10.1.25.17:8502 — актуальный IP смотреть в `ipconfig` или в «Network URL» Streamlit. Это UI оператора для демо/dev, не публичный интернет; на проде — сервер во внутренней сети, порт 8502 за reverse proxy.

---

## L1 Simple (профит раньше глубины)

Фокус UI: **5 тумблеров**. Остальное — «Расширенные».

| Флаг | Смысл |
|:--|:--|
| Просрочка «До просрочки» | take + скрытый разбор |
| Автопост скрытого | watch пишет internal note |
| Открытый ответ заявителю | при просрочке |
| **Только если есть KB** (`public_reply_only_if_kb`) | без KB — только скрытый |
| AI-KB из закрытых | черновики в папку самообучения |

Take в работу на **всех** новых заявках выключен (`auto_take_in_work=false`) — take только из `watch_overdue`.

### Smoke-чеклист профита

1. Заявка с эскалацией «До просрочки» → Status **27**, **один** скрытый «Сервис HD:…», публичный **только** если KB/ясный prior/1С-факт; без повторов каждые 15 мин.
2. Простая с KB (резерв в пути) → краткий открытый gist.
3. Без KB → скрытый есть, публичный skip (`public_reply_only_if_kb`).

Статьи самообучения: [папка ревью](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124640307) — нормальные заголовки `BP-06. …`, метки `ai-kb-draft` / `ai-kb-published`, без `[ЧЕРНОВИК]`/`[ОПУБЛИКОВАНО]`.

### Самообучение (Corrective RAG)

Закрытая заявка без ответа в KB → сравнение бот/человек → поиск в Confluence → черновик → ревью → Promote в «Быстрые ответы».

| Документ | Назначение |
|:--|:--|
| [`docs/pipeline/самообучение.md`](docs/pipeline/самообучение.md) | кратко для операторов |
| [`pipeline/IDEA_RAG_LEARNING.md`](pipeline/IDEA_RAG_LEARNING.md) | полная схема + файлы |
| [Confluence ONttBw §3.1](https://confluence.dev.iek.ru/x/ONttBw) | свод на WEBKB |
| [Corrective RAG (детально)](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124641312) | дочерняя страница схемы |

Включение: Streamlit → **AI-KB: учиться из закрытых** + `pipeline_watch` в планировщике.

Причёска страниц: `python scripts/push_kb_draft_confluence_review.py --refresh-existing`

---

## Установка (ноутбук / сервер)

### 1. Код и Python

```powershell
# клон монорепо или standalone
cd "C:\path\to\AI Assistant IEK"   # или iek-chatbot-intraservice

python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Linux: source .venv/bin/activate
pip install -r requirements.txt
# нужен streamlit (если его нет в requirements):
pip install streamlit python-dotenv requests
# Outlook .msg (точнее тема/от/тело); PDF/DOC/DOCX (pymupdf, python-docx):
pip install extract-msg pymupdf python-docx olefile
# или всё из пакета чатбота:
pip install -r chatbot_intraservice\requirements.txt
```

Рабочая папка пакета:

```powershell
cd chatbot_intraservice
```

### 2. Секреты

```powershell
copy .env.example .env
# заполнить INTRASERVICE_*, IEK_LLM_*, CONFLUENCE_* …
# или из корня монорепо:
python ..\scripts\copy_intraservice_env.py
```

Серверу нужны доступ к `helpdesk.iek.local`, `llm.iek.local`, при необходимости VPN/корп. DNS.

### 3. Настройки поведения

- `config/settings.default.json` — defaults (в git);
- `config/settings.local.json` — локальные флаги (не коммитить секреты; создаётся из UI).

Типично для автономии: `auto_post_comment`, `auto_learn_kb`, watch_* = true; `auto_take_in_work` = false.

---

## Запуск приложения

### Локально (UI)

```powershell
cd chatbot_intraservice
streamlit run app.py --server.port 8502
```

Открыть в браузере: http://localhost:8502

### Разовый разбор заявки (без UI)

```powershell
cd chatbot_intraservice
python scripts\analyze_and_comment.py 696955 --post
python scripts\run_ticket_pipeline.py 696955
```

### Автозапуск на ноутбуке (Windows)

```powershell
cd chatbot_intraservice
powershell -ExecutionPolicy Bypass -File scripts\install_scheduler.ps1
# опционально UI при входе в Windows:
powershell -ExecutionPolicy Bypass -File scripts\install_scheduler.ps1 -WithStreamlit
```

Проверка: `Get-ScheduledTask IEK-IntraService-*`

### Автозапуск через n8n (оркестрация)

**Рекомендуется:** Streamlit на ноутбуке (настройки + ревью KB), **Execute Command на сервере n8n** (автономные watch).

| Шаг | Команда / файл |
|-----|----------------|
| Инструкция | [`docs/интеграции/n8n.md`](docs/интеграции/n8n.md) |
| Workflow Execute (без HTTP) | `n8n_setup_helpdesk_watch.py --mode execute` |
| Push настроек на сервер | `scripts/push_deploy_settings.ps1` |
| HTTP API (если Execute недоступен) | `python scripts/n8n_http_server.py` |
| Диагностика | `python scripts/n8n_diag_bot_url.py` |

```powershell
python scripts\n8n_setup_helpdesk_watch.py --mode execute --bot-path /opt/iek-chatbot-intraservice
```


### Установка на сервер (Linux, пример)

1. Склонировать репозиторий, создать venv, поставить зависимости, положить `.env`.
2. **Watch’и** — через systemd timer или cron (аналог Scheduler):

```bash
# /etc/cron.d/iek-intraservice-bot  (каждые 15 мин)
*/15 * * * * iekbot cd /opt/iek-chatbot-intraservice && /opt/iek-chatbot-intraservice/.venv/bin/python scripts/watch_new.py >>/var/log/iek-bot/watch_new.log 2>&1
*/15 * * * * iekbot cd /opt/iek-chatbot-intraservice && /opt/iek-chatbot-intraservice/.venv/bin/python scripts/watch_user_reply.py >>/var/log/iek-bot/watch_reply.log 2>&1
*/15 * * * * iekbot cd /opt/iek-chatbot-intraservice && /opt/iek-chatbot-intraservice/.venv/bin/python scripts/watch_overdue.py >>/var/log/iek-bot/watch_overdue.log 2>&1
*/30 * * * * iekbot cd /opt/iek-chatbot-intraservice && /opt/iek-chatbot-intraservice/.venv/bin/python scripts/pipeline_watch.py >>/var/log/iek-bot/learn.log 2>&1
```

3. **Streamlit UI** — unit systemd (доступ только из корп. сети / за reverse proxy):

```ini
# /etc/systemd/system/iek-intraservice-ui.service
[Unit]
Description=IEK IntraService chatbot Streamlit UI
After=network.target

[Service]
User=iekbot
WorkingDirectory=/opt/iek-chatbot-intraservice
ExecStart=/opt/iek-chatbot-intraservice/.venv/bin/streamlit run app.py \
  --server.address 0.0.0.0 --server.port 8502 --server.headless true
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now iek-intraservice-ui
# UI: http://<server>:8502
```

Рекомендуется nginx/IIS с HTTPS и ограничением по IP; не выставлять порт в интернет без аутентификации.

### Windows Server

Те же шаги, что на ноутбуке: `install_scheduler.ps1` (+ `-WithStreamlit` или отдельная служба NSSM/`schtasks` на `streamlit run app.py --server.headless true --server.port 8502`).

---

## Что внутри

| Путь | Содержание |
|:--|:--|
| `docs/` | Промпты, правила L1, API IntraService, Confluence pageId |
| `src/intraservice.py` | Клиент HelpDesk |
| `src/assistants.py` | Профили ЛК / БП / 1С |
| `src/settings.py`, `src/pipeline.py` | Настройки + прогоны в `pipeline/runs/` |
| `app.py` | Streamlit: настройки + пайплайн + AI-KB |
| `config/settings.default.json` | Defaults |
| `scripts/watch_*.py` | Автономное отслеживание заявок |
| `.env` / `.env.example` | Секреты (`.env` не в git) |

## Команды (шпаргалка)

```powershell
cd chatbot_intraservice
streamlit run app.py --server.port 8502
python scripts\analyze_and_comment.py 696955 --post
python scripts\run_ticket_pipeline.py 696955
python scripts\watch_new.py --dry-run
python scripts\pipeline_watch.py --dry-run
python scripts\push_kb_draft_confluence_review.py --all-pending
python scripts\sync_kb_after_review.py --task-id 696965
python scripts\n8n_http_server.py
python scripts\n8n_diag_bot_url.py
```

## Confluence

- Схема 1 линии: https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124630073  
- Пайплайн / AI-KB / настройки: https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124640056  
- Черновики на ревью: https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124640307  

## Быстрая проверка

```powershell
cd chatbot_intraservice
python scripts\intraservice_get_task.py 693437
```
