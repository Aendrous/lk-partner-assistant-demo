# -*- coding: utf-8 -*-
"""UI-хелперы: черновики AI-KB по командам ЛК / БП / 1С / CRM."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any, Callable

import kb_learning

HERE = Path(__file__).resolve().parent
PKG = HERE.parent

TEAM_ORDER: tuple[str, ...] = ("lk", "bp", "edi", "crm", "other", "all")

TEAM_META: dict[str, dict[str, Any]] = {
    "lk": {
        "label": "ЛК",
        "hint": "lk.iek.ru · ServiceId 731/732",
        "service_keys": frozenset({"lk"}),
    },
    "bp": {
        "label": "БП",
        "hint": "bp.iek.ru · ServiceId 833/827",
        "service_keys": frozenset({"bp"}),
    },
    "edi": {
        "label": "1С",
        "hint": "Солярис · ServiceId 69 · контур edi",
        "service_keys": frozenset({"edi", "1c", "onec", "solaris"}),
    },
    "crm": {
        "label": "CRM",
        "hint": "crmrf.iek.local",
        "service_keys": frozenset({"crm"}),
    },
    "other": {
        "label": "Прочее",
        "hint": "mail, vpn, kp и др.",
        "service_keys": frozenset(),
    },
    "all": {
        "label": "Все",
        "hint": "все контуры",
        "service_keys": frozenset(),
    },
}


def resolve_team(service_key: str | None) -> str:
    sk = (service_key or "other").strip().lower()
    if sk in {"1c", "onec", "solaris"}:
        return "edi"
    for key in ("lk", "bp", "edi", "crm"):
        if sk in TEAM_META[key]["service_keys"]:
            return key
    return "other"


def enrich_entry(entry: dict[str, Any]) -> dict[str, Any]:
    row = dict(entry)
    row["team"] = resolve_team(str(entry.get("service_key") or ""))
    row["team_label"] = TEAM_META[row["team"]]["label"]
    return row


def filter_team(entries: list[dict[str, Any]], team: str) -> list[dict[str, Any]]:
    if team == "all":
        return list(entries)
    return [e for e in entries if e.get("team") == team]


def count_pending_by_team(pending: list[dict[str, Any]]) -> dict[str, int]:
    counts = {k: 0 for k in TEAM_ORDER if k != "all"}
    for row in pending:
        team = str(row.get("team") or resolve_team(str(row.get("service_key") or "")))
        if team in counts:
            counts[team] += 1
    counts["all"] = len(pending)
    return counts


def team_target_markdown(team: str) -> str:
    if team in {"", "all", "other"}:
        return ""
    contour = team if team != "all" else "other"
    target = kb_learning.target_for_contour(contour)
    title = str(target.get("title") or target.get("qa_webkb_title") or "").strip()
    page_id = str(
        target.get("page_id")
        or target.get("fallback_page_id")
        or target.get("qa_webkb_page_id")
        or ""
    ).strip()
    url = (
        str(target.get("qa_webkb_url") or target.get("hub_url") or "").strip()
        or (kb_learning.confluence_view_url(page_id) if page_id else "")
    )
    space = str(target.get("target_space") or "WEBKB").strip()
    if not title and not url:
        return f"**Promote:** контур `{contour}` — целевая страница не задана в `kb_assistant_pages.json`."
    link = f"[{title or 'Быстрые ответы'}]({url})" if url else title
    note = str(target.get("target_note") or target.get("note") or "").strip()
    bits = [f"**Promote →** {link}", f"пространство **{space}**"]
    if note:
        bits.append(note)
    return " · ".join(bits)


def draft_preview_line(entry: dict[str, Any], *, max_len: int = 120) -> str:
    rel = str(entry.get("draft_path") or "").strip()
    if rel:
        path = PKG / rel
        if path.is_file():
            body = path.read_text(encoding="utf-8")
            insert = kb_learning.extract_insert_sections(body)
            blob = insert or body
            for pat in (
                r"(?im)^\*\*Сценарий:\*\*\s*(.+)$",
                r"(?im)^##\s+.+?\.\s*(.+)$",
                r"(?im)^\*\*Ключевые слова:\*\*\s*(.+)$",
            ):
                m = re.search(pat, blob)
                if m:
                    line = re.sub(r"\s+", " ", m.group(1).strip())
                    return line[:max_len]
            first = ""
            for raw in blob.splitlines():
                s = raw.strip()
                if not s or s.startswith("<!--") or s.startswith("#"):
                    continue
                first = re.sub(r"[*_`]", "", s)
                break
            if first:
                return first[:max_len]
    gap = kb_learning.humanize_gap_reason(str(entry.get("gap_reason") or ""))
    return (gap or "")[:max_len]


def draft_card_title(entry: dict[str, Any]) -> str:
    tid = str(entry.get("task_id") or "")
    mode = str(entry.get("mode") or "new")
    sup = str(entry.get("supplement_of") or "").strip()
    cf = " · CF" if entry.get("confluence_draft_page_id") else ""
    mode_bit = f" · доп. {sup}" if mode == "supplement" and sup else ""
    preview = draft_preview_line(entry)
    head = f"**{entry.get('code')}** · #{tid} · `{entry.get('status')}`{mode_bit}{cf}"
    if preview:
        return f"{head} — {preview}"
    return head


def load_draft_digest_module():
    spec = importlib.util.spec_from_file_location(
        "drafts_review_digest", PKG / "scripts" / "drafts_review_digest.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("drafts_review_digest.py not found")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_all_lists() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], Any]:
    mod = load_draft_digest_module()
    pending = [enrich_entry(e) for e in mod.list_pending_drafts()]
    published = [enrich_entry(e) for e in mod.list_published_drafts()]
    rejected = [enrich_entry(e) for e in mod.list_rejected_drafts()]
    return pending, published, rejected, mod


def team_radio_label(team: str, counts: dict[str, int]) -> str:
    meta = TEAM_META.get(team) or {}
    n = counts.get(team, 0)
    return f"{meta.get('label', team)} ({n})"


def search_filter(entries: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    if not q:
        return entries
    out: list[dict[str, Any]] = []
    for e in entries:
        hay = " ".join(
            str(e.get(k) or "")
            for k in ("code", "task_id", "service_key", "status", "gap_reason", "draft_path")
        ).lower()
        hay += " " + draft_preview_line(e).lower()
        if q in hay or q.lstrip("#") in str(e.get("task_id") or ""):
            out.append(e)
    return out
