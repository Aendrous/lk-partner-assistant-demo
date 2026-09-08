# -*- coding: utf-8 -*-
"""Клиент HelpDesk IntraService (helpdesk.iek.local). Basic Auth, JSON.

Документация: docs/интеграции/intraservice_api.md (в этой папке).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
CATALOG_PATH = PKG / "docs" / "интеграции" / "service_catalog.json"
ENV_PATH = PKG / ".env"


def load_env(path: Path | None = None) -> None:
    """Загрузить .env пакета и корневой .env репозитория (1C_* и др.)."""
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path)
    else:
        candidates.append(ENV_PATH)
        candidates.append(PKG.parent / ".env")
    seen: set[Path] = set()
    for env_path in candidates:
        env_path = env_path.resolve()
        if env_path in seen or not env_path.exists():
            continue
        seen.add(env_path)
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path, override=False)
            continue
        except ImportError:
            pass
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip("'").strip('"'))


def _env() -> None:
    load_env()


def host_base() -> str:
    _env()
    raw = (os.environ.get("INTRASERVICE_BASE_URL") or "https://helpdesk.iek.local").strip().rstrip("/")
    parts = urlsplit(raw if "://" in raw else f"https://{raw}")
    return urlunsplit((parts.scheme or "https", parts.netloc, "", "", ""))


def api_base() -> str:
    return f"{host_base()}/api"


def has_credentials() -> bool:
    _env()
    return bool(
        (os.environ.get("INTRASERVICE_USER") or "").strip()
        and (os.environ.get("INTRASERVICE_PASSWORD") or "").strip()
    )


def _user() -> str:
    _env()
    user = (os.environ.get("INTRASERVICE_USER") or "").strip()
    if not user:
        raise RuntimeError("Нет INTRASERVICE_USER")
    as_is = (os.environ.get("INTRASERVICE_USER_AS_IS") or "").strip().lower() in {"1", "true", "yes"}
    if not as_is and "@" in user:
        return user.split("@", 1)[0]
    return user


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    _env()
    password = (os.environ.get("INTRASERVICE_PASSWORD") or "").strip()
    if not password:
        raise RuntimeError("Нет INTRASERVICE_PASSWORD")
    url = path if path.startswith("http") else f"{api_base()}{path}"
    resp = requests.request(
        method,
        url,
        json=body,
        auth=(_user(), password),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=45,
        verify=False,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"IntraService {method} {url} HTTP {resp.status_code}: {resp.text[:1200]}")
    if not resp.content:
        return {}
    return resp.json()


def load_catalog() -> dict[str, Any]:
    if not CATALOG_PATH.exists():
        return {"services": {}}
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def task_url(task_id: int | str) -> str:
    return f"{host_base()}/Task/View/{task_id}"


def short_task_url(task_id: int | str) -> str:
    """Короткая ссылка на заявку: шаблон INTRASERVICE_SHORT_TASK_URL_TEMPLATE.

    Пример: INTRASERVICE_SHORT_TASK_URL_TEMPLATE=https://hd.iek.group/Task/View/{id}
    Без шаблона — обычный helpdesk.iek.local.
    """
    tid = str(task_id).strip()
    try:
        _env()
        tpl = (os.environ.get("INTRASERVICE_SHORT_TASK_URL_TEMPLATE") or "").strip()
        if tpl and "{id}" in tpl:
            return tpl.format(id=tid, Id=tid)
    except Exception:
        pass
    return task_url(tid)


def get_task_lifetime(task_id: str | int, *, page_size: int = 50) -> dict[str, Any]:
    """GET /api/tasklifetime?taskid= — история статусов и комментарии (Description)."""
    tid = str(task_id).strip()
    return _request("GET", f"/tasklifetime?taskid={tid}&pagesize={int(page_size)}")


def get_task(task_id: str) -> dict[str, Any]:
    data = _request(
        "GET",
        f"/task/{task_id}?fields=Id,Name,StatusId,PriorityId,Description,Created,Changed,ServiceId,TypeId,"
        "ExecutorIds,ObserverIds,ParentId,CreatorId,CreatorEmail,Deadline,Files,FileIds"
        "&include=status,priority,executors,creator,service",
    )
    task = data.get("Task") or data
    statuses = data.get("Statuses") or []
    status_name = ""
    if isinstance(statuses, list):
        for item in statuses:
            if isinstance(item, dict) and item.get("Id") == task.get("StatusId"):
                status_name = item.get("Name") or ""
                break
    if not status_name:
        one = data.get("Status")
        if isinstance(one, dict):
            status_name = one.get("Name") or ""
    services = data.get("Services") or []
    service_name = ""
    if isinstance(services, list) and services:
        service_name = (services[0] or {}).get("Name") or ""
    creator_email = (task.get("CreatorEmail") or "").strip()
    if not creator_email:
        creators = data.get("Creators") or data.get("Creator")
        if isinstance(creators, list) and creators:
            creator_email = (creators[0] or {}).get("Email") or ""
        elif isinstance(creators, dict):
            creator_email = (creators.get("Email") or "").strip()
    return {
        "Id": task.get("Id"),
        "Name": task.get("Name"),
        "StatusId": task.get("StatusId"),
        "StatusName": status_name,
        "PriorityId": task.get("PriorityId"),
        "TypeId": task.get("TypeId"),
        "ServiceId": task.get("ServiceId"),
        "ServiceName": service_name,
        "CreatorId": task.get("CreatorId"),
        "CreatorEmail": creator_email,
        "Creator": task.get("Creator"),
        "ParentId": task.get("ParentId"),
        "ExecutorIds": task.get("ExecutorIds"),
        "ObserverIds": task.get("ObserverIds"),
        "Files": task.get("Files"),
        "FileIds": task.get("FileIds"),
        "Description": (task.get("Description") or "")[:4000],
        "Created": task.get("Created"),
        "Changed": task.get("Changed"),
        "Deadline": task.get("Deadline"),
        "url": task_url(task.get("Id") or task_id),
    }


def search_tasks(query: str, *, page_size: int = 20) -> list[dict[str, Any]]:
    """GET /api/task?search=… — поиск заявок по тексту (заказ/счёт/GUID и т.п.)."""
    q = (query or "").strip()
    if not q:
        return []
    from urllib.parse import quote

    data = _request("GET", f"/task?search={quote(q)}&pagesize={int(page_size)}")
    items = data.get("Tasks") or []
    out: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict) or item.get("Id") is None:
            continue
        out.append(
            {
                "Id": item.get("Id"),
                "Name": item.get("Name"),
                "Created": item.get("Created"),
                "CreatorId": item.get("CreatorId"),
                "CreatorEmail": item.get("CreatorEmail"),
                "Creator": item.get("Creator"),
                "ParentId": item.get("ParentId"),
                "ServiceId": item.get("ServiceId"),
                "TypeId": item.get("TypeId"),
                "PriorityId": item.get("PriorityId"),
                "StatusId": item.get("StatusId"),
                "url": task_url(item.get("Id")),
            }
        )
    return out


def _parse_id_list(raw: Any) -> list[str]:
    ids: list[str] = []
    if raw is None:
        return ids
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("Id") is not None:
                ids.append(str(item["Id"]))
            elif item is not None and str(item).strip():
                ids.append(str(item).strip())
        return ids
    ids.extend(p.strip() for p in str(raw).split(",") if p.strip())
    return ids


def set_task_parent(child_id: str | int, parent_id: str | int) -> dict[str, Any]:
    """PUT ParentId: сделать заявку подчинённой к parent."""
    cid, pid = str(child_id).strip(), str(parent_id).strip()
    if not cid or not pid or cid == pid:
        return {"ok": False, "error": "некорректные child/parent"}
    before = get_task(cid)
    if str(before.get("ParentId") or "") == pid:
        return {
            "ok": True,
            "skipped": True,
            "Id": before.get("Id"),
            "ParentId": before.get("ParentId"),
            "url": before.get("url"),
            "reason": "ParentId уже установлен",
        }
    data = _request("PUT", f"/task/{cid}", {"ParentId": int(pid)})
    task = data.get("Task") or data
    after = get_task(str(task.get("Id") or cid))
    return {
        "ok": True,
        "Id": after.get("Id"),
        "ParentId": after.get("ParentId"),
        "previous_ParentId": before.get("ParentId"),
        "url": after.get("url"),
        "parent_url": task_url(pid),
    }


def add_task_observers(task_id: str | int, user_ids: list[int | str]) -> dict[str, Any]:
    """PUT ObserverIds: добавить наблюдателей (не затирая существующих)."""
    tid = str(task_id).strip()
    before = get_task(tid)
    ids = _parse_id_list(before.get("ObserverIds"))
    added: list[str] = []
    for uid in user_ids:
        s = str(uid).strip()
        if not s or s in ids:
            continue
        ids.append(s)
        added.append(s)
    if not added:
        return {
            "ok": True,
            "skipped": True,
            "Id": before.get("Id"),
            "ObserverIds": before.get("ObserverIds"),
            "reason": "наблюдатели уже есть",
        }
    data = _request("PUT", f"/task/{tid}", {"ObserverIds": ", ".join(ids)})
    task = data.get("Task") or data
    after = get_task(str(task.get("Id") or tid))
    return {
        "ok": True,
        "Id": after.get("Id"),
        "ObserverIds": after.get("ObserverIds"),
        "added": added,
        "url": after.get("url"),
    }


def list_task_statuses() -> list[dict[str, Any]]:
    data = _request("GET", "/taskstatus")
    items = data if isinstance(data, list) else data.get("Statuses") or data.get("TaskStatuses") or []
    out: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "Id": item.get("Id"),
                "Name": item.get("Name"),
                "IsInitial": item.get("IsInitial"),
                "IsFinal": item.get("IsFinal"),
                "IsCommentRequired": item.get("IsCommentRequired"),
            }
        )
    return out


def current_user() -> dict[str, Any]:
    data = _request("GET", "/user?getcurrentuserinfo=true")
    user = data.get("User") or data
    return {
        "Id": user.get("Id"),
        "Login": user.get("Login"),
        "Name": user.get("Name"),
        "Email": user.get("Email"),
    }


# Ключи статусов IEK HelpDesk (helpdesk.iek.local, /api/taskstatus).
# «В работе» в справочнике нет — используем «В процессе».
STATUS_KEYS: dict[str, int] = {
    "open": 31,
    "in_progress": 27,
    "transferred": 38,
    "awaiting_reply": 46,
    "awaiting_reply_autoclose": 120,
    "done": 29,
    "closed": 28,
    "l1": 121,
}

STATUS_ALIASES: dict[str, str] = {
    "открыта": "open",
    "в работе": "in_progress",
    "в процессе": "in_progress",
    "передана исполнителю": "transferred",
    "ожидает ответа": "awaiting_reply",
    "ожидание ответа": "awaiting_reply",
    "ожидание ответа пользователя": "awaiting_reply",
    "выполнена": "done",
    "закрыта": "closed",
    "1 линия": "l1",
    "1 линия тп": "l1",
}


def resolve_status(status: str | int) -> dict[str, Any]:
    catalog = load_catalog().get("statuses") or {}
    if isinstance(status, int) or (isinstance(status, str) and status.strip().isdigit()):
        sid = int(status)
        name = ""
        for item in list_task_statuses():
            if item.get("Id") == sid:
                name = item.get("Name") or ""
                break
        return {"StatusId": sid, "Name": name, "key": str(sid)}

    raw = (status or "").strip().lower().replace("ё", "е")
    key = STATUS_ALIASES.get(raw) or raw
    if key in STATUS_KEYS:
        sid = int(catalog.get(key) or STATUS_KEYS[key])
        return {"StatusId": sid, "Name": "", "key": key}
    if key in catalog and str(catalog[key]).isdigit():
        return {"StatusId": int(catalog[key]), "Name": "", "key": key}

    for item in list_task_statuses():
        name = (item.get("Name") or "").lower().replace("ё", "е")
        if raw == name or raw in name:
            return {"StatusId": int(item["Id"]), "Name": item.get("Name") or "", "key": raw}
    return {"StatusId": None, "error": f"Неизвестный статус «{status}»", "known_keys": list(STATUS_KEYS)}


def _merge_executor_ids(existing: Any, user_id: int) -> str:
    ids: list[str] = []
    if existing is not None:
        if isinstance(existing, list):
            for item in existing:
                if isinstance(item, dict) and item.get("Id") is not None:
                    ids.append(str(item["Id"]))
                elif item is not None:
                    ids.append(str(item).strip())
        else:
            ids.extend(p.strip() for p in str(existing).split(",") if p.strip())
    uid = str(user_id)
    if uid not in ids:
        ids.append(uid)
    return ", ".join(ids)


def update_task_status(
    task_id: str,
    status: str | int,
    *,
    comment: str = "",
    assign_self: bool = False,
) -> dict[str, Any]:
    """PUT /api/task/{id}: сменить StatusId (и опционально назначить себя исполнителем)."""
    resolved = resolve_status(status)
    sid = resolved.get("StatusId")
    if not sid:
        return {"ok": False, **resolved}

    before = get_task(str(task_id).strip())
    statuses = {int(s["Id"]): s for s in list_task_statuses() if s.get("Id") is not None}
    meta = statuses.get(int(sid)) or {}
    if meta.get("IsCommentRequired") and not (comment or "").strip():
        return {
            "ok": False,
            "error": f"Для статуса «{meta.get('Name') or sid}» нужен комментарий",
            "StatusId": sid,
        }

    body: dict[str, Any] = {"StatusId": int(sid)}
    if (comment or "").strip():
        body["Comment"] = comment.strip()

    me: dict[str, Any] | None = None
    if assign_self:
        me = current_user()
        uid = me.get("Id")
        if not uid:
            return {"ok": False, "error": "Не удалось определить текущего пользователя API"}
        body["ExecutorIds"] = _merge_executor_ids(before.get("ExecutorIds"), int(uid))

    data = _request("PUT", f"/task/{task_id}", body)
    task = data.get("Task") or data
    after_id = task.get("Id") or task_id
    after = get_task(str(after_id))
    return {
        "ok": True,
        "Id": after.get("Id"),
        "Name": after.get("Name"),
        "StatusId": after.get("StatusId"),
        "StatusName": after.get("StatusName") or meta.get("Name") or resolved.get("Name"),
        "ExecutorIds": after.get("ExecutorIds"),
        "url": after.get("url"),
        "assigned_self": bool(assign_self),
        "executor": me,
        "previous_StatusId": before.get("StatusId"),
        "previous_StatusName": before.get("StatusName"),
    }


# Статусы, при которых чатбот не берёт «В работе» и не делает разбор/скрытый комментарий
# (если включён skip_if_in_progress_or_awaiting + take_in_work / auto_take_in_work).
SKIP_TAKE_STATUS_IDS: frozenset[int] = frozenset(
    {
        STATUS_KEYS["in_progress"],  # 27 В процессе
        STATUS_KEYS["awaiting_reply"],  # 46 Ожидание ответа пользователя
        STATUS_KEYS["awaiting_reply_autoclose"],  # 120
    }
)


def status_blocks_take_in_work(task: dict[str, Any]) -> dict[str, Any]:
    """True, если заявка уже «В процессе» или в ожидании ответа — брать/разбирать не нужно."""
    sid = task.get("StatusId")
    try:
        sid_int = int(sid) if sid is not None else None
    except (TypeError, ValueError):
        sid_int = None
    name = (task.get("StatusName") or "").strip()
    if sid_int is not None and sid_int in SKIP_TAKE_STATUS_IDS:
        if sid_int == STATUS_KEYS["in_progress"]:
            reason = f"уже в работе (StatusId={sid_int} {name or 'В процессе'})"
        else:
            reason = f"уже ожидание ответа (StatusId={sid_int} {name or 'Ожидание ответа'})"
        return {
            "blocked": True,
            "StatusId": sid_int,
            "StatusName": name,
            "reason": reason,
        }
    return {"blocked": False, "StatusId": sid_int, "StatusName": name}


def take_task_in_work(task_id: str, comment: str = "") -> dict[str, Any]:
    """Взять заявку: статус «В процессе» + текущий пользователь в исполнителях.

    Если уже «В процессе» или «Ожидание ответа» — no-op (не менять статус).
    """
    before = get_task(str(task_id).strip())
    gate = status_blocks_take_in_work(before)
    if gate.get("blocked"):
        return {
            "ok": True,
            "skipped": True,
            "reason": gate.get("reason"),
            "Id": before.get("Id"),
            "StatusId": before.get("StatusId"),
            "StatusName": before.get("StatusName"),
            "url": before.get("url"),
        }
    return update_task_status(
        task_id,
        "in_progress",
        comment=comment or "Взято в работу (чатбот 1 линии)",
        assign_self=True,
    )


def set_task_awaiting_reply(task_id: str, comment: str) -> dict[str, Any]:
    """Перевести в «Ожидание ответа пользователя» (комментарий обязателен)."""
    return update_task_status(
        task_id,
        "awaiting_reply",
        comment=comment,
        assign_self=False,
    )


def update_task_priority(task_id: str, priority_id: int) -> dict[str, Any]:
    """PUT /api/task/{id}: сменить PriorityId (важность)."""
    return update_task_fields(task_id, {"PriorityId": int(priority_id)})


def update_task_fields(task_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """PUT /api/task/{id}: доп. поля Field{id} (код закрытия, тип, ссылка на инструкцию)."""
    tid = str(task_id).strip()
    body: dict[str, Any] = {}
    for key, val in (fields or {}).items():
        if val is None:
            continue
        s = str(val).strip() if not isinstance(val, bool) else val
        if s == "" and not isinstance(val, bool):
            continue
        body[str(key)] = val
    if not body:
        return {"ok": True, "skipped": True, "reason": "нет полей для обновления", "Id": tid}
    data = _request("PUT", f"/task/{tid}", body)
    task = data.get("Task") or data
    return {
        "ok": True,
        "Id": task.get("Id") or tid,
        "updated": sorted(body.keys()),
        "values": {k: body[k] for k in body},
        "url": task_url(task.get("Id") or tid),
    }


def add_private_comment(task_id: str, comment: str) -> dict[str, Any]:
    """Скрытый от клиента комментарий: PUT Comment + IsPrivateComment=true."""
    text = (comment or "").strip()
    if not text:
        return {"ok": False, "error": "Пустой комментарий"}
    data = _request(
        "PUT",
        f"/task/{task_id}",
        {"Comment": text, "IsPrivateComment": True},
    )
    task = data.get("Task") or data
    return {
        "ok": True,
        "Id": task.get("Id") or task_id,
        "StatusId": task.get("StatusId"),
        "url": task_url(task.get("Id") or task_id),
        "private": True,
    }


def shift_deadline(task_id: str, *, days: int = 1) -> dict[str, Any]:
    """PUT Deadline: сдвинуть срок на N дней (по умолчанию +1)."""
    import overdue as overdue_mod

    tid = str(task_id).strip()
    before = get_task(tid)
    old = before.get("Deadline")
    new_iso = overdue_mod.next_deadline_iso(str(old) if old else None, days=days)
    data = _request("PUT", f"/task/{tid}", {"Deadline": new_iso})
    task = data.get("Task") or data
    after = get_task(str(task.get("Id") or tid))
    return {
        "ok": True,
        "Id": after.get("Id") or tid,
        "Deadline": after.get("Deadline") or new_iso,
        "previous_Deadline": old,
        "shifted_days": days,
        "url": after.get("url") or task_url(tid),
    }


def add_public_comment(task_id: str, comment: str) -> dict[str, Any]:
    """Публичный комментарий клиенту (виден заявителю).

    IntraService: одного IsPrivateComment=false часто недостаточно (коммент остаётся
    скрытым) — явно шлём IsPublic=true.
    """
    text = (comment or "").strip()
    if not text:
        return {"ok": False, "error": "Пустой комментарий"}
    tid = str(task_id).strip()
    data = _request(
        "PUT",
        f"/task/{tid}",
        {"Comment": text, "IsPrivateComment": False, "IsPublic": True},
    )
    task = data.get("Task") or data
    # проверить последнюю запись lifetime
    is_public: bool | None = None
    try:
        lt = get_task_lifetime(tid, page_size=10)
        rows = lt.get("TaskLifetimes") or []
        for row in sorted(rows, key=lambda r: str((r or {}).get("Date") or ""), reverse=True):
            if not isinstance(row, dict):
                continue
            if str(row.get("Comments") or "").strip()[:80] == text[:80]:
                is_public = bool(row.get("IsPublic"))
                break
    except Exception:
        is_public = None
    return {
        "ok": True,
        "Id": task.get("Id") or tid,
        "StatusId": task.get("StatusId"),
        "url": task_url(task.get("Id") or tid),
        "private": False if is_public is None else (not is_public),
        "IsPublic": is_public,
        "warning": None
        if is_public is not False
        else "комментарий записан, но IsPublic=false — проверьте права API/UI",
    }


def update_task_service(task_id: str, service_id: int) -> dict[str, Any]:
    """PUT /api/task/{id}: сменить ServiceId (ветка HelpDesk)."""
    before = get_task(str(task_id).strip())
    data = _request("PUT", f"/task/{task_id}", {"ServiceId": int(service_id)})
    task = data.get("Task") or data
    after = get_task(str(task.get("Id") or task_id))
    return {
        "ok": True,
        "Id": after.get("Id"),
        "ServiceId": after.get("ServiceId"),
        "ServiceName": after.get("ServiceName"),
        "previous_ServiceId": before.get("ServiceId"),
        "previous_ServiceName": before.get("ServiceName"),
        "url": after.get("url"),
    }


def list_services_for_create() -> list[dict[str, Any]]:
    data = _request("GET", "/service?for=createtask&fields=Id,Name,Code")
    items = data.get("Services") or data.get("Result") or data
    if isinstance(items, dict):
        items = items.get("data") or items.get("Items") or []
    out: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "Id": item.get("Id"),
                "Name": item.get("Name"),
                "Code": item.get("Code"),
            }
        )
    return out[:80]


def resolve_service(service_key: str) -> dict[str, Any]:
    catalog = load_catalog().get("services") or {}
    entry = catalog.get(service_key) or {}
    if entry.get("ServiceId"):
        return entry
    services = list_services_for_create()
    needles = {
        "lk": ("лк", "личн", "партнёр", "партнер"),
        "lk_incident": ("инцидент", "лк"),
        "kp": ("портал", "кп", "corp"),
        "bp": ("бизнес-платформ", "цкг", "bp", "dbp"),
        "logistics": ("перевозчик", "logistic"),
        "expeditors": ("экспедитор", "expd"),
        "quart": ("quart", "ткп"),
        "iprice": ("iprice",),
        "vpn": ("vpn", "доступ"),
        "mail": ("почт", "exchange", "mail"),
        "other": (),
    }
    keys = needles.get(service_key.lower(), ())
    for svc in services:
        name = (svc.get("Name") or "").lower()
        if any(n in name for n in keys):
            return {
                "ServiceId": svc.get("Id"),
                "name": svc.get("Name"),
                "TypeId": entry.get("TypeId"),
                "PriorityId_default": entry.get("PriorityId_default"),
                "StatusId_open": entry.get("StatusId_open"),
            }
    return {"ServiceId": None, "available": services[:20], "hint": entry.get("name")}


def newtask_defaults(service_id: int, type_id: int | None = None) -> dict[str, Any]:
    path = f"/newtask?serviceid={service_id}"
    if type_id:
        path += f"&tasktypeid={type_id}"
    data = _request("GET", path)
    return data.get("Task") or data


def create_task(
    *,
    name: str,
    description: str,
    service_key: str = "lk",
    user_email: str = "",
    service_id: int | None = None,
) -> dict[str, Any]:
    resolved = resolve_service(service_key)
    sid = service_id or resolved.get("ServiceId")
    if not sid:
        return {
            "ok": False,
            "error": "Неизвестный ServiceId. Уточните сервис или заполните docs/интеграции/service_catalog.json",
            "resolved": resolved,
        }
    defaults: dict[str, Any] = {}
    try:
        defaults = newtask_defaults(int(sid), resolved.get("TypeId"))
    except RuntimeError:
        defaults = {}
    body: dict[str, Any] = {
        "Name": name[:120],
        "Description": description,
        "ServiceId": int(sid),
        "TypeId": resolved.get("TypeId") or defaults.get("TypeId"),
        "StatusId": resolved.get("StatusId_open") or defaults.get("StatusId"),
        "PriorityId": resolved.get("PriorityId_default") or defaults.get("PriorityId"),
    }
    body = {k: v for k, v in body.items() if v is not None}
    if user_email:
        body["UserEmail"] = user_email
    data = _request("POST", "/task", body)
    task = data.get("Task") or data
    tid = task.get("Id")
    return {
        "ok": True,
        "Id": tid,
        "Name": task.get("Name") or name,
        "url": task_url(tid) if tid else None,
        "ServiceId": body.get("ServiceId"),
    }
