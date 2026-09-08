# -*- coding: utf-8 -*-
"""Пайплайн заявки HelpDesk: шаги, артефакты в pipeline/runs/, интеграция с KB learning."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from settings import load_settings

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
RUNS_DIR = PKG / "pipeline" / "runs"

Trigger = Literal[
    "manual",
    "analyze",
    "watch_close",
    "watch_overdue",
    "watch_new",
    "watch_user_reply",
    "cli",
    "ui",
    "n8n",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PipelineRun:
    """Один прогон пайплайна по заявке — папка pipeline/runs/{run_id}/."""

    def __init__(self, task_id: str | int, trigger: Trigger = "manual") -> None:
        self.task_id = str(task_id).strip()
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self.run_id = f"{self.task_id}_{ts}_{uuid.uuid4().hex[:6]}"
        self.trigger = trigger
        self.settings = load_settings()
        self.started_at = _now_iso()
        self.steps: list[dict[str, Any]] = []
        self.status = "running"
        self.finished_at: str | None = None
        self.dir = RUNS_DIR / self.run_id
        if self.settings.get("pipeline_save_runs", True):
            self.dir.mkdir(parents=True, exist_ok=True)

    def _write_manifest(self) -> None:
        if not self.settings.get("pipeline_save_runs", True):
            return
        manifest = {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "trigger": self.trigger,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "settings_snapshot": {
                k: self.settings.get(k)
                for k in (
                    "auto_learn_kb",
                    "auto_learn_on_close",
                    "auto_learn_on_analyze",
                    "auto_post_comment",
                    "auto_take_in_work",
                    "skip_if_in_progress_or_awaiting",
                    "link_related_on_post",
                    "add_parent_creator_as_observer",
                    "skip_if_kb_found",
                    "skip_if_draft_exists",
                )
            },
            "steps": [{"id": s["id"], "status": s["status"], "title": s["title"]} for s in self.steps],
        }
        (self.dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def step(self, step_id: str, title: str) -> "_StepCtx":
        return _StepCtx(self, step_id, title)

    def finish(self, status: str = "completed", result: dict[str, Any] | None = None) -> None:
        self.status = status
        self.finished_at = _now_iso()
        if self.settings.get("pipeline_save_runs", True):
            self._write_manifest()
            if result is not None:
                (self.dir / "result.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )

    @staticmethod
    def list_runs(limit: int = 30) -> list[dict[str, Any]]:
        if not RUNS_DIR.is_dir():
            return []
        runs: list[dict[str, Any]] = []
        for path in sorted(RUNS_DIR.iterdir(), reverse=True):
            if not path.is_dir():
                continue
            mf = path / "manifest.json"
            if mf.is_file():
                try:
                    runs.append(json.loads(mf.read_text(encoding="utf-8")))
                except Exception:
                    runs.append({"run_id": path.name, "status": "unknown"})
            else:
                runs.append({"run_id": path.name, "status": "legacy"})
            if len(runs) >= limit:
                break
        return runs


class _StepCtx:
    def __init__(self, run: PipelineRun, step_id: str, title: str) -> None:
        self.run = run
        self.step_id = step_id
        self.title = title
        self.started = _now_iso()
        self._payload: dict[str, Any] = {}

    def __enter__(self) -> "_StepCtx":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        status = "failed" if exc else "completed"
        row = {
            "id": self.step_id,
            "title": self.title,
            "status": status,
            "started_at": self.started,
            "finished_at": _now_iso(),
            "error": str(exc)[:500] if exc else None,
        }
        self.run.steps.append(row)
        if self.run.settings.get("pipeline_save_runs", True):
            steps_dir = self.run.dir / "steps"
            steps_dir.mkdir(parents=True, exist_ok=True)
            out = {"step": row, **self._payload}
            (steps_dir / f"{self.step_id}.json").write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self.run._write_manifest()

    def save(self, payload: dict[str, Any]) -> None:
        self._payload = payload


def run_ticket_pipeline(
    task_id: str | int,
    *,
    post: bool | None = None,
    learn: bool | None = None,
    take_in_work: bool | None = None,
    trigger: Trigger = "manual",
) -> dict[str, Any]:
    """Полный пайплайн: analyze → (post) → auto-learn по настройкам."""
    import importlib.util

    settings = load_settings()
    run = PipelineRun(task_id, trigger=trigger)
    script = PKG / "scripts" / "analyze_and_comment.py"
    spec = importlib.util.spec_from_file_location("analyze_and_comment", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("analyze_and_comment.py не найден")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    do_post = bool(post) if post is not None else bool(settings.get("auto_post_comment"))
    do_take = bool(take_in_work) if take_in_work is not None else bool(settings.get("auto_take_in_work"))
    if learn is True:
        learn_mode = "force"
    elif learn is False:
        learn_mode = "off"
    elif settings.get("auto_learn_kb") and settings.get("auto_learn_on_analyze"):
        learn_mode = "auto"
    else:
        learn_mode = "off"

    result: dict[str, Any] = {}
    with run.step("01_analyze", "Разбор ассистентом") as step:
        result = mod.run_pipeline(
            str(task_id),
            post=do_post,
            learn_mode=learn_mode,
            trigger=trigger,
            pipeline_run=run,
            take_in_work=do_take,
        )
        step.save(
            {
                "kb_gap": result.get("kb_gap"),
                "profile": result.get("profile"),
                "skipped": result.get("skipped"),
                "reason": result.get("reason"),
            }
        )

    with run.step("02_kb_learn", "Обучение AI-KB") as step:
        step.save(
            {
                "auto_learn_decision": result.get("auto_learn_decision"),
                "kb_learning": result.get("kb_learning"),
            }
        )

    run.finish("completed", result)
    result["pipeline_run_id"] = run.run_id
    result["pipeline_dir"] = str(run.dir) if settings.get("pipeline_save_runs") else None
    return result
