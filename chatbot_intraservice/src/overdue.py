# -*- coding: utf-8 -*-
"""Эскалация IntraService «До просрочки» (lifetime Comments).

Только запись робота (Editor=IntraService, «эскалирована по правилу»), не комментарии чатбота.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

DEFAULT_MARKER = "До просрочки"
# Жёсткий шаблон робота HD (не наши фразы про «свежая эскалация»)
_ROBOT_RE = re.compile(
    r"эскалирован\w*\s+по\s+правилу\s*[«\"]?\s*до\s+просрочки",
    re.I,
)
_BOT_PUBLIC_PREFIX = re.compile(r"^добрый\s+день", re.I)
_USER_CLOSING_RE = re.compile(
    r"(?i)^(?:спасибо|благодар|завершаем|закрыва|можно\s+закры|ожидаем\s+закрыт|"
    r"всё\s+работает|все\s+работает|принято|хорошо|ок)[!.…,\s]*$"
)
_BOT_NOISE = re.compile(
    r"получили уведомление о приближении|продлили дедлайн|просрочка:\s*свежая эскалация|"
    r"сервис hd:|чатбот 1 линии",
    re.I,
)
_SYSTEM_EDITORS = {"intraservice", "система", "system", "робот"}


def _is_user_closing_message(text: str) -> bool:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return True
    if _USER_CLOSING_RE.match(t):
        return True
    low = t.lower()
    if low.startswith("спасибо") or "завершаем" in low or "можно закры" in low:
        return True
    return False


def _is_bot_overdue_public(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _BOT_PUBLIC_PREFIX.match(t):
        return True
    if _BOT_NOISE.search(t):
        return True
    return False


def parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def is_robot_escalation(row: dict[str, Any], marker: str = DEFAULT_MARKER) -> bool:
    comments = str(row.get("Comments") or "")
    if not comments.strip():
        return False
    if _BOT_NOISE.search(comments):
        return False
    editor = str(row.get("Editor") or "").strip().lower()
    if editor and editor not in _SYSTEM_EDITORS and "intraservice" not in editor:
        return False
    if _ROBOT_RE.search(comments):
        return True
    # запасной вариант: маркер + Editor IntraService
    if (marker or DEFAULT_MARKER).lower() in comments.lower() and (
        not editor or editor in _SYSTEM_EDITORS or "intraservice" in editor
    ):
        return "эскалир" in comments.lower() or "правил" in comments.lower()
    return False


def find_overdue_marker(
    lifetime: dict[str, Any],
    marker: str = DEFAULT_MARKER,
    *,
    max_age_hours: float = 6.0,
) -> dict[str, Any] | None:
    rows = lifetime.get("TaskLifetimes") or []
    hits: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not is_robot_escalation(row, marker):
            continue
        dt = parse_dt(str(row.get("Date") or ""))
        if dt is not None and max_age_hours > 0:
            age_h = (now - dt.astimezone(timezone.utc)).total_seconds() / 3600.0
            if age_h > max_age_hours:
                continue
        hits.append(
            {
                "Date": row.get("Date"),
                "Editor": row.get("Editor"),
                "Comments": str(row.get("Comments") or "")[:240],
                "IsPublic": row.get("IsPublic"),
            }
        )
    if not hits:
        return None
    hits.sort(key=lambda r: str(r.get("Date") or ""), reverse=True)
    return hits[0]


def detect_overdue_escalation(
    task_id: str | int,
    *,
    marker: str = DEFAULT_MARKER,
    max_age_hours: float = 6.0,
) -> dict[str, Any] | None:
    import intraservice

    lifetime = intraservice.get_task_lifetime(str(task_id).strip(), page_size=50)
    return find_overdue_marker(lifetime, marker, max_age_hours=max_age_hours)


def already_handled_for_escalation(
    lifetime: dict[str, Any],
    escalation_date: str | None,
) -> bool:
    """True, если после этой эскалации робота уже был наш follow-up (продление/ответ)."""
    esc_dt = parse_dt(escalation_date)
    rows = lifetime.get("TaskLifetimes") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        comments = str(row.get("Comments") or "")
        if not comments:
            continue
        if not (
            "продлили дедлайн" in comments.lower()
            or "получили уведомление о приближении" in comments.lower()
            or _is_bot_overdue_public(comments)
            or (
                comments.startswith("Добрый день")
                and ("резерв" in comments.lower() or "1с" in comments.lower() or "подтвержд" in comments.lower())
            )
        ):
            # наш скрытый разбор тоже считается обработкой этой эскалации
            if "просрочка: свежая эскалация" not in comments.lower() and "сервис hd:" not in comments.lower():
                continue
        dt = parse_dt(str(row.get("Date") or ""))
        if esc_dt and dt and dt >= esc_dt:
            return True
        if not esc_dt and dt:
            return True
    return False


def next_deadline_iso(current: str | None, *, days: int = 1) -> str:
    dt = parse_dt(current)
    if dt is None:
        dt = datetime.now(timezone.utc) + timedelta(days=days)
    else:
        dt = dt + timedelta(days=days)
    naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
    return naive.strftime("%Y-%m-%dT%H:%M:%S")


def extract_prior_public_answer(lifetime: dict[str, Any]) -> str:
    """Последний содержательный публичный ответ исполнителя (не робот, не наш шаблон просрочки)."""
    rows = lifetime.get("TaskLifetimes") or []
    for row in sorted(rows, key=lambda r: str((r or {}).get("Date") or ""), reverse=True):
        if not isinstance(row, dict):
            continue
        if row.get("IsPublic") is False:
            continue
        comments = str(row.get("Comments") or "").strip()
        if not comments or len(comments) < 20:
            continue
        if is_robot_escalation(row):
            continue
        if _BOT_NOISE.search(comments):
            continue
        if comments.startswith("Сервис HD:") or comments.startswith("Разбор от чатбота IEK LLM") or comments.startswith("Разбор IEK LLM") or comments.startswith("Результат преданализа IEK LLM"):
            continue
        if _is_user_closing_message(comments):
            continue
        if _is_bot_overdue_public(comments):
            continue
        editor = str(row.get("Editor") or "")
        if "intraservice" in editor.lower():
            continue
        return comments[:900]
    return ""


def has_confident_public_answer(
    parsed: dict[str, Any] | None,
    *,
    prior_public: str = "",
    hidden_facts: list[str] | None = None,
) -> bool:
    """Достаточно ли уверенности для открытого ответа заявителю."""
    parsed = parsed or {}
    prior = (prior_public or "").strip()
    if prior and _is_user_closing_message(prior):
        prior = ""
    if prior:
        return True
    steps = [str(s).strip() for s in (parsed.get("solution_steps_ru") or []) if str(s).strip()]
    links = [u for u in (parsed.get("article_links") or []) if str(u).strip()]
    if parsed.get("has_kb_solution") and (steps or links):
        return True
    blob = " ".join(str(x) for x in (hidden_facts or [])).lower()
    if "резервировать товары в пути" in blob or "в лк подтверждать не требуется" in blob:
        return True
    return False


def format_overdue_public_comment(
    *,
    new_deadline: str = "",
    parsed: dict[str, Any] | None = None,
    prior_public: str = "",
    hidden_facts: list[str] | None = None,
    only_if_kb: bool = False,
) -> str:
    """Открытый ответ по сути проблемы. Без воды про перенос срока.

    only_if_kb=True → пустая строка, если нет уверенного KB/prior/1С-факта
    (тогда вызывающий не постит публично, только скрытый разбор).
    """
    parsed = parsed or {}
    prior = (prior_public or "").strip()
    if prior and _is_user_closing_message(prior):
        prior = ""
    if only_if_kb and not has_confident_public_answer(
        parsed, prior_public=prior, hidden_facts=hidden_facts
    ):
        return ""

    lines = ["Добрый день!", ""]

    # 1) Уже был ясный ответ исполнителя — сжать по сути (без «продлили срок»)
    if prior:
        short = prior.replace("\r\n", "\n").strip()
        short = re.sub(r"(?i)^добрый\s+день[,!]?\s*", "", short).strip()
        # убрать просьбу «перешлите письмо» — оставить факт
        short = re.sub(r"(?i)перешлите\s+это\s+письмо[, ]*", "", short).strip()
        parts = re.split(r"(?<=[.!?])\s+", short)
        gist = " ".join(parts[:2]).strip()[:420]
        if gist:
            lines.append(gist)
        else:
            lines.append("По этому вопросу ответ уже есть в переписке заявки.")
        return "\n".join(lines).strip()

    steps = [str(s).strip() for s in (parsed.get("solution_steps_ru") or []) if str(s).strip()]
    if parsed.get("has_kb_solution") and steps:
        lines.append(steps[0][:450])
        if len(steps) > 1:
            lines.append(steps[1][:300])
        return "\n".join(lines).strip()

    # 2) Факты из разбора (1С / заказ)
    facts = [str(x).strip() for x in (hidden_facts or []) if str(x).strip()]
    onec = next((f for f in facts if f.lower().startswith("1с:") or "резервировать товары в пути" in f.lower()), "")
    order = next((f for f in facts if f.lower().startswith("заказ ")), "")
    if onec or "пути" in " ".join(facts).lower():
        bit = onec or (
            "В 1С у заказа уже включено «Резервировать товары в пути» — отдельно подтверждать в ЛК не нужно."
        )
        if bit.lower().startswith("1с:"):
            bit = bit[3:].strip()
        lines.append(bit[:500])
        if order:
            lines.append(f"Заказ: {order.split(' ', 1)[-1]}.")
        lines.append("")
        lines.append("Если в ЛК по-прежнему нет статуса «уже зарезервировано» — это отображение; на резерв в 1С это не влияет.")
        return "\n".join(lines).strip()

    # 3) Непонятно — короткий запрос сведений
    lines.append(
        "Чтобы продолжить, уточните кратко: номер заказа/счёта, что именно не получается в ЛК "
        "(текст ошибки или скрин), и с какого времени."
    )
    return "\n".join(lines).strip()
