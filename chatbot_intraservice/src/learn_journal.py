# -*- coding: utf-8 -*-
"""Журнал событий самообучения (бот vs человек, вердикт KB, черновик)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
EVENTS_PATH = PKG / "knowledge" / "learned" / "learning_events.jsonl"
MAX_LINES = 5000


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def append_learn_event(event: dict[str, Any]) -> None:
    """Дописать строку JSONL (для ретро / дайджестов)."""
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": _now_iso(), **event}
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    _trim()


def _trim() -> None:
    if not EVENTS_PATH.is_file():
        return
    lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    if len(lines) <= MAX_LINES:
        return
    EVENTS_PATH.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")


def record_from_learn_result(task_id: str | int, result: dict[str, Any]) -> None:
    """Сжатая запись после learn_from_task_data."""
    cmp = result.get("learn_compare") or {}
    gap = result.get("gap_judgment") or {}
    append_learn_event(
        {
            "type": "kb_learn",
            "task_id": str(task_id),
            "ok": bool(result.get("ok")),
            "skipped": bool(result.get("skipped")),
            "reason": str(result.get("reason") or "")[:300],
            "code": str(result.get("code") or ""),
            "mode": str(result.get("mode") or ""),
            "updated_in_place": bool(result.get("updated_in_place")),
            "compare_aligned": cmp.get("aligned"),
            "compare_skipped": cmp.get("skipped"),
            "kb_lesson": str(cmp.get("kb_lesson_ru") or "")[:400],
            "gap_mode": gap.get("mode"),
            "gap_incomplete": gap.get("incomplete"),
            "target_page_id": gap.get("target_page_id") or result.get("target_page_id"),
            "confluence_search": gap.get("confluence_search"),
            "draft_path": str(result.get("draft_path") or "")[:200],
        }
    )


def load_events(limit: int = 200) -> list[dict[str, Any]]:
    if not EVENTS_PATH.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]
