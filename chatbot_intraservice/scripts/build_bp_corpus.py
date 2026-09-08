# -*- coding: utf-8 -*-
"""Fetch BP training materials: Confluence pages + closed IntraService tasks (sanitized)."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests
import urllib3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

import intraservice  # noqa: E402
from gigachat_client import load_env  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Known WEBKB pages for BP
BP_PAGES = (
    "124629661",  # Быстрые ответы WEB: Бизнес-платформа
    "124629493",  # Шаблоны ответов WEB: ЛК, уведомления, email и API БП
    "6096003",  # Заявка на регистрацию-защиту (if relevant)
)

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"\b(?:\+?7|8)?[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b")
INN_RE = re.compile(r"\b\d{10}(?:\d{2})?\b")


def sanitize(text: str) -> str:
    t = text or ""
    t = EMAIL_RE.sub("[email]", t)
    t = PHONE_RE.sub("[phone]", t)
    # keep short INN pattern but mask
    t = INN_RE.sub("[inn]", t)
    # drop external mail banner
    lines = []
    for line in t.replace("\r\n", "\n").split("\n"):
        low = line.lower()
        if "внешнее сообщение" in low or "шифрования данных" in low:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def confluence_session() -> requests.Session | None:
    load_env(ROOT / ".env")
    load_env(REPO / ".env")
    base = (os.environ.get("CONFLUENCE_BASE_URL") or "").rstrip("/")
    pat = (os.environ.get("CONFLUENCE_PAT") or "").strip()
    if not base or not pat:
        return None
    s = requests.Session()
    s.verify = False
    s.headers.update({"Authorization": f"Bearer {pat}", "Accept": "application/json"})
    s.base = base  # type: ignore[attr-defined]
    return s


def fetch_page(session: requests.Session, page_id: str) -> dict:
    resp = session.get(
        f"{session.base}/rest/api/content/{page_id}",  # type: ignore[attr-defined]
        params={"expand": "body.storage,space,version"},
        timeout=45,
    )
    resp.raise_for_status()
    data = resp.json()
    body = ((data.get("body") or {}).get("storage") or {}).get("value") or ""
    # strip tags lightly
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", text).strip()
    return {
        "id": page_id,
        "title": data.get("title"),
        "url": f"{session.base}/pages/viewpage.action?pageId={page_id}",  # type: ignore[attr-defined]
        "text": text[:12000],
    }


def fetch_closed_bp_tasks(limit: int = 40) -> list[dict]:
    data = intraservice._request(
        "GET",
        "/task?ServiceIds=833&StatusIds=28,29&pagesize="
        f"{limit}&fields=Id,Name,StatusId,ServiceId,Description,Changed"
        "&include=status&sort=Changed desc",
    )
    out = []
    for item in data.get("Tasks") or []:
        desc = sanitize(item.get("Description") or "")
        name = sanitize(item.get("Name") or "")
        if not name:
            continue
        out.append(
            {
                "Id": item.get("Id"),
                "Name": name,
                "StatusId": item.get("StatusId"),
                "Changed": item.get("Changed"),
                "Description": desc[:2500],
                "url": intraservice.task_url(item.get("Id")),
            }
        )
    return out


def build_corpus() -> Path:
    dest_dir = ROOT / "knowledge" / "bp"
    dest_dir.mkdir(parents=True, exist_ok=True)
    parts: list[str] = [
        "# Корпус ассистента разбора заявок БП (bp.iek.ru)\n",
        "Обезличено. Источники: WEBKB Confluence + закрытые заявки ServiceId=833.\n",
        "\n## Операционная проверка регистрации в adm\n",
        "Если в заявке есть email/телефон клиента — проверить в админке БП:\n",
        "`https://adm.bp.iek.ru/main?search=<email>&page=1&pageSize=16`\n",
        "Цель: понять, создалась ли учётка / незавершённая регистрация, до ответа клиенту.\n",
        "Добавить результат в скрытый комментарий одной строкой: `adm: найден / не найден / ошибка доступа`.\n",
    ]

    session = confluence_session()
    pages_meta = []
    if session:
        for pid in BP_PAGES:
            try:
                page = fetch_page(session, pid)
                pages_meta.append({"id": page["id"], "title": page["title"], "url": page["url"]})
                parts.append(f"\n---\n# Confluence: {page['title']}\nURL: {page['url']}\n\n{page['text']}\n")
            except Exception as err:
                parts.append(f"\n<!-- page {pid} error: {err} -->\n")
    else:
        parts.append("\n<!-- Confluence PAT missing — pages skipped -->\n")

    tasks = fetch_closed_bp_tasks(50)
    parts.append("\n---\n# Ранее закрытые заявки БП (обезличенные примеры)\n")
    for t in tasks:
        parts.append(
            f"\n### Заявка {t['Id']}: {t['Name']}\n"
            f"StatusId={t['StatusId']} Changed={t.get('Changed')}\n"
            f"{t['Description']}\n"
        )

    corpus_path = dest_dir / "corpus.md"
    corpus_path.write_text("".join(parts), encoding="utf-8")
    meta = {
        "pages": pages_meta,
        "closed_tasks": len(tasks),
        "corpus": str(corpus_path.relative_to(ROOT)),
        "adm_check_template": "https://adm.bp.iek.ru/main?search={email}&page=1&pageSize=16",
    }
    (dest_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("corpus_chars", corpus_path.stat().st_size, "tasks", len(tasks), "pages", len(pages_meta))
    return corpus_path


def probe_adm(email: str) -> dict:
    """Best-effort check: corporate SSO cookie may be required."""
    url = f"https://adm.bp.iek.ru/main?search={requests.utils.quote(email)}&page=1&pageSize=16"
    try:
        resp = requests.get(url, timeout=30, verify=False, allow_redirects=True)
    except Exception as err:
        return {"ok": False, "url": url, "error": str(err)[:300]}
    text = resp.text or ""
    low = text.lower()
    loginish = "login" in low or "войти" in low or "auth" in resp.url.lower()
    # crude signals
    found = None
    if email.lower() in low:
        found = True
    elif "ничего не найдено" in low or "no data" in low or "не найдено" in low:
        found = False
    return {
        "ok": resp.status_code < 400 and not loginish,
        "http": resp.status_code,
        "url": url,
        "final_url": resp.url,
        "login_required": loginish,
        "email_mentioned": email.lower() in low,
        "found_guess": found,
        "snippet": re.sub(r"\s+", " ", text)[:400],
    }


def main() -> int:
    load_env(ROOT / ".env")
    path = build_corpus()
    adm = probe_adm("shdi81@mail.ru")
    Path(ROOT / "knowledge" / "bp" / "adm_probe.json").write_text(
        json.dumps(adm, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("adm", json.dumps({k: adm[k] for k in adm if k != "snippet"}, ensure_ascii=False))
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
