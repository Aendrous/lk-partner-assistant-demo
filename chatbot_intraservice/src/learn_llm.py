# -*- coding: utf-8 -*-
"""Модель и контекст для пайплайна самообучения AI-KB."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
INDEX_PATH = PKG / "knowledge" / "learned" / "index.json"

_WORD = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{4,}")


def learn_kb_model() -> str:
    """Модель для learn_compare / kb_gap_llm (с проверкой /v1/models)."""
    import sys

    repo = PKG.parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    import llm_client

    raw = (
        os.environ.get("IEK_LLM_LEARN_MODEL")
        or os.environ.get("IEK_LLM_SUPPORT_MODEL")
        or llm_client.DEFAULT_SUPPORT_MODEL
    )
    fb = (
        os.environ.get("IEK_LLM_SUPPORT_FALLBACK_MODEL")
        or llm_client.DEFAULT_SUPPORT_MODEL
    )
    return llm_client.resolve_model(raw, fallback=fb)


def load_index() -> dict[str, Any]:
    if not INDEX_PATH.is_file():
        return {"entries": []}
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"entries": []}


def load_rejected_entries(*, service_key: str = "") -> list[dict[str, Any]]:
    sk = (service_key or "").strip().lower()
    out: list[dict[str, Any]] = []
    for row in load_index().get("entries") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").lower() != "rejected":
            continue
        if sk and str(row.get("service_key") or "").lower() not in {sk, "", "other"}:
            continue
        out.append(row)
    return out


def rejected_paths_set() -> set[str]:
    return {
        str(e.get("draft_path") or "").replace("\\", "/")
        for e in load_rejected_entries()
        if e.get("draft_path")
    }


def rejected_codes_set(*, service_key: str = "") -> set[str]:
    return {
        str(e.get("code") or "").upper()
        for e in load_rejected_entries(service_key=service_key)
        if e.get("code")
    }


def rejection_for_code(code: str) -> dict[str, Any] | None:
    key = (code or "").strip().upper()
    if not key:
        return None
    for row in load_rejected_entries():
        if str(row.get("code") or "").upper() == key:
            return row
    return None


def is_rejected_code(code: str) -> bool:
    return rejection_for_code(code) is not None


def _overlap_score(query: str, blob: str) -> int:
    q = {w.lower() for w in _WORD.findall(query or "")}
    b = {w.lower() for w in _WORD.findall(blob or "")}
    if not q or not b:
        return 0
    return len(q & b)


def rejection_context(
    query: str,
    *,
    service_key: str = "",
    task_id: str | int = "",
    limit: int = 5,
) -> str:
    """Текст для промпта: что уже отклоняли на ревью и почему."""
    tid = str(task_id).strip()
    rows: list[tuple[int, dict[str, Any]]] = []
    for row in load_rejected_entries(service_key=service_key):
        blob = " ".join(
            str(row.get(k) or "")
            for k in ("code", "gap_reason", "rejection_reason", "service_key")
        )
        score = _overlap_score(query, blob)
        if tid and str(row.get("task_id")) == tid:
            score += 100
        if score > 0 or row.get("rejection_reason"):
            rows.append((score, row))
    rows.sort(key=lambda x: x[0], reverse=True)
    lines: list[str] = []
    for score, row in rows[:limit]:
        if score <= 0 and not row.get("rejection_reason"):
            continue
        code = row.get("code") or "?"
        reason = str(row.get("rejection_reason") or "без причины")[:300]
        lines.append(f"- {code} (HD#{row.get('task_id')}): {reason}")
    if not lines:
        return ""
    return "Ранее отклонённые черновики (учесть, не повторять ошибку):\n" + "\n".join(lines)
