# -*- coding: utf-8 -*-
"""После ревью черновика AI-KB: publish → rebuild corpus → sync Open WebUI Knowledge.

  python scripts/sync_kb_after_review.py --task-id 697221
  python scripts/sync_kb_after_review.py --draft docs/черновики_статей/lk-06_ns_reserve_hd697221.md
  python scripts/sync_kb_after_review.py --rebuild-only
  python scripts/sync_kb_after_review.py --task-id 697221 --skip-publish --skip-owui

Шаги:
  1) publish_kb_draft_confluence (если не --skip-publish)
  2) build_bp_corpus.py (если не --skip-rebuild)
  3) create_owui_bp_1c_models.py (идемпотентно обновляет Knowledge — если не --skip-owui)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import kb_learning  # noqa: E402


def _run(cmd: list[str], *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"ok": True, "dry_run": True, "cmd": cmd}
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "cmd": cmd,
        "stdout": (proc.stdout or "")[-2000:],
        "stderr": (proc.stderr or "")[-800:],
    }


def resolve_draft(args: argparse.Namespace) -> Path | None:
    if args.draft:
        p = Path(args.draft)
        if not p.is_absolute():
            p = ROOT / p
        return p if p.is_file() else None
    if args.task_id:
        entry = kb_learning.draft_exists_for_task(args.task_id)
        if not entry:
            # поиск в index по любому status
            for e in kb_learning.load_index().get("entries") or []:
                if str(e.get("task_id")) == str(args.task_id):
                    entry = e
                    break
        if entry and entry.get("draft_path"):
            p = ROOT / str(entry["draft_path"])
            return p if p.is_file() else None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync KB after human review")
    parser.add_argument("--task-id", type=str, default="")
    parser.add_argument("--draft", type=str, default="")
    parser.add_argument("--rebuild-only", action="store_true")
    parser.add_argument("--skip-publish", action="store_true")
    parser.add_argument("--skip-rebuild", action="store_true")
    parser.add_argument("--skip-owui", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    py = sys.executable
    out: dict[str, Any] = {"ok": True, "steps": [], "warnings": []}

    def _step_failed(step: dict[str, Any], *, critical: bool) -> None:
        if step.get("ok") or step.get("skipped"):
            return
        name = str(step.get("name") or "step")
        if critical:
            out["ok"] = False
        else:
            out["warnings"].append(f"{name}: см. stderr/stdout шага")


    if args.rebuild_only:
        args.skip_publish = True

    draft = None if args.rebuild_only else resolve_draft(args)
    if not args.rebuild_only and not draft:
        raise SystemExit("Укажите --task-id или --draft (файл черновика)")

    if draft and not args.skip_publish:
        step = _run(
            [py, "scripts/publish_kb_draft_confluence.py", str(draft.relative_to(ROOT))],
            dry_run=args.dry_run,
        )
        step["name"] = "publish"
        pub: dict[str, Any] | None = None
        if step.get("stdout"):
            try:
                raw = (step.get("stdout") or "").strip()
                if raw.startswith("{"):
                    pub = json.loads(raw)
                else:
                    for line in reversed(raw.splitlines()):
                        line = line.strip()
                        if line.startswith("{"):
                            pub = json.loads(line)
                            break
                if pub:
                    step["publish_result"] = pub
                    out["success_message"] = pub.get("success_message")
                    out["promote_plan"] = pub.get("promote_plan")
                    if pub.get("ok"):
                        step["ok"] = True
            except Exception:
                pass
        if not step.get("ok") and args.task_id:
            for row in kb_learning.load_index().get("entries") or []:
                if str(row.get("task_id")) == str(args.task_id) and str(row.get("status")) == "published":
                    step["ok"] = True
                    step["note"] = "Confluence обновлён (index=published, subprocess exit≠0)"
                    if not step.get("publish_result"):
                        pid = str(row.get("published_page_id") or row.get("target_page_id") or "")
                        step["publish_result"] = {
                            "ok": True,
                            "page_id": pid,
                            "url": kb_learning.confluence_view_url(pid) if pid else "",
                        }
                    break
        out["steps"].append(step)
        _step_failed(step, critical=True)
        if not step.get("ok") and not step.get("skipped"):
            out_path = ROOT / "_sync_kb_after_review.json"
            out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 1

    if not args.skip_rebuild:
        step = _run([py, "scripts/build_bp_corpus.py"], dry_run=args.dry_run)
        step["name"] = "rebuild_bp_corpus"
        out["steps"].append(step)
        _step_failed(step, critical=False)

        step = _run([py, "scripts/build_1c_corpus.py"], dry_run=args.dry_run)
        step["name"] = "rebuild_1c_corpus"
        out["steps"].append(step)
        _step_failed(step, critical=False)

    if not args.skip_owui:
        owui = ROOT / "scripts" / "create_owui_bp_1c_models.py"
        if owui.is_file():
            step = _run([py, str(owui), "--refresh-knowledge"], dry_run=args.dry_run)
            step["name"] = "owui_sync"
            step["note"] = "refresh corpus.md в support-bp/1c-webkb-safe"
            out["steps"].append(step)
            _step_failed(step, critical=False)
        else:
            out["steps"].append({"name": "owui_sync", "ok": False, "skipped": True, "reason": "нет скрипта"})

    publish_ok = any(s.get("name") == "publish" and s.get("ok") for s in out["steps"])
    if publish_ok and not out.get("ok"):
        # Promote в Confluence прошёл — не блокировать оператора из-за corpus/OWUI
        out["ok"] = True
        out["partial"] = True

    out_path = ROOT / "_sync_kb_after_review.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
