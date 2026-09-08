# Карта scripts/

37 файлов. **Сначала смотри «ядро».** Префикс `_` = зонд/одноразовое, не часть продукта.

## Ядро (продакшен / ежедневно)

| Скрипт | Роль |
|--------|------|
| `analyze_and_comment.py` | разбор одной заявки |
| `run_ticket_pipeline.py` | полный прогон + artifacts |
| `l0_ask.py` | L0: вопрос → KB / черновик; `--task-id` → разбор HD + уточнения |
| `watch_user_reply.py` | ответ заявителя |
| `watch_overdue.py` | «До просрочки» |
| `pipeline_watch.py` | закрытые → AI-KB |
| `learn_from_ticket.py` | ручной learn |
| `install_scheduler.ps1` | Windows Task Scheduler |

## AI-KB / Confluence / corpus

| Скрипт | Роль |
|--------|------|
| `push_kb_draft_confluence_review.py` | черновик → папка ревью |
| `publish_kb_draft_confluence.py` | Promote KB_INSERT |
| `sync_kb_after_review.py` | Promote + corpus + OWUI |
| `weekly_gap_digest.py` / `drafts_review_digest.py` | дайджесты |
| `build_bp_corpus.py` | пересборка corpus БП |
| `build_crm_corpus.py` | Q&A корпус CRM из Confluence (`--publish` → WEBKB) |
| `build_1c_corpus.py` | Q&A корпус 1С Солярис (локально) |
| `publish_1c_l1_confluence.py` | Публикация в Confluence **1C** (хаб + Q&A L1) |
| `publish_1c_logistics_tn_confluence.py` | Q&A **выгрузка ТН** ОП-2765 → pageId 124642131 |
| `publish_features_confluence.py` | Настройки и идеи (pageId 124642220) |
| `publish_bugs_confluence.py` | Журнал багов и исправлений (pageId 124642389) |
| `publish_learning_confluence.py` | страница Corrective RAG |
| `publish_iek_llm_mcp_confluence.py` | IEK LLM + Confluence (MCP vs REST) |
| `probe_iek_llm_tools.py` | зонд LiteLLM tools / OWUI MCP |
| `n8n_probe.py` | ping n8n + health `N8N_BOT_CALLBACK_URL` |
| `n8n_diag_bot_url.py` | URL нод workflow + probe `/health` (connection refused) |
| `n8n_http_server.py` | HTTP API :8765 для вызовов **из** n8n → `n8n_run.py` |
| `publish_n8n_http_confluence.py` | Confluence: запуск n8n_http на ноутбуке (pageId 124642190) |
| `publish_vlan_l0_confluence.py` | Confluence: VLAN/VM + L0 чеклист, спека L0 и черновик сети в expand (pageId 124642475) |
| `n8n_run.py` | CLI-обёртка watch_* для Execute Command |
| `sync_n8n_env_from_root.py` | N8N_* → пакетный .env |
| `n8n_setup_helpdesk_watch.py` | workflow на n8n.iek.local (`--co-located` → 127.0.0.1:8765) |
| `disable_iek_scheduler_for_n8n.ps1` | Disable Task Scheduler при переходе на n8n |

## Тесты (smoke)

| Скрипт | Роль |
|--------|------|
| `test_kb_draft_quality.py` | черновик / KB_INSERT |
| `test_onec_logistics_tn.py` | роутинг ТН логистика vs Солярис |
| `test_kb_drafts_ui.py` | фильтр AI-KB по командам ЛК/БП/1С/CRM |
| `test_attachments_extract.py` | PDF/DOCX extract |
| `test_learn_llm.py` | rejection context |
| `test_service_classification.py` | тип HD / сервис / важность в преданализе |
| `test_pick_resolution.py` | learn: resolution исполнителя, не заявителя |
| `test_bp_adm.py` | adm.bp |

## Вспомогательные (редко)

`take_task.py`, `intraservice_get_task.py`, `create_owui_bp_1c_models.py`, `set_bp_adm_cookie.py`, `refresh_bp_adm.py`, `import_bp_adm_from_cursor_browser.py`

## Зонды `_*.py` (не развивать)

`_probe_*`, `_scan_*`, `_discover_*`, `_cql_search.py`, `_find_users_search.py`, `_try_user_search.py` — отладка adm/API. Можно удалить после стабилизации cookie/API или оставить локально вне git.

**Правило:** новый зонд → только `_имя.py` + не добавлять в scheduler.
