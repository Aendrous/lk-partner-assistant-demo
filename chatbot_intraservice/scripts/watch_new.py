# -*- coding: utf-8 -*-
"""Watch: новые/переданные заявки (31/38/121) → разбор пайплайном.

Пост и «взять в работу» — только если в настройках auto_post_comment / auto_take_in_work.

  python scripts/watch_new.py
  python scripts/watch_new.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import urllib3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

import call_history  # noqa: E402
import intraservice  # noqa: E402
import overdue  # noqa: E402
import watch_common  # noqa: E402
from pipeline import run_ticket_pipeline  # noqa: E402
from settings import load_settings  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SEEN_PATH = ROOT / "pipeline" / "seen_new.json"


def _is_fresh(task_row: dict[str, Any], max_age_hours: float) -> bool:
    if max_age_hours <= 0:
        return True
    from datetime import datetime, timezone

    raw = str(task_row.get("Changed") or task_row.get("Created") or "")
    dt = overdue.parse_dt(raw)
    if dt is None:
        return True
    age_h = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0
    return age_h <= max_age_hours


def process_task(
    task_row: dict[str, Any],
    *,
    dry_run: bool,
    settings: dict[str, Any],
    seen: dict[str, Any],
) -> dict[str, Any]:
    tid = str(task_row.get("Id") or "").strip()
    if not tid:
        return {"ok": False, "error": "no id"}

    import service_filter

    skip_watch = service_filter.skip_for_task(task_row, "watch", settings)
    if skip_watch:
        return {"task_id": tid, "skipped": True, "reason": skip_watch}

    changed = str(task_row.get("Changed") or task_row.get("Created") or "")
    prev = (seen.get("tasks") or {}).get(tid) or {}
    if prev.get("handled") and prev.get("Changed") == changed:
        return {"task_id": tid, "skipped": True, "reason": "уже обработана (тот же Changed)"}
    if prev.get("handled") and not changed:
        return {"task_id": tid, "skipped": True, "reason": "уже в seen_new"}

    # Антидубль петли: наш пост сам обновляет Changed → без этого watch_new
    # постил один и тот же скрытый разбор каждые 15 мин (#696928).
    if prev.get("handled") and prev.get("posted"):
        try:
            lifetime = intraservice.get_task_lifetime(tid, page_size=40)
            full_task = intraservice.get_task(tid) or task_row
        except Exception:
            lifetime = None
            full_task = task_row
        new_user = watch_common.find_new_user_comment(
            lifetime or {},
            after_date=prev.get("at") or prev.get("Changed"),
            max_age_hours=float(settings.get("watch_new_max_age_hours") or 72),
            creator_id=full_task.get("CreatorId"),
            creator_name=str(full_task.get("Creator") or ""),
            executor_ids=full_task.get("ExecutorIds"),
            requester_only=True,
        )
        if not new_user:
            # обновить Changed в seen, чтобы не долбить API зря
            seen.setdefault("tasks", {})[tid] = {
                **prev,
                "Changed": changed,
                "at": watch_common.utc_now_iso(),
                "skip_reason": "нет нового комментария после поста (антипетля Changed)",
            }
            return {
                "task_id": tid,
                "skipped": True,
                "reason": "уже постили; Changed от своего комментария / без нового user-input",
            }

    do_post = bool(settings.get("auto_post_comment"))
    do_take = bool(settings.get("auto_take_in_work"))

    if dry_run:
        return {
            "task_id": tid,
            "dry_run": True,
            "action": "would_analyze",
            "Name": task_row.get("Name"),
            "StatusId": task_row.get("StatusId"),
            "ServiceId": task_row.get("ServiceId"),
            "Changed": changed,
            "post": do_post,
            "take_in_work": do_take,
            "url": intraservice.task_url(tid),
        }

    result = run_ticket_pipeline(
        tid,
        post=do_post,
        take_in_work=do_take,
        trigger="watch_new",
    )
    # после поста Changed в HD новее — зафиксировать актуальный
    fresh_changed = changed
    try:
        if (result.get("post") or {}).get("ok"):
            fresh = intraservice.get_task(tid)
            fresh_changed = str(fresh.get("Changed") or changed)
    except Exception:
        pass

    seen.setdefault("tasks", {})[tid] = {
        "Changed": fresh_changed,
        "handled": True,
        "pipeline_run_id": result.get("pipeline_run_id"),
        "skipped": result.get("skipped"),
        "reason": result.get("reason"),
        "posted": bool((result.get("post") or {}).get("ok")) or bool(prev.get("posted")),
        "at": watch_common.utc_now_iso(),
        "name": result.get("task_name") or task_row.get("Name"),
        "ServiceId": task_row.get("ServiceId"),
        "StatusId": task_row.get("StatusId"),
        "url": intraservice.task_url(tid),
    }
    call_history.append_event(
        {
            "type": "watch_new",
            "task_id": tid,
            "ok": not result.get("skipped"),
            "pipeline_run_id": result.get("pipeline_run_id"),
            "skipped": result.get("skipped"),
            "reason": result.get("reason"),
            "post": do_post,
            "take_in_work": do_take,
        }
    )
    return {
        "task_id": tid,
        "ok": True,
        "pipeline": {
            "skipped": result.get("skipped"),
            "reason": result.get("reason"),
            "pipeline_run_id": result.get("pipeline_run_id"),
            "post": (result.get("post") or {}).get("ok"),
            "comment_preview": (result.get("comment_preview") or "")[:400],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch new/transferred HelpDesk tickets")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    if not intraservice.has_credentials():
        raise SystemExit("Нет IntraService credentials")

    settings = load_settings()
    if not settings.get("watch_new_enabled", True):
        print(json.dumps({"ok": True, "skipped": True, "reason": "watch_new_enabled=false"}, ensure_ascii=False))
        return 0

    import service_filter

    service_ids = service_filter.effective_watch_service_ids(
        settings,
        legacy_key="watch_new_service_ids",
        default=[731, 732, 833, 827],
        action="watch",
    )
    status_ids = list(settings.get("watch_new_status_ids") or [31, 38, 121])
    max_age = float(settings.get("watch_new_max_age_hours") or 72)
    page_size = max(args.limit * 4, 40)

    candidates = watch_common.list_tasks(
        service_ids=service_ids, status_ids=status_ids, page_size=page_size
    )
    # свежие сверху; отсечь слишком старые (иначе вечные «Передана» за годы)
    candidates = [r for r in candidates if isinstance(r, dict) and _is_fresh(r, max_age)]
    candidates.sort(key=lambda r: str((r or {}).get("Changed") or ""), reverse=True)

    seen = watch_common.load_seen(SEEN_PATH)
    results: list[dict] = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        if len(results) >= args.limit:
            break
        try:
            results.append(
                process_task(row, dry_run=args.dry_run, settings=settings, seen=seen)
            )
        except Exception as exc:
            results.append({"task_id": row.get("Id"), "ok": False, "error": str(exc)[:300]})

    if not args.dry_run:
        watch_common.save_seen(SEEN_PATH, seen)

    out = {
        "ok": True,
        "dry_run": args.dry_run,
        "candidates": len(candidates),
        "checked": len(results),
        "actionable": len([r for r in results if r.get("pipeline") or r.get("dry_run")]),
        "auto_post_comment": bool(settings.get("auto_post_comment")),
        "auto_take_in_work": bool(settings.get("auto_take_in_work")),
        "results": results,
    }
    watch_common.dump_json(ROOT / "_watch_new.json", out)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
