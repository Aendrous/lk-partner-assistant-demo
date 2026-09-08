# -*- coding: utf-8 -*-
"""Публикация черновика KB в Confluence (append к быстрым ответам WEBKB).

  python scripts/publish_kb_draft_confluence.py docs/черновики_статей/bp-06_api_hd696965.md
  python scripts/publish_kb_draft_confluence.py --task-id 696965

Если у записи в index есть confluence_draft_page_id — берём тело из Confluence
(правки команды в UI), иначе — локальный .md.

Требует CONFLUENCE_PAT. После публикации: python scripts/build_bp_corpus.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import confluence_client as cf  # noqa: E402
import kb_learning  # noqa: E402
import kb_promote_preview  # noqa: E402
import kb_insert_builder  # noqa: E402


def extract_promote_markdown(md: str) -> tuple[str, str]:
    """Только текст для вставки (KB_INSERT) + краткий заголовок; без meta/PII ревью."""
    insert = kb_learning.extract_insert_sections(md)
    if insert:
        insert = kb_insert_builder.sanitize_kb_insert_for_promote(insert)
        insert = kb_insert_builder.enrich_insert_from_draft(md, insert)
        code_m = re.search(r"(?im)^#\s+(?:Черновик|Дополнение):\s*([A-Z0-9+-]+)", md)
        code = (code_m.group(1) if code_m else "").strip()
        meta = kb_insert_builder.parse_draft_context(md)
        sup = meta.get("supplement_of") or ""
        # заголовок: код + одна строка сценария (для людей и поиска)
        scenario_m = re.search(r"\*\*Сценарий:\*\*\s*(.+)", insert)
        scenario_short = (scenario_m.group(1)[:90] + "…") if scenario_m else ""
        if sup:
            head = f"### {sup} — дополнение ({code})\n\n"
        else:
            head = f"### {code or 'AI-KB'}\n\n"
        if scenario_short:
            head += f"*{scenario_short}*\n\n"
        return head + insert.strip() + "\n", "kb_insert"
    # fallback: весь md (старые черновики без маркеров)
    return md, "full_md"


def markdown_block_to_storage(md: str) -> str:
    body_md, _src = extract_promote_markdown(md)
    is_sup = bool(
        re.search(r"(?im)^#\s*Дополнение:|^\*\*Режим:\*\*\s*supplement|статья неполная", md)
    )
    if is_sup:
        banner = (
            '<ac:structured-macro ac:name="info" ac:schema-version="1">'
            "<ac:rich-text-body>"
            "<p><strong>Дополнение к быстрым ответам</strong> — блок ниже для исполнителей "
            "(сценарий + ключевые слова + шаги). Страница ревью — архив.</p>"
            "</ac:rich-text-body></ac:structured-macro>"
        )
    else:
        banner = (
            '<ac:structured-macro ac:name="info" ac:schema-version="1">'
            "<ac:rich-text-body>"
            "<p><strong>AI-KB</strong> — блок вставки после ревью (без PII/meta черновика).</p>"
            "</ac:rich-text-body></ac:structured-macro>"
        )
    return banner + "\n" + cf.markdown_to_storage(body_md)


def strip_review_banner(storage: str) -> str:
    """Убрать info/warning-макрос черновика перед переносом в «Быстрые ответы»."""
    cleaned = re.sub(
        r'<ac:structured-macro ac:name="(?:warning|info)">[\s\S]*?</ac:structured-macro>\s*',
        "",
        storage or "",
        count=1,
    ).strip()
    return cleaned


def append_to_page(s, page_id: str, storage_append: str, message: str) -> dict:
    page = cf.get_page(s, page_id, expand="body.storage,version,title")
    old = ((page.get("body") or {}).get("storage") or {}).get("value") or ""
    version = int((page.get("version") or {}).get("number") or 1)
    payload = {
        "id": page_id,
        "type": "page",
        "title": page.get("title"),
        "version": {"number": version + 1, "message": message[:200]},
        "body": {
            "storage": {
                "value": old + "\n<hr/>\n" + storage_append,
                "representation": "storage",
            }
        },
    }
    resp = s.put(f"{s.base}/rest/api/content/{page_id}", json=payload, timeout=90)  # type: ignore[attr-defined]
    if resp.status_code >= 400:
        raise RuntimeError(f"Confluence PUT HTTP {resp.status_code}: {resp.text[:800]}")
    return resp.json()


def resolve_draft_path(task_id: str = "", draft: str = "") -> Path:
    if draft:
        p = Path(draft)
        return p if p.is_absolute() else ROOT / p
    index = kb_learning.load_index()
    for row in index.get("entries") or []:
        if str(row.get("task_id")) == str(task_id):
            return ROOT / str(row.get("draft_path"))
    raise SystemExit(f"Черновик для #{task_id} не найден в knowledge/learned/index.json")


def find_index_entry(task_id: str = "", draft_path: Path | None = None) -> dict | None:
    index = kb_learning.load_index()
    rel = ""
    if draft_path:
        try:
            rel = str(draft_path.resolve().relative_to(ROOT)).replace("\\", "/")
        except Exception:
            rel = str(draft_path).replace("\\", "/")
    for row in index.get("entries") or []:
        if task_id and str(row.get("task_id")) == str(task_id):
            return row
        if rel and str(row.get("draft_path") or "").replace("\\", "/") == rel:
            return row
    return None


def mark_published(task_id: str, page_id: str) -> None:
    index = kb_learning.load_index()
    for row in index.get("entries") or []:
        if str(row.get("task_id")) == str(task_id):
            row["status"] = "published"
            row["published_page_id"] = page_id
            row["published_at"] = kb_learning._now_iso()
    kb_learning.save_index(index)


def archive_review_page(s, entry: dict | None, code: str) -> dict | None:
    """После Promote — удалить страницу ревью (черновик только локально)."""
    if not entry:
        return None
    rid = str(entry.get("confluence_draft_page_id") or "").strip()
    if not rid:
        return None
    try:
        resp = s.delete(
            f"{s.base}/rest/api/content/{rid}",  # type: ignore[attr-defined]
            timeout=60,
        )
        if resp.status_code in (200, 204):
            return {"ok": True, "action": "deleted", "page_id": rid}
        return {
            "ok": False,
            "action": "delete_failed",
            "page_id": rid,
            "status": resp.status_code,
            "hint": f"Удалите вручную: {cf.view_url(s, rid)}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "action": "delete_failed",
            "page_id": rid,
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "hint": f"Удалите вручную: {cf.view_url(s, rid)}",
        }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser()
    parser.add_argument("draft", nargs="?", help="Путь к .md черновику")
    parser.add_argument("--task-id", help="Взять черновик из index по task_id")
    parser.add_argument("--page-id", help="Override pageId (иначе из kb_assistant_pages.json)")
    parser.add_argument("--from-local", action="store_true", help="Игнорировать Confluence review page")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = resolve_draft_path(args.task_id or "", args.draft or "")
    if not path.is_file():
        raise SystemExit(f"Файл не найден: {path}")
    md = path.read_text(encoding="utf-8")
    entry = find_index_entry(args.task_id or "", path)
    plan = kb_promote_preview.build_promote_plan(entry or {"draft_path": str(path.relative_to(ROOT))}, md)

    m = re.search(r"\*\*Контур:\*\*\s*(\w+)", md)
    contour = (
        (m.group(1) if m else "")
        or str((entry or {}).get("service_key") or "")
        or "bp"
    ).lower()
    profile_key = str(
        (entry or {}).get("profile_key") or (entry or {}).get("assistant_profile") or ""
    ).strip()
    target = kb_learning.target_for_contour(contour, profile_key=profile_key)
    # всегда contour mapping; не брать мусорный target_page_id из старых черновиков
    page_id = (
        args.page_id
        or plan.get("target_page_id")
        or target.get("page_id")
        or target.get("fallback_page_id")
    )
    if not page_id:
        raise SystemExit(f"Не задан page_id для контура {contour}")

    s = cf.session()
    # Prefer local md with KB_INSERT markers (sanitize); Confluence review may have edits
    # inside the same markers — try extract from storage first, else local insert.
    source = "local_md"
    body_md, insert_src = extract_promote_markdown(md)
    storage = markdown_block_to_storage(md)
    review_id = "" if args.from_local else str((entry or {}).get("confluence_draft_page_id") or "")
    if review_id:
        try:
            rev = cf.get_page(s, review_id, expand="body.storage,title")
            raw = ((rev.get("body") or {}).get("storage") or {}).get("value") or ""
            cleaned = strip_review_banner(raw)
            # HTML-комментарии KB_INSERT в storage
            insert_html = kb_learning.extract_insert_sections(cleaned)
            if insert_html:
                banner = (
                    '<ac:structured-macro ac:name="info"><ac:rich-text-body>'
                    "<p><strong>AI-KB</strong> — только блок вставки из страницы ревью.</p>"
                    "</ac:rich-text-body></ac:structured-macro>"
                )
                # insert_html может быть plain text из комментариев; обернём в storage
                storage = banner + "\n" + cf.markdown_to_storage(insert_html)
                source = f"confluence_review_insert:{review_id}"
                insert_src = "kb_insert"
            elif cleaned and insert_src == "full_md":
                # старый черновик без маркеров — не тащим весь review body с PII
                # если локально тоже full — тогда review; иначе local insert уже в storage
                banner = (
                    '<ac:structured-macro ac:name="info"><ac:rich-text-body>'
                    "<p><strong>AI-KB</strong> — после ревью (legacy, без KB_INSERT).</p>"
                    "</ac:rich-text-body></ac:structured-macro>"
                )
                storage = banner + "\n" + cleaned
                source = f"confluence_review:{review_id}"
        except Exception:
            source = "local_md_fallback"

    if args.dry_run:
        print(
            json.dumps(
                {
                    "page_id": page_id,
                    "chars": len(storage),
                    "source": source,
                    "insert_src": insert_src,
                    "insert_preview": body_md[:400],
                    "promote_plan": plan,
                    "success_message": kb_promote_preview.format_success_message(plan),
                },
                ensure_ascii=False,
            )
        )
        return 0

    result = append_to_page(s, str(page_id), storage, f"AI-KB publish {path.name}")
    tid_m = re.search(r"HelpDesk #(\d+)", md)
    tid = tid_m.group(1) if tid_m else str((entry or {}).get("task_id") or "")
    code = str((entry or {}).get("code") or path.stem.split("_")[0].upper())
    if tid:
        mark_published(tid, str(page_id))
    archive = archive_review_page(s, entry, code)

    payload = json.dumps(
        {
            "ok": True,
            "page_id": page_id,
            "url": cf.view_url(s, page_id),
            "confluence_id": result.get("id"),
            "source": source,
            "review_archived": archive,
            "promote_plan": plan,
            "success_message": kb_promote_preview.format_success_message(
                plan, publish_url=cf.view_url(s, page_id)
            ),
        },
        ensure_ascii=False,
        indent=2,
    )
    try:
        print(payload)
    except UnicodeEncodeError:
        print(json.dumps(json.loads(payload), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
