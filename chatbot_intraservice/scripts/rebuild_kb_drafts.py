# -*- coding: utf-8 -*-
"""Пересборка черновиков AI-KB по новому шаблону (compose_kb_article + KB_INSERT).

Сохраняет коды и пути из index.json; не трогает published / merged_into.

  python scripts/rebuild_kb_drafts.py --dry-run
  python scripts/rebuild_kb_drafts.py --limit 3
  python scripts/rebuild_kb_drafts.py
  python scripts/rebuild_kb_drafts.py --push-confluence
  python scripts/rebuild_kb_drafts.py --task-id 696955
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import kb_learning  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Пересобрать in_review черновики AI-KB")
    ap.add_argument("--dry-run", action="store_true", help="не писать файлы")
    ap.add_argument("--push-confluence", action="store_true", help="обновить страницы ревью в Confluence")
    ap.add_argument("--use-gap-llm", action="store_true", help="повторно вызвать gap LLM (медленнее)")
    ap.add_argument("--limit", type=int, default=0, help="макс. число черновиков (0 = все)")
    ap.add_argument("--task-id", action="append", default=[], help="только указанные HD id")
    args = ap.parse_args()

    task_ids = [str(t).strip() for t in args.task_id if str(t).strip()]
    summary = kb_learning.rebuild_all_review_drafts(
        push_confluence=args.push_confluence,
        dry_run=args.dry_run,
        use_gap_llm=args.use_gap_llm,
        limit=args.limit,
        task_ids=task_ids or None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for row in summary.get("results") or []:
        tid = row.get("task_id")
        if row.get("skipped"):
            print(f"SKIP {tid}: {row.get('reason')}", file=sys.stderr)
        elif not row.get("ok"):
            print(f"FAIL {tid}: {row.get('error') or row}", file=sys.stderr)
        else:
            fb = " (fallback)" if row.get("compose_fallback") else ""
            print(f"OK {tid} {row.get('code')}{fb}", file=sys.stderr)
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
