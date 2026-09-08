# -*- coding: utf-8 -*-
"""Выгрузка черновиков AI-KB в Confluence как видимые страницы «на ревью».

Confluence Server/DC не даёт общих unpublished drafts через REST для всей команды.
Поэтому создаём обычные страницы под родителем «AI-KB: черновики на ревью»
с префиксом [ЧЕРНОВИК] и warning-баннером. Их все видят и правят в UI.
В боевые «Быстрые ответы» контент попадает только через sync_kb_after_review /
publish_kb_draft_confluence.

  python scripts/push_kb_draft_confluence_review.py --init-parent
  python scripts/push_kb_draft_confluence_review.py --task-id 697323
  python scripts/push_kb_draft_confluence_review.py --all-pending
  python scripts/push_kb_draft_confluence_review.py --dry-run --all-pending
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import confluence_client as cf  # noqa: E402
import kb_learning  # noqa: E402

PARENT_TITLE = "Чатбот IntraService: статьи самообучения (ревью)"
PARENT_INTRO = """
<ac:structured-macro ac:name="info"><ac:rich-text-body>
<p><strong>Папка самообучения чатбота IntraService.</strong> Дочерние страницы — статьи из закрытых заявок HelpDesk.
Править здесь как обычные страницы Confluence. Метка <code>ai-kb-draft</code> = ещё на ревью;
<code>ai-kb-published</code> = уже перенесено в «Быстрые ответы».</p>
<p>Не копировать в ответы заявителям до Promote.</p>
</ac:rich-text-body></ac:structured-macro>
<h2>Правила</h2>
<ol>
<li><strong>Править здесь</strong> — обычный заголовок вида <code>BP-06. …</code>. Не переносить вручную в «Быстрые ответы».</li>
<li><strong>Promote</strong> — Streamlit → «AI-KB черновики» → Promote, либо
<code>python scripts/sync_kb_after_review.py --task-id &lt;id&gt;</code>
(append в быстрые ответы, метка published, corpus + OWUI).</li>
<li><strong>Дубли</strong> — один task_id = одна статья; похожая тема на <em>in_review</em> → правка того же черновика (не плодить HD-xx-SUP-SUP).</li>
<li><strong>После Promote</strong> — только новый review-черновик; silent-edit опубликованной страницы запрещён.</li>
</ol>
"""


def _cfg() -> dict[str, Any]:
    pages = kb_learning.load_kb_pages()
    review = pages.get("ai_kb_review") or {}
    root = pages.get("chatbot_root_page_id") or "124630073"
    return {
        "space": pages.get("space") or "WEBKB",
        "parent_page_id": review.get("page_id"),
        "parent_of_parent": review.get("parent_page_id") or root,
        "title": review.get("title") or PARENT_TITLE,
        "pages": pages,
        "review": review,
    }


def save_parent_id(page_id: str) -> None:
    pages = kb_learning.load_kb_pages()
    review = dict(pages.get("ai_kb_review") or {})
    review["page_id"] = str(page_id)
    review["title"] = review.get("title") or PARENT_TITLE
    if not review.get("parent_page_id"):
        review["parent_page_id"] = pages.get("chatbot_root_page_id") or "124630073"
    pages["ai_kb_review"] = review
    kb_learning.KB_PAGES_PATH.write_text(
        json.dumps(pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def ensure_parent(s: Any, *, dry_run: bool = False) -> dict[str, Any]:
    cfg = _cfg()
    space = cfg["space"]
    title = cfg["title"]
    parent_of = str(cfg["parent_of_parent"])
    if cfg.get("parent_page_id"):
        pid = str(cfg["parent_page_id"])
        if dry_run:
            return {"ok": True, "page_id": pid, "url": cf.view_url(s, pid), "dry_run": True}
        try:
            page = cf.get_page(s, pid, expand="version,title")
            # обновить правила на корневой странице ревью
            cf.update_page(
                s,
                pid,
                title=title,
                storage=PARENT_INTRO.strip(),
                message="AI-KB review rules",
            )
            return {
                "ok": True,
                "page_id": str(page.get("id") or pid),
                "url": cf.view_url(s, page.get("id") or pid),
                "existed": True,
                "rules_updated": True,
            }
        except Exception:
            pass

    existing = cf.find_page_by_title(s, space=space, title=title)
    if existing:
        pid = str(existing["id"])
        if not dry_run:
            save_parent_id(pid)
            cf.add_labels(s, pid, ["ai-kb-review-root"])
        return {
            "ok": True,
            "page_id": pid,
            "url": cf.view_url(s, pid),
            "existed": True,
            "dry_run": dry_run,
        }

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "would_create": title,
            "parent": parent_of,
        }

    created = cf.create_page(
        s,
        space=space,
        title=title,
        parent_id=parent_of,
        storage=PARENT_INTRO.strip(),
        message="AI-KB review root",
    )
    pid = str(created.get("id"))
    save_parent_id(pid)
    cf.add_labels(s, pid, ["ai-kb-review-root"])
    return {"ok": True, "page_id": pid, "url": cf.view_url(s, pid), "created": True}


def draft_title(code: str, md: str, task_id: str, *, supplement_of: str = "") -> str:
    """Человеческий заголовок без [ЧЕРНОВИК]/[ОПУБЛИКОВАНО]."""
    m = re.search(r"^#\s+(?:Черновик|Дополнение):\s*(.+)$", md, re.M)
    raw = (m.group(1).strip() if m else "")[:120]
    raw = re.sub(rf"^{re.escape(code)}\s*[—\-–:]?\s*", "", raw, flags=re.I).strip()
    raw = re.sub(r"^к\s+([A-Z0-9-]+)\s*[—\-–:]?\s*", "", raw, flags=re.I).strip()
    if supplement_of or md.lstrip().startswith("# Дополнение"):
        base = supplement_of or code.split("-SUP")[0]
        topic = raw or f"HD#{task_id}"
        return f"Дополнение: {base} — {topic}"[:255]
    topic = raw or f"HD#{task_id}"
    # BP-06. Тема
    if re.match(rf"^{re.escape(code)}\.", topic, re.I):
        return topic[:255]
    return f"{code}. {topic}"[:255]


def update_index_row(
    task_id: str,
    *,
    confluence_draft_page_id: str,
    confluence_draft_url: str,
    status: str = "in_review",
) -> None:
    index = kb_learning.load_index()
    for row in index.get("entries") or []:
        if str(row.get("task_id")) == str(task_id):
            row["confluence_draft_page_id"] = confluence_draft_page_id
            row["confluence_draft_url"] = confluence_draft_url
            row["status"] = status
            row["pushed_to_confluence_at"] = kb_learning._now_iso()
            break
    kb_learning.save_index(index)


def push_one(
    s: Any,
    entry: dict[str, Any],
    *,
    parent_id: str,
    space: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    tid = str(entry.get("task_id") or "")
    code = str(entry.get("code") or "HD-00")
    path = ROOT / str(entry.get("draft_path") or "")
    if not path.is_file():
        return {"ok": False, "task_id": tid, "error": f"нет файла {path}"}

    md = path.read_text(encoding="utf-8")
    supplement_of = str(entry.get("supplement_of") or "")
    title = draft_title(code, md, tid, supplement_of=supplement_of)
    hd = entry.get("helpdesk_url") or f"https://helpdesk.iek.local/Task/View/{tid}"
    storage = (
        cf.review_banner(
            code=code, task_id=tid, helpdesk_url=str(hd), supplement_of=supplement_of
        )
        + "\n"
        + cf.markdown_to_storage(md)
    )

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "task_id": tid,
            "code": code,
            "title": title,
            "chars": len(storage),
            "parent_id": parent_id,
        }

    # если уже есть page_id — обновить; иначе create_or_update по title
    page_id = str(entry.get("confluence_draft_page_id") or "").strip()
    if page_id:
        try:
            page = cf.update_page(s, page_id, title=title, storage=storage, message=f"AI-KB review {code}")
        except Exception:
            page = cf.create_or_update_child(
                s,
                space=space,
                title=title,
                parent_id=parent_id,
                storage=storage,
                message=f"AI-KB review {code}",
            )
    else:
        page = cf.create_or_update_child(
            s,
            space=space,
            title=title,
            parent_id=parent_id,
            storage=storage,
            message=f"AI-KB review {code}",
        )

    pid = str(page.get("id"))
    url = cf.view_url(s, pid)
    cf.add_labels(s, pid, ["ai-kb-draft", f"hd-{tid}", str(code).lower().replace(" ", "-")])
    update_index_row(tid, confluence_draft_page_id=pid, confluence_draft_url=url)
    return {
        "ok": True,
        "task_id": tid,
        "code": code,
        "page_id": pid,
        "url": url,
        "title": title,
    }


def resolve_entries(args: argparse.Namespace) -> list[dict[str, Any]]:
    index = kb_learning.load_index().get("entries") or []
    if args.task_id:
        for e in index:
            if str(e.get("task_id")) == str(args.task_id):
                return [e]
        raise SystemExit(f"#{args.task_id} нет в knowledge/learned/index.json")
    if args.all_pending:
        return [
            e
            for e in index
            if str(e.get("status") or "draft").lower() in {"draft", "in_review"}
        ]
    if getattr(args, "refresh_existing", False):
        return [
            e
            for e in index
            if e.get("confluence_draft_page_id")
            and str(e.get("status") or "").lower() in {"draft", "in_review", "published"}
        ]
    if args.draft:
        p = Path(args.draft)
        if not p.is_absolute():
            p = ROOT / p
        # найти по пути или синтезировать entry
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        for e in index:
            if str(e.get("draft_path") or "").replace("\\", "/") == rel:
                return [e]
        m = re.search(r"hd(\d+)", p.stem, re.I)
        tid = m.group(1) if m else "0"
        code_m = re.match(r"([a-z]+-\d+)", p.stem, re.I)
        return [
            {
                "task_id": tid,
                "code": (code_m.group(1).upper() if code_m else "HD-00"),
                "draft_path": rel,
                "status": "draft",
            }
        ]
    raise SystemExit("Укажите --task-id / --all-pending / путь --draft")


def main() -> int:
    parser = argparse.ArgumentParser(description="Push AI-KB drafts to Confluence review folder")
    parser.add_argument("--init-parent", action="store_true", help="Создать/запомнить родителя ревью")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--draft", default="")
    parser.add_argument("--all-pending", action="store_true")
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Перезалить title+body для страниц с confluence_draft_page_id (причёска)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    s = cf.session()
    out: dict[str, Any] = {"ok": True, "steps": []}

    parent = ensure_parent(s, dry_run=args.dry_run)
    out["parent"] = parent
    if not parent.get("ok"):
        out["ok"] = False
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1

    if args.init_parent and not (args.task_id or args.draft or args.all_pending or args.refresh_existing):
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    parent_id = str(parent.get("page_id") or "")
    if not parent_id and not args.dry_run:
        out["ok"] = False
        out["error"] = "нет parent page_id"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1

    space = _cfg()["space"]
    if not (args.task_id or args.draft or args.all_pending or args.refresh_existing):
        raise SystemExit("Укажите --task-id / --all-pending / --refresh-existing / --draft")
    entries = resolve_entries(args)
    results = []
    for e in entries:
        r = push_one(
            s,
            e,
            parent_id=parent_id or str(_cfg()["parent_of_parent"]),
            space=space,
            dry_run=args.dry_run,
        )
        results.append(r)
        if not r.get("ok"):
            out["ok"] = False
    out["pushed"] = results
    out["count"] = len(results)

    out_path = ROOT / "_push_kb_draft_confluence_review.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
