# -*- coding: utf-8 -*-
"""Единая точка входа: пайплайн заявки с записью в pipeline/runs/.

  python scripts/run_ticket_pipeline.py 696955
  python scripts/run_ticket_pipeline.py 696955 --post --learn
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

import intraservice  # noqa: E402
import llm_client  # noqa: E402
from pipeline import run_ticket_pipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Пайплайн разбора заявки HelpDesk")
    parser.add_argument("task_id", help="Номер заявки")
    parser.add_argument("--post", action="store_true", help="Записать скрытый комментарий")
    parser.add_argument("--learn", action="store_true", help="Принудительно создать черновик AI-KB")
    parser.add_argument("--no-learn", action="store_true", help="Не обучать даже если auto включён")
    args = parser.parse_args()

    if not intraservice.has_credentials():
        raise SystemExit("Нет IntraService credentials")
    if not llm_client.has_credentials():
        raise SystemExit("Нет IEK_LLM_TOKEN")

    learn = False if args.no_learn else (True if args.learn else None)
    result = run_ticket_pipeline(
        args.task_id.strip(),
        post=args.post or None,
        learn=learn,
        trigger="cli",
    )

    out_path = ROOT / f"_pipeline_{args.task_id.strip()}.json"
    summary = {
        "task_id": result.get("task_id"),
        "pipeline_run_id": result.get("pipeline_run_id"),
        "pipeline_dir": result.get("pipeline_dir"),
        "profile": result.get("profile"),
        "kb_gap": result.get("kb_gap"),
        "auto_learn_decision": result.get("auto_learn_decision"),
        "kb_learning": result.get("kb_learning"),
        "comment_preview": result.get("comment_preview"),
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        print(result.get("comment_preview") or "")
        print("---")
        print("run_id=", result.get("pipeline_run_id"))
        print("learn=", (result.get("kb_learning") or {}).get("ok"), (result.get("kb_learning") or {}).get("reason"))
    except UnicodeEncodeError:
        sys.stdout.buffer.write(json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
