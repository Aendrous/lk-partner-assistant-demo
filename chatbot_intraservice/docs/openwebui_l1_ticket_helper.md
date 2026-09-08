# Карточка Open WebUI: ассистент разбора заявок L1 (опционально)

**Не менять** существующий `support-dep-lk-web-helper`.

Чатбот IntraService по API использует `iek/confluence-agent` + fallback `iek/gpt-oss-120b` (см. `src/assistants.py`).  
Отдельная карточка в UI нужна только для ручного чата аналитиков.

## Создать Knowledge

1. https://chatgpt.iek.local/workspace/knowledge → Create
2. Name: `support-l1-webkb-safe`
3. Загрузить **обезличенные** выдержки WEBKB / FAQ (без ПДн из заявок).
4. Access: Private.

## Создать Model

| Поле | Значение |
|:--|:--|
| Name | `Разбор заявок WEB L1` |
| Model ID | `support-dep-l1-ticket-helper` |
| Base Model | тот же Base, что у `support-dep-lk-web-helper` (обычно gpt-oss / Qwen из списка UI) |
| Knowledge | `support-l1-webkb-safe` |
| System prompt | текст из `docs/правила/разбор_заявки_для_исполнителя.md` + краткий L1 промпт |

Visibility: Private.

В `.env` чатбота можно указать ссылку-подсказку:

```
IEK_LLM_SUPPORT_OWUI_ID=support-dep-l1-ticket-helper
```

В `chat/completions` это имя **не** передаётся — только API-модели.
