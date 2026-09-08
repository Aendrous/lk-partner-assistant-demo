# -*- coding: utf-8 -*-
"""Минимальный клиент Confluence REST (Server/DC) для AI-KB."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import requests
import urllib3

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parent

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_env() -> None:
    for p in (PKG / ".env", REPO / ".env"):
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


def session() -> requests.Session:
    load_env()
    base = (os.environ.get("CONFLUENCE_BASE_URL") or "").rstrip("/")
    pat = (os.environ.get("CONFLUENCE_PAT") or "").strip()
    if not base or not pat:
        raise RuntimeError("Задайте CONFLUENCE_BASE_URL и CONFLUENCE_PAT")
    s = requests.Session()
    s.verify = False
    s.headers.update(
        {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )
    s.base = base  # type: ignore[attr-defined]
    return s


def view_url(s: requests.Session, page_id: str | int) -> str:
    return f"{s.base}/pages/viewpage.action?pageId={page_id}"  # type: ignore[attr-defined]


def _cql_space(space: str) -> str:
    """CQL space clause — ключи вроде 1C нужно в кавычках."""
    sp = (space or "").strip()
    if not sp:
        return ""
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", sp):
        return f"space = {sp}"
    safe = sp.replace("\\", "\\\\").replace('"', '\\"')
    return f'space = "{safe}"'


def find_page_by_title(
    s: requests.Session, *, space: str, title: str, parent_id: str | None = None
) -> dict[str, Any] | None:
    safe = title.replace('"', '\\"')
    cql = f'{_cql_space(space)} AND type = page AND title = "{safe}"'
    if parent_id:
        cql += f" AND parent = {parent_id}"
    resp = s.get(
        f"{s.base}/rest/api/content/search",  # type: ignore[attr-defined]
        params={"cql": cql, "limit": 5},
        timeout=45,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    return results[0] if results else None


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _plain_excerpt(html_or_text: str, *, max_len: int = 280) -> str:
    t = _TAG_RE.sub(" ", html_or_text or "")
    t = (
        t.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    t = _WS_RE.sub(" ", t).strip()
    if len(t) > max_len:
        t = t[: max_len - 1].rstrip() + "…"
    return t


def search_pages(
    query: str,
    *,
    spaces: list[str] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """CQL text search → title, url, короткая формулировка для ответа."""
    q = (query or "").strip()
    if not q:
        return {"ok": True, "hits": [], "reason": "пустой запрос"}
    try:
        s = session()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "hits": []}
    spaces = spaces or ["WEBKB"]
    # экранируем кавычки в CQL
    safe = q.replace("\\", "\\\\").replace('"', '\\"')[:120]
    space_clause = " OR ".join(_cql_space(sp) for sp in spaces if sp)
    cql = f"type = page AND ({space_clause}) AND text ~ \"{safe}\""
    try:
        resp = s.get(
            f"{s.base}/rest/api/content/search",  # type: ignore[attr-defined]
            params={
                "cql": cql,
                "limit": int(limit),
                "expand": "body.view,metadata.labels",
            },
            timeout=45,
        )
        if not resp.ok:
            return {
                "ok": False,
                "error": f"HTTP {resp.status_code}",
                "hits": [],
                "cql": cql,
            }
        results = resp.json().get("results") or []
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "hits": [], "cql": cql}

    hits: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "")
        title = str(item.get("title") or "").strip()
        body = ((item.get("body") or {}).get("view") or {}).get("value") or ""
        excerpt = _plain_excerpt(body, max_len=280)
        if not excerpt:
            excerpt = title
        url = view_url(s, pid) if pid else ""
        hits.append(
            {
                "id": pid,
                "title": title,
                "url": url,
                "excerpt": excerpt,
            }
        )
    return {"ok": True, "query": q, "cql": cql, "hits": hits}


def format_kb_hint_lines(
    hits: list[dict[str, Any]],
    *,
    paste_text: str = "",
) -> list[str]:
    """Строки скрытого разбора: ссылка + формулировка для открытого комментария."""
    if not hits and not (paste_text or "").strip():
        return []
    lines = ["Confluence (для открытого ответа):"]
    paste = (paste_text or "").strip()
    if paste:
        lines.append(f"Текст: «{paste[:420]}»")
    for h in hits[:3]:
        title = (h.get("title") or "статья").strip()
        url = (h.get("url") or "").strip()
        lines.append(f"• {title} · {url}" if url else f"• {title}")
        if not paste:
            ex = (h.get("excerpt") or "").strip()
            if ex and ex != title:
                lines.append(f"  Текст: «{ex[:320]}»")
    return lines


def search_for_ticket(
    *,
    name: str = "",
    summary: str = "",
    facts: list[str] | None = None,
    spaces: list[str] | None = None,
) -> dict[str, Any]:
    """Подбор запроса из темы/саммари заявки и поиск в Confluence."""
    parts: list[str] = []
    for blob in (name, summary):
        words = [w for w in re.findall(r"[A-Za-zА-Яа-яЁё0-9]{4,}", blob or "") if len(w) >= 4]
        parts.extend(words[:4])
    for f in facts or []:
        parts.extend(re.findall(r"[A-Za-zА-Яа-яЁё0-9]{5,}", str(f))[:2])
    # уникальные, порядок сохранения
    seen: set[str] = set()
    tokens: list[str] = []
    for w in parts:
        key = w.lower().replace("ё", "е")
        if key in seen:
            continue
        seen.add(key)
        tokens.append(w)
    query = " ".join(tokens[:5]).strip()
    if len(query) < 6:
        query = (name or summary or "").strip()[:80]
    return search_pages(query, spaces=spaces or ["WEBKB"], limit=4)


def get_page(s: requests.Session, page_id: str, *, expand: str = "version,title,body.storage") -> dict[str, Any]:
    resp = s.get(
        f"{s.base}/rest/api/content/{page_id}",  # type: ignore[attr-defined]
        params={"expand": expand},
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json()


def create_page(
    s: requests.Session,
    *,
    space: str,
    title: str,
    parent_id: str,
    storage: str,
    message: str = "create",
) -> dict[str, Any]:
    payload = {
        "type": "page",
        "title": title,
        "space": {"key": space},
        "ancestors": [{"id": str(parent_id)}],
        "body": {"storage": {"value": storage, "representation": "storage"}},
    }
    resp = s.post(f"{s.base}/rest/api/content", json=payload, timeout=90)  # type: ignore[attr-defined]
    if resp.status_code >= 400:
        raise RuntimeError(f"Confluence create HTTP {resp.status_code}: {resp.text[:800]}")
    _ = message
    return resp.json()


def update_page(
    s: requests.Session,
    page_id: str,
    *,
    title: str,
    storage: str,
    message: str = "update",
) -> dict[str, Any]:
    meta = get_page(s, page_id, expand="version,title")
    version = int((meta.get("version") or {}).get("number") or 1)
    payload = {
        "id": str(page_id),
        "type": "page",
        "title": title,
        "version": {"number": version + 1, "message": message[:200]},
        "body": {"storage": {"value": storage, "representation": "storage"}},
    }
    resp = s.put(f"{s.base}/rest/api/content/{page_id}", json=payload, timeout=90)  # type: ignore[attr-defined]
    if resp.status_code >= 400:
        raise RuntimeError(f"Confluence update HTTP {resp.status_code}: {resp.text[:800]}")
    return resp.json()


def create_or_update_child(
    s: requests.Session,
    *,
    space: str,
    title: str,
    parent_id: str,
    storage: str,
    message: str = "AI-KB",
) -> dict[str, Any]:
    existing = find_page_by_title(s, space=space, title=title, parent_id=str(parent_id))
    if existing:
        return update_page(
            s, str(existing["id"]), title=title, storage=storage, message=message
        )
    return create_page(
        s, space=space, title=title, parent_id=str(parent_id), storage=storage, message=message
    )


def remove_label(s: requests.Session, page_id: str, label: str) -> None:
    name = (label or "").strip()
    if not name:
        return
    resp = s.delete(
        f"{s.base}/rest/api/content/{page_id}/label/{name}",  # type: ignore[attr-defined]
        timeout=30,
    )
    if resp.status_code >= 400 and resp.status_code not in {404, 400}:
        raise RuntimeError(f"Confluence remove label HTTP {resp.status_code}: {resp.text[:400]}")


def add_labels(s: requests.Session, page_id: str, labels: list[str]) -> None:
    if not labels:
        return
    payload = [{"prefix": "global", "name": name} for name in labels]
    resp = s.post(
        f"{s.base}/rest/api/content/{page_id}/label",  # type: ignore[attr-defined]
        json=payload,
        timeout=30,
    )
    # 400 если метка уже есть — не фатально
    if resp.status_code >= 400 and resp.status_code != 400:
        raise RuntimeError(f"Confluence labels HTTP {resp.status_code}: {resp.text[:400]}")


def _inline_md(text: str) -> str:
    """Экранирование + inline markdown: ссылки, **жирный**, *курсив*, `код`."""
    t = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2">\1</a>',
        t,
    )
    codes: list[str] = []

    def _stash_code(m: re.Match[str]) -> str:
        codes.append(m.group(1))
        return f"\x00CODE{len(codes) - 1}\x00"

    t = re.sub(r"`([^`]+)`", _stash_code, t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    for i, inner in enumerate(codes):
        t = t.replace(f"\x00CODE{i}\x00", f"<code>{inner}</code>")
    return t


def _is_table_line(line: str) -> bool:
    s = line.strip()
    return len(s) >= 2 and s.startswith("|") and s.endswith("|")


def _split_table_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_table_separator(line: str) -> bool:
    cells = _split_table_cells(line)
    if not cells:
        return False
    return all(re.fullmatch(r":?-{2,}:?", cell.replace(" ", "")) for cell in cells)


def _table_to_html(lines: list[str]) -> str:
    """Markdown-таблица → Confluence storage <table>."""
    if not lines:
        return ""
    header = _split_table_cells(lines[0])
    body_lines = lines[1:]
    if body_lines and _is_table_separator(body_lines[0]):
        body_lines = body_lines[1:]
    rows = [header]
    for line in body_lines:
        rows.append(_split_table_cells(line))
    parts = ['<table class="wrapped"><tbody>']
    parts.append(
        "<tr>" + "".join(f"<th>{_inline_md(c)}</th>" for c in rows[0]) + "</tr>"
    )
    for row in rows[1:]:
        # выровнять число колонок с заголовком
        while len(row) < len(header):
            row.append("")
        parts.append(
            "<tr>"
            + "".join(f"<td>{_inline_md(c)}</td>" for c in row[: len(header)])
            + "</tr>"
        )
    parts.append("</tbody></table>")
    return "\n".join(parts)


def markdown_to_storage(md: str) -> str:
    """Конвертация markdown черновика в Confluence storage (заголовки, списки, inline)."""
    lines = md.replace("\r\n", "\n").split("\n")
    html: list[str] = []
    in_code = False
    in_ul = False
    in_ol = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            html.append("</ul>")
            in_ul = False

    def close_ol() -> None:
        nonlocal in_ol
        if in_ol:
            html.append("</ol>")
            in_ol = False

    def close_lists() -> None:
        close_ul()
        close_ol()

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            close_lists()
            in_code = not in_code
            if in_code:
                html.append(
                    '<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA['
                )
            else:
                html.append("]]></ac:plain-text-body></ac:structured-macro>")
            i += 1
            continue
        if in_code:
            html.append(line)
            i += 1
            continue
        if _is_table_line(line):
            close_lists()
            table_lines = [line]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if _is_table_line(nxt):
                    table_lines.append(nxt)
                    j += 1
                    continue
                if not nxt.strip():
                    # пустые строки между рядами MD-таблицы (часто после экспорта)
                    k = j + 1
                    while k < len(lines) and not lines[k].strip():
                        k += 1
                    if k < len(lines) and _is_table_line(lines[k]):
                        j = k
                        continue
                break
            i = j
            html.append(_table_to_html(table_lines))
            continue
        if line.startswith("# "):
            close_lists()
            html.append(f"<h2>{_inline_md(line[2:].strip())}</h2>")
        elif line.startswith("## "):
            close_lists()
            html.append(f"<h3>{_inline_md(line[3:].strip())}</h3>")
        elif line.startswith("### "):
            close_lists()
            html.append(f"<h4>{_inline_md(line[4:].strip())}</h4>")
        elif line.startswith("> "):
            close_lists()
            html.append(f"<blockquote><p>{_inline_md(line[2:].strip())}</p></blockquote>")
        elif re.fullmatch(r"-{3,}", line.strip()):
            close_lists()
            html.append("<hr />")
        elif line.startswith("- ") or line.startswith("* "):
            close_ol()
            if not in_ul:
                html.append("<ul>")
                in_ul = True
            html.append(f"<li>{_inline_md(line[2:].strip())}</li>")
        elif re.match(r"^\d+\.\s", line):
            close_ul()
            if not in_ol:
                html.append("<ol>")
                in_ol = True
            m = re.match(r"^\d+\.\s+(.*)", line)
            html.append(f"<li>{_inline_md((m.group(1) if m else line).strip())}</li>")
        elif line.strip():
            close_lists()
            html.append(f"<p>{_inline_md(line.strip())}</p>")
        else:
            close_lists()
        i += 1
    close_lists()
    return "\n".join(html)


def review_banner(*, code: str, task_id: str, helpdesk_url: str = "", supplement_of: str = "") -> str:
    hd = helpdesk_url or f"https://helpdesk.iek.local/Task/View/{task_id}"
    kind = f"Дополнение к {supplement_of}" if supplement_of else "Черновик на ревью"
    return (
        '<ac:structured-macro ac:name="info"><ac:rich-text-body>'
        f"<p><strong>AI-KB · {kind}</strong> ({code}). Править здесь; в ответы пользователям "
        "не копировать, пока не сделан Promote в «Быстрые ответы».</p>"
        f'<p>Заявка: <a href="{hd}">#{task_id}</a>. '
        f"Promote: <code>python scripts/sync_kb_after_review.py --task-id {task_id}</code></p>"
        "</ac:rich-text-body></ac:structured-macro>"
    )
