# 1С · Выгрузка ТН (ОП-2765)

Пилот чатбота на ServiceId **69** (Солярис): только заявки **портал перевозчиков → 1С**.

## Профиль

| | |
|:--|:--|
| Ключ | `onec_logistics_tn` |
| Корпус | `knowledge/1c/corpus_logistics_tn.md` |
| Промпт | `knowledge/prompts/system_onec_logistics_tn.md` |
| Источник | ОП-2765, `_source_op2765_logistics_tn.txt` |

## Примеры заявок

- #699796 — «Не выгружается **транспортная** накладная», TypeId 1008
- #699810 — «Не выгружается **ТН** на контрагента …», TypeId 1009

## Настройка scope

`config/settings.default.json`:

```json
"onec_analyze_scope": "all"
```

- `logistics_tn` — разбор только ТН (остальные заявки Солярис пропускаются)
- `all` — весь контур `onec_tickets` (заказы, НС, резерв…) — **по умолчанию**

Независимо от scope предразбор не выполняется для заявок «запрос на изменение»
(TypeId 1010) и уже «в работе» (StatusId 27) — см. `assistants.skip_onec_task()`.

## Проверка

```powershell
python scripts/test_onec_logistics_tn.py
python scripts/analyze_and_comment.py 699796
python scripts/analyze_and_comment.py 699810
```

Ожидание: `profile=onec_logistics_tn`, шаги из ОП-2765 (портал → XMLImportTransport).

## Confluence

| | |
|:--|:--|
| Быстрые ответы ТН | [pageId 124642131](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642131) |
| Хаб 1С | [124642089](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642089) |
| Публикация | `python scripts/publish_1c_logistics_tn_confluence.py` |

Promote AI-KB для профиля `onec_logistics_tn` → страница **124642131** (не Солярис 124642091).
