# -*- coding: utf-8 -*-
"""Проверка учётки клиента в adm.bp.iek.ru (админка БП).

Сессия Keycloak (cookies kc-access, kc-state, опционально kc-refresh):
  BP_ADM_COOKIE=kc-access=...; kc-state=...; kc-refresh=...

Перед запросом access обновляется через POST /api/auth/v1/refresh
(если до exp < BP_ADM_REFRESH_SEC, по умолчанию 120 с).
Кэш: chatbot_intraservice/.bp_adm_session.json (+ синхронизация в .env).
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ADM_BASE = "https://adm.bp.iek.ru"
PROFILES_PATH = "/api/user/v1/profiles"
REFRESH_PATH = "/api/auth/v1/refresh"
PKG_ROOT = Path(__file__).resolve().parents[1]
SESSION_FILE = PKG_ROOT / ".bp_adm_session.json"
ENV_FILE = PKG_ROOT / ".env"
KC_NAMES = ("kc-access", "kc-state", "kc-refresh", "id_token")


def _refresh_sec() -> int:
    try:
        return max(30, int(os.environ.get("BP_ADM_REFRESH_SEC", "120")))
    except ValueError:
        return 120


KC_NAMES = ("kc-access", "kc-state", "kc-refresh", "id_token")


def _parse_cookie_string(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (raw or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if name:
            out[name] = value.strip()
    # только Keycloak-сессия adm; _ga/_ym/mdd из буфера не нужны
    return {k: v for k, v in out.items() if k in KC_NAMES or k.startswith("kc-")}


def _cookie_string(cookies: dict[str, str]) -> str:
    order = [n for n in KC_NAMES if n in cookies]
    order += sorted(k for k in cookies if k not in order)
    return "; ".join(f"{k}={cookies[k]}" for k in order if cookies.get(k))


def _raw_env() -> str:
    return (os.environ.get("BP_ADM_COOKIE") or "").strip().strip('"').strip("'")


def _jwt_exp(token: str) -> int | None:
    tok = (token or "").strip()
    if not tok.startswith("eyJ") or tok.count(".") < 2:
        return None
    try:
        payload = tok.split(".")[1]
        payload += "=" * ((4 - len(payload) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = data.get("exp")
        return int(exp) if isinstance(exp, (int, float)) else None
    except Exception:
        return None


def _access_exp(cookies: dict[str, str]) -> int | None:
    return _jwt_exp(cookies.get("kc-access", ""))


def _load_session_file() -> dict[str, Any]:
    if not SESSION_FILE.is_file():
        return {}
    try:
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_session(cookies: dict[str, str], *, refreshed: bool = False) -> None:
    exp = _access_exp(cookies)
    payload = {
        "cookies": cookies,
        "cookie": _cookie_string(cookies),
        "access_exp": exp,
        "updated_at": int(time.time()),
        "refreshed": refreshed,
    }
    SESSION_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _patch_env_cookie(cookie_str: str) -> None:
    if not ENV_FILE.is_file():
        return
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith("BP_ADM_COOKIE="):
            out.append(f"BP_ADM_COOKIE={cookie_str}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"BP_ADM_COOKIE={cookie_str}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def _sync_env(cookies: dict[str, str]) -> None:
    cookie_str = _cookie_string(cookies)
    os.environ["BP_ADM_COOKIE"] = cookie_str
    _save_session(cookies, refreshed=True)
    _patch_env_cookie(cookie_str)


def load_cookies() -> dict[str, str]:
    """Загрузить cookies: session-файл → BP_ADM_COOKIE."""
    session = _load_session_file()
    file_cookies = session.get("cookies")
    if isinstance(file_cookies, dict) and file_cookies.get("kc-access"):
        cookies = {str(k): str(v) for k, v in file_cookies.items()}
    else:
        raw = _raw_env()
        if raw.startswith("eyJ"):
            cookies = {"kc-access": raw}
        else:
            cookies = _parse_cookie_string(raw)
            if cookies.get("kc-access") and not cookies.get("kc-state") and "kc-access=" in raw:
                # одна пара kc-access без kc-state уже в dict
                pass
    if cookies.get("kc-access") and not cookies["kc-access"].startswith("eyJ"):
        # BP_ADM_COOKIE=kc-access=eyJ... разобрано верно
        pass
    return cookies


def _needs_refresh(cookies: dict[str, str]) -> bool:
    exp = _access_exp(cookies)
    if exp is None:
        return bool(cookies.get("kc-state"))
    return exp - int(time.time()) <= _refresh_sec()


def refresh_cookies(cookies: dict[str, str] | None = None) -> dict[str, Any]:
    """POST /api/auth/v1/refresh. Возвращает ok + обновлённые cookies."""
    current = dict(cookies or load_cookies())
    if not current.get("kc-access") and not current.get("kc-state"):
        return {
            "ok": False,
            "error": "нет kc-access/kc-state",
            "hint": "Скопируйте из браузера все cookies adm.bp (kc-access; kc-state; kc-refresh)",
        }

    session = requests.Session()
    session.verify = False
    cookie_hdr = _cookie_string(current)
    try:
        resp = session.post(
            ADM_BASE + REFRESH_PATH,
            headers={
                "Accept": "application/json",
                "User-Agent": "iek-l1-bot/1.0",
                "Cookie": cookie_hdr,
            },
            timeout=30,
        )
    except Exception as err:
        return {"ok": False, "error": str(err)[:300]}

    merged = dict(current)
    for key, value in resp.cookies.items():
        merged[key] = value
    # Set-Cookie иногда не попадает в jar — парсим вручную
    for name in KC_NAMES:
        m = re.search(rf"{re.escape(name)}=([^;]+)", resp.headers.get("Set-Cookie", "") or "")
        if m:
            merged[name] = m.group(1)

    new_exp = _access_exp(merged)
    old_exp = _access_exp(current)
    changed = merged.get("kc-access") != current.get("kc-access")
    success = resp.status_code < 400 or (changed and new_exp and (not old_exp or new_exp > old_exp))

    if success and merged.get("kc-access"):
        _sync_env(merged)
        return {
            "ok": True,
            "http": resp.status_code,
            "access_exp": new_exp,
            "ttl_sec": (new_exp - int(time.time())) if new_exp else None,
            "cookies": list(merged.keys()),
        }

    return {
        "ok": False,
        "http": resp.status_code,
        "error": (resp.text or "")[:200] or "refresh did not return new kc-access",
        "hint": (
            "Sessiya adm.bp istekla. Voydite v adm.bp.iek.ru i obnovite BP_ADM_COOKIE "
            "(kc-access + kc-state + kc-refresh iz Application -> Cookies)."
        ),
    }


def ensure_fresh_auth() -> dict[str, Any]:
    """Обновить kc-access при необходимости. Возвращает meta для диагностики."""
    cookies = load_cookies()
    if not cookies.get("kc-access") and not cookies.get("kc-state"):
        return {"ok": False, "login_required": True, "reason": "BP_ADM_COOKIE пуст"}
    exp = _access_exp(cookies)
    expired = bool(exp and exp <= int(time.time()))
    if expired or _needs_refresh(cookies):
        result = refresh_cookies(cookies)
        result["refreshed"] = bool(result.get("ok"))
        if not result.get("ok"):
            result["login_required"] = True
            if expired:
                result.setdefault(
                    "hint",
                    "kc-access протух. Скопируйте свежий Cookie из adm.bp (kc-access; kc-state; kc-refresh)",
                )
        return result
    return {
        "ok": True,
        "refreshed": False,
        "access_exp": exp,
        "ttl_sec": (exp - int(time.time())) if exp else None,
    }


def _cookie() -> str:
    return _cookie_string(load_cookies())


def _bearer() -> str:
    return load_cookies().get("kc-access", "")


def _auth_headers() -> dict[str, str]:
    ensure_fresh_auth()
    cookies = load_cookies()
    headers = {
        "Accept": "application/json",
        "User-Agent": "iek-l1-bot/1.0",
    }
    cookie_hdr = _cookie_string(cookies)
    token = cookies.get("kc-access", "")
    if cookie_hdr:
        headers["Cookie"] = cookie_hdr
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def search_user_url(query: str) -> str:
    q = (query or "").strip()
    return f"{ADM_BASE}/main?search={quote(q)}&page=1&pageSize=16"


def _summarize_profiles(data: dict[str, Any], query: str) -> dict[str, Any]:
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return {"found": None, "count": None, "matches": []}
    meta = data.get("_meta") if isinstance(data, dict) else {}
    total = meta.get("totalCount") if isinstance(meta, dict) else None
    if not isinstance(total, int):
        total = len(items)
    q = (query or "").strip().lower()
    matches: list[dict[str, Any]] = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        email = (item.get("email") or item.get("profileEmail") or "").strip()
        matches.append(
            {
                "id": item.get("id"),
                "email": email,
                "accountType": item.get("accountType"),
                "inn": item.get("inn"),
                "phone": item.get("phone"),
                "isActive": item.get("isActive"),
                "isBlocked": item.get("isBlocked"),
                "createdAt": item.get("createdAt"),
                "name": " ".join(
                    str(x)
                    for x in (item.get("lastName"), item.get("firstName"), item.get("secondName"))
                    if x
                ).strip(),
            }
        )
    if q and "@" in q:
        exact = [m for m in matches if (m.get("email") or "").lower() == q]
        if exact:
            matches = exact
            total = len(exact)
    return {"found": (total or 0) > 0, "count": total, "matches": matches}


def search_user(query: str) -> dict[str, Any]:
    """Искать клиента в adm по email/телефону/ФИО."""
    q = (query or "").strip()
    url = search_user_url(q)
    if not q:
        return {"ok": False, "error": "пустой search", "url": url}

    auth_meta = ensure_fresh_auth()
    cookies = load_cookies()
    if not cookies.get("kc-access"):
        return {
            "ok": False,
            "query": q,
            "url": url,
            "login_required": True,
            "found": None,
            "auth": auth_meta,
            "hint": auth_meta.get("hint") or "Задайте BP_ADM_COOKIE в chatbot_intraservice/.env",
        }

    headers = _auth_headers()
    try:
        resp = requests.get(
            ADM_BASE + PROFILES_PATH,
            headers=headers,
            params={"search": q, "page": 1, "pageSize": 16},
            timeout=30,
            verify=False,
        )
    except Exception as err:
        return {"ok": False, "query": q, "url": url, "error": str(err)[:300]}

    if resp.status_code in (401, 403):
        # одна попытка принудительного refresh
        refresh = refresh_cookies(cookies)
        if refresh.get("ok"):
            headers = _auth_headers()
            resp = requests.get(
                ADM_BASE + PROFILES_PATH,
                headers=headers,
                params={"search": q, "page": 1, "pageSize": 16},
                timeout=30,
                verify=False,
            )
        if resp.status_code in (401, 403):
            return {
                "ok": False,
                "query": q,
                "url": url,
                "http": resp.status_code,
                "path": PROFILES_PATH,
                "login_required": True,
                "found": None,
                "auth": refresh if refresh.get("ok") is False else auth_meta,
                "hint": refresh.get("hint") or "Обновите BP_ADM_COOKIE из браузера (adm.bp)",
            }

    if resp.status_code >= 400:
        return {
            "ok": False,
            "query": q,
            "url": url,
            "http": resp.status_code,
            "path": PROFILES_PATH,
            "error": (resp.text or "")[:300],
        }

    try:
        data = resp.json()
    except Exception:
        return {"ok": False, "query": q, "url": url, "http": resp.status_code, "error": "ответ не JSON"}

    summary = _summarize_profiles(data if isinstance(data, dict) else {}, q)
    exp = _access_exp(load_cookies())
    return {
        "ok": True,
        "query": q,
        "url": url,
        "path": PROFILES_PATH,
        "http": resp.status_code,
        "login_required": False,
        "found": summary["found"],
        "count": summary["count"],
        "matches": summary["matches"],
        "auth": {
            "refreshed": auth_meta.get("refreshed"),
            "access_exp": exp,
            "ttl_sec": (exp - int(time.time())) if exp else None,
        },
        "hint": None,
    }
