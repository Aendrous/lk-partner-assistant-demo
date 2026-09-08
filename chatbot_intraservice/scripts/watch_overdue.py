# -*- coding: utf-8 -*-
"""Watch: заявки LK/BP с эскалацией «До просрочки» → взять в работу + скрытый комментарий.

Робот IntraService за ~30 мин до дедлайна пишет в lifetime:
  Comments: Заявка эскалирована по правилу "До просрочки".
  Editor: IntraService

  python scripts/watch_overdue.py
  python scripts/watch_overdue.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import urllib3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

import call_history  # noqa: E402
import overdue  # noqa: E402
import intraservice  # noqa: E402
from pipeline import run_ticket_pipeline  # noqa: E402
from settings import load_settings  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SEEN_PATH = ROOT / "pipeline" / "overdue_seen.json"


def find_overdue_marker(
    lifetime: dict[str, Any],
    marker: str,
    *,
    max_age_hours: float = 6.0,
) -> dict[str, Any] | None:
    return overdue.find_overdue_marker(lifetime, marker, max_age_hours=max_age_hours)


def _parse_dt(raw: str | None):
    return overdue.parse_dt(raw)


def _load_seen() -> dict[str, Any]:
    if not SEEN_PATH.is_file():
        return {"tasks": {}}
    try:
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"tasks": {}}


def _save_seen(data: dict[str, Any]) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_candidate_tasks(service_ids: list[int], status_ids: list[int], page_size: int) -> list[dict]:
    intraservice.load_env()
    base = intraservice.api_base()
    user = intraservice._user()
    password = (os.environ.get("INTRASERVICE_PASSWORD") or "").strip()
    params: dict[str, str] = {
        "StatusIds": ",".join(str(x) for x in status_ids),
        "pagesize": str(page_size),
        "page": "1",
        "fields": "Id,Name,StatusId,ServiceId,Deadline,Changed,Created,CreatorEmail",
    }
    if service_ids:
        params["ServiceIds"] = ",".join(str(x) for x in service_ids)
    resp = requests.get(
        f"{base}/task",
        params=params,
        auth=(user, password),
        headers={"Accept": "application/json"},
        timeout=60,
        verify=False,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("Tasks") or data.get("TaskList") or []


def process_task(
    task_row: dict[str, Any],
    *,
    dry_run: bool,
    marker: str,
    settings: dict[str, Any],
    seen: dict[str, Any],
) -> dict[str, Any]:
    tid = str(task_row.get("Id") or "").strip()
    if not tid:
        return {"ok": False, "error": "no id"}

    lifetime = intraservice.get_task_lifetime(tid, page_size=40)
    max_age = float(settings.get("watch_overdue_max_age_hours") or settings.get("_max_age_hours") or 6)
    hit = find_overdue_marker(lifetime, marker, max_age_hours=max_age)
    if not hit:
        return {"task_id": tid, "skipped": True, "reason": "нет свежей эскалации «До просрочки»"}

    prev = (seen.get("tasks") or {}).get(tid) or {}
    if prev.get("escalation_date") == hit.get("Date") and prev.get("handled"):
        return {"task_id": tid, "skipped": True, "reason": "уже обработана эта эскалация"}
    if overdue.already_handled_for_escalation(lifetime, hit.get("Date")):
        seen.setdefault("tasks", {})[tid] = {
            "escalation_date": hit.get("Date"),
            "handled": True,
            "skipped_reason": "follow-up уже в lifetime",
            "at": datetime.now(timezone.utc).isoformat(),
        }
        return {
            "task_id": tid,
            "skipped": True,
            "reason": "уже есть follow-up после эскалации робота",
            "escalation": hit,
        }

    task = intraservice.get_task(tid)
    if dry_run:
        return {
            "task_id": tid,
            "dry_run": True,
            "action": "would_take_and_analyze",
            "escalation": hit,
            "StatusId": task.get("StatusId"),
            "Deadline": task.get("Deadline") or task_row.get("Deadline"),
            "url": task.get("url"),
        }

    result = run_ticket_pipeline(
        tid,
        post=True,
        take_in_work=True,
        trigger="watch_overdue",
    )
    handled = not result.get("skipped")
    seen.setdefault("tasks", {})[tid] = {
        "escalation_date": hit.get("Date"),
        "handled": True,
        "pipeline_run_id": result.get("pipeline_run_id"),
        "skipped": result.get("skipped"),
        "reason": result.get("reason"),
        "at": datetime.now(timezone.utc).isoformat(),
        "name": task.get("Name"),
        "ServiceId": task.get("ServiceId"),
        "StatusId": task.get("StatusId"),
        "url": task.get("url") or intraservice.task_url(tid),
        "escalation": hit,
    }
    call_history.append_event(
        {
            "type": "overdue_watch",
            "task_id": tid,
            "ok": handled,
            "escalation": hit,
            "pipeline_run_id": result.get("pipeline_run_id"),
            "skipped": result.get("skipped"),
            "reason": result.get("reason"),
        }
    )
    return {
        "task_id": tid,
        "ok": True,
        "escalation": hit,
        "pipeline": {
            "skipped": result.get("skipped"),
            "reason": result.get("reason"),
            "pipeline_run_id": result.get("pipeline_run_id"),
            "post": (result.get("post") or {}).get("ok"),
            "take_in_work": result.get("take_in_work"),
            "comment_preview": (result.get("comment_preview") or "")[:400],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch IntraService overdue escalations (LK/BP)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    if not intraservice.has_credentials():
        raise SystemExit("Нет IntraService credentials")

    settings = load_settings()
    if not settings.get("watch_overdue_enabled", True):
        print(json.dumps({"ok": True, "skipped": True, "reason": "watch_overdue_enabled=false"}, ensure_ascii=False))
        return 0

    import service_filter

    service_ids = service_filter.effective_watch_service_ids(
        settings,
        legacy_key="watch_overdue_service_ids",
        default=[731, 732, 833, 827],
        action="watch",
    )
    status_ids = list(settings.get("watch_overdue_status_ids") or [31, 38, 121, 27, 46, 120])
    marker = str(settings.get("watch_overdue_marker") or overdue.DEFAULT_MARKER)
    page_size = max(args.limit * 4, 40)

    candidates = list_candidate_tasks(service_ids, status_ids, page_size)
    seen = _load_seen()
    results: list[dict] = []

    for row in candidates:
        if not isinstance(row, dict):
            continue
        if len(results) >= args.limit:
            break
        try:
            results.append(
                process_task(
                    row,
                    dry_run=args.dry_run,
                    marker=marker,
                    settings=settings,
                    seen=seen,
                )
            )
        except Exception as exc:
            results.append({"task_id": row.get("Id"), "ok": False, "error": str(exc)[:300]})

    if not args.dry_run:
        _save_seen(seen)

    actionable = [r for r in results if not r.get("skipped") or r.get("dry_run")]
    out = {
        "ok": True,
        "dry_run": args.dry_run,
        "candidates": len(candidates),
        "checked": len(results),
        "actionable": len([r for r in results if r.get("action") or r.get("pipeline")]),
        "results": results,
    }
    out_path = ROOT / "_watch_overdue.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
