# -*- coding: utf-8 -*-
"""Проверка заказа в 1С.

Поддержка:
- HTTP OData: 1C_BASE_URL=https://...
- COM-строка: 1C_CONN=Srvr=\"jack\";Ref=\"plazma\" (или то же в 1C_BASE_URL)
  Учётка: 1C_USER / 1C_USER_PASSWORD.
  Нужен зарегистрированный V83.COMConnector (часто 32-bit 1С + совпадающий Python).

Override: knowledge/learned/1c_overrides.json (скрин исполнителя).
"""
from __future__ import annotations

import os
import re
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_COM_HINT = re.compile(r'(?:Srvr|Ref)\s*=', re.I)


def _creds() -> tuple[str, str]:
    try:
        import intraservice as _is

        _is.load_env()
    except Exception:
        pass
    return (os.environ.get("1C_USER") or "").strip(), (os.environ.get("1C_USER_PASSWORD") or "").strip()


def base_url() -> str:
    try:
        import intraservice as _is

        _is.load_env()
    except Exception:
        pass
    return (os.environ.get("1C_BASE_URL") or os.environ.get("ONEC_BASE_URL") or "").rstrip("/")


def com_connection_string() -> str:
    """COM-строка Srvr=…;Ref=… (без Usr/Pwd)."""
    try:
        import intraservice as _is

        _is.load_env()
    except Exception:
        pass
    for key in ("1C_CONN", "1C_COM_CONN", "1C_BASE_URL", "ONEC_BASE_URL"):
        raw = (os.environ.get(key) or "").strip()
        if raw and _COM_HINT.search(raw) and not raw.lower().startswith("http"):
            return raw.rstrip(";")
    return ""


def check_reserve_in_transit_http(order_number: str) -> dict[str, Any]:
    num = (order_number or "").strip()
    user, password = _creds()
    base = base_url()
    if not base or _COM_HINT.search(base):
        return {"ok": False, "skipped": True, "order": num, "reason": "нет HTTP 1C_BASE_URL"}
    if not user or not password:
        return {"ok": False, "skipped": True, "order": num, "reason": "нет 1C_USER / 1C_USER_PASSWORD"}

    entity = os.environ.get("1C_ORDER_ENTITY") or "Document_ЗаказПокупателя"
    field = os.environ.get("1C_RESERVE_IN_TRANSIT_FIELD") or "РезервироватьТоварыВПути"
    url = f"{base}/odata/standard.odata/{entity}"
    params = {"$format": "json", "$filter": f"Number eq '{num}'", "$select": f"Number,{field},Ref_Key"}
    try:
        resp = requests.get(url, params=params, auth=(user, password), timeout=25, verify=False)
    except requests.RequestException as exc:
        return {"ok": False, "skipped": True, "order": num, "reason": f"сеть 1С: {type(exc).__name__}"}
    if resp.status_code >= 400:
        return {
            "ok": False,
            "skipped": True,
            "order": num,
            "http": resp.status_code,
            "reason": f"1С HTTP {resp.status_code}",
        }
    values = (resp.json() or {}).get("value") or []
    if not values:
        return {"ok": True, "found": False, "order": num, "reserve_in_transit": None, "source": "http"}
    row = values[0]
    return {
        "ok": True,
        "found": True,
        "order": num,
        "reserve_in_transit": bool(row.get(field)),
        "field": field,
        "source": "http",
    }


def check_reserve_in_transit_com(order_number: str) -> dict[str, Any]:
    """Поиск Документ.ЗаказПокупателя через V83.COMConnector."""
    num = (order_number or "").strip()
    conn = com_connection_string()
    if not conn:
        return {"ok": False, "skipped": True, "order": num, "reason": "нет COM-строки 1C_CONN / Srvr=…"}
    user, password = _creds()
    if not user or not password:
        return {"ok": False, "skipped": True, "order": num, "reason": "нет 1C_USER / 1C_USER_PASSWORD"}

    try:
        import win32com.client  # type: ignore
    except ImportError:
        return {"ok": False, "skipped": True, "order": num, "reason": "нет pywin32 (win32com)"}

    field = os.environ.get("1C_RESERVE_IN_TRANSIT_FIELD") or "РезервироватьТоварыВПути"
    doc_name = os.environ.get("1C_ORDER_DOC") or "ЗаказПокупателя"
    cs = conn if "Usr=" in conn else f'{conn};Usr="{user}";Pwd="{password}"'
    try:
        connector = win32com.client.Dispatch("V83.COMConnector")
        try:
            app = connector.Connect(cs)
        except AttributeError:
            return {
                "ok": False,
                "skipped": True,
                "order": num,
                "reason": (
                    "V83.COMConnector без Connect (typelib не зарегистрирована; "
                    "нужен Python той же разрядности, что и COM 1С, обычно 32-bit)"
                ),
            }
    except Exception as exc:
        return {
            "ok": False,
            "skipped": True,
            "order": num,
            "reason": f"COM Connect: {type(exc).__name__}: {str(exc)[:180]}",
        }

    try:
        q = app.NewObject("Query")
        q.Text = (
            f"ВЫБРАТЬ ПЕРВЫЕ 1 Номер, Дата, {field} КАК РезервВПути "
            f"ИЗ Документ.{doc_name} ГДЕ Номер = &Num"
        )
        q.SetParameter("Num", num)
        sel = q.Execute().Choose()
        if not sel.Next():
            return {"ok": True, "found": False, "order": num, "reserve_in_transit": None, "source": "com"}
        return {
            "ok": True,
            "found": True,
            "order": num,
            "reserve_in_transit": bool(sel.РезервВПути),
            "field": field,
            "source": "com",
            "date": str(sel.Дата),
        }
    except Exception as exc:
        return {
            "ok": False,
            "skipped": True,
            "order": num,
            "reason": f"COM query: {type(exc).__name__}: {str(exc)[:200]}",
        }


def check_reserve_in_transit(order_number: str) -> dict[str, Any]:
    """Вернуть, стоит ли галка «Резервировать товары в пути» у заказа покупателя."""
    num = (order_number or "").strip()
    if not num:
        return {"ok": False, "skipped": True, "reason": "нет номера заказа"}

    if com_connection_string():
        com = check_reserve_in_transit_com(num)
        if com.get("ok") and com.get("found"):
            return com
        http = check_reserve_in_transit_http(num)
        if http.get("ok") and not http.get("skipped"):
            return http
        # COM не сработал — вернуть COM-причину (часто typelib), HTTP как доп.
        if com.get("skipped") and http.get("skipped"):
            return {
                "ok": False,
                "skipped": True,
                "order": num,
                "reason": com.get("reason") or http.get("reason"),
                "http_reason": http.get("reason"),
            }
        return com if not com.get("skipped") else http

    return check_reserve_in_transit_http(num)


def match_overrides_from_text(text: str) -> list[dict[str, Any]]:
    """Если в OCR есть GUID/номер из 1c_overrides — вернуть записи."""
    from pathlib import Path
    import json

    blob = (text or "").lower()
    path = Path(__file__).resolve().parents[1] / "knowledge" / "learned" / "1c_overrides.json"
    if not path.is_file() or not blob:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    hits: list[dict[str, Any]] = []
    for order, row in data.items():
        if order.startswith("_") or not isinstance(row, dict):
            continue
        guid = str(row.get("guid") or "").lower()
        eapp = str(row.get("eapp") or "")
        if order.lower() in blob or (guid and guid in blob) or (eapp and eapp in blob):
            hits.append({"order": order, **row})
    return hits


def override_check(order_number: str) -> dict[str, Any] | None:
    """Локальный снимок проверки 1С (скрин исполнителя), пока нет HTTP/COM."""
    from pathlib import Path
    import json

    path = Path(__file__).resolve().parents[1] / "knowledge" / "learned" / "1c_overrides.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    row = data.get(order_number.strip())
    if not isinstance(row, dict):
        return None
    return {
        "ok": True,
        "found": True,
        "order": order_number,
        "reserve_in_transit": bool(row.get("reserve_in_transit")),
        "source": row.get("source") or "1c_overrides.json",
        "override": True,
    }


def resolve_reserve_in_transit(order_number: str) -> dict[str, Any]:
    api = check_reserve_in_transit(order_number)
    if api.get("ok") and api.get("found"):
        return api
    ov = override_check(order_number)
    if ov:
        if api.get("skipped"):
            ov["api_reason"] = api.get("reason")
        return ov
    return api


def format_onec_line(check: dict[str, Any] | None, *, screenshot_hint: str = "") -> str:
    """Строка в скрытый комментарий — только при реальной проверке галки. Skip/нет заказа — молчим."""
    if screenshot_hint:
        return screenshot_hint
    if not check:
        return ""
    if check.get("skipped"):
        return ""
    src = f" ({check['source']})" if check.get("source") else ""
    if check.get("reserve_in_transit") is True:
        return (
            f"1С: заказ {check.get('order')} — галка «Резервировать товары в пути» стоит"
            f"{src} → в ЛК подтверждать не требуется (уже зарезервировано)"
        )
    if check.get("reserve_in_transit") is False:
        return f"1С: заказ {check.get('order')} — галка «Резервировать товары в пути» снята{src}"
    if check.get("found") is False:
        return f"1С: заказ {check.get('order')} не найден"
    return ""
