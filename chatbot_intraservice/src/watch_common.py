# -*- coding: utf-8 -*-
"""Общие хелперы для watch_* скриптов IntraService."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

import overdue

PKG = Path(__file__).resolve().parents[1]

_BOT_COMMENT = re.compile(
    r"сервис hd:|сервис:|разбор от чатбота iek llm|разбор iek llm|"
    r"результат преданализа iek llm|"
    r"чатбот 1 линии|просрочка:\s*свежая эскалация|"
    r"получили уведомление о приближении|продлили дедлайн|"
    r"взято в работу \(чатбот|"
    r"ai-kb:\s*на основе заявки|"
    r"мы зафиксировали подтверждение|"
    r"пользователь подтвердил решение|"
    r"автозакрытие по правилу|"
    r"заявитель задал дополнительный вопрос|"
    r"закроется автоматически через",
    re.I,
)

_DIGEST_HEAD = re.compile(
    r"сервис\s*hd\s*:|разбор от чатбота iek llm|разбор iek llm|"
    r"результат преданализа iek llm",
    re.I,
)


def comment_fingerprint(text: str, *, max_len: int = 420) -> str:
    """Нормализованный отпечаток скрытого разбора для антидубля."""
    t = (text or "").replace("\r\n", "\n").strip().lower()
    t = re.sub(r"\s+", " ", t)
    # даты/время в хвосте AI-KB не должны ломать сравнение
    t = re.sub(r"\d{4}-\d{2}-\d{2}t[\d:+.\-]+", "", t)
    return t[:max_len]


def is_hidden_digest(text: str) -> bool:
    return bool(_DIGEST_HEAD.search(text or ""))


def find_recent_bot_digest(
    lifetime: dict[str, Any] | None,
    *,
    max_age_hours: float = 72.0,
) -> dict[str, Any] | None:
    """Последний скрытый разбор чатбота («Разбор от чатбота IEK LLM» / «Сервис HD:…»)."""
    if not lifetime:
        return None
    rows = lifetime.get("TaskLifetimes") or []
    now = datetime.now(timezone.utc)
    hits: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        comments = str(row.get("Comments") or "").strip()
        if not is_hidden_digest(comments):
            continue
        # публичные ответы заявителю не считаем digest
        if row.get("IsPublic") is True:
            continue
        dt = overdue.parse_dt(str(row.get("Date") or ""))
        if dt is not None and max_age_hours > 0:
            age_h = (now - dt.astimezone(timezone.utc)).total_seconds() / 3600.0
            if age_h > max_age_hours:
                continue
        hits.append(
            {
                "Date": row.get("Date"),
                "Editor": row.get("Editor"),
                "Comments": comments,
                "fingerprint": comment_fingerprint(comments),
            }
        )
    if not hits:
        return None
    hits.sort(key=lambda r: str(r.get("Date") or ""), reverse=True)
    return hits[0]


def is_duplicate_digest(new_text: str, existing: dict[str, Any] | None, *, min_ratio: float = 0.82) -> bool:
    """True если новый скрытый комментарий почти совпадает с уже написанным."""
    if not existing:
        return False
    a = comment_fingerprint(new_text)
    b = str(existing.get("fingerprint") or comment_fingerprint(str(existing.get("Comments") or "")))
    if not a or not b:
        return False
    if a == b:
        return True
    # префикс «Сервис HD…Факты» часто стабилен при том же разборе
    n = min(len(a), len(b), 280)
    if n < 40:
        return False
    same = sum(1 for i in range(n) if a[i] == b[i])
    return (same / float(n)) >= min_ratio


def load_seen(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"tasks": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"tasks": {}}


def save_seen(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_tasks(
    *,
    service_ids: list[int],
    status_ids: list[int],
    page_size: int,
    fields: str = "Id,Name,StatusId,ServiceId,Deadline,Changed,Created,CreatorEmail,Creator,CreatorId,ExecutorIds",
) -> list[dict[str, Any]]:
    import intraservice

    intraservice.load_env()
    base = intraservice.api_base()
    user = intraservice._user()
    password = (os.environ.get("INTRASERVICE_PASSWORD") or "").strip()
    params: dict[str, str] = {
        "StatusIds": ",".join(str(x) for x in status_ids),
        "pagesize": str(page_size),
        "page": "1",
        "fields": fields,
    }
    if service_ids:
        params["ServiceIds"] = ",".join(str(x) for x in service_ids)
    resp = requests.get(
        f"{base}/task",
        params=params,
        auth=(user, password),
        headers={"Accept": "application/json"},
        timeout=60,
        verify=False,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("Tasks") or data.get("TaskList") or []


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_bot_or_robot_comment(row: dict[str, Any]) -> bool:
    if overdue.is_robot_escalation(row):
        return True
    comments = str(row.get("Comments") or "")
    if not comments.strip():
        return True
    if _BOT_COMMENT.search(comments):
        return True
    editor = str(row.get("Editor") or "").strip().lower()
    if editor in {"intraservice", "система", "system", "робот"}:
        return True
    return False


_GRATITUDE_RE = re.compile(
    r"(?i)("
    r"спасибо|благодарю|заработало|помогло|решилось|решено|"
    r"вс[её]\s*(ок|хорошо|работает|отлично)|все\s*(ок|хорошо|работает)|"
    r"вопрос\s*снят|больше\s*не\s*актуально|"
    r"проблема\s*решена|работает\s*(отлично|норм|хорошо)?|"
    r"провел(ось|и|а)?|ok[\s,.!]*thanks|thank\s*you|it\s*works"
    r")"
)

# Заявитель просит закрыть — считаем подтверждением решения (→ «Выполнена»).
_CLOSE_REQUEST_RE = re.compile(
    r"(?i)("
    r"можно\s*закры(вать|ть)|заявк[ау]\s+можно\s*закры|"
    r"закрывайте\s+заявк|прошу\s+закрыть"
    r")"
)

_UNRESOLVED_RE = re.compile(
    r"(?i)("
    r"вопрос\s+оста|не\s+решил|не\s+решено|"
    r"помогите|снова\s+не|опять\s+не|"
    r"ещ[её]\s+актуальн|заявк[ауи]\s+актуальн|требуется\s+помощь|нужна\s+помощь|"
    r"переоткры|верните\s+в\s+работу"
    r")"
)

_STOP_CLOSE_RE = re.compile(
    r"(?i)(не\s+помогло|не\s+заработало|вс[её]\s+ещ[её]|по-прежнему|"
    r"ошибка|не\s+работает|не\s+открывается|не\s+вижу)"
)

# Повторный вопрос исполнителя: «ещё нужны действия / актуальна ли заявка?»
_RELEVANCE_NUDGE_RE = re.compile(
    r"(?i)("
    r"требу(ется|ются)\s+(ли\s+)?(какие-?то\s+)?действи|"
    r"нужны\s+ли\s+(ещ[её]\s+)?действи|"
    r"актуальн[ао]\s+ли\s+заявк|"
    r"заявк[ауи]\s+(ещ[её]\s+)?актуальн|"
    r"требуется\s+ли\s+ещ[её]|нужно\s+ли\s+ещ[её]|"
    r"ожидаем\s+(ваш\s+)?ответ|есть\s+ли\s+ещ[её]\s+вопросы"
    r")"
)


def is_gratitude_resolved(text: str) -> bool:
    """Заявитель подтвердил решение («спасибо / помогло / можно закрывать») → «Выполнена»."""
    t = (text or "").replace("\r\n", "\n").strip()
    if len(t) < 4:
        return False
    if _STOP_CLOSE_RE.search(t):
        return False
    has_thanks = bool(_GRATITUDE_RE.search(t))
    has_close = bool(_CLOSE_REQUEST_RE.search(t))
    if not has_thanks and not has_close:
        return False
    # длинный техответ со словом «спасибо» в конце — не закрывать
    if len(t) > 280 and not re.search(
        r"(?i)(заработало|вопрос\s*снят|проблема\s*решена|можно\s*закры)", t
    ):
        return False
    return True


def is_needs_executor_attention(text: str) -> bool:
    """«Проблема не решена» — вернуть в «Передано исполнителю».

    Простой уточняющий вопрос («уточните…», «не понял», «дополнительный вопрос»)
    НЕ возвращает исполнителю — заявка остаётся в «Ожидании ответа».
    """
    t = (text or "").replace("\r\n", "\n").strip()
    if len(t) < 8:
        return False
    if is_gratitude_resolved(t):
        return False
    if _STOP_CLOSE_RE.search(t):
        return True
    if _UNRESOLVED_RE.search(t):
        return True
    return False


def is_relevance_nudge(text: str) -> bool:
    """Повторный вопрос исполнителя: нужна ли ещё помощь / актуальна ли заявка."""
    t = (text or "").replace("\r\n", "\n").strip()
    if len(t) < 12:
        return False
    if is_gratitude_resolved(t) or _STOP_CLOSE_RE.search(t):
        return False
    return bool(_RELEVANCE_NUDGE_RE.search(t))


def _parse_id_set(raw: Any) -> set[str]:
    out: set[str] = set()
    if raw is None:
        return out
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("Id") is not None:
                out.add(str(item["Id"]))
            elif item is not None and str(item).strip():
                out.add(str(item).strip())
        return out
    out.update(p.strip() for p in str(raw).split(",") if p.strip())
    return out


def is_requester_comment(
    row: dict[str, Any],
    *,
    creator_id: Any = None,
    creator_name: str = "",
    executor_ids: Any = None,
) -> bool:
    """True если комментарий похож на ответ заявителя, а не исполнителя HD."""
    eid = row.get("EditorId")
    cid = str(creator_id).strip() if creator_id is not None else ""
    if eid is not None and cid and str(eid).strip() == cid:
        return True
    exec_ids = _parse_id_set(executor_ids)
    if eid is not None and str(eid).strip() in exec_ids:
        return False
    # fallback по ФИО, если EditorId нет
    editor = str(row.get("Editor") or "").strip().lower()
    creator = (creator_name or "").strip().lower()
    if editor and creator and (editor == creator or creator in editor or editor in creator):
        return True
    # Публичный комментарий = заявитель только при совпадении с Creator, не любой IEK-сотрудник
    return False


def is_client_side_comment(
    row: dict[str, Any],
    *,
    creator_id: Any = None,
    creator_name: str = "",
    executor_ids: Any = None,
) -> bool:
    """Заявитель или другой не-исполнитель (коллега/наблюдатель) — сторона клиента."""
    if is_requester_comment(
        row,
        creator_id=creator_id,
        creator_name=creator_name,
        executor_ids=executor_ids,
    ):
        return True
    if is_bot_or_robot_comment(row):
        return False
    eid = row.get("EditorId")
    exec_ids = _parse_id_set(executor_ids)
    if eid is not None and str(eid).strip() in exec_ids:
        return False
    # без списка исполнителей не угадываем «чужих»
    if not exec_ids:
        return False
    comments = str(row.get("Comments") or "").strip()
    if len(comments) < 4:
        return False
    # скрытые служебные от HD-сотрудников не считаем клиентскими
    if row.get("IsPublic") is False:
        return False
    return True


def find_new_user_comment(
    lifetime: dict[str, Any],
    *,
    after_date: str | None = None,
    max_age_hours: float = 72.0,
    creator_id: Any = None,
    creator_name: str = "",
    executor_ids: Any = None,
    requester_only: bool = False,
    client_side_only: bool = False,
) -> dict[str, Any] | None:
    """Последний содержательный комментарий не-бота.

    requester_only=True — только CreatorId.
    client_side_only=True — заявитель или иной не-исполнитель (публичный).
    """
    rows = lifetime.get("TaskLifetimes") or []
    after_dt = overdue.parse_dt(after_date) if after_date else None
    now = datetime.now(timezone.utc)
    hits: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if is_bot_or_robot_comment(row):
            continue
        if requester_only and not is_requester_comment(
            row,
            creator_id=creator_id,
            creator_name=creator_name,
            executor_ids=executor_ids,
        ):
            continue
        if client_side_only and not is_client_side_comment(
            row,
            creator_id=creator_id,
            creator_name=creator_name,
            executor_ids=executor_ids,
        ):
            continue
        comments = str(row.get("Comments") or "").strip()
        if len(comments) < 8:
            continue
        dt = overdue.parse_dt(str(row.get("Date") or ""))
        if dt is not None and max_age_hours > 0:
            age_h = (now - dt.astimezone(timezone.utc)).total_seconds() / 3600.0
            if age_h > max_age_hours:
                continue
        if after_dt and dt and dt <= after_dt:
            continue
        hits.append(
            {
                "Date": row.get("Date"),
                "Editor": row.get("Editor"),
                "EditorId": row.get("EditorId"),
                "IsPublic": row.get("IsPublic"),
                "Comments": comments[:400],
            }
        )
    if not hits:
        return None
    hits.sort(key=lambda r: str(r.get("Date") or ""), reverse=True)
    return hits[0]


def _lifetime_comment_rows(lifetime: dict[str, Any]) -> list[dict[str, Any]]:
    rows = lifetime.get("TaskLifetimes") or []
    return [r for r in rows if isinstance(r, dict)]


def find_first_executor_public_reply(
    lifetime: dict[str, Any],
    *,
    creator_id: Any = None,
    creator_name: str = "",
    executor_ids: Any = None,
) -> dict[str, Any] | None:
    """Первый публичный содержательный ответ не-заявителя (обычно исполнитель)."""
    hits: list[dict[str, Any]] = []
    for row in _lifetime_comment_rows(lifetime):
        if is_bot_or_robot_comment(row):
            continue
        if row.get("IsPublic") is False:
            continue
        comments = str(row.get("Comments") or "").strip()
        if len(comments) < 8:
            continue
        if is_requester_comment(
            row,
            creator_id=creator_id,
            creator_name=creator_name,
            executor_ids=executor_ids,
        ):
            continue
        hits.append(
            {
                "Date": row.get("Date"),
                "Editor": row.get("Editor"),
                "EditorId": row.get("EditorId"),
                "Comments": comments[:400],
            }
        )
    if not hits:
        return None
    hits.sort(key=lambda r: str(r.get("Date") or ""))
    return hits[0]


def find_executor_relevance_nudge(
    lifetime: dict[str, Any],
    *,
    after_date: str | None = None,
    max_age_hours: float = 72.0,
    min_hours_after_first_reply: float = 24.0,
    creator_id: Any = None,
    creator_name: str = "",
    executor_ids: Any = None,
) -> dict[str, Any] | None:
    """Повторный вопрос исполнителя про актуальность (≥N ч после первого ответа)."""
    first = find_first_executor_public_reply(
        lifetime,
        creator_id=creator_id,
        creator_name=creator_name,
        executor_ids=executor_ids,
    )
    if not first:
        return None
    first_dt = overdue.parse_dt(str(first.get("Date") or ""))
    after_dt = overdue.parse_dt(after_date) if after_date else None
    now = datetime.now(timezone.utc)
    hits: list[dict[str, Any]] = []
    for row in _lifetime_comment_rows(lifetime):
        if is_bot_or_robot_comment(row):
            continue
        if is_requester_comment(
            row,
            creator_id=creator_id,
            creator_name=creator_name,
            executor_ids=executor_ids,
        ):
            continue
        comments = str(row.get("Comments") or "").strip()
        if not is_relevance_nudge(comments):
            continue
        dt = overdue.parse_dt(str(row.get("Date") or ""))
        if dt is None:
            continue
        if first_dt is not None:
            gap_h = (dt.astimezone(timezone.utc) - first_dt.astimezone(timezone.utc)).total_seconds() / 3600.0
            if gap_h < float(min_hours_after_first_reply):
                continue
            # тот же первый ответ не считаем «повторным»
            if str(row.get("Date") or "") == str(first.get("Date") or ""):
                continue
        if max_age_hours > 0:
            age_h = (now - dt.astimezone(timezone.utc)).total_seconds() / 3600.0
            if age_h > max_age_hours:
                continue
        if after_dt and dt <= after_dt:
            continue
        hits.append(
            {
                "Date": row.get("Date"),
                "Editor": row.get("Editor"),
                "EditorId": row.get("EditorId"),
                "IsPublic": row.get("IsPublic"),
                "Comments": comments[:400],
                "first_reply_date": first.get("Date"),
            }
        )
    if not hits:
        return None
    hits.sort(key=lambda r: str(r.get("Date") or ""), reverse=True)
    return hits[0]


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
