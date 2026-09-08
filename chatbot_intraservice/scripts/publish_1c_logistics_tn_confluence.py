# -*- coding: utf-8 -*-
"""Публикация Q&A «Выгрузка ТН в 1С» (ОП-2765) в пространство Confluence 1C.

  python scripts/publish_1c_logistics_tn_confluence.py
  python scripts/publish_1c_logistics_tn_confluence.py --dry-run
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import confluence_client as cf  # noqa: E402
from env_bootstrap import load_package_env  # noqa: E402

SPACE = "1C"
QA_TITLE = "Быстрые ответы: 1С · Выгрузка ТН (ОП-2765)"
QA_PATH = ROOT / "knowledge" / "1c" / "qa_logistics_tn.md"
META_PATH = ROOT / "docs" / "confluence" / "onec_logistics_tn_qa.json"
HUB_META_PATH = ROOT / "docs" / "confluence" / "onec_l1_hub.json"

_SECTION_RE = re.compile(r"^###\s+(1C-TN-\d+)\.\s+(.+)$", re.M)
_KW_RE = re.compile(r"\*\*Ключевые слова:\*\*\s*(.+)", re.I)
_SOURCE_RE = re.compile(r"\*\*Источник:\*\*\s*(.+)", re.I)


def _load_publish_1c():
    spec = importlib.util.spec_from_file_location(
        "publish_1c_l1_confluence", ROOT / "scripts" / "publish_1c_l1_confluence.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def parse_qa_items(md: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    chunks = re.split(r"\n---\n", md.replace("\r\n", "\n"))
    for chunk in chunks:
        m = _SECTION_RE.search(chunk)
        if not m:
            continue
        qid = m.group(1).strip()
        question = m.group(2).strip()
        body = chunk[m.end() :].strip()
        kw_m = _KW_RE.search(body)
        keywords = kw_m.group(1).strip() if kw_m else ""
        src_m = _SOURCE_RE.search(body)
        source = src_m.group(1).strip() if src_m else "ОП-2765"
        answer_lines: list[str] = []
        for line in body.splitlines():
            if _KW_RE.match(line) or _SOURCE_RE.match(line):
                continue
            answer_lines.append(line)
        answer = "\n".join(answer_lines).strip()
        answer = re.sub(r"\*\*([^*]+)\*\*", r"\1", answer)
        items.append(
            {
                "id": qid,
                "question": question,
                "keywords": keywords,
                "answer": answer,
                "source_title": source,
            }
        )
    return items


def hub_storage_with_tn(
    guide_url: str, qa_solaris_url: str, qa_l1_url: str, qa_tn_url: str
) -> str:
    md = f"""# Чатбот IntraService · 1С Солярис

База знаний для **автоматического разбора заявок HelpDesk** (ServiceId **69**) и **самообучения AI-KB**.

| Страница | Назначение |
|----------|------------|
| [Руководство оператора]({guide_url}) | Как запускать бот, ревью и Promote статей |
| [Быстрые ответы: Солярис]({qa_solaris_url}) | Заказы, НС, резерв, EDI |
| [Выгрузка ТН (ОП-2765)]({qa_tn_url}) | Портал перевозчиков → 1С, XMLImportTransport |
| [Типовые кейсы 1 линии]({qa_l1_url}) | Q&A из инструкций раздела «Первая линия» |

**Родительский раздел:** [Первая линия поддержки](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=39887131)

**Локальный корпус (git):** `chatbot_intraservice/knowledge/1c/`
"""
    return cf.markdown_to_storage(md)


def main() -> int:
    load_package_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not QA_PATH.is_file():
        print(f"Нет {QA_PATH}", file=sys.stderr)
        return 1

    pub1c = _load_publish_1c()
    items = parse_qa_items(QA_PATH.read_text(encoding="utf-8"))
    if not items:
        print("Не распознаны статьи 1C-TN-*", file=sys.stderr)
        return 1

    hub_meta: dict[str, Any] = {}
    if HUB_META_PATH.is_file():
        hub_meta = json.loads(HUB_META_PATH.read_text(encoding="utf-8"))
    hub_id = str(hub_meta.get("hub_page_id") or "124642089")

    intro = (
        "# Быстрые ответы: 1С · Выгрузка ТН (ОП-2765)\n\n"
        "> Профиль чатбота `onec_logistics_tn`. Портал перевозчиков → **XMLImportTransport**.\n\n"
        f"Статей: **{len(items)}**. Коды **1C-TN-00…06**.\n\n"
        "Примеры заявок: #699796, #699810, #513629.\n\n"
        "**Формат:** вопрос → ключевые слова → «Ответ (копировать)».\n"
    )
    storage = pub1c.qa_page_storage(intro, items)

    s = cf.session()
    if args.dry_run:
        out = {
            "action": "dry_run",
            "title": QA_TITLE,
            "parent_id": hub_id,
            "items": len(items),
            "storage_len": len(storage),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    res = cf.create_or_update_child(
        s,
        space=SPACE,
        title=QA_TITLE,
        parent_id=hub_id,
        storage=storage,
        message="publish_1c_logistics_tn",
    )
    page_id = str(res.get("id") or "")
    page_url = cf.view_url(s, page_id) if page_id else ""

    meta = {
        "space": SPACE,
        "hub_page_id": hub_id,
        "page_id": page_id,
        "title": QA_TITLE,
        "url": page_url,
        "source_md": str(QA_PATH.relative_to(ROOT)).replace("\\", "/"),
        "instruction": "ОП-2765",
        "profile": "onec_logistics_tn",
        "promote_target_note": "Promote AI-KB для профиля onec_logistics_tn → эта страница",
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    guide_url = str(hub_meta.get("guide_url") or "")
    qa_s_url = str(hub_meta.get("qa_solaris_url") or "")
    qa_l_url = str(hub_meta.get("qa_l1_url") or "")
    if hub_id and guide_url and qa_s_url:
        cf.update_page(
            s,
            hub_id,
            title=str(hub_meta.get("hub_title") or "Чатбот IntraService · 1С Солярис"),
            storage=hub_storage_with_tn(guide_url, qa_s_url, qa_l_url, page_url),
            message="hub + logistics TN link",
        )
        hub_meta["qa_logistics_tn_page_id"] = page_id
        hub_meta["qa_logistics_tn_url"] = page_url
        hub_meta["qa_logistics_tn_title"] = QA_TITLE
        HUB_META_PATH.write_text(json.dumps(hub_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(json.dumps({"ok": True, "page_id": page_id, "url": page_url, "count": len(items)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
