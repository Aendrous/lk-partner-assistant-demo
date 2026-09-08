# -*- coding: utf-8 -*-
"""Подчинение дублирующих заявок HelpDesk (ParentId).

Отдельно от «похожих» заявок в комментарии: подчиняем только явные дубли
в один день и в открытом статусе, с одинаковым сильным идентификатором.
"""
from __future__ import annotations

import re
from typing import Any

import related_tasks
import service_filter

_GUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
_TENDER_FULL = re.compile(r"^[TТ]\d{6}-\d{3,}$")
_TENDER_PREFIX = re.compile(r"^[TТ]\d{6}$")

DEFAULT_LINK_BY_CONTOUR: dict[str, bool] = {
    "lk": True,
    "bp": True,
    "crm": False,
    "edi": True,
    "1c": True,
    "mail": True,
    "other": True,
}

DEFAULT_OPEN_STATUS_IDS = (31, 38, 121, 27, 46, 120)


def link_by_contour_map(settings: dict[str, Any] | None) -> dict[str, bool]:
    base = dict(DEFAULT_LINK_BY_CONTOUR)
    raw = (settings or {}).get("link_related_by_contour") or {}
    if isinstance(raw, dict):
        for key, val in raw.items():
            k = str(key).strip().lower()
            if k == "1c":
                k = "edi"
            base[k] = bool(val)
    return base


def link_enabled_for_task(
    settings: dict[str, Any] | None,
    task: dict[str, Any],
    parsed: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    if not (settings or {}).get("link_related_on_post", True):
        return False, "link_related_on_post=false"
    contour = service_filter.resolve_task_contour(task, parsed)
    if contour == "1c":
        contour = "edi"
    flags = link_by_contour_map(settings)
    if not flags.get(contour, True):
        label = service_filter.CONTOUR_LABELS.get(contour, contour)
        return False, f"контур {label}: подчинение дублей выключено"
    return True, None


def tokens_for_linking(
    refs: list[str],
    task: dict[str, Any],
    parsed: dict[str, Any] | None,
    *extra_blobs: str,
) -> list[str]:
    """Токены поиска дублей для подчинения (строже, чем для справки в комментарии)."""
    contour = service_filter.resolve_task_contour(task, parsed)
    if contour == "1c":
        contour = "edi"
    raw = related_tasks.tokens_from_refs(refs, *extra_blobs)
    out: list[str] = []
    for tok in raw:
        t = (tok or "").strip()
        if not t:
            continue
        if contour == "crm":
            # GUID компании/контрагента — годами одни и те же; не использовать для ParentId
            if _GUID.match(t):
                continue
            # префикс тендера T260831 без суффикса даёт сотни ложных совпадений
            if _TENDER_PREFIX.match(t) and not _TENDER_FULL.match(t):
                continue
        out.append(t)
    return out[:12]


def _created_day(created: str) -> str:
    return (created or "").strip()[:10]


def _status_open(status_id: Any, open_ids: set[int]) -> bool:
    try:
        return int(status_id) in open_ids
    except (TypeError, ValueError):
        return False


def filter_for_linking(
    current: dict[str, Any],
    related: list[dict[str, Any]],
    settings: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Оставить только кандидатов на подчинение: тот же день, открытые, тот же ServiceId."""
    open_ids = set((settings or {}).get("link_related_open_status_ids") or list(DEFAULT_OPEN_STATUS_IDS))
    same_day = bool((settings or {}).get("link_related_same_day_only", True))
    same_service = bool((settings or {}).get("link_related_same_service", True))

    cur_day = _created_day(str(current.get("Created") or ""))
    cur_sid = str(current.get("ServiceId") or "").strip()
    cur_status = current.get("StatusId")

    if not _status_open(cur_status, open_ids):
        return [], {
            "skipped": True,
            "reason": f"текущая заявка не в открытом статусе (StatusId={cur_status})",
        }

    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in related or []:
        reasons: list[str] = []
        if same_day and _created_day(str(row.get("Created") or "")) != cur_day:
            reasons.append("другой день")
        if not _status_open(row.get("StatusId"), open_ids):
            reasons.append(f"не открыта (StatusId={row.get('StatusId')})")
        if same_service and cur_sid and str(row.get("ServiceId") or "").strip() != cur_sid:
            reasons.append(f"другой ServiceId ({row.get('ServiceId')})")
        if reasons:
            rejected.append({"Id": row.get("Id"), "reasons": reasons})
        else:
            kept.append(row)

    return kept, {
        "same_day": same_day,
        "same_service": same_service,
        "open_status_ids": sorted(open_ids),
        "kept": len(kept),
        "rejected": len(rejected),
        "rejected_sample": rejected[:8],
    }


def plan_link(
    task: dict[str, Any],
    related: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    *,
    parsed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """План подчинения (dry-run) с учётом контура и фильтров."""
    enabled, reason = link_enabled_for_task(settings, task, parsed)
    if not enabled:
        return {"ok": True, "skipped": True, "reason": reason, "actions": []}
    filtered, meta = filter_for_linking(task, related, settings)
    if not filtered:
        return {
            "ok": True,
            "skipped": True,
            "reason": "нет дублей для подчинения (день/статус/сервис)",
            "filter": meta,
            "actions": [],
        }
    plan = related_tasks.link_later_to_earlier(task, filtered, apply=False)
    plan["filter"] = meta
    plan["related_total"] = len(related or [])
    plan["related_for_link"] = len(filtered)
    return plan


def apply_link_on_post(
    task: dict[str, Any],
    related: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    *,
    parsed: dict[str, Any] | None = None,
    add_observer: bool = True,
) -> dict[str, Any]:
    """Подчинить дубли при --post (или пропустить с причиной)."""
    enabled, reason = link_enabled_for_task(settings, task, parsed)
    if not enabled:
        return {"ok": True, "skipped": True, "reason": reason, "actions": []}
    filtered, meta = filter_for_linking(task, related, settings)
    if not filtered:
        return {
            "ok": True,
            "skipped": True,
            "reason": "нет дублей для подчинения (день/статус/сервис)",
            "filter": meta,
            "actions": [],
        }
    result = related_tasks.link_later_to_earlier(
        task,
        filtered,
        apply=True,
        add_observer=add_observer,
    )
    result["filter"] = meta
    result["related_total"] = len(related or [])
    result["related_for_link"] = len(filtered)
    return result
