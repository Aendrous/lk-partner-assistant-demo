# -*- coding: utf-8 -*-
"""Связанные заявки HelpDesk по сильным идентификаторам (заказ/счёт/эл.заявка/GUID).

Более поздняя → ParentId = более ранняя; инициатор ранней → ObserverIds поздней.
"""
from __future__ import annotations

import re
from typing import Any

import intraservice

# токены для поиска: номер документа без метки
_TOKEN_RE = re.compile(
    r"(?:"
    r"заказ|сч[её]т|эл\.?\s*заявка|guid\s*лк"
    r")\s+([^\s,;]+)",
    re.I,
)
_BARE_ORDER = re.compile(r"\b([А-ЯA-Z]{1,3}\d{6,12})\b")
_EAPP = re.compile(r"\b(0000\d{5,})\b")
_GUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)


def tokens_from_refs(refs: list[str], *extra_blobs: str) -> list[str]:
    """Уникальные сильные идентификаторы для IntraService search."""
    seen: set[str] = set()
    out: list[str] = []

    def add(tok: str) -> None:
        t = (tok or "").strip()
        if not t:
            return
        key = t.lower()
        if key in seen or len(t) < 5:
            return
        seen.add(key)
        out.append(t)

    for ref in refs or []:
        m = _TOKEN_RE.search(ref)
        if m:
            add(m.group(1))
        else:
            # «заказ ХИ…» уже пойман; иначе — голый номер
            for pat in (_BARE_ORDER, _EAPP, _GUID):
                for hit in pat.findall(ref):
                    add(hit)

    blob = "\n".join(b or "" for b in extra_blobs)
    for pat in (_BARE_ORDER, _EAPP, _GUID):
        for hit in pat.findall(blob):
            add(hit)
    return out[:12]


def find_related_tasks(
    current_task_id: str | int,
    tokens: list[str],
    *,
    page_size: int = 20,
) -> dict[str, Any]:
    """Найти другие заявки с теми же токенами; сгруппировать match_by."""
    cur = str(current_task_id).strip()
    by_id: dict[str, dict[str, Any]] = {}
    for tok in tokens:
        try:
            hits = intraservice.search_tasks(tok, page_size=page_size)
        except Exception as exc:
            return {"ok": False, "error": f"search {tok}: {type(exc).__name__}", "related": []}
        for hit in hits:
            hid = str(hit.get("Id") or "")
            if not hid or hid == cur:
                continue
            row = by_id.setdefault(
                hid,
                {
                    "Id": hit.get("Id"),
                    "Name": hit.get("Name"),
                    "Created": hit.get("Created"),
                    "CreatorId": hit.get("CreatorId"),
                    "CreatorEmail": hit.get("CreatorEmail"),
                    "Creator": hit.get("Creator"),
                    "ParentId": hit.get("ParentId"),
                    "url": hit.get("url") or intraservice.task_url(hid),
                    "matched_by": [],
                },
            )
            if tok not in row["matched_by"]:
                row["matched_by"].append(tok)

    related = sorted(
        by_id.values(),
        key=lambda r: str(r.get("Created") or ""),
    )
    return {"ok": True, "tokens": tokens, "related": related}


_STOPWORDS = frozenset(
    {
        "заявка",
        "запрос",
        "ошибка",
        "проблема",
        "добрый",
        "день",
        "пожалуйста",
        "прошу",
        "помогите",
        "нужно",
        "надо",
        "личный",
        "кабинет",
        "партнер",
        "партнёр",
        "iek",
        "http",
        "https",
        "www",
        "mail",
        "email",
        "уважаемые",
        "коллеги",
    }
)
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{4,}", re.U)


def keywords_from_text(*blobs: str, limit: int = 6) -> list[str]:
    """Значимые слова для поиска похожих заявок."""
    seen: set[str] = set()
    out: list[str] = []
    blob = " ".join(b or "" for b in blobs).lower().replace("ё", "е")
    for m in _WORD_RE.findall(blob):
        w = m.lower().replace("ё", "е")
        if w in _STOPWORDS or w.isdigit() or len(w) < 4:
            continue
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def find_creator_prior_tasks(
    current_task_id: str | int,
    *,
    creator_id: Any = None,
    creator_email: str = "",
    page_size: int = 15,
) -> dict[str, Any]:
    """Предыдущие заявки того же инициатора (по email / CreatorId)."""
    cur = str(current_task_id).strip()
    email = (creator_email or "").strip()
    cid = str(creator_id).strip() if creator_id is not None else ""
    query = email or cid
    if not query:
        return {"ok": True, "prior": [], "reason": "нет CreatorEmail/CreatorId"}
    try:
        hits = intraservice.search_tasks(query, page_size=page_size)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "prior": []}
    prior: list[dict[str, Any]] = []
    for hit in hits:
        hid = str(hit.get("Id") or "")
        if not hid or hid == cur:
            continue
        same = False
        if cid and str(hit.get("CreatorId") or "").strip() == cid:
            same = True
        if email and (hit.get("CreatorEmail") or "").strip().lower() == email.lower():
            same = True
        if not same:
            continue
        prior.append(
            {
                "Id": hit.get("Id"),
                "Name": hit.get("Name"),
                "Created": hit.get("Created"),
                "StatusId": hit.get("StatusId"),
                "ServiceId": hit.get("ServiceId"),
                "TypeId": hit.get("TypeId"),
                "PriorityId": hit.get("PriorityId"),
                "url": hit.get("url") or intraservice.task_url(hid),
            }
        )
    prior.sort(key=lambda r: str(r.get("Created") or ""), reverse=True)
    return {"ok": True, "query": query, "prior": prior[:5]}


def find_similar_tasks(
    current_task_id: str | int,
    *,
    name: str = "",
    description: str = "",
    service_id: Any = None,
    page_size: int = 12,
    max_hits: int = 3,
) -> dict[str, Any]:
    """Похожие заявки по ключевым словам названия (не только заказ/GUID)."""
    cur = str(current_task_id).strip()
    kws = keywords_from_text(name, (description or "")[:400])
    if not kws:
        return {"ok": True, "keywords": [], "similar": []}
    by_id: dict[str, dict[str, Any]] = {}
    sid = str(service_id).strip() if service_id is not None else ""
    # ищем по 1–2 самым «тяжёлым» словам и по короткой фразе из названия
    queries = kws[:3]
    title_q = " ".join((name or "").split()[:5]).strip()
    if title_q and len(title_q) >= 8:
        queries = [title_q] + queries
    for q in queries[:4]:
        try:
            hits = intraservice.search_tasks(q, page_size=page_size)
        except Exception:
            continue
        for hit in hits:
            hid = str(hit.get("Id") or "")
            if not hid or hid == cur:
                continue
            if sid and str(hit.get("ServiceId") or "").strip() and str(hit.get("ServiceId")) != sid:
                # тот же сервис предпочтительнее, но не отбрасываем сразу
                pass
            row = by_id.setdefault(
                hid,
                {
                    "Id": hit.get("Id"),
                    "Name": hit.get("Name"),
                    "Created": hit.get("Created"),
                    "StatusId": hit.get("StatusId"),
                    "ServiceId": hit.get("ServiceId"),
                    "url": hit.get("url") or intraservice.task_url(hid),
                    "score": 0,
                    "matched_by": [],
                },
            )
            if q not in row["matched_by"]:
                row["matched_by"].append(q)
            # score: пересечение слов названия
            hit_words = set(keywords_from_text(str(hit.get("Name") or ""), limit=12))
            overlap = len(hit_words & set(kws))
            same_svc = 1 if sid and str(hit.get("ServiceId") or "") == sid else 0
            row["score"] = max(row["score"], overlap * 2 + same_svc + len(row["matched_by"]))
    similar = sorted(by_id.values(), key=lambda r: (-int(r.get("score") or 0), str(r.get("Created") or "")), reverse=False)
    similar = [r for r in similar if int(r.get("score") or 0) >= 2][:max_hits]
    return {"ok": True, "keywords": kws, "similar": similar}


def format_related_lines(current: dict[str, Any], related: list[dict[str, Any]]) -> list[str]:
    """Строки для скрытого комментария."""
    lines: list[str] = []
    parent_id = current.get("ParentId")
    if parent_id:
        lines.append(
            f"Подчинена заявке #{parent_id} · {intraservice.task_url(parent_id)}"
        )
    if not related:
        return lines
    matched_all = sorted({m for r in related for m in (r.get("matched_by") or [])})
    lines.append(f"Связанные заявки (по {', '.join(matched_all)}):")
    cur_created = str(current.get("Created") or "")
    for r in related:
        rid = r.get("Id")
        who = (r.get("CreatorEmail") or r.get("Creator") or "?").strip()
        when = (r.get("Created") or "")[:19].replace("T", " ")
        role = "раньше" if str(r.get("Created") or "") < cur_created else "позже"
        matched = ", ".join(r.get("matched_by") or [])
        parent = r.get("ParentId")
        parent_note = f" · parent={parent}" if parent else ""
        lines.append(
            f"• #{rid} ({role}, {when}, {who}) · {matched}{parent_note} · {r.get('url')}"
        )
    return lines


def format_prior_lines(prior: list[dict[str, Any]]) -> list[str]:
    if not prior:
        return []
    lines = ["Предыдущие обращения инициатора:"]
    for r in prior[:3]:
        when = (r.get("Created") or "")[:19].replace("T", " ")
        topic = (r.get("topic") or r.get("Name") or "")[:100]
        lines.append(f"• #{r.get('Id')} ({when}) · {topic} · {r.get('url')}")
    return lines


def format_similar_lines(similar: list[dict[str, Any]]) -> list[str]:
    if not similar:
        return ["Похожие заявки: по смыслу не найдены"]
    lines = ["Похожие заявки (по смыслу):"]
    for r in similar[:3]:
        topic = (r.get("topic") or r.get("Name") or "")[:100]
        why = (r.get("why") or "").strip()
        bit = f"• #{r.get('Id')} · {topic} · {r.get('url')}"
        if why:
            bit += f" — {why}"
        lines.append(bit)
    return lines


def link_later_to_earlier(
    current: dict[str, Any],
    related: list[dict[str, Any]],
    *,
    apply: bool = True,
    add_observer: bool = True,
) -> dict[str, Any]:
    """Более поздние → подчинённые к более ранней; Creator ранней → наблюдатель поздней.

    Берём кластер: current + related, сортируем по Created, parent = earliest.
    """
    cluster: list[dict[str, Any]] = [
        {
            "Id": current.get("Id"),
            "Created": current.get("Created"),
            "CreatorId": current.get("CreatorId"),
            "CreatorEmail": current.get("CreatorEmail"),
            "ParentId": current.get("ParentId"),
            "url": current.get("url"),
        }
    ]
    for r in related:
        cluster.append(r)
    # unique by Id
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for row in cluster:
        iid = str(row.get("Id") or "")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        # refresh CreatorId if missing
        if row.get("CreatorId") is None:
            try:
                full = intraservice.get_task(iid)
                row["CreatorId"] = full.get("CreatorId")
                row["CreatorEmail"] = full.get("CreatorEmail") or row.get("CreatorEmail")
                row["ParentId"] = full.get("ParentId")
                row["Created"] = full.get("Created") or row.get("Created")
            except Exception:
                pass
        uniq.append(row)

    if len(uniq) < 2:
        return {"ok": True, "skipped": True, "reason": "нет пары для связывания", "actions": []}

    ordered = sorted(uniq, key=lambda r: str(r.get("Created") or ""))
    parent = ordered[0]
    parent_id = parent.get("Id")
    parent_creator = parent.get("CreatorId")
    actions: list[dict[str, Any]] = []

    for child in ordered[1:]:
        cid = child.get("Id")
        action: dict[str, Any] = {
            "child_id": cid,
            "parent_id": parent_id,
            "parent_creator_id": parent_creator,
            "child_url": child.get("url") or intraservice.task_url(cid),
            "parent_url": parent.get("url") or intraservice.task_url(parent_id),
        }
        if not apply:
            action["dry_run"] = True
            actions.append(action)
            continue
        parent_res = intraservice.set_task_parent(cid, parent_id)
        action["parent"] = parent_res
        if add_observer and parent_creator:
            obs_res = intraservice.add_task_observers(cid, [parent_creator])
            action["observer"] = obs_res
        elif not add_observer:
            action["observer"] = {"ok": False, "skipped": True, "reason": "add_parent_creator_as_observer=false"}
        else:
            action["observer"] = {"ok": False, "skipped": True, "reason": "нет CreatorId у parent"}
        actions.append(action)

    return {
        "ok": True,
        "parent_id": parent_id,
        "parent_url": parent.get("url") or intraservice.task_url(parent_id),
        "parent_creator_id": parent_creator,
        "parent_creator_email": parent.get("CreatorEmail"),
        "actions": actions,
    }
