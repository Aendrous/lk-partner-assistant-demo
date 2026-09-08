# Пайплайн чатбота IntraService

Каждый запрос по заявке HelpDesk — **прогон** с шагами и артефактами.

**Самообучение (Corrective RAG):** [самообучение.md](самообучение.md) · [отладка LLM](отладка_llm.md) · [IDEA_RAG_LEARNING.md](../../pipeline/IDEA_RAG_LEARNING.md) · Confluence [ONttBw](https://confluence.dev.iek.ru/x/ONttBw) §3.1.

## Структура папок

```
chatbot_intraservice/
  config/
    settings.default.json    # defaults (в git)
    settings.local.json      # переопределения UI (не в git)
  pipeline/
    runs/
      {task_id}_{timestamp}_{id}/
        manifest.json        # метаданные прогона
        analysis.json        # полный разбор
        result.json          # итог
        steps/
          01_analyze.json
          02_kb_learn.json
  knowledge/
    learned/index.json       # task → черновик → status
  docs/черновики_статей/     # markdown до Confluence
  pipeline/IDEA_RAG_LEARNING.md  # самообучение Corrective RAG (схема + файлы)
  _analysis_{id}.json        # legacy summary (gitignored)
```

## Шаги пайплайна

| Шаг | Что делает |
|:--|:--|
| `01_analyze` | Загрузка заявки, ассистент, adm, ServiceId, скрытый комментарий |
| `02_kb_learn` | Решение `should_auto_learn` + черновик AI-KB (если нужно) |

## Точки входа

| Команда | Назначение |
|:--|:--|
| `streamlit run app.py` | UI: настройки + запуск + история |
| `python scripts/run_ticket_pipeline.py <id>` | CLI полный прогон |
| `python scripts/analyze_and_comment.py <id>` | Только разбор (+ `--learn`) |
| `python scripts/watch_new.py` | Cron: новые/переданные 31/38/121 |
| `python scripts/watch_user_reply.py` | Cron: ответ в 46/120 |
| `python scripts/watch_overdue.py` | Cron: эскалация «До просрочки» |
| `python scripts/pipeline_watch.py` | Cron: закрытые → AI-KB |
| `python scripts/weekly_gap_digest.py` | Weekly: gap без черновика |
| `python scripts/push_kb_draft_confluence_review.py --all-pending` | Выгрузка `[ЧЕРНОВИК]` в папку ревью Confluence |
| `python scripts/sync_kb_after_review.py --task-id <id>` | После ревью: Confluence «Быстрые ответы» + corpus + OWUI |

## Streamlit UI

Панель оператора (`app.py`): настройки автозапуска, ручной прогон, история, Promote AI-KB.

```powershell
cd chatbot_intraservice
streamlit run app.py --server.port 8502
```

Как поставить на сервер и зачем UI — в корневом `chatbot_intraservice/README.md`.

## Автозапуск (watch)

Windows Task Scheduler / cron:

```powershell
cd chatbot_intraservice
powershell -ExecutionPolicy Bypass -File scripts\install_scheduler.ps1
```

Ставит: WatchNew / WatchUserReply / WatchOverdue (15 мин), WatchLearn (30 мин), GapDigest (вс 09:00).

Включить в UI: **Автообучение AI-KB** + watch-тогглы. Пост в заявку — только если **Автопост**.

## Связанные документы

- `docs/pipeline/решения.md` — принятые правила + roadmap vs industry
- `docs/правила/наполнение_kb_ассистента.md` — KB → Confluence → corpus

## Industry references

Closed-loop KB from tickets: Intercom Fin (accumulation + dedup), Zendesk Knowledge Builder (batch drafts), KnowledgeForge (generation + curation). Подробнее — § «Сверка с индустрией» в `решения.md`.
