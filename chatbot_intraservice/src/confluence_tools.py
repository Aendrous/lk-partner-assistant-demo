# -*- coding: utf-8 -*-
"""MCP-совместимый слой Confluence для чатбота (REST + PAT).

Аналог инструментов OWUI `confluence_search` / `confluence_get_page` без сессии Open WebUI.
Используется prefetch перед вызовом IEK LLM в analyze_and_comment.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import confluence_client as cf

DEFAULT_SPACES = ["WEBKB"]
PKG = Path(__file__).resolve().parents[1]

# Закреплённые страницы для профиля (get_page даёт стабильный контекст)
_SEED_PAGE_IDS: dict[str, list[str]] = {
    "onec_tickets": ["124642091", "124642092"],
    "onec_logistics_tn": ["124642131", "124642091"],
    "bp_tickets": ["124629661"],
    "l1_web": ["124630014"],
}


def confluence_search(
    query: str,
    *,
    spaces: list[str] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Поиск страниц (CQL text ~), как confluence_search в OWUI."""
    out = cf.search_pages(query, spaces=spaces or DEFAULT_SPACES, limit=limit)
    return {
        "tool": "confluence_search",
        "ok": bool(out.get("ok")),
        "query": out.get("query") or query,
        "cql": out.get("cql"),
        "error": out.get("error"),
        "hits": out.get("hits") or [],
    }


def confluence_get_page(
    page_id: str | int,
    *,
    max_excerpt: int = 1500,
) -> dict[str, Any]:
    """Страница по id, как confluence_get_page в OWUI."""
    pid = str(page_id or "").strip()
    if not pid:
        return {"tool": "confluence_get_page", "ok": False, "error": "пустой page_id"}
    try:
        s = cf.session()
        page = cf.get_page(s, pid, expand="body.view,version,metadata.labels")
    except Exception as exc:
        return {
            "tool": "confluence_get_page",
            "ok": False,
            "page_id": pid,
            "error": f"{type(exc).__name__}: {exc}",
        }
    title = str(page.get("title") or "").strip()
    body = ((page.get("body") or {}).get("view") or {}).get("value") or ""
    excerpt = cf._plain_excerpt(body, max_len=max_excerpt)  # type: ignore[attr-defined]
    return {
        "tool": "confluence_get_page",
        "ok": True,
        "page_id": pid,
        "title": title,
        "url": cf.view_url(s, pid),
        "excerpt": excerpt,
        "version": (page.get("version") or {}).get("number"),
    }


def _query_from_task(task: dict[str, Any]) -> str:
    name = str(task.get("Name") or "").strip()
    desc = str(task.get("Description") or "").strip()
    narrative = str(task.get("_narrative_ru") or "").strip()
    intent = str(task.get("_ticket_intent") or "").strip()
    bits = [name, narrative, intent]
    # первое осмысленное предложение из описания (без дисклеймера внешнего письма)
    for line in re.split(r"[\r\n]+", desc):
        line = line.strip()
        if len(line) < 12:
            continue
        low = line.lower()
        if "внешнее сообщение" in low or "шифрования данных" in low:
            continue
        bits.append(line[:200])
        break
    query = " ".join(b for b in bits if b).strip()
    return query[:160]


def prefetch_for_ticket(
    task: dict[str, Any],
    *,
    profile_key: str = "",
    spaces: list[str] | None = None,
    search_limit: int = 4,
    fetch_top_page: bool = True,
) -> dict[str, Any]:
    """Prefetch: search + опционально get_page по лучшему hit — для промпта LLM."""
    try:
        import assistants

        if spaces is None and profile_key:
            spaces = assistants.prefetch_spaces_for_profile(profile_key)
    except Exception:
        pass
    use_spaces = spaces or DEFAULT_SPACES
    query = _query_from_task(task)
    if not query or len(query) < 4:
        return {"ok": False, "reason": "пустой запрос", "mode": "rest_prefetch"}

    search = confluence_search(query, spaces=use_spaces, limit=search_limit)
    seed_pages: list[dict[str, Any]] = []
    for pid in _SEED_PAGE_IDS.get((profile_key or "").strip().lower(), []):
        page = confluence_get_page(pid)
        if page.get("ok"):
            seed_pages.append(page)

    if not search.get("ok"):
        hits_from_seed = [
            {
                "id": p.get("page_id"),
                "title": p.get("title") or "",
                "url": p.get("url") or "",
                "excerpt": (p.get("excerpt") or "")[:280],
                "space": "seed",
            }
            for p in seed_pages
        ]
        if hits_from_seed:
            top_page = seed_pages[0] if seed_pages else None
            return {
                "ok": True,
                "mode": "rest_prefetch",
                "query": query,
                "spaces": use_spaces,
                "profile_key": profile_key,
                "hits": hits_from_seed,
                "top_page": top_page,
                "seed_pages": seed_pages,
                "search": search,
                "note": "CQL search failed; only seed pages",
            }
        return {
            "ok": False,
            "mode": "rest_prefetch",
            "query": query,
            "spaces": use_spaces,
            "search": search,
            "reason": search.get("error") or "search failed",
        }
    hits = list(search.get("hits") or [])
    for page in seed_pages:
        pid = str(page.get("page_id") or "")
        if pid and not any(str(h.get("id")) == pid for h in hits):
            hits.insert(
                0,
                {
                    "id": pid,
                    "title": page.get("title") or "",
                    "url": page.get("url") or "",
                    "excerpt": (page.get("excerpt") or "")[:280],
                    "space": "seed",
                },
            )

    if not hits:
        return {
            "ok": True,
            "mode": "rest_prefetch",
            "query": query,
            "spaces": use_spaces,
            "search": search,
            "hits": [],
            "reason": f"нет совпадений в {', '.join(use_spaces)}",
        }

    top_page: dict[str, Any] | None = None
    if fetch_top_page and hits[0].get("id"):
        top_page = confluence_get_page(str(hits[0]["id"]))

    return {
        "ok": True,
        "mode": "rest_prefetch",
        "query": query,
        "spaces": use_spaces,
        "profile_key": profile_key,
        "cql": search.get("cql"),
        "hits": hits,
        "top_page": top_page,
        "seed_pages": seed_pages,
    }


def format_prefetch_for_prompt(prefetch: dict[str, Any], *, max_hits: int = 3) -> str:
    """Текстовый блок для system/user промпта."""
    if not prefetch.get("ok"):
        err = prefetch.get("reason") or prefetch.get("error") or "ошибка"
        return f"Confluence prefetch: {err}"

    hits = prefetch.get("hits") or []
    spaces = prefetch.get("spaces") or DEFAULT_SPACES
    if not hits:
        return (
            f"Confluence prefetch (CQL по запросу «{prefetch.get('query', '')}»; "
            f"spaces: {', '.join(spaces)}): совпадений не найдено."
        )

    lines = [
        "CONFLUENCE PREFETCH (REST, аналог confluence_search / get_page в OWUI):",
        f"Профиль: {(prefetch.get('profile_key') or '—')} · spaces: {', '.join(spaces)}",
        f"Запрос: {prefetch.get('query', '')}",
    ]
    for h in hits[:max_hits]:
        title = (h.get("title") or "статья").strip()
        url = (h.get("url") or "").strip()
        ex = (h.get("excerpt") or "").strip()
        lines.append(f"• [{title}]({url})" if url else f"• {title}")
        if ex and ex != title:
            lines.append(f"  Фрагмент: {ex[:400]}")

    top = prefetch.get("top_page") or {}
    if top.get("ok") and top.get("excerpt"):
        long_ex = str(top.get("excerpt") or "")[:1200]
        if long_ex and long_ex not in "\n".join(lines):
            lines.append(
                f"Подробнее (get_page {top.get('page_id')}): {long_ex}"
            )
    lines.append(
        "Если сценарий совпадает — has_kb_solution=true, kb_refs и article_links с реальными URL."
    )
    return "\n".join(lines)
