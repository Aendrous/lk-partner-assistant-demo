# Чатбот ИИЭК — ассистент 1 линии техподдержки

Материалы продукта **«IEK: Помощник сотрудника»** (HelpDesk / IntraService).  
Корень пакета: `chatbot_intraservice/` (клиент API, tools, `.env`).

**Навигация пакета:** [`../AGENTS.md`](../AGENTS.md) · [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`ROADMAP.md`](ROADMAP.md).

| Слой | Статус | Где |
|------|--------|-----|
| **IntraService** (разбор заявок для исполнителя) | **сейчас, по деке** | `../scripts/analyze_and_comment.py`, watch_* |
| **AI-KB** | **в коде** | `pipeline/самообучение.md` |
| **Встречающий чат (L0)** | **будет** | `specs/L0_employee_chatbot.md` |

**Роль продукта (целевая):** ответы из KB → уточнения → заявка в IntraService  
**UI (целевой):** https://corp.iek.ru/services/gptassistants/… · HelpDesk: https://helpdesk.iek.local

## Структура

| Путь | Содержание |
|:--|:--|
| `ARCHITECTURE.md` / `ROADMAP.md` / `handoff.md` | управление проектом |
| `specs/` | спеки итераций (L0, …) |
| `scripts_map.md` | карта CLI |
| `источники/` | PDF схемы, макеты, переписка по продукту |
| `правила/` | Правила поведения L1, эскалация, tone of voice |
| `prompts/` | Системный промпт, уточняющие вопросы, формирование заявки |
| `интеграции/` | IntraService REST API — автосоздание заявки |
| `схемы/` | BPMN / flowchart (Mermaid) |
| `confluence/` | pageId опубликованных страниц |
| `pipeline/` | решения, самообучение |

## Ключевой сценарий (продукт L0 / чат сотрудника)

Описан ниже; **реализация — Iteration 3** (пока код обслуживает L1 HD).

1. Пользователь задаёт вопрос.
2. Бот ищет ответ в AI-Библиотеке / WEBKB / шаблонах.
3. Если решено — ответ + ссылки; «Это не помогло» → эскалация.
4. Если не решено — **цикл уточнений по матрице** (`prompts/матрица_уточнений.md`).
5. «Создать заявку из этого чата» → POST в IntraService.
6. Возврат номера заявки и ссылки `helpdesk.iek.local/Task/View/{id}`.

## Confluence

- Схема 1 линии: https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124630073  
- **Пайплайн, AI-KB и настройки:** https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124640056  
  (`confluence/intraservice_project_page_id.json`)
- Схемы: макрос draw.io Board + Mermaid. См. `confluence/как_вставлять_схемы.md`.

## Код, UI и запуск

См. родительский [`../README.md`](../README.md):

- как работает чатбот (watch / CLI / Streamlit);
- **зачем Streamlit** (панель оператора, не чат для партнёра);
- установка на ноутбук и сервер;
- `streamlit run app.py --server.port 8502`.

Клиент API: `../src/intraservice.py`. Секреты: `../.env` (не в git).
