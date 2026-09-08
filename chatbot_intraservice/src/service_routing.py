# -*- coding: utf-8 -*-
"""Проверка ServiceId HelpDesk vs контур lk/bp и подсказка переноса."""
from __future__ import annotations

import re
from typing import Any

# Наблюдение по helpdesk.iek.local (WEB → WEB)
HD_BRANCH: dict[int, dict[str, Any]] = {
    713: {"key": "lk", "name": "Личный кабинет партнера (lk.iek.ru)"},
    731: {"key": "lk", "name": "Инцидент (ветка ЛК)", "parent": 713},
    732: {"key": "lk", "name": "Запрос на обслуживание (ветка ЛК)", "parent": 713},
    14: {"key": "edi", "name": "1С Предприятие"},
    69: {"key": "edi", "name": "Солярис", "parent": 14},
    827: {"key": "bp", "name": "Бизнес платформа (Портал ЦКГ)"},
    833: {"key": "bp", "name": "Запрос на обслуживание (ветка БП)", "parent": 827},
    29: {"key": "crm", "name": "CRM"},
}

HD_REQUEST_BY_KEY = {"lk": 732, "bp": 833}
HD_INCIDENT_BY_KEY = {"lk": 731}

# GET /api/tasktype · /api/taskpriority (helpdesk.iek.local, 2026-09)
HD_TYPE = {
    "incident": 1008,
    "request": 1009,
    "change": 1010,
}
HD_TYPE_NAME = {
    1008: "инцидент",
    1009: "запрос на обслуживание",
    1010: "запрос на изменение",
}
HD_PRIORITY = {
    "standard": 11,
    "elevated": 9,
    "high": 10,
    "critical": 12,
}
HD_PRIORITY_NAME = {
    11: "стандартный",
    9: "повышенный",
    10: "высокий",
    12: "критичный",
}
_PRIORITY_RANK = {11: 0, 9: 1, 10: 2, 12: 3}

_INCIDENT = re.compile(
    r"(?i)не\s+работа|недоступ|сбой|упал[аио]?|ошибк[аи]\s*500|не\s+гру[зж]|"
    r"висит|бесконечн\w*\s+загруз|глобальн\w*\s+сбой|временно\s+недоступ|"
    r"service\s+temporarily|инцидент|массовый\s+сбой",
)
_CHANGE = re.compile(
    r"(?i)запрос\s+на\s+изменение|добавить\s+пользовател|удалить\s+пользовател|"
    r"сменить\s+ответствен|назначить\s+заместител|доработк|выдать\s+права|"
    r"включить\s+доступ|завести\s+пользовател",
)
_CRITICAL = re.compile(
    r"(?i)глобальн\w*\s+сбой|массовый\s+сбой|у\s+всех|простой\s+бизнес|"
    r"не\s+работа\w*\s+(?:лк|кабинет|портал)",
)
_HIGH = re.compile(
    r"(?i)не\s+работа|недоступ|не\s+гру[зж]|временно\s+недоступ|упал",
)

_BP = re.compile(
    r"bp\.iek|бизнес[\s-]*платформ|цкг|dbp|api[\s-]*ключ|oauth/login|profile#api|"
    r"iek[\s\-]*id|авторизац|неверн\w*\s+парол|восстановлен\w*\s+парол|сброс\w*\s+парол|"
    r"не\s*корректн\w*\s*e?-?mail|слетел\w*\s+авторизац",
    re.I,
)
_LK = re.compile(
    r"lk\.iek|личн\w*\s+кабинет|партн[её]р(?:ский|\s+лк)?|заказ\s+покупател|"
    r"резерв\w*\s+в\s+пути|неудовлетвор|упд|тендер|сч[её]т\s+не\s+(?:отображ|видн)",
    re.I,
)
_EDI = re.compile(
    r"\bedi\b|\badi\b|электронн\w*\s+обмен|данные\s+обмена|"
    r"заказ\s+поставщик|эл\.?\s*заявк|подтверд\w*\s+заказ|"
    r"провести\s+сч[её]т|выстав\w*\s+сч[её]т|сч[её]т\s+по\s+обмен",
    re.I,
)
_API = re.compile(r"\bapi\b|api[\s-]?(?:ключ|key|шлюз)|products/api|mailer@iek\.ru", re.I)
_CRM = re.compile(
    r"crm\.iek|crmrf\.iek|битрикс.*crm|контур.*crm|"
    r"передач\w*\s+фин\.?\s*отчет|фин\.?\s*отчетност",
    re.I,
)


def infer_contour(text: str = "", service_key: str = "") -> str:
    key = (service_key or "").strip().lower()
    blob = text or ""
    if _CRM.search(blob):
        return "crm"
    if key in {"bp", "lk", "kp", "vpn", "mail", "crm", "edi", "1c"}:
        if key == "1c":
            return "edi"
        return key if key != "kp" else "kp"
    edi_hit = bool(_EDI.search(blob))
    bp_hit = bool(_BP.search(blob))
    lk_hit = bool(_LK.search(blob))
    api_hit = bool(_API.search(blob))
    # EDI / электронный обмен / заказ поставщику → 1С (не путать с API каталога ЛК)
    if edi_hit and not (api_hit and re.search(r"(?i)products/api|mailer@iek", blob)):
        return "edi"
    if bp_hit and not lk_hit and not edi_hit:
        return "bp"
    if lk_hit and not bp_hit and not edi_hit:
        return "lk"
    if bp_hit and lk_hit:
        if re.search(r"iek[\s\-]*id|авторизац|парол", blob, re.I):
            return "bp"
        return "other"
    if api_hit and not edi_hit:
        # API каталога ЛК vs bp API-ключ
        if re.search(r"(?i)products/api|api\s+каталог|mailer@iek", blob):
            return "lk"
        return "bp"
    return "other"


def branch_for_service_id(service_id: int | str | None) -> dict[str, Any]:
    sid: int | None = None
    if isinstance(service_id, int):
        sid = service_id
    elif isinstance(service_id, str) and service_id.strip().isdigit():
        sid = int(service_id.strip())
    if sid is None:
        return {"key": "unknown", "name": "ServiceId не задан", "service_id": service_id}
    row = HD_BRANCH.get(sid, {})
    if row:
        return {"key": row["key"], "name": row["name"], "service_id": sid, "parent": row.get("parent")}
    return {"key": "other", "name": f"ServiceId={sid}", "service_id": sid}


def infer_type_key(text: str = "", *, service_id: int | str | None = None) -> str:
    """incident | change | request по тексту и ветке HD (731 = инцидент ЛК)."""
    sid = None
    if isinstance(service_id, int):
        sid = service_id
    elif isinstance(service_id, str) and service_id.strip().isdigit():
        sid = int(service_id.strip())
    blob = text or ""
    change = bool(_CHANGE.search(blob))
    incident = bool(_INCIDENT.search(blob))
    if change and not incident:
        return "change"
    if incident or sid == 731:
        return "incident"
    return "request"


def infer_priority_id(
    text: str = "",
    *,
    type_key: str = "",
    prior_priority_id: int | None = None,
) -> tuple[int, str]:
    """(PriorityId, краткая причина). Не понижает критичность относительно prior."""
    blob = text or ""
    if _CRITICAL.search(blob):
        return HD_PRIORITY["critical"], "критичный: массовый/глобальный сбой"
    if type_key == "incident" or _HIGH.search(blob):
        return HD_PRIORITY["high"], "высокий: недоступность"
    if prior_priority_id in (HD_PRIORITY["high"], HD_PRIORITY["critical"]):
        name = HD_PRIORITY_NAME.get(prior_priority_id) or str(prior_priority_id)
        return int(prior_priority_id), f"{name}: по аналогии с заявителем"
    if prior_priority_id == HD_PRIORITY["elevated"]:
        return HD_PRIORITY["elevated"], "повышенный: по аналогии с заявителем"
    return HD_PRIORITY["standard"], "стандартный"


def _majority_int(values: list[Any], *, min_n: int = 2) -> tuple[int | None, int]:
    counts: dict[int, int] = {}
    for v in values:
        if v is None or v == "":
            continue
        try:
            i = int(v)
        except (TypeError, ValueError):
            continue
        counts[i] = counts.get(i, 0) + 1
    if not counts:
        return None, 0
    best = max(counts, key=lambda k: counts[k])
    n = counts[best]
    if n < min_n:
        return None, n
    return best, n


def type_name(type_id: Any) -> str:
    try:
        return HD_TYPE_NAME.get(int(type_id), str(type_id))
    except (TypeError, ValueError):
        return "?"


def priority_name(priority_id: Any) -> str:
    try:
        return HD_PRIORITY_NAME.get(int(priority_id), str(priority_id))
    except (TypeError, ValueError):
        return "?"


def priority_rank(priority_id: Any) -> int:
    try:
        return _PRIORITY_RANK.get(int(priority_id), -1)
    except (TypeError, ValueError):
        return -1


def check_service(
    task: dict[str, Any],
    *,
    contour: str = "",
    adm_found: bool | None = None,
    prior: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Сравнить ветку HD, тип заявки и важность с текстом и prior заявителя."""
    sid_raw = task.get("ServiceId")
    sid: int | None = None
    if isinstance(sid_raw, int):
        sid = sid_raw
    elif isinstance(sid_raw, str) and sid_raw.strip().isdigit():
        sid = int(sid_raw.strip())
    text = f"{task.get('Name') or ''}\n{task.get('Description') or ''}"
    expected = (contour or infer_contour(text)).lower()
    if expected == "1c":
        expected = "edi"
    actual = branch_for_service_id(sid)
    actual_key = actual.get("key") or "unknown"

    if expected not in {"lk", "bp", "edi"} and actual_key in {"lk", "bp", "edi"}:
        expected = str(actual_key)

    if adm_found is True and expected not in {"lk", "edi"}:
        expected = "bp"
    elif adm_found is True and expected == "lk" and infer_contour(text) == "bp":
        expected = "bp"

    prior_rows = [p for p in (prior or []) if isinstance(p, dict)]
    prior_sid, prior_sid_n = _majority_int([p.get("ServiceId") for p in prior_rows])
    prior_tid, prior_tid_n = _majority_int([p.get("TypeId") for p in prior_rows])
    prior_pid, prior_pid_n = _majority_int([p.get("PriorityId") for p in prior_rows])
    prior_contour = branch_for_service_id(prior_sid).get("key") if prior_sid else ""
    contradiction = bool(
        expected in {"lk", "bp", "edi"}
        and prior_contour in {"lk", "bp", "edi"}
        and expected != prior_contour
    )

    type_key = infer_type_key(text, service_id=sid)
    suggest_type_id = HD_TYPE.get(type_key)
    if expected == "edi":
        ok = actual_key == "edi"
        note = "ветка 1С Солярис" if ok else "действия в 1С (не UI ЛК/БП)"
        suggest_id = 69 if (not ok and sid != 69) else None
    elif expected == "crm":
        ok = False
        note = "разбор в CRM (не UI ЛК/БП)"
        suggest_id = None
    else:
        if expected == "lk" and type_key == "incident":
            suggest_id = HD_INCIDENT_BY_KEY.get("lk")
        elif expected in HD_REQUEST_BY_KEY:
            suggest_id = HD_REQUEST_BY_KEY.get(expected)
        else:
            suggest_id = None
        if (
            not contradiction
            and prior_sid
            and expected == prior_contour
            and type_key != "incident"
            and suggest_id
            and prior_sid in {731, 732, 833}
        ):
            # prior того же контура усиливает leaf-сервис (кроме инцидента по тексту)
            suggest_id = int(prior_sid)
        ok = actual_key == expected and expected in {"lk", "bp"}
        if suggest_id and sid and int(suggest_id) != int(sid):
            ok = False
        note = ""
        if not ok and suggest_id and sid != suggest_id:
            leaf = HD_BRANCH.get(int(suggest_id), {})
            note = f"вероятно перенести на ServiceId={suggest_id} ({leaf.get('name') or suggest_id})"
        elif not ok and expected == "other":
            note = "контур неясен — уточнить ЛК / БП / EDI(1С)"
        elif ok:
            note = "ветка HD совпадает с контуром"
        if contradiction:
            note = (note + " · " if note else "") + (
                f"prior заявителя чаще ServiceId={prior_sid} ({prior_contour}), "
                f"текст — {expected}: prior не используем"
            )

    cur_type = task.get("TypeId")
    try:
        cur_type_i = int(cur_type) if cur_type is not None else None
    except (TypeError, ValueError):
        cur_type_i = None
    type_ok = bool(suggest_type_id and cur_type_i == suggest_type_id)
    if not type_ok and suggest_type_id:
        type_note = f"→ тип {HD_TYPE_NAME.get(suggest_type_id)} ({suggest_type_id})"
        if prior_tid and prior_tid == suggest_type_id:
            type_note += f" · как у заявителя (n={prior_tid_n})"
    else:
        type_note = "тип ок"

    pri_id, pri_why = infer_priority_id(
        text,
        type_key=type_key,
        prior_priority_id=prior_pid if not contradiction else None,
    )
    try:
        cur_pri = int(task.get("PriorityId")) if task.get("PriorityId") is not None else None
    except (TypeError, ValueError):
        cur_pri = None
    can_auto_priority = (
        not contradiction
        and pri_id is not None
        and cur_pri is not None
        and priority_rank(pri_id) > priority_rank(cur_pri)
    )
    if cur_pri is None and pri_id:
        can_auto_priority = not contradiction

    return {
        "service_id": sid,
        "service_branch": actual.get("name"),
        "contour_expected": expected,
        "contour_hd": actual_key,
        "service_ok": ok,
        "suggest_service_id": suggest_id if (not ok and suggest_id) else sid,
        "note": note,
        "type_id": cur_type_i,
        "type_name": type_name(cur_type_i) if cur_type_i else "?",
        "type_key": type_key,
        "type_ok": type_ok,
        "suggest_type_id": suggest_type_id,
        "type_note": type_note,
        "priority_id": cur_pri,
        "priority_name": priority_name(cur_pri) if cur_pri else "?",
        "suggest_priority_id": pri_id,
        "priority_why": pri_why,
        "priority_ok": cur_pri == pri_id,
        "can_auto_priority": can_auto_priority,
        "prior_service_id": prior_sid,
        "prior_type_id": prior_tid,
        "prior_priority_id": prior_pid,
        "prior_n": {"service": prior_sid_n, "type": prior_tid_n, "priority": prior_pid_n},
        "contradiction": contradiction,
    }


def format_service_line(check: dict[str, Any]) -> str:
    """Строка преданализа: сервис + тип + важность (рекомендации без автосмены сервиса/типа)."""
    sid = check.get("service_id")
    ok = check.get("service_ok")
    exp = check.get("contour_expected")
    branch = check.get("service_branch") or "?"
    tname = check.get("type_name") or type_name(check.get("type_id"))
    pname = check.get("priority_name") or priority_name(check.get("priority_id"))
    bits = [f"Сервис: {sid} · {branch}"]
    bits.append(f"тип: {tname}")
    if not check.get("type_ok") and check.get("suggest_type_id"):
        bits.append(str(check.get("type_note") or "сменить тип?"))
    else:
        bits.append("тип ок")
    bits.append(f"важность: {pname}")
    if not check.get("priority_ok"):
        sug_p = check.get("suggest_priority_id")
        why = check.get("priority_why") or ""
        auto = "авто" if check.get("can_auto_priority") else "рекомендация"
        bits.append(f"{auto} → {priority_name(sug_p)} ({why})")
    if exp == "crm":
        bits.append("по смыслу CRM")
    elif exp == "edi":
        bits.append(str(check.get("note") or "EDI/1С"))
    elif ok:
        bits.append(f"контур {exp} ок")
    else:
        sug = check.get("suggest_service_id")
        bits.append(f"ожидался {exp}")
        if sug and sug != sid:
            bits.append(f"→ сервис {sug}?")
        note = check.get("note")
        if note:
            bits.append(str(note))
    return " · ".join(str(b) for b in bits if b)


def format_service_mismatch_line(check: dict[str, Any]) -> str:
    """Всегда строка классификации (Качанов: тип + сервис + важность в преданализе)."""
    return format_service_line(check)


def api_key_hint(contour: str) -> str:
    if contour == "bp":
        return "API-ключ БП: https://bp.iek.ru/profile#api-keys (username=ticket, password=ключ)"
    if contour == "lk":
        return "API каталога ЛК: учётка «внешний пользователь API» — создаёт поддержка, не self-service"
    return ""
