# -*- coding: utf-8 -*-
"""Digest: черновики AI-KB, требующие ревью и публикации.

  python scripts/drafts_review_digest.py
  python scripts/drafts_review_digest.py --dry-run

Пишет pipeline/digests/drafts_review_YYYYMMDD.md (+ .json).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import kb_learning  # noqa: E402
import watch_common  # noqa: E402
from settings import load_settings  # noqa: E402

DIGEST_DIR = ROOT / "pipeline" / "digests"


def list_pending_drafts() -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    for entry in kb_learning.load_index().get("entries") or []:
        status = str(entry.get("status") or "draft").lower()
        if status not in {"draft", "in_review"}:
            continue
        page_id = entry.get("confluence_draft_page_id") or entry.get("target_page_id")
        review_url = (
            entry.get("confluence_draft_url")
            or (kb_learning.confluence_view_url(entry.get("confluence_draft_page_id")) if entry.get("confluence_draft_page_id") else "")
            or (kb_learning.confluence_view_url(page_id) if page_id else "")
        )
        pending.append(
            {
                "code": entry.get("code"),
                "task_id": entry.get("task_id"),
                "service_key": entry.get("service_key"),
                "status": status,
                "draft_path": entry.get("draft_path"),
                "gap_reason": entry.get("gap_reason"),
                "created_at": entry.get("created_at"),
                "helpdesk_url": entry.get("helpdesk_url")
                or f"https://helpdesk.iek.local/Task/View/{entry.get('task_id')}",
                "confluence_url": review_url,
                "confluence_draft_page_id": entry.get("confluence_draft_page_id"),
                "target_page_id": entry.get("target_page_id"),
                "mode": entry.get("mode") or "new",
                "supplement_of": entry.get("supplement_of") or "",
                "match_score": entry.get("match_score"),
            }
        )
    pending.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return pending


def list_rejected_drafts() -> list[dict[str, Any]]:
    rejected: list[dict[str, Any]] = []
    for entry in kb_learning.load_index().get("entries") or []:
        status = str(entry.get("status") or "").lower()
        if status != "rejected":
            continue
        review_url = ""
        if entry.get("confluence_draft_page_id"):
            review_url = kb_learning.confluence_view_url(entry.get("confluence_draft_page_id"))
        rejected.append(
            {
                "code": entry.get("code"),
                "task_id": entry.get("task_id"),
                "service_key": entry.get("service_key"),
                "status": status,
                "draft_path": entry.get("draft_path"),
                "rejection_reason": entry.get("rejection_reason"),
                "rejected_at": entry.get("rejected_at"),
                "confluence_url": review_url,
            }
        )
    rejected.sort(key=lambda r: str(r.get("rejected_at") or ""), reverse=True)
    return rejected


def list_published_drafts(*, limit: int = 20) -> list[dict[str, Any]]:
    """Недавно опубликованные в «Быстрые ответы» (для UI после Promote)."""
    rows: list[dict[str, Any]] = []
    for entry in kb_learning.load_index().get("entries") or []:
        if str(entry.get("status") or "").lower() != "published":
            continue
        pid = str(entry.get("published_page_id") or entry.get("target_page_id") or "")
        rows.append(
            {
                "code": entry.get("code"),
                "task_id": entry.get("task_id"),
                "service_key": entry.get("service_key"),
                "published_at": entry.get("published_at"),
                "published_page_id": pid,
                "published_url": kb_learning.confluence_view_url(pid) if pid else "",
                "helpdesk_url": entry.get("helpdesk_url")
                or f"https://helpdesk.iek.local/Task/View/{entry.get('task_id')}",
            }
        )
    rows.sort(key=lambda r: str(r.get("published_at") or ""), reverse=True)
    return rows[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-KB drafts pending review digest")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    if not settings.get("drafts_review_digest_enabled", True):
        print(
            json.dumps(
                {"ok": True, "skipped": True, "reason": "drafts_review_digest_enabled=false"},
                ensure_ascii=False,
            )
        )
        return 0

    pending = list_pending_drafts()
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out: dict[str, Any] = {
        "ok": True,
        "dry_run": args.dry_run,
        "generated_at": watch_common.utc_now_iso(),
        "pending_count": len(pending),
        "pending": pending,
        "actions": [
            "1. Открыть страницу [ЧЕРНОВИК] в Confluence (колонка Confluence)",
            "2. Отредактировать прямо в Confluence (без ПДн)",
            "3. python scripts/sync_kb_after_review.py --task-id <id>  → Быстрые ответы + corpus + OWUI",
            "4. Если страницы ещё нет: python scripts/push_kb_draft_confluence_review.py --all-pending",
        ],
    }

    md = [
        f"# AI-KB: черновики на ревью ({day})",
        "",
        f"Требуется ревью и публикация: **{len(pending)}**",
        "",
        "| Код | Заявка | Контур | Создан | Confluence | Черновик |",
        "|:--|:--|:--|:--|:--|:--|",
    ]
    for p in pending:
        md.append(
            f"| {p.get('code')} | [{p.get('task_id')}]({p.get('helpdesk_url')}) | "
            f"{p.get('service_key')} | {(p.get('created_at') or '')[:10]} | "
            f"{('[открыть](' + p['confluence_url'] + ')') if p.get('confluence_url') else '—'} | "
            f"`{p.get('draft_path')}` |"
        )
    if not pending:
        md.append("| — | — | — | — | — | нет черновиков |")
    md.extend(
        [
            "",
            "## Что сделать",
            "",
            "1. Прочитать и поправить markdown в `docs/черновики_статей/`.",
            "2. Опубликовать: `python scripts/sync_kb_after_review.py --task-id <id>`",
            "   (Confluence → rebuild corpus → OWUI Knowledge).",
            "",
            f"Сгенерировано: {out['generated_at']}",
            "",
        ]
    )

    if not args.dry_run:
        DIGEST_DIR.mkdir(parents=True, exist_ok=True)
        json_path = DIGEST_DIR / f"drafts_review_{day}.json"
        md_path = DIGEST_DIR / f"drafts_review_{day}.md"
        watch_common.dump_json(json_path, out)
        md_path.write_text("\n".join(md), encoding="utf-8")
        out["files"] = [json_path.name, md_path.name]
        # актуальная «витрина» для UI
        latest = DIGEST_DIR / "drafts_review_latest.md"
        latest.write_text("\n".join(md), encoding="utf-8")
        out["latest"] = latest.name

    watch_common.dump_json(ROOT / "_drafts_review_digest.json", out)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("\n" + "\n".join(md[: min(25, len(md))]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
