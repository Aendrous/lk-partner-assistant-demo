# Отладка: что ушло в IEK LLM и что вернулось

Для каждой разобранной заявки сохраняется локальный артефакт **`chatbot_intraservice/_analysis_{task_id}.json`** (и копия в `pipeline/runs/{run_id}/analysis.json`, если включено «Сохранять прогоны»).

Пример: заявка [#699197](https://helpdesk.iek.local/Task/View/699197) → `_analysis_699197.json`.

## Где что искать

| Блок в JSON | Содержимое |
|-------------|------------|
| **`llm_request`** | Что **отправили** в LiteLLM (`llm.iek.local/v1/chat/completions`): `messages` (system усечён до 2k, **user — целиком**), `model_requested`, `model_used`, `fallback_used`, `api_base` |
| **`llm_meta`** | Что **вернул** API: `model`, `http`, `raw` — полный ответ chat/completions (в т.ч. `choices[0].message.content`) |
| **`raw`** | Текст ответа ассистента (JSON разбора) после парсинга |
| **`ocr`** | Вложения: `items[]` (файл, kind, смысл через VL-модель), `text_preview` (сырой OCR/текст), `meaning` |
| **`profile`** | Профиль и модель (`iek/confluence-agent` или fallback `iek/gpt-oss-120b`) |
| **`comment_preview`** | Итоговый скрытый комментарий в HelpDesk |
| **`parsed`** | Распарсенный JSON от LLM (facts, kb_refs, …) |
| **`confluence_search`** | Доп. обогащение (compose / kb_refs) |

### Вложения

В промпт попадает не файл целиком, а **смысл** после `attachments.analyze_task_attachments`:

- в `llm_request.messages` → блок user: строки `Вложения (смысл IEK LLM…)` и `Ключевые фрагменты из вложений`;
- детали по каждому файлу — в `ocr.items`.

Скриншоты обрабатывает `iek/qwen3.5-122b-vl-int4-nothink` (см. `IEK_LLM_OCR_MODEL`).

## Быстрые команды (PowerShell)

```powershell
cd chatbot_intraservice

# весь файл
Get-Content .\_analysis_699197.json | ConvertFrom-Json | ConvertTo-Json -Depth 20

# только промпт user
(jq -r '.llm_request.messages[] | select(.role=="user") | .content' _analysis_699197.json)

# ответ LLM (content)
(jq -r '.llm_meta.raw.choices[0].message.content' _analysis_699197.json)

# вложения
(jq '.ocr' _analysis_699197.json)
```

Без `jq` — открыть файл в IDE или вкладка **«История LLM»** в Streamlit (`streamlit run app.py`) → блок **«Разбор заявки (артефакт)»**.

## call_history.jsonl

`knowledge/learned/call_history.jsonl` — **краткий журнал** (до 800 симв. ответа, без промпта). Для полной отладки используйте `_analysis_*.json`.

## Два API IEK

| | LiteLLM (бот) | Open WebUI (ручной чат) |
|--|---------------|-------------------------|
| URL | `https://llm.iek.local/v1` | `https://chatgpt.iek.local` |
| Токен | `IEK_LLM_TOKEN` | `IEK_LLM_API_KEY` |
| Модель в запросе | `iek/confluence-agent`, `iek/gpt-oss-120b`, … | `support-dep-lk-web-helper` (карточка UI) |
| MCP Confluence | **нет** (только RAG на стороне `confluence-agent`) | **да** (интеграции в карточке модели) |

Подробнее про MCP: [интеграции/iek_llm_owui_mcp.md](../интеграции/iek_llm_owui_mcp.md).
