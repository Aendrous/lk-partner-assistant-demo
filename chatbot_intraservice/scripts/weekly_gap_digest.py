# -*- coding: utf-8 -*-
"""Weekly digest: закрытые заявки с gap в KB и без черновика AI-KB.

  python scripts/weekly_gap_digest.py
  python scripts/weekly_gap_digest.py --dry-run --limit 30
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import urllib3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

import intraservice  # noqa: E402
import kb_learning  # noqa: E402
import watch_common  # noqa: E402
from settings import load_settings  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DIGEST_DIR = ROOT / "pipeline" / "digests"


def main() -> int:
    parser = argparse.ArgumentParser(description="Gap digest for closed tickets without AI-KB draft")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()

    if not intraservice.has_credentials():
        raise SystemExit("Нет IntraService credentials")

    settings = load_settings()
    if not settings.get("gap_digest_enabled", True):
        print(json.dumps({"ok": True, "skipped": True, "reason": "gap_digest_enabled=false"}, ensure_ascii=False))
        return 0

    import service_filter

    service_ids = service_filter.effective_watch_service_ids(
        settings,
        legacy_key="watch_service_ids",
        default=[731, 732, 833],
        action="kb_learn",
    )
    status_ids = list(settings.get("watch_closed_status_ids") or [28, 29])
    tasks = watch_common.list_tasks(
        service_ids=service_ids,
        status_ids=status_ids,
        page_size=max(args.limit * 3, 50),
        fields="Id,Name,StatusId,ServiceId,Changed,Created,CreatorEmail",
    )
    tasks.sort(key=lambda r: str((r or {}).get("Changed") or ""), reverse=True)

    gaps: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in tasks:
        if not isinstance(row, dict):
            continue
        if len(gaps) + len(skipped) >= args.limit * 2 and len(gaps) >= args.limit:
            break
        tid = str(row.get("Id") or "").strip()
        if not tid:
            continue
        analysis = kb_learning.load_analysis(tid)
        gap = kb_learning.assess_kb_gap(analysis)
        existing = kb_learning.draft_exists_for_task(tid)
        if existing:
            skipped.append(
                {
                    "task_id": tid,
                    "reason": f"черновик есть ({existing.get('code')})",
                    "status": existing.get("status"),
                }
            )
            continue
        if not gap.get("gap"):
            skipped.append({"task_id": tid, "reason": "KB был найден при разборе"})
            continue
        gaps.append(
            {
                "task_id": tid,
                "name": row.get("Name"),
                "ServiceId": row.get("ServiceId"),
                "StatusId": row.get("StatusId"),
                "Changed": row.get("Changed"),
                "gap_reason": gap.get("reason"),
                "has_analysis": analysis is not None,
                "url": intraservice.task_url(tid),
            }
        )
        if len(gaps) >= args.limit:
            break

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out = {
        "ok": True,
        "dry_run": args.dry_run,
        "generated_at": watch_common.utc_now_iso(),
        "gap_count": len(gaps),
        "skipped_count": len(skipped),
        "gaps": gaps,
        "skipped_sample": skipped[:20],
        "hint": "python scripts/learn_from_ticket.py <id>  или  analyze_and_comment.py <id> --learn",
    }

    md_lines = [
        f"# Gap digest {day}",
        "",
        f"Закрытые заявки без ответа в KB и без черновика AI-KB: **{len(gaps)}**",
        "",
        "| Task | Service | Changed | Причина |",
        "|:--|:--|:--|:--|",
    ]
    for g in gaps:
        md_lines.append(
            f"| [{g['task_id']}]({g['url']}) | {g.get('ServiceId')} | "
            f"{(g.get('Changed') or '')[:16]} | {(g.get('gap_reason') or '')[:80]} |"
        )
    if not gaps:
        md_lines.append("| — | — | — | нет пробелов |")
    md_lines.extend(["", f"Сгенерировано: {out['generated_at']}", ""])

    if not args.dry_run:
        DIGEST_DIR.mkdir(parents=True, exist_ok=True)
        json_path = DIGEST_DIR / f"gap_{day}.json"
        md_path = DIGEST_DIR / f"gap_{day}.md"
        watch_common.dump_json(json_path, out)
        md_path.write_text("\n".join(md_lines), encoding="utf-8")
        out["files"] = [json_path.name, md_path.name]

    watch_common.dump_json(ROOT / "_gap_digest.json", out)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if gaps:
        print("\n" + "\n".join(md_lines[: min(20, len(md_lines))]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
