# -*- coding: utf-8 -*-
"""Публикация базы чатбота IntraService в пространство CRMRF.

Создаёт под «База знаний CRM РФ» (pageId 786565):
  - хаб «Чатбот IntraService · CRM РФ»
  - руководство оператора (разбор заявок + AI-KB)
  - быстрые ответы (корпус + Promote из AI-KB)

  python scripts/publish_crm_l1_confluence.py
  python scripts/publish_crm_l1_confluence.py --dry-run

См. также WEBKB-зеркало: python scripts/build_crm_corpus.py --publish
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import confluence_client as cf  # noqa: E402
from env_bootstrap import load_package_env  # noqa: E402

SPACE = "CRMRF"
CRMRF_KB_ROOT = "786565"
CRM_DEV_ROOT = "786562"

HUB_TITLE = "Чатбот IntraService · CRM РФ"
GUIDE_TITLE = "Руководство: чатбот IntraService и AI-KB (CRM)"
QA_TITLE = "Быстрые ответы: CRM РФ (чатбот)"

META_PATH = ROOT / "docs" / "confluence" / "crm_l1_hub.json"


def _load_build_crm():
    spec = importlib.util.spec_from_file_location("build_crm_corpus", ROOT / "scripts" / "build_crm_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def guide_storage() -> str:
    md = """# Руководство оператора: чатбот IntraService и AI-KB (CRM)

## Назначение

**Чатбот IntraService** помогает **исполнителелю** HelpDesk разобрать заявку за ~10 секунд:
скрытый комментарий, проверки, черновик ответа, ссылки на KB.

Контур **CRM РФ**: HelpDesk ServiceId **29** (`crmrf.iek.local`, Dynamics).

## Как запустить разбор

1. Панель оператора: `streamlit run app.py` → вкладка **Запуск** → номер заявки.
2. CLI: `python scripts/analyze_and_comment.py <task_id>` (без `--post` — только предпросмотр).
3. Автоматически: watch / n8n на ServiceId **29** (включить контур **CRM** в Streamlit).

В артефакте `_analysis_<id>.json` и в UI «История» — промпт и preview скрытого комментария.

## Что делает бот для CRM

| Шаг | Действие |
|-----|----------|
| Профиль | `l1_crm` — корпус `knowledge/crm/`, prefetch CRMRF + WEBKB |
| Контур | `crm` в скрытом комментарии; не путать с ЛК и БП |
| Подчинение дублей | **Выключено** для CRM (слишком много ложных совпадений по GUID) |

## Быстрые ответы (эта база)

Статьи с кодами **CRM-NN** — сценарии для 1 линии: спеццены ↔ 1С, доступ к сделкам, интеграции CRM↔IEK+.

**Формат:** вопрос → ключевые слова → «Ответ (копировать)».

Обязательная статья **CRM-Q00** — отличие CRM РФ от корпоративной CRM.

## Самообучение AI-KB

После закрытия заявки (если включено **Обучение KB** для контура CRM):

1. Черновик → `docs/черновики_статей/` + `knowledge/learned/index.json`.
2. Оператор правит блок **KB_INSERT** в Streamlit (вкладка AI-KB).
3. **Promote** → статья дописывается в **«Быстрые ответы: CRM РФ»** (эта страница, пространство **CRMRF**).
4. `sync_kb_after_review.py` пересобирает локальный корпус.

### Ревью — что проверить

- Только **шаги для исполнителя**, без переписки HD и PII (email, ИНН).
- Не дублировать существующий **CRM-** код.
- **Отклонить** с причиной — учтётся при следующем learn.

### Зеркало WEBKB

Дубликат Q&A для разработчиков пайплайна: pageId **124642008** в WEBKB.
Обновление: `python scripts/build_crm_corpus.py --publish`.

## Связь с 1С и ЛК

- **Спеццены CRM → 1С** — отдельный контур; бот не подменяет 1С-разбор заказов.
- **ЛК / БП** — другие ServiceId; при смешанной теме смотрите URL в заявке.

## Обновление базы

```powershell
cd chatbot_intraservice
python scripts/build_crm_corpus.py
python scripts/publish_crm_l1_confluence.py
```

Документация: `docs/pipeline/самообучение_crm.md`.
"""
    return cf.markdown_to_storage(md)


def hub_storage(guide_url: str, qa_url: str) -> str:
    md = f"""# Чатбот IntraService · CRM РФ

База знаний для **автоматического разбора заявок HelpDesk** (ServiceId **29**) и **самообучения AI-KB**.

| Страница | Назначение |
|----------|------------|
| [Руководство оператора]({guide_url}) | Как запускать бот, ревью и Promote статей |
| [Быстрые ответы: CRM РФ]({qa_url}) | Основной корпус Q&A + цель Promote AI-KB |

**Родительский раздел:** [База знаний CRM РФ](https://confluence.dev.iek.ru/x/hQAM)

**Техдок разработки CRM:** [CRM Разработка](https://confluence.dev.iek.ru/x/ggAM)

**Локальный корпус (git):** `chatbot_intraservice/knowledge/crm/`
"""
    return cf.markdown_to_storage(md)


def publish_page(
    s: Any,
    *,
    space: str,
    title: str,
    parent_id: str,
    storage: str,
    dry_run: bool,
) -> dict[str, Any]:
    if dry_run:
        return {"action": "dry_run", "title": title, "parent_id": parent_id, "storage_len": len(storage)}
    return cf.create_or_update_child(
        s,
        space=space,
        title=title,
        parent_id=parent_id,
        storage=storage,
        message="publish_crm_l1_confluence",
    )


def main() -> int:
    load_package_env()
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    bcrm = _load_build_crm()
    s = cf.session()
    qa_items, pages, support_pages, user_request_pages = bcrm.collect_crm_qa(s)

    hub_id = ""
    if META_PATH.is_file():
        try:
            hub_id = str(json.loads(META_PATH.read_text(encoding="utf-8")).get("hub_page_id") or "")
        except json.JSONDecodeError:
            hub_id = ""

    if hub_id and not args.dry_run:
        try:
            cf.get_page(s, hub_id, expand="version")
        except Exception:
            hub_id = ""

    if not hub_id:
        placeholder = cf.markdown_to_storage(
            f"# {HUB_TITLE}\n\n(ссылки обновятся после публикации дочерних страниц)"
        )
        hub_res = publish_page(
            s,
            space=SPACE,
            title=HUB_TITLE,
            parent_id=CRMRF_KB_ROOT,
            storage=placeholder,
            dry_run=args.dry_run,
        )
        hub_id = str(hub_res.get("id") or hub_id or "")

    guide_res = publish_page(
        s,
        space=SPACE,
        title=GUIDE_TITLE,
        parent_id=hub_id,
        storage=guide_storage(),
        dry_run=args.dry_run,
    )
    guide_id = str(guide_res.get("id") or "")
    guide_url = cf.view_url(s, guide_id) if guide_id else ""

    intro = (
        "# Быстрые ответы: CRM РФ (чатбот IntraService)\n\n"
        "> HelpDesk ServiceId **29**. Promote из AI-KB дописывает сюда блоки **CRM-NN**.\n\n"
        f"Статей: **{len(qa_items)}** "
        f"(ручной корпус + KB CRM РФ + [Поддержка]({bcrm.CRM_SUPPORT_URL}) + "
        f"[Обращения]({bcrm.CRM_USER_REQUESTS_URL})).\n\n"
        "**Формат:** вопрос → ключевые слова → «Ответ (копировать)».\n"
    )
    qa_storage = bcrm.qa_items_to_confluence_storage(qa_items, intro)
    qa_res = publish_page(
        s,
        space=SPACE,
        title=QA_TITLE,
        parent_id=hub_id,
        storage=qa_storage,
        dry_run=args.dry_run,
    )
    qa_id = str(qa_res.get("id") or "")
    qa_url = cf.view_url(s, qa_id) if qa_id else ""

    if hub_id and not args.dry_run:
        cf.update_page(
            s,
            hub_id,
            title=HUB_TITLE,
            storage=hub_storage(guide_url, qa_url),
            message="hub links",
        )

    meta = {
        "space": SPACE,
        "crmrf_kb_root_page_id": CRMRF_KB_ROOT,
        "crmrf_kb_root_url": "https://confluence.dev.iek.ru/x/hQAM",
        "crm_dev_root_page_id": CRM_DEV_ROOT,
        "crm_dev_root_url": "https://confluence.dev.iek.ru/x/ggAM",
        "hub_page_id": hub_id,
        "hub_title": HUB_TITLE,
        "hub_url": cf.view_url(s, hub_id) if hub_id else "",
        "guide_page_id": guide_id,
        "guide_url": guide_url,
        "qa_page_id": qa_id,
        "qa_url": qa_url,
        "qa_title": QA_TITLE,
        "promote_target_page_id": qa_id,
        "note": "Promote AI-KB (контур crm) → qa_page_id в CRMRF",
    }
    if not args.dry_run:
        META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        qa_meta = ROOT / "docs" / "confluence" / "crm_qa_page_id.json"
        if qa_meta.is_file():
            old = json.loads(qa_meta.read_text(encoding="utf-8"))
        else:
            old = {}
        old.update(
            {
                "crmrf_hub_page_id": hub_id,
                "crmrf_qa_page_id": qa_id,
                "crmrf_qa_url": qa_url,
                "promote_target_page_id": qa_id,
                "promote_target_space": SPACE,
            }
        )
        qa_meta.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
