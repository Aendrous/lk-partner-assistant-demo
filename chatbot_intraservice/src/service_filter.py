# -*- coding: utf-8 -*-
"""Фильтр обработки заявок по контуру (ЛК/БП/CRM/EDI/…) и ServiceId."""
from __future__ import annotations

from typing import Any

import service_routing

CONTOUR_LABELS: dict[str, str] = {
    "lk": "ЛК",
    "bp": "БП",
    "crm": "CRM",
    "edi": "EDI / 1С",
    "1c": "EDI / 1С",
    "kp": "КП",
    "mail": "Почта / рассылки",
    "other": "Прочее",
}

DEFAULT_CONTOUR_ENABLED: dict[str, dict[str, bool]] = {
    "lk": {"comment": True, "kb_learn": True, "watch": True},
    "bp": {"comment": True, "kb_learn": True, "watch": True},
    "crm": {"comment": False, "kb_learn": False, "watch": False},
    "edi": {"comment": True, "kb_learn": True, "watch": True},
    "mail": {"comment": True, "kb_learn": True, "watch": True},
    "other": {"comment": True, "kb_learn": True, "watch": True},
}

# ServiceId HelpDesk для опроса watch / pipeline (ветки + Солярис + CRM)
CONTOUR_WATCH_SERVICE_IDS: dict[str, list[int]] = {
    "lk": [731, 732],
    "bp": [833, 827],
    "crm": [29],
    "edi": [69],
    "1c": [69],
    "mail": [],
    "other": [],
}

ACTION_LABELS = {
    "comment": "скрытый разбор / комментарий",
    "kb_learn": "самообучение AI-KB",
    "watch": "опрос заявок (watch)",
}


def contour_enabled_map(settings: dict[str, Any] | None) -> dict[str, dict[str, bool]]:
    base = {k: dict(v) for k, v in DEFAULT_CONTOUR_ENABLED.items()}
    raw = (settings or {}).get("contour_enabled") or {}
    if isinstance(raw, dict):
        for contour, flags in raw.items():
            if not isinstance(flags, dict):
                continue
            row = base.setdefault(str(contour).lower(), {})
            for action, val in flags.items():
                if action in ACTION_LABELS:
                    row[action] = bool(val)
    return base


def resolve_task_contour(
    task: dict[str, Any],
    parsed: dict[str, Any] | None = None,
) -> str:
    sk = str((parsed or {}).get("service_key") or "").strip().lower()
    text = f"{task.get('Name') or ''}\n{task.get('Description') or ''}"
    contour = service_routing.infer_contour(text, sk)
    branch = service_routing.branch_for_service_id(task.get("ServiceId"))
    bk = str(branch.get("key") or "")
    if bk == "edi":
        return "edi"
    # Явная ветка HD (731/732/833) важнее короткого названия «Заказы» → other
    if bk in {"lk", "bp"} and contour in {"unknown", "", "other"}:
        return bk
    if contour in {"unknown", ""}:
        if bk in {"lk", "bp"}:
            return bk
    return contour or "other"


def is_action_enabled(
    contour: str,
    action: str,
    settings: dict[str, Any] | None = None,
) -> bool:
    key = (contour or "other").strip().lower()
    if key == "1c":
        key = "edi"
    flags = contour_enabled_map(settings).get(key) or contour_enabled_map(settings).get("other", {})
    return bool(flags.get(action, True))


def disabled_service_ids(settings: dict[str, Any] | None) -> set[int]:
    out: set[int] = set()
    for raw in (settings or {}).get("disabled_service_ids") or []:
        try:
            out.add(int(raw))
        except (TypeError, ValueError):
            continue
    return out


def service_ids_for_contour_action(
    settings: dict[str, Any] | None,
    action: str,
) -> list[int]:
    """ServiceId для опроса HD по включённым контурам (watch / kb_learn / comment)."""
    act = (action or "watch").strip().lower()
    if act not in ACTION_LABELS:
        act = "watch"
    out: set[int] = set()
    for contour, flags in contour_enabled_map(settings).items():
        if not flags.get(act):
            continue
        key = (contour or "").strip().lower()
        if key == "1c":
            key = "edi"
        for sid in CONTOUR_WATCH_SERVICE_IDS.get(key, []):
            out.add(int(sid))
    out -= disabled_service_ids(settings)
    return sorted(out)


def effective_watch_service_ids(
    settings: dict[str, Any] | None,
    *,
    legacy_key: str,
    default: list[int],
    action: str = "watch",
) -> list[int]:
    """Список ServiceId: из contour_enabled.*, иначе legacy-ключ settings."""
    from_contours = service_ids_for_contour_action(settings, action)
    if from_contours:
        return from_contours
    raw = list((settings or {}).get(legacy_key) or default)
    disabled = disabled_service_ids(settings)
    out: set[int] = set()
    for x in raw:
        try:
            sid = int(x)
        except (TypeError, ValueError):
            continue
        if sid not in disabled:
            out.add(sid)
    return sorted(out)


def sync_watch_service_ids(settings: dict[str, Any]) -> dict[str, list[int]]:
    """Синхронизировать watch_*_service_ids с contour_enabled (для сохранения в UI)."""
    watch_ids = service_ids_for_contour_action(settings, "watch")
    learn_ids = service_ids_for_contour_action(settings, "kb_learn")
    closed_ids = learn_ids or watch_ids
    return {
        "watch_new_service_ids": watch_ids,
        "watch_overdue_service_ids": watch_ids,
        "watch_user_reply_service_ids": watch_ids,
        "watch_service_ids": closed_ids,
    }


def skip_for_task(
    task: dict[str, Any],
    action: str,
    settings: dict[str, Any] | None = None,
    *,
    parsed: dict[str, Any] | None = None,
) -> str | None:
    """Причина пропуска или None если обработка разрешена."""
    sid_raw = task.get("ServiceId")
    sid: int | None = None
    if isinstance(sid_raw, int):
        sid = sid_raw
    elif isinstance(sid_raw, str) and sid_raw.strip().isdigit():
        sid = int(sid_raw.strip())
    if sid is not None and sid in disabled_service_ids(settings):
        return f"ServiceId {sid} отключён в настройках чатбота"

    import assistants

    onec_skip = assistants.skip_onec_task(task)
    if onec_skip:
        return onec_skip

    scope_skip = assistants.skip_onec_out_of_scope(task, settings)
    if scope_skip:
        return scope_skip

    contour = resolve_task_contour(task, parsed)
    if not is_action_enabled(contour, action, settings):
        label = CONTOUR_LABELS.get(contour, contour)
        act = ACTION_LABELS.get(action, action)
        return f"контур {label}: {act} выключен в UI"
    return None


def contour_line_for_comment(contour: str) -> str:
    label = CONTOUR_LABELS.get((contour or "other").lower(), contour or "прочее")
    return f"Контур: {label}"


def contour_label(service_key: str) -> str:
    sk = (service_key or "other").strip().lower()
    if sk in CONTOUR_LABELS:
        return CONTOUR_LABELS[sk]
    return sk or "прочее"
