# -*- coding: utf-8 -*-
"""Автозапуск обучения AI-KB при закрытии заявок (cron / Task Scheduler).

  python scripts/pipeline_watch.py
  python scripts/pipeline_watch.py --dry-run

Условия (см. config/settings.default.json):
  - auto_learn_kb=true (master switch)
  - auto_learn_on_close=true
  - skip_if_kb_found / skip_if_draft_exists
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests
import urllib3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

import intraservice  # noqa: E402
import kb_learning  # noqa: E402
from pipeline import PipelineRun, run_ticket_pipeline  # noqa: E402
from settings import load_settings  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def fetch_closed_tasks(service_ids: list[int], status_ids: list[int], page_size: int) -> list[dict]:
    intraservice.load_env()
    base = intraservice.api_base()
    user = intraservice._user()
    password = (os.environ.get("INTRASERVICE_PASSWORD") or "").strip()
    params: dict[str, str] = {
        "StatusIds": ",".join(str(x) for x in status_ids),
        "pagesize": str(page_size),
        "page": "1",
        "fields": "Id,Name,StatusId,ServiceId,Changed",
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


def process_closed_task(task_id: str, *, dry_run: bool) -> dict:
    settings = load_settings()
    task = intraservice.get_task(task_id)
    analysis = kb_learning.load_analysis(task_id)
    if not analysis:
        if dry_run:
            return {"task_id": task_id, "action": "would_analyze_first", "dry_run": True}
        result = run_ticket_pipeline(task_id, trigger="watch_close")
        analysis = kb_learning.load_analysis(task_id)
        return {"task_id": task_id, "action": "analyzed", "pipeline_run_id": result.get("pipeline_run_id")}

    decision = kb_learning.should_auto_learn(
        task, analysis, trigger="watch_close", settings=settings
    )
    if dry_run:
        return {"task_id": task_id, "decision": decision, "dry_run": True}

    if not decision.get("run"):
        return {"task_id": task_id, "skipped": True, "reason": decision.get("reason")}

    run = PipelineRun(task_id, trigger="watch_close")
    lifetime = None
    try:
        lifetime = intraservice.get_task_lifetime(task_id)
    except Exception:
        pass
    learn_result = kb_learning.learn_from_task_data(
        task, analysis, lifetime=lifetime, force=False, require_closed=True
    )
    with run.step("01_learn", "Черновик AI-KB") as step:
        step.save({"decision": decision, "learn": learn_result})
    run.finish("completed" if learn_result.get("ok") else "skipped", learn_result)
    learn_result["pipeline_run_id"] = run.run_id
    return learn_result


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch closed HelpDesk tickets for AI-KB learning")
    parser.add_argument("--dry-run", action="store_true", help="Только показать что будет сделано")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    if not intraservice.has_credentials():
        raise SystemExit("Нет IntraService credentials")

    settings = load_settings()
    if not settings.get("auto_learn_kb"):
        print(json.dumps({"ok": True, "skipped": True, "reason": "auto_learn_kb выключен"}, ensure_ascii=False))
        return 0
    if not settings.get("auto_learn_on_close"):
        print(json.dumps({"ok": True, "skipped": True, "reason": "auto_learn_on_close выключен"}, ensure_ascii=False))
        return 0

    import service_filter

    service_ids = service_filter.effective_watch_service_ids(
        settings,
        legacy_key="watch_service_ids",
        default=[731, 732, 833],
        action="kb_learn",
    )
    status_ids = list(settings.get("watch_closed_status_ids") or [28, 29])
    tasks = fetch_closed_tasks(service_ids, status_ids, max(args.limit * 3, 20))

    results: list[dict] = []
    for row in tasks:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("Id") or "")
        if not tid:
            continue
        if len(results) >= args.limit:
            break
        try:
            results.append(process_closed_task(tid, dry_run=args.dry_run))
        except Exception as exc:
            results.append({"task_id": tid, "ok": False, "error": str(exc)[:300]})

    out = {"ok": True, "count": len(results), "dry_run": args.dry_run, "results": results}
    out_path = ROOT / "_pipeline_watch.json"
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
