# -*- coding: utf-8 -*-
"""Единая точка запуска watch/analyze для n8n (Execute Command или HTTP server).

  python scripts/n8n_run.py watch_new
  python scripts/n8n_run.py watch_overdue
  python scripts/n8n_run.py analyze 699465 --post
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

SCRIPTS: dict[str, str] = {
    "watch_new": "scripts/watch_new.py",
    "watch_overdue": "scripts/watch_overdue.py",
    "watch_user_reply": "scripts/watch_user_reply.py",
    "pipeline_watch": "scripts/pipeline_watch.py",
    "analyze": "scripts/analyze_and_comment.py",
}


def run_script(name: str, extra_args: list[str] | None = None) -> dict[str, Any]:
    rel = SCRIPTS.get(name)
    if not rel:
        return {"ok": False, "error": f"unknown action: {name}"}
    script = ROOT / rel
    if not script.is_file():
        return {"ok": False, "error": f"missing {script}"}
    cmd = [sys.executable, str(script)] + (extra_args or [])
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    try:
        body = json.loads(out) if out.startswith("{") else {"output": out[:4000]}
    except json.JSONDecodeError:
        body = {"output": out[:4000]}
    if "ok" not in body:
        body["ok"] = proc.returncode == 0
    body["exit_code"] = proc.returncode
    if err:
        body["stderr"] = err[:1000]
    body["action"] = name
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description="n8n runner for chatbot IntraService")
    parser.add_argument(
        "action",
        choices=list(SCRIPTS.keys()),
        help="watch_new | watch_overdue | watch_user_reply | pipeline_watch | analyze",
    )
    parser.add_argument("task_id", nargs="?", help="для analyze")
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--learn", action="store_true")
    parser.add_argument("--take-in-work", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    extra: list[str] = []
    if args.action == "analyze":
        if not args.task_id:
            print(json.dumps({"ok": False, "error": "task_id required"}, ensure_ascii=False))
            return 2
        extra = [args.task_id]
        if args.post:
            extra.append("--post")
        if args.learn:
            extra.append("--learn")
        if args.take_in_work:
            extra.append("--take-in-work")
    elif args.dry_run:
        extra = ["--dry-run"]

    result = run_script(args.action, extra_args=extra)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
