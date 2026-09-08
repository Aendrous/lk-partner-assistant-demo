# -*- coding: utf-8 -*-
"""Публикация базы чатбота IntraService в пространство Confluence 1C (1 линия).

Создаёт под «Первая линия поддержки» (pageId 39887131):
  - хаб «Чатбот IntraService · 1С Солярис»
  - руководство оператора (разбор заявок + AI-KB)
  - быстрые ответы (корпус + Q&A из инструкций L1 / Солярис)

  python scripts/publish_1c_l1_confluence.py
  python scripts/publish_1c_l1_confluence.py --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
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
L1_ROOT_PAGE_ID = "39887131"
SOLARIS_SECTION_ID = "50023946"  # «Солярис инструкции»

HUB_TITLE = "Чатбот IntraService · 1С Солярис"
GUIDE_TITLE = "Руководство: чатбот IntraService и AI-KB (1 линия)"
QA_SOLARIS_TITLE = "Быстрые ответы: 1С Солярис (чатбот)"
QA_L1_TITLE = "Быстрые ответы: типовые кейсы 1 линии (инструкции)"

META_PATH = ROOT / "docs" / "confluence" / "onec_l1_hub.json"
TREE_PATH = ROOT / "_l1_1c_tree.json"

_HD_TITLE_RE = re.compile(
    r"helpdesk\.iek\.local|/Task/View/|#\d{5,}|^Заявка\s+на\s+HD",
    re.I,
)
_PROBLEM_BLOCK_RE = re.compile(
    r"(?:(\d+)\.\s*)?([^\n]+?)\s*Проблема:\s*(.*?)\s*Решение:\s*(.*?)(?=\n\d+\.\s|\Z)",
    re.I | re.S,
)


def _load_build_1c():
    spec = importlib.util.spec_from_file_location("build_1c_corpus", ROOT / "scripts" / "build_1c_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def _xml_esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _answer_plain(answer: str) -> str:
    t = answer or ""
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    return t.replace("]]>", "]] >").strip()[:3500]


def qa_item_storage(item: dict[str, str]) -> str:
    qid = item.get("id", "1C-Q")
    question = item.get("question", "")
    kw = item.get("keywords", "")
    parts = [
        f"<h4>{_xml_esc(qid)}. {_xml_esc(question)}</h4>",
        f"<p><strong>Ключевые слова:</strong> {_xml_esc(kw)}</p>",
    ]
    if item.get("not_confused_with"):
        parts.append(
            f"<p><strong>Не путать с:</strong> {_xml_esc(item['not_confused_with'])}</p>"
        )
    code = _answer_plain(item.get("answer", ""))
    if item.get("not_confused_with"):
        code = f"Не путать с: {item['not_confused_with']}\n\n{code}"
    code = f"Ключевые слова: {kw}\n\n{code}".strip()
    parts.append(
        '<ac:structured-macro ac:name="expand" ac:schema-version="1">'
        '<ac:parameter ac:name="title">Ответ (копировать)</ac:parameter>'
        "<ac:rich-text-body>"
        '<ac:structured-macro ac:name="code" ac:schema-version="1">'
        '<ac:parameter ac:name="language">text</ac:parameter>'
        f"<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>"
        "</ac:structured-macro></ac:rich-text-body></ac:structured-macro>"
    )
    if item.get("source_url"):
        parts.append(
            f'<p><strong>Источник:</strong> <a href="{_xml_esc(item["source_url"])}">'
            f'{_xml_esc(item.get("source_title") or "Confluence")}</a></p>'
        )
    parts.append("<hr />")
    return "\n".join(parts)


def qa_page_storage(intro_md: str, items: list[dict[str, str]]) -> str:
    blocks = [cf.markdown_to_storage(intro_md)]
    for item in items:
        blocks.append(qa_item_storage(item))
    return "\n".join(blocks)


def guide_storage() -> str:
    md = """# Руководство оператора: чатбот IntraService и AI-KB (1С)

## Назначение

**Чатбот IntraService** помогает **исполнителю** HelpDesk разобрать заявку за ~10 секунд:
скрытый комментарий, проверки, черновик ответа, ссылки на KB.

Контур **1С Солярис**: HelpDesk ServiceId **69** (родитель «1С Предприятие» 14).

## Как запустить разбор

1. Панель оператора: `streamlit run app.py` → вкладка **Запуск** → номер заявки.
2. CLI: `python scripts/analyze_and_comment.py <task_id>` (без `--post` — только предпросмотр).
3. Автоматически: watch / n8n на ServiceId **69** (см. `config/settings.default.json`).

В артефакте `_analysis_<id>.json` и в UI «История» — промпт system/user и preview скрытого комментария.

## Что делает бот для 1С

| Шаг | Действие |
|-----|----------|
| Профиль | `onec_tickets` — корпус `knowledge/1c/`, Confluence **1C** + WEBKB + LK |
| Prefetch | CQL-поиск по теме заявки в пространстве **1C** |
| Проверка 1С | По номеру заказа ХИ… (резерв в пути), если настроен COM/HTTP |
| Контур | `edi` / EDI · 1С в скрытом комментарии |

## Быстрые ответы (эта база)

- **Быстрые ответы: 1С Солярис** — сценарии для ServiceId 69 (заказы, НС, резерв, EDI).
- **Типовые кейсы 1 линии** — Q&A из инструкций раздела [Первая линия поддержки](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=39887131).

Коды статей: **1C-01…** (ручной корпус), **1C-L1-…** (из инструкций L1).

## Самообучение AI-KB

После закрытия заявки (если включено в UI / settings):

1. Черновик → `docs/черновики_статей/` + `knowledge/learned/index.json`.
2. Оператор правит блок **KB_INSERT** в Streamlit (вкладка AI-KB).
3. **Promote** → статья дописывается в **«Быстрые ответы: 1С Солярис»** (эта папка, пространство **1C**).
4. `sync_kb_after_review.py` пересобирает локальный корпус и OWUI knowledge.

### Ревью — что проверить

- Только **шаги для исполнителя**, без переписки HD и PII.
- Не дублировать существующий **1C-** код (дедуп в UI).
- **Отклонить** с причиной — учтётся при следующем learn.

### Метки Confluence

Черновики на ревью (опционально) — страницы с меткой `ai-kb-draft` под хабом чатбота.

## Связь с ЛК и WEB

Заявка на **Солярис** разбирается по **1С**, даже если тема про отображение в ЛК (НС, остатки).
Смежные статьи ЛК — только как справка (LK-06 резерв в пути).

## Обновление базы

```powershell
cd chatbot_intraservice
python scripts/build_1c_corpus.py
python scripts/publish_1c_l1_confluence.py
```

Контакт по доработкам пайплайна: репозиторий `chatbot_intraservice`, `docs/pipeline/самообучение_1c_solaris.md`.
"""
    return cf.markdown_to_storage(md)


def hub_storage(guide_url: str, qa_solaris_url: str, qa_l1_url: str) -> str:
    md = f"""# Чатбот IntraService · 1С Солярис

База знаний для **автоматического разбора заявок HelpDesk** (ServiceId **69**) и **самообучения AI-KB**.

| Страница | Назначение |
|----------|------------|
| [Руководство оператора]({guide_url}) | Как запускать бот, ревью и Promote статей |
| [Быстрые ответы: Солярис]({qa_solaris_url}) | Основной корпус Q&A для чатбота |
| [Типовые кейсы 1 линии]({qa_l1_url}) | Q&A из инструкций раздела «Первая линия поддержки» |

**Родительский раздел:** [Первая линия поддержки](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=39887131)

**Локальный корпус (git):** `chatbot_intraservice/knowledge/1c/`
"""
    return cf.markdown_to_storage(md)


def _parent_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {str(r["id"]): str(r.get("parent") or "") for r in rows}


def _under_section(page_id: str, section_id: str, pmap: dict[str, str]) -> bool:
    cur = page_id
    seen: set[str] = set()
    while cur and cur not in seen:
        if cur == section_id:
            return True
        seen.add(cur)
        cur = pmap.get(cur, "")
    return False


def _is_process_page(row: dict[str, Any]) -> bool:
    title = str(row.get("title") or "")
    if _HD_TITLE_RE.search(title):
        return False
    if row.get("body_len", 0) < 350:
        return False
    text = str(row.get("body_text") or "")
    if len(text) < 200:
        return False
    return True


def _keywords_from_title(title: str) -> str:
    t = re.sub(r"[^\w\s\-./]", " ", title.lower(), flags=re.UNICODE)
    words = [w for w in t.split() if len(w) > 2][:12]
    return ", ".join(words)[:120]


def extract_qa_from_page(row: dict[str, Any], *, prefix: str, seq: list[int]) -> list[dict[str, str]]:
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or "")
    text = str(row.get("body_text") or "").strip()
    out: list[dict[str, str]] = []

    pairs = list(_PROBLEM_BLOCK_RE.finditer(text))
    if pairs:
        for m in pairs:
            sub_title = (m.group(2) or title).strip()
            problem = re.sub(r"\s+", " ", (m.group(3) or "").strip())[:800]
            solution = re.sub(r"\s+", " ", (m.group(4) or "").strip())[:2000]
            if len(solution) < 40:
                continue
            seq[0] += 1
            out.append(
                {
                    "id": f"{prefix}{seq[0]:03d}",
                    "question": sub_title[:200],
                    "keywords": _keywords_from_title(sub_title),
                    "answer": f"Проблема: {problem}\n\nРешение: {solution}",
                    "source_url": url,
                    "source_title": title,
                }
            )
        return out

    if "Основная суть:" in text or re.search(r"^\d+\.\s", text, re.M):
        answer = text[:2200]
    else:
        answer = text[:1600]
    answer = re.sub(r"https?://helpdesk\.iek\.local/\S+", "[заявка HD]", answer)
    seq[0] += 1
    out.append(
        {
            "id": f"{prefix}{seq[0]:03d}",
            "question": title[:200],
            "keywords": _keywords_from_title(title),
            "answer": answer,
            "source_url": url,
            "source_title": title,
        }
    )
    return out


def build_l1_qa_items(rows: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    pmap = _parent_map(rows)
    solaris_seq = [0]
    l1_seq = [0]
    solaris_items: list[dict[str, str]] = []
    l1_items: list[dict[str, str]] = []
    seen: set[str] = set()

    for row in rows:
        if not _is_process_page(row):
            continue
        pid = str(row["id"])
        if _under_section(pid, SOLARIS_SECTION_ID, pmap):
            batch = extract_qa_from_page(row, prefix="1C-S-", seq=solaris_seq)
            target = solaris_items
        else:
            batch = extract_qa_from_page(row, prefix="1C-L1-", seq=l1_seq)
            target = l1_items
        for item in batch:
            h = hashlib.sha1((item["question"] + item["answer"][:200]).encode()).hexdigest()[:16]
            if h in seen:
                continue
            seen.add(h)
            target.append(item)

    return solaris_items[:55], l1_items[:70]


def load_tree_rows() -> list[dict[str, Any]]:
    if not TREE_PATH.is_file():
        raise FileNotFoundError(
            f"Нет {TREE_PATH.name}. Запустите crawl из publish или пересоберите дерево L1."
        )
    return json.loads(TREE_PATH.read_text(encoding="utf-8"))


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
        message="publish_1c_l1_confluence",
    )


def main() -> int:
    load_package_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    b1c = _load_build_1c()
    curated = b1c.curated_qa()

    if not TREE_PATH.is_file():
        print(f"WARN: нет {TREE_PATH.name} — только curated Q&A", file=sys.stderr)
        solaris_l1: list[dict[str, str]] = []
        other_l1: list[dict[str, str]] = []
    else:
        rows = load_tree_rows()
        solaris_l1, other_l1 = build_l1_qa_items(rows)

    qa_solaris = list(curated) + solaris_l1
    # renumber curated ids stay, L1 keep 1C-S-xxx

    s = cf.session()
    out: dict[str, Any] = {"space": SPACE, "l1_root": L1_ROOT_PAGE_ID, "pages": {}}

    if META_PATH.is_file():
        prev = json.loads(META_PATH.read_text(encoding="utf-8"))
        hub_id = str(prev.get("hub_page_id") or "")
    else:
        hub_id = ""

    # 1) Hub
    if hub_id and not args.dry_run:
        hub_page = cf.get_page(s, hub_id, expand="version")
    else:
        hub_page = None

    if not hub_page:
        placeholder = cf.markdown_to_storage(
            f"# {HUB_TITLE}\n\n(ссылки обновятся после публикации дочерних страниц)"
        )
        hub_res = publish_page(
            s,
            space=SPACE,
            title=HUB_TITLE,
            parent_id=L1_ROOT_PAGE_ID,
            storage=placeholder,
            dry_run=args.dry_run,
        )
        hub_id = str(hub_res.get("id") or hub_id or "")
    out["pages"]["hub"] = {"page_id": hub_id, "title": HUB_TITLE}

    # 2) Guide
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
    out["pages"]["guide"] = {"page_id": guide_id, "url": guide_url}

    # 3) Q&A Solaris
    intro_solaris = (
        "# Быстрые ответы: 1С Солярис (чатбот IntraService)\n\n"
        "> HelpDesk ServiceId **69**. Promote из AI-KB дописывает сюда блоки **1C-NN**.\n\n"
        f"Статей: **{len(qa_solaris)}** (ручной корпус + инструкции раздела «Солярис»).\n\n"
        "**Формат:** вопрос → ключевые слова → «Ответ (копировать)».\n"
    )
    qa_s_storage = qa_page_storage(intro_solaris, qa_solaris)
    qa_s_res = publish_page(
        s,
        space=SPACE,
        title=QA_SOLARIS_TITLE,
        parent_id=hub_id,
        storage=qa_s_storage,
        dry_run=args.dry_run,
    )
    qa_s_id = str(qa_s_res.get("id") or "")
    qa_s_url = cf.view_url(s, qa_s_id) if qa_s_id else ""
    out["pages"]["qa_solaris"] = {"page_id": qa_s_id, "url": qa_s_url, "count": len(qa_solaris)}

    # 4) Q&A L1 other
    intro_l1 = (
        "# Быстрые ответы: типовые кейсы 1 линии (инструкции)\n\n"
        "> Сгенерировано из страниц раздела "
        "[Первая линия поддержки](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=39887131) "
        "(формат «Проблема / Решение» и процессные статьи).\n\n"
        f"Статей: **{len(other_l1)}**. Коды **1C-L1-***.\n"
    )
    qa_l_storage = qa_page_storage(intro_l1, other_l1)
    qa_l_res = publish_page(
        s,
        space=SPACE,
        title=QA_L1_TITLE,
        parent_id=hub_id,
        storage=qa_l_storage,
        dry_run=args.dry_run,
    )
    qa_l_id = str(qa_l_res.get("id") or "")
    qa_l_url = cf.view_url(s, qa_l_id) if qa_l_id else ""
    out["pages"]["qa_l1"] = {"page_id": qa_l_id, "url": qa_l_url, "count": len(other_l1)}

    # 5) Update hub with links
    if hub_id and not args.dry_run:
        cf.update_page(
            s,
            hub_id,
            title=HUB_TITLE,
            storage=hub_storage(guide_url, qa_s_url, qa_l_url),
            message="hub links",
        )

    meta = {
        "space": SPACE,
        "l1_root_page_id": L1_ROOT_PAGE_ID,
        "l1_root_url": "https://confluence.dev.iek.ru/pages/viewpage.action?pageId=39887131",
        "hub_page_id": hub_id,
        "hub_title": HUB_TITLE,
        "hub_url": cf.view_url(s, hub_id) if hub_id else "",
        "guide_page_id": guide_id,
        "guide_url": guide_url,
        "qa_solaris_page_id": qa_s_id,
        "qa_solaris_url": qa_s_url,
        "qa_solaris_title": QA_SOLARIS_TITLE,
        "qa_l1_page_id": qa_l_id,
        "qa_l1_url": qa_l_url,
        "promote_target_page_id": qa_s_id,
        "note": "Promote AI-KB (контур edi) → qa_solaris_page_id",
    }
    if not args.dry_run:
        META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    out["meta"] = meta
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
