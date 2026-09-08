# -*- coding: utf-8 -*-
"""История вызовов LLM / Open WebUI-подсказок и результатов AI-KB обучения.

Пишется в knowledge/learned/call_history.jsonl (локально, не секреты).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
HISTORY_PATH = PKG / "knowledge" / "learned" / "call_history.jsonl"
MAX_LINES = 2000

PARTNER_LK_HINT = "https://chatgpt.iek.local/?model=partner-lk-web-helper"
PARTNER_LK_MODEL_ID = "partner-lk-web-helper"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def append_event(event: dict[str, Any]) -> Path:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": _now(), **event}
    with HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    _trim()
    return HISTORY_PATH


def record_llm_call(
    *,
    task_id: str | int | None,
    model: str,
    profile_key: str = "",
    openwebui_hint: str = "",
    ok: bool,
    response_preview: str = "",
    error: str = "",
    kind: str = "analyze",
) -> None:
    hint = (openwebui_hint or "").strip()
    is_partner = PARTNER_LK_MODEL_ID in hint or "partner-lk" in (model or "").lower()
    append_event(
        {
            "type": "llm_call",
            "kind": kind,
            "task_id": str(task_id) if task_id else None,
            "model": model,
            "profile_key": profile_key,
            "openwebui_hint": hint,
            "partner_lk_ui": is_partner,
            "ok": bool(ok),
            "response_preview": (response_preview or "")[:800],
            "error": (error or "")[:300],
        }
    )


def record_kb_learn(
    *,
    task_id: str | int,
    ok: bool,
    draft_path: str = "",
    reason: str = "",
    code: str = "",
) -> None:
    append_event(
        {
            "type": "kb_learn",
            "task_id": str(task_id),
            "ok": bool(ok),
            "draft_path": draft_path,
            "code": code,
            "reason": (reason or "")[:400],
            "article_written": bool(ok and draft_path),
        }
    )


def record_partner_lk_probe(
    *,
    ok: bool,
    response_preview: str = "",
    error: str = "",
    source: str = "ui_hint",
) -> None:
    """Явная отметка обращения к карточке partner-lk-web-helper (UI / n8n)."""
    append_event(
        {
            "type": "partner_lk_call",
            "openwebui_hint": PARTNER_LK_HINT,
            "model": PARTNER_LK_MODEL_ID,
            "partner_lk_ui": True,
            "ok": bool(ok),
            "response_preview": (response_preview or "")[:800],
            "error": (error or "")[:300],
            "source": source,
        }
    )


def _trim() -> None:
    if not HISTORY_PATH.is_file():
        return
    lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    if len(lines) <= MAX_LINES:
        return
    HISTORY_PATH.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")


def load_events(limit: int = 200) -> list[dict[str, Any]]:
    if not HISTORY_PATH.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def list_overdue_taken(limit: int = 100) -> list[dict[str, Any]]:
    """Заявки, которые watch_overdue взял в работу (из call_history + overdue_seen)."""
    seen_path = PKG / "pipeline" / "overdue_seen.json"
    by_id: dict[str, dict[str, Any]] = {}
    if seen_path.is_file():
        try:
            data = json.loads(seen_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        for tid, row in (data.get("tasks") or {}).items():
            if not isinstance(row, dict):
                continue
            by_id[str(tid)] = {
                "task_id": str(tid),
                "url": f"https://helpdesk.iek.local/Task/View/{tid}",
                "source": "overdue_seen",
                **row,
            }
    for ev in load_events(limit=800):
        if ev.get("type") != "overdue_watch":
            continue
        tid = str(ev.get("task_id") or "")
        if not tid:
            continue
        row = by_id.setdefault(
            tid,
            {"task_id": tid, "url": f"https://helpdesk.iek.local/Task/View/{tid}", "source": "call_history"},
        )
        row["last_event_ts"] = ev.get("ts")
        row["ok"] = ev.get("ok")
        row["skipped"] = ev.get("skipped")
        row["reason"] = ev.get("reason") or row.get("reason")
        row["pipeline_run_id"] = ev.get("pipeline_run_id") or row.get("pipeline_run_id")
        if ev.get("escalation"):
            row["escalation"] = ev.get("escalation")
    rows = sorted(
        by_id.values(),
        key=lambda r: str(r.get("at") or r.get("last_event_ts") or ""),
        reverse=True,
    )
    return rows[:limit]


def summarize(limit: int = 500) -> dict[str, Any]:
    events = load_events(limit=limit)
    llm = [e for e in events if e.get("type") == "llm_call"]
    partner = [
        e
        for e in events
        if e.get("type") == "partner_lk_call"
        or e.get("partner_lk_ui")
        or PARTNER_LK_MODEL_ID in str(e.get("openwebui_hint") or "")
    ]
    learns = [e for e in events if e.get("type") == "kb_learn"]
    written = [e for e in learns if e.get("article_written") or e.get("ok")]
    overdue = list_overdue_taken(50)
    return {
        "total_events": len(events),
        "llm_calls": len(llm),
        "partner_lk_calls": len(partner),
        "kb_learn_attempts": len(learns),
        "kb_articles_written": len(written),
        "overdue_taken_count": len(overdue),
        "partner_lk_hint": PARTNER_LK_HINT,
        "history_file": str(HISTORY_PATH),
        "recent_partner": partner[-10:],
        "recent_learns": learns[-10:],
        "recent_llm": llm[-15:],
        "overdue_taken": overdue,
    }
