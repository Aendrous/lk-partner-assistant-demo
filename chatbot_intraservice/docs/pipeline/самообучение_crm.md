# Самообучение и корпус CRM

Раздел контура **CRM** (Dynamics, `crmrf.iek.local`) для чатбота IntraService.

Общая схема Corrective RAG: [`самообучение.md`](самообучение.md).

---

## Зачем отдельный корпус CRM

| Контур | Система | Не путать с |
|--------|---------|-------------|
| **CRM РФ** | `crmrf.iek.local` | ЛК, БП, API каталога |
| **CRM корпоративная** | IEK+, интеграции | ежедневная работа МРК в CRM РФ |

Заявки HelpDesk по CRM часто про: **спеццены ↔ 1С**, доступ к сделкам, интеграцию CRM↔IEK+, фин. отчётность партнёра.

В Streamlit контур **crm** для watch/learn **включён** (пилот ServiceId **29**).

| Страница | URL |
|----------|-----|
| **Хаб** | [Чатбот IntraService · CRM РФ](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642254) |
| **Руководство оператора** | [Гайд AI-KB CRM](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642255) |
| **Быстрые ответы + Promote** | [CRM РФ (чатбот)](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642256) — пространство **CRMRF** |
| **Зеркало WEBKB** | [Q&A CRM](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642008) |

Техдок разработки: [CRM Разработка](https://confluence.dev.iek.ru/x/ggAM) · пользовательская KB: [База знаний CRM РФ](https://confluence.dev.iek.ru/x/hQAM).

---

## Источники Confluence

| Пространство | Назначение | URL |
|--------------|------------|-----|
| **CRMRF** | Пользовательская KB CRM РФ | [База знаний CRM РФ](https://confluence.dev.iek.ru/x/hQAM) (pageId 786565) |
| **CRM** | Поддержка: проблемы и решения | [Поддержка](https://confluence.dev.iek.ru/x/iAFd) (pageId 6095240, дочерние статьи) |
| **CRM** | Темы обращений пользователей | [Обращения](https://confluence.dev.iek.ru/x/-QntAQ) (pageId 32311805, 10 тем) |
| **CRM** | Разработка, интеграции, сущности | [CRM Разработка](https://confluence.dev.iek.ru/x/ggAM) (pageId 786562) |

В Q&A попадают **инструкции и процессы**, не dev-страницы сущностей (`[account]`, SQL, команды разработки).

---

## Формат Q&A (локально и в Confluence)

Файлы:

- `knowledge/crm/qa.md` — **только вопросы и ответы** (для человека и LLM)
- `knowledge/crm/corpus.md` — Q&A + выдержки из Confluence
- `knowledge/crm/meta.json` — метаданные сборки

Структура одной записи:

```markdown
### CRM-Q00. В чём отличие CRM РФ от CRM?

**Ключевые слова:** …
**Не путать с:** ЛК, БП, …

Ответ для исполнителя…

**Источник:** [статья](url)
```

Обязательный вопрос **CRM-Q00** — отличие CRM РФ от корпоративной CRM (см. `/x/hQAM`).

---

## Публикация

```powershell
cd chatbot_intraservice

# Собрать корпус из Confluence (CRMRF + интеграции)
python scripts/build_crm_corpus.py

# Опубликовать в CRMRF (хаб + гайд + быстрые ответы, цель Promote)
python scripts/publish_crm_l1_confluence.py

# Зеркало в WEBKB (для разработчиков пайплайна)
python scripts/build_crm_corpus.py --publish
```

**Promote** из Streamlit → страница **124642256** (`docs/confluence/crm_l1_hub.json`).

---

## Связанные файлы

| Файл | Роль |
|------|------|
| `knowledge/prompts/system_l1_crm.md` | системный промпт профиля |
| `scripts/build_crm_corpus.py` | сбор Q&A из Confluence |
| `docs/confluence/crm_qa_page_id.json` | pageId WEBKB |
