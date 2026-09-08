# Самообучение и Q&A: 1С Солярис

Контур **edi** / профиль `onec_tickets` — разбор заявок HelpDesk на сервисе **Солярис** (ServiceId **69**).

## Confluence (основная база)

Раздел под [Первая линия поддержки](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=39887131):

| Страница | URL |
|----------|-----|
| Хаб | [Чатбот IntraService · 1С Солярис](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642089) |
| Руководство оператора | [pageId 124642090](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642090) |
| Быстрые ответы Солярис | [pageId 124642091](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642091) — **Promote AI-KB** |
| Типовые кейсы L1 | [pageId 124642092](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642092) |

Метаданные: `docs/confluence/onec_l1_hub.json`

## Локально (git)

| Артефакт | Путь |
|----------|------|
| Q&A | `knowledge/1c/qa.md` |
| Корпус LLM | `knowledge/1c/corpus.md` |
| Сборка корпуса | `python scripts/build_1c_corpus.py` |
| Публикация в 1C | `python scripts/publish_1c_l1_confluence.py` |

Дерево L1 для генерации Q&A: `_l1_1c_tree.json` (пересборка — crawl из скрипта или вручную).

## Promote после ревью

`targets_by_contour.edi` → **pageId 124642091** (пространство **1C**, не WEBKB).

## Маршрутизация

- ServiceId **69** / **14** → `onec_tickets`
- Prefetch Confluence: **1C**, WEBKB, LK
- Watch: ServiceId **69** в `settings.default.json`
