# -*- coding: utf-8 -*-
"""Поиск пользователя в админке ЛК (Bitrix): lk.iek.ru/bitrix/admin/user_admin.php
Аутентификация (по приоритету):
  1. LK_ADMIN_COOKIE — PHPSESSID + BITRIX_SM_* из браузера
  2. LK_USER + LK_PASSWORD — вход в /bitrix/admin/ (если cookie нет или истекла)
"""
from __future__ import annotations
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
LK_BASE = os.environ.get("LK_BASE_URL", "https://lk.iek.ru").rstrip("/")
USER_ADMIN_PATH = "/bitrix/admin/user_admin.php"
USER_EDIT_PATH = "/bitrix/admin/user_edit.php"
ADMIN_INDEX = "/bitrix/admin/index.php"
PKG_ROOT = Path(__file__).resolve().parents[1]
_SESSION_CACHE: dict[str, Any] = {"ts": 0.0, "cookies": {}}
_CACHE_TTL = 900
def load_env() -> None:

    for p in (PKG_ROOT / ".env", PKG_ROOT.parent / ".env"):
        if not p.is_file():
            continue
        try:
            from dotenv import load_dotenv
            load_dotenv(p, override=False)
        except ImportError:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))
def search_user_url(email: str) -> str:

    q = (email or "").strip()
    params = {
        "PAGEN_1": "1",
        "SIZEN_1": "100",
        "lang": "ru",
        "set_filter": "Y",
        "adm_filter_applied": "0",
        "find": q,
        "find_type": "email",
    }
    return f"{LK_BASE}{USER_ADMIN_PATH}?{urlencode(params)}"
def _cookie_header() -> str:

    load_env()
    return (os.environ.get("LK_ADMIN_COOKIE") or "").strip().strip('"').strip("'")
def _login_variants(user: str) -> list[str]:

    u = (user or "").strip()
    if not u:
        return []
    variants = [u]
    for v in (f"IEK\\{u}", f"{u}@iek.ru", f"{u}@iek.local"):
        if v not in variants:
            variants.append(v)
    return variants
def _extract_sessid(html: str) -> str:

    for pat in (
        r'name="sessid"\s+value="([^"]+)"',
        r'name="bitrix_sessid"\s+value="([^"]+)"',
        r"bitrix_sessid\s*:\s*['\"]([^'\"]+)['\"]",
    ):
        m = re.search(pat, html or "", re.I)
        if m:
            return m.group(1)
    return ""
def _login_with_password() -> tuple[requests.Session | None, str]:

    """Вход LK_USER/LK_PASSWORD в Bitrix admin. Возвращает (session, error)."""
    load_env()
    user = (os.environ.get("LK_USER") or "").strip()
    pwd = (os.environ.get("LK_PASSWORD") or "").strip()
    if not user or not pwd:
        return None, "нет LK_USER/LK_PASSWORD"
    now = time.time()
    cached = _SESSION_CACHE.get("cookies") or {}
    if cached and now - float(_SESSION_CACHE.get("ts") or 0) < _CACHE_TTL:
        s = requests.Session()
        s.verify = False
        s.headers.update({"User-Agent": "IEK-IntraService-Chatbot/1.0"})
        for k, v in cached.items():
            s.cookies.set(k, v, domain="lk.iek.ru")
        probe = s.get(f"{LK_BASE}{USER_ADMIN_PATH}?lang=ru", timeout=25)
        if not _looks_like_login_page(probe.text or ""):
            return s, ""
    last_err = "не удалось войти"
    for login in _login_variants(user):
        s = requests.Session()
        s.verify = False
        s.headers.update(
            {
                "User-Agent": "IEK-IntraService-Chatbot/1.0",
                "Accept": "text/html,application/xhtml+xml",
            }
        )
        try:
            r0 = s.get(f"{LK_BASE}{ADMIN_INDEX}", timeout=30, allow_redirects=True)
        except requests.RequestException as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            continue
        sessid = _extract_sessid(r0.text or "")
        data: dict[str, str] = {
            "AUTH_FORM": "Y",
            "TYPE": "AUTH",
            "USER_LOGIN": login,
            "USER_PASSWORD": pwd,
            "Login": "Войти",
        }
        if sessid:
            data["sessid"] = sessid
        try:
            s.post(f"{LK_BASE}{ADMIN_INDEX}", data=data, timeout=30, allow_redirects=True)
            probe = s.get(f"{LK_BASE}{USER_ADMIN_PATH}?lang=ru", timeout=25)
        except requests.RequestException as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            continue
        if _looks_like_login_page(probe.text or ""):
            last_err = "неверный логин/пароль или нет прав admin"
            continue
        _SESSION_CACHE["ts"] = now
        _SESSION_CACHE["cookies"] = s.cookies.get_dict()
        return s, ""
    return None, last_err
def _session() -> tuple[requests.Session | None, str]:

    raw = _cookie_header()
    if raw:
        s = requests.Session()
        s.verify = False
        s.headers.update(
            {
                "User-Agent": "IEK-IntraService-Chatbot/1.0",
                "Accept": "text/html,application/xhtml+xml",
                "Cookie": raw,
            }
        )
        return s, ""
    return _login_with_password()
def _looks_like_login_page(html: str) -> bool:

    low = (html or "").lower()
    if "недостаточно прав" in low:
        return True
    if "login.min.css" in low and ("user_login" in low or "authorize" in low):
        return True
    if "auth_form" in low and "user_password" in low and "adm-main-wrap" not in low:
        return True
    return False
def _noise_login(login: str, email: str = "") -> bool:
    """Мусор из колонок Bitrix (группа Marketplace и т.п.), не логин пользователя."""
    v = (login or "").strip()
    if not v:
        return True
    low = v.lower()
    if email and low == email.strip().lower():
        return False
    if "@" in v:
        return False
    noise = {
        "marketplace",
        "admin",
        "administrator",
        "guest",
        "user",
        "login",
        "email",
        "активен",
        "да",
        "нет",
        "y",
        "n",
    }
    if low in noise:
        return True
    if re.fullmatch(r"\d+", v):
        return True
    return False


_DATE_RE = re.compile(
    r"\d{2}\.\d{2}\.\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?"
    r"|\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?"
)


def _clean_login_date(raw: str) -> str:
    """Оставить только дату/время; отбросить подпись «Последняя авторизация:» без значения."""
    v = re.sub(r"\s+", " ", (raw or "")).strip().strip(":").strip()
    v = re.sub(r"(?i)^последн(?:ий|ая)\s+авторизац\w*\s*:?\s*", "", v).strip()
    m = _DATE_RE.search(v)
    if m:
        return m.group(0).strip()
    if v and re.search(r"\d", v) and not re.search(r"(?i)авторизац|last_?login", v):
        return v[:40]
    return ""


def _plain_cell(html: str) -> str:
    t = re.sub(r"(?is)<[^>]+>", " ", html or "")
    t = re.sub(r"&nbsp;", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _header_columns(html: str) -> list[str]:
    """Заголовки колонок adm-list-table (для индекса «Последняя авторизация»)."""
    for pat in (
        r'(?is)<tr[^>]*class="[^"]*adm-list-table-header[^"]*"[^>]*>(.*?)</tr>',
        r'(?is)<tr[^>]*>\s*<td[^>]*class="[^"]*adm-list-table-cell-sort[^"]*"[^>]*>(.*?)</tr>',
    ):
        m = re.search(pat, html or "")
        if not m:
            continue
        cells = re.findall(r"(?is)<td[^>]*>(.*?)</td>", m.group(1))
        headers = [_plain_cell(c) for c in cells]
        if headers:
            return headers
    return []


def _last_login_col_index(headers: list[str]) -> int | None:
    for i, h in enumerate(headers):
        low = (h or "").lower().replace("ё", "е")
        if "последн" in low and "авториз" in low:
            return i
        if "last" in low and "login" in low:
            return i
        if low.strip() in {"последняя авторизация", "дата авторизации"}:
            return i
    # Bitrix RU часто: колонка рядом с login/email без явного «последн» в урезанном HTML —
    # ищем по подписи «авторизац»
    for i, h in enumerate(headers):
        if re.search(r"(?i)авторизац", h or ""):
            return i
    return None


def _parse_user_rows(html: str, email: str) -> list[dict[str, Any]]:
    """Разбор строк user_admin: email + дата последней авторизации из колонки таблицы."""
    target = (email or "").strip().lower()
    if not target or not html:
        return []
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    if re.search(r"(?i)не\s+найдено|нет\s+данных|список\s+пуст", text) and target not in text.lower():
        return []

    headers = _header_columns(text)
    login_idx = _last_login_col_index(headers)

    matches: list[dict[str, Any]] = []
    # только строки данных adm-list-table-row (не весь вложенный DOM)
    row_iter = list(
        re.finditer(
            r'(?is)<tr[^>]*class="[^"]*adm-list-table-row[^"]*"[^>]*>(.*?)</tr>',
            text,
        )
    )
    if not row_iter:
        # fallback: короткие tr с user_edit + email
        row_iter = list(
            re.finditer(
                r'(?is)<tr[^>]*>((?:(?!</tr>).){20,8000}?user_edit\.php\?[^"\']*ID=(\d+)(?:(?!</tr>).){20,8000}?)</tr>',
                text,
            )
        )

    for m in row_iter:
        row = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
        if target not in row.lower():
            continue
        uid = ""
        um = re.search(r"user_edit\.php\?[^\"']*ID=(\d+)", row, re.I)
        if um:
            uid = um.group(1)
        elif m.lastindex and m.lastindex >= 2:
            uid = m.group(2)

        cells = [_plain_cell(c) for c in re.findall(r"(?is)<td[^>]*>(.*?)</td>", row)]
        login = target
        for c in cells:
            if c.lower() == target:
                login = c
                break
            if "@" in c and not _noise_login(c, target):
                login = c
                break

        last_login = ""
        if login_idx is not None and login_idx < len(cells):
            last_login = _clean_login_date(cells[login_idx])
        if not last_login:
            # эвристика: даты в строке; после login/email обычно LAST_LOGIN, затем ID, DATE_REGISTER
            dates = [_clean_login_date(c) for c in cells if _DATE_RE.search(c or "")]
            dates = [d for d in dates if d]
            if len(dates) >= 2:
                # типичный порядок: … activity?, last_login, register → берём предпоследнюю или max
                # user сказал: 26.08.2026 12:44:05 в ячейке — это last login (новее register)
                last_login = max(dates)  # dd.mm.yyyy сравнимо лексикографически? NO
                # парсим как datetime-like string DD.MM.YYYY
                def _key(d: str) -> str:
                    m2 = re.match(r"(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?", d)
                    if not m2:
                        return d
                    return f"{m2.group(3)}{m2.group(2)}{m2.group(1)}{m2.group(4) or '00'}{m2.group(5) or '00'}"

                last_login = max(dates, key=_key)
            elif len(dates) == 1:
                last_login = dates[0]

        item: dict[str, Any] = {
            "id": uid or None,
            "login": login,
            "email": target,
        }
        if last_login:
            item["last_login"] = last_login
            item["never_logged_in"] = False
        else:
            item["never_logged_in"] = True
        matches.append(item)

    if matches:
        return matches
    id_m = re.search(rf"(?i){re.escape(target)}.*?user_edit\.php\?[^\"']*ID=(\d+)", text)
    if id_m:
        return [{"id": id_m.group(1), "email": target, "login": target, "name": ""}]
    if target in text.lower() and "user_admin" in text.lower():
        occurrences = len(re.findall(re.escape(target), text.lower()))
        if occurrences >= 2:
            return [{"email": target, "id": None, "login": target, "name": "", "weak": True}]
    return []


def _fetch_user_edit(sess: requests.Session, user_id: str) -> dict[str, Any]:
    """Логин, email, дата последнего входа из user_edit."""
    uid = (user_id or "").strip()
    if not uid or not uid.isdigit():
        return {}
    url = f"{LK_BASE}{USER_EDIT_PATH}?lang=ru&ID={uid}"
    try:
        resp = sess.get(url, timeout=35)
    except requests.RequestException:
        return {}
    html = resp.text or ""
    if _looks_like_login_page(html):
        return {}
    out: dict[str, Any] = {"edit_url": url}
    m = re.search(r'(?i)name="LOGIN"[^>]*value="([^"]*)"', html)
    if m and m.group(1).strip():
        out["login"] = m.group(1).strip()
    m = re.search(r'(?i)name="EMAIL"[^>]*value="([^"]*)"', html)
    if m and m.group(1).strip():
        out["email"] = m.group(1).strip().lower()
    last = ""
    m = re.search(r'(?i)name="LAST_LOGIN"[^>]*value="([^"]*)"', html)
    if m:
        last = _clean_login_date(m.group(1))
    if not last:
        m = re.search(
            r"(?is)Последн(?:ий|ая)\s+авторизац\w*.{0,120}?(" + _DATE_RE.pattern + ")",
            html,
        )
        if m:
            last = _clean_login_date(m.group(1))
    if last:
        out["last_login"] = last
    m = re.search(r'(?i)name="DATE_REGISTER"[^>]*value="([^"]*)"', html)
    if m and _clean_login_date(m.group(1)):
        out["registered"] = _clean_login_date(m.group(1))
    if re.search(r'(?i)name="ACTIVE"[^>]*checked', html):
        out["active"] = "Y"
    out["never_logged_in"] = not bool(out.get("last_login"))
    return out


def search_user(email: str) -> dict[str, Any]:
    """Поиск пользователя ЛК по email."""
    q = (email or "").strip()
    url = search_user_url(q)
    if not q or "@" not in q:
        return {"ok": False, "skipped": True, "reason": "пустой email", "url": url, "found": None}
    sess, auth_err = _session()
    if sess is None:
        reason = auth_err or "нет LK_ADMIN_COOKIE и LK_USER/LK_PASSWORD"
        return {
            "ok": False,
            "skipped": True,
            "reason": reason,
            "url": url,
            "found": None,
            "login_required": True,
        }
    try:
        resp = sess.get(url, timeout=45)
    except requests.RequestException as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "url": url,
            "found": None,
        }
    html = resp.text or ""
    if resp.status_code >= 400:
        return {
            "ok": False,
            "error": f"HTTP {resp.status_code}",
            "url": url,
            "found": None,
        }
    if _looks_like_login_page(html):
        _SESSION_CACHE["ts"] = 0
        return {
            "ok": False,
            "login_required": True,
            "reason": "сессия ЛК истекла — обновить LK_ADMIN_COOKIE или LK_USER/LK_PASSWORD",
            "url": url,
            "found": None,
        }
    matches = _parse_user_rows(html, q)
    for m in matches:
        uid = str(m.get("id") or "")
        if uid.isdigit():
            detail = _fetch_user_edit(sess, uid)
            if not detail:
                continue
            # login/email из карточки; last_login из списка приоритетнее пустого из edit
            if detail.get("login"):
                m["login"] = detail["login"]
            if detail.get("email"):
                m["email"] = detail["email"]
            for k, v in detail.items():
                if k in {"login", "email"}:
                    continue
                if k == "last_login" and m.get("last_login") and not v:
                    continue
                if k == "never_logged_in" and m.get("last_login") and v:
                    continue
                m[k] = v
            if m.get("last_login"):
                m["never_logged_in"] = False
    return {
        "ok": True,
        "found": bool(matches),
        "matches": matches,
        "url": url,
        "email": q.lower(),
        "http": resp.status_code,
    }


def format_lk_line(lk: dict[str, Any] | None) -> str:
    if not lk:
        return ""
    reason_l = str(lk.get("reason") or "").lower()
    # пропуск не по доступу — не засоряем разбор
    if lk.get("skipped") and any(
        x in reason_l for x in ("не контур", "не сценарий", "не нуж", "пропуск")
    ):
        return ""
    url = lk.get("url") or search_user_url(str(lk.get("email") or lk.get("query") or ""))
    if lk.get("skipped"):
        return f"lk-admin: пропущено ({lk.get('reason')})"
    if lk.get("login_required") or (not lk.get("ok") and lk.get("found") is None and not lk.get("error")):
        return (
            f"lk-admin: нет доступа "
            f"({lk.get('reason') or 'нужен LK_ADMIN_COOKIE или LK_USER/LK_PASSWORD'}) · {url}"
        )
    if lk.get("error"):
        return f"lk-admin: ошибка {lk.get('error')} · {url}"
    if lk.get("found") is True:
        m = (lk.get("matches") or [{}])[0]
        email = (m.get("email") or lk.get("email") or "").strip().lower()
        login = (m.get("login") or "").strip()
        bits = ["найден"]
        # учётка = email партнёра; login только если осмысленный и отличается
        if email:
            bits.append(f"учётка {email}")
        if login and not _noise_login(login, email) and login.lower() != email:
            bits.append(f"login={login}")
        last = _clean_login_date(str(m.get("last_login") or ""))
        if last:
            bits.append(f"вход={last}")
        elif m.get("never_logged_in"):
            bits.append("вход: не заходил -> IEK ID forgot-password")
        else:
            bits.append("вход: дата не определена")
        if m.get("weak"):
            bits.append("нужна ручная сверка")
        return f"lk-admin: {' · '.join(bits)} · {url}"
    if lk.get("found") is False:
        return f"lk-admin: не найден · {url}"
    return f"lk-admin: проверить вручную · {url}"
