# -*- coding: utf-8 -*-
"""IEK LLM: заявка vs статья KB → new | supplement | skip + слова для вставки."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_SERVICE_ID_FACT = re.compile(r"(?i)^\s*service\s*id\s*[=:]", re.I)
_CREATOR_MAIL_FACT = re.compile(r"(?i)^\s*(creator)?e?-?mail\s*[=:]", re.I)


def strip_emails(text: str, *, placeholder: str = "") -> str:
    """Убрать email из текста (черновик / insert — без PII)."""
    if not text:
        return ""
    out = EMAIL_RE.sub(placeholder, text)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def fact_is_redundant_or_pii(fact: str) -> bool:
    """CreatorEmail / ServiceId / голый email — не в шаблон черновика."""
    raw = (fact or "").strip()
    if not raw:
        return True
    if EMAIL_RE.search(raw):
        return True
    low = raw.lower().replace("ё", "е")
    if _CREATOR_MAIL_FACT.match(low) or low.startswith("creatormail"):
        return True
    if _SERVICE_ID_FACT.match(low) or re.match(r"(?i)^serviceid\b", low):
        return True
    if re.match(r"(?i)^партн[её]р\s*\(email\)", low):
        return True
    return False


def sanitize_facts(facts: list[Any] | None, *, limit: int = 6) -> list[str]:
    out: list[str] = []
    for x in facts or []:
        raw = str(x).strip()
        if not raw:
            continue
        # факт с email целиком отбрасываем (не маскируем — шаблон без PII)
        if EMAIL_RE.search(raw) or fact_is_redundant_or_pii(raw):
            continue
        s = strip_emails(raw)
        if not s or fact_is_redundant_or_pii(s):
            continue
        if re.match(r"(?i)^(creator)?e?-?mail\s*[=:]?\s*$", s):
            continue
        out.append(s[:200])
        if len(out) >= limit:
            break
    return out


def _parse_json_content(content: str) -> dict[str, Any] | None:
    raw = (content or "").strip()
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _fallback_judgment(
    *,
    task_id: str,
    mode_hint: str,
    target_title: str,
    target_page_id: str,
    target_url: str,
    resolution: str,
    matched_excerpt: str,
    summary_ru: str = "",
    category: str = "",
    facts: list[str] | None = None,
    supplement_of: str = "",
) -> dict[str, Any]:
    import kb_insert_builder

    mode = mode_hint if mode_hint in {"new", "supplement", "skip"} else "new"
    raw = strip_emails(resolution or "")[:1500]
    if kb_insert_builder.is_weak_kb_insert(raw):
        words = kb_insert_builder.build_structured_insert(
            summary=summary_ru,
            category=category,
            facts=facts,
            supplement_of=supplement_of,
            resolution=raw,
            code=f"HD#{task_id}",
        )
    else:
        words = raw
    incomplete = mode in {"new", "supplement"} and bool(words)
    if mode == "supplement":
        why = (
            "Похожая статья есть, но в ней нет полного решения из этой закрытой заявки "
            "(эвристика без LLM)."
        )
    elif mode == "new":
        why = "Подходящей статьи в KB не найдено — зафиксировать решение исполнителя (эвристика без LLM)."
    else:
        why = "Совпадение с существующим материалом — дополнение не требуется (эвристика)."
        incomplete = False
        words = ""
    return {
        "ok": True,
        "fallback": True,
        "mode": mode,
        "incomplete": incomplete,
        "target_title": target_title,
        "target_page_id": target_page_id,
        "target_url": target_url,
        "words_to_add": words,
        "why_incomplete": why,
        "source_ticket_id": str(task_id),
        "matched_excerpt_used": bool((matched_excerpt or "").strip()),
    }


def judge_kb_gap(
    *,
    task_id: str | int,
    task_name: str = "",
    summary_ru: str = "",
    resolution: str = "",
    facts: list[str] | None = None,
    matched_title: str = "",
    matched_code: str = "",
    matched_excerpt: str = "",
    mode_hint: str = "new",
    target_title: str = "",
    target_page_id: str = "",
    target_url: str = "",
    model: str = "",
    rejection_context: str = "",
) -> dict[str, Any]:
    """Сравнить контекст заявки с фрагментом статьи (или «нет статьи») → JSON-вердикт."""
    tid = str(task_id).strip()
    clean_summary = strip_emails(summary_ru or task_name or "")
    clean_resolution = strip_emails(resolution or "")
    clean_facts = sanitize_facts(facts)
    clean_excerpt = strip_emails((matched_excerpt or "")[:3500])
    article_block = (
        f"Код: {matched_code or '—'}\nЗаголовок: {matched_title or '—'}\n\n{clean_excerpt}"
        if (matched_code or matched_title or clean_excerpt)
        else "Статьи нет (no article)."
    )

    import requests

    import llm_client

    model = llm_client.resolve_model(
        model or __import__("learn_llm").learn_kb_model(),
        fallback=os.environ.get("IEK_LLM_SUPPORT_FALLBACK_MODEL") or llm_client.DEFAULT_SUPPORT_MODEL,
    )
    facts_json = json.dumps(clean_facts, ensure_ascii=False)
    prompt = (
        "Ты методист KB HelpDesk IEK. Сравни заявку со статьёй. "
        "Верни строго JSON: mode, incomplete, target_title, target_page_id, "
        "target_url, words_to_add, why_incomplete, source_ticket_id. "
        "mode=skip|supplement|new. Без email/ServiceId в words_to_add.\n\n"
        "КРИТИЧНО — не выдумывать:\n"
        "- URL, hostname, пути API (GET/POST), флаги прав в админке — только если они "
        "есть в Existing article / Resolution / Facts.\n"
        "- Не придумывать status.iek.local, /api/v2/tracking/status и подобное.\n"
        "- Если в excerpt нет техдеталей — общие шаги (инкогнито, DevTools Network/Console), "
        "без вымышленных curl.\n"
        "- Эскалация WEB: статус HelpDesk «На разработку» → задача Jira создаётся "
        "автоматически; не писать «закройте заявку» после эскалации.\n\n"
        "words_to_add — НЕ отписка заявителю («спасибо, ожидайте»). "
        "Формат markdown для исполнителя и поиска:\n"
        "**Сценарий:** … (в чём проблема, 1–2 предложения)\n"
        "**Ключевые слова:** … (через запятую)\n"
        "**Не путать с:** … (если supplement к другому коду)\n"
        "**Проверка исполнителя:** нумерованные шаги\n"
        "Опционально **Открытый ответ (шаблон):** только если есть готовая формулировка.\n\n"
        "Ticket HD#" + tid + ": " + strip_emails(task_name)[:200] + "\n"
        "Summary: " + clean_summary[:800] + "\n"
        "Facts: " + facts_json + "\n"
        "Resolution:\n" + clean_resolution[:2000] + "\n\n"
        "Mode hint: " + str(mode_hint) + "\n"
        "Contour target: " + str(target_title) + " | pageId=" + str(target_page_id)
        + " | " + str(target_url) + "\n\n"
        "Existing article / excerpt:\n" + article_block + "\n"
    )
    if (rejection_context or "").strip():
        prompt += "\n" + rejection_context.strip() + "\n"

    try:
        if not llm_client.has_credentials():
            return _fallback_judgment(
                task_id=tid,
                mode_hint=mode_hint,
                target_title=target_title,
                target_page_id=target_page_id,
                target_url=target_url,
                resolution=clean_resolution,
                matched_excerpt=clean_excerpt,
                summary_ru=clean_summary,
                category="",
                facts=clean_facts,
                supplement_of=matched_code,
            )
        resp = requests.post(
            f"{llm_client.base_url()}/chat/completions",
            headers=llm_client._headers(),
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "stream": False,
            },
            timeout=120,
            verify=False,
        )
    except Exception as exc:
        fb = _fallback_judgment(
            task_id=tid,
            mode_hint=mode_hint,
            target_title=target_title,
            target_page_id=target_page_id,
            target_url=target_url,
            resolution=clean_resolution,
            matched_excerpt=clean_excerpt,
            summary_ru=clean_summary,
            facts=clean_facts,
            supplement_of=matched_code,
        )
        fb["llm_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return fb

    if resp.status_code >= 400:
        fb = _fallback_judgment(
            task_id=tid,
            mode_hint=mode_hint,
            target_title=target_title,
            target_page_id=target_page_id,
            target_url=target_url,
            resolution=clean_resolution,
            matched_excerpt=clean_excerpt,
            summary_ru=clean_summary,
            facts=clean_facts,
            supplement_of=matched_code,
        )
        fb["llm_error"] = f"HTTP {resp.status_code}"
        return fb

    content = (
        (resp.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    ).strip()
    data = _parse_json_content(content)
    if not data:
        fb = _fallback_judgment(
            task_id=tid,
            mode_hint=mode_hint,
            target_title=target_title,
            target_page_id=target_page_id,
            target_url=target_url,
            resolution=clean_resolution,
            matched_excerpt=clean_excerpt,
            summary_ru=clean_summary,
            facts=clean_facts,
            supplement_of=matched_code,
        )
        fb["llm_error"] = "не JSON"
        fb["raw"] = content[:500]
        return fb

    mode = str(data.get("mode") or mode_hint or "new").strip().lower()
    if mode not in {"new", "supplement", "skip"}:
        mode = mode_hint if mode_hint in {"new", "supplement", "skip"} else "new"
    words = strip_emails(str(data.get("words_to_add") or "").strip())
    # убрать строки с ServiceId если LLM всё же вставил
    words_lines = [
        ln
        for ln in words.splitlines()
        if not fact_is_redundant_or_pii(ln) and not _SERVICE_ID_FACT.search(ln)
    ]
    words = "\n".join(words_lines).strip()
    import kb_insert_builder

    if kb_insert_builder.is_weak_kb_insert(words):
        words = kb_insert_builder.build_structured_insert(
            summary=clean_summary,
            category="",
            facts=clean_facts,
            supplement_of=matched_code,
            resolution=words,
            code=f"HD#{tid}",
        )
    why = strip_emails(str(data.get("why_incomplete") or "").strip())[:600]
    incomplete = data.get("incomplete")
    if incomplete is None:
        incomplete = mode in {"new", "supplement"} and bool(words)

    return {
        "ok": True,
        "fallback": False,
        "mode": mode,
        "incomplete": bool(incomplete),
        "target_title": str(data.get("target_title") or target_title or "").strip()[:200],
        "target_page_id": str(data.get("target_page_id") or target_page_id or "").strip(),
        "target_url": str(data.get("target_url") or target_url or "").strip(),
        "words_to_add": words[:2500],
        "why_incomplete": why or "Статья не покрывает решение из заявки.",
        "source_ticket_id": str(data.get("source_ticket_id") or tid),
        "model": model,
    }


def format_judgment_markdown(
    gap: dict[str, Any] | None,
    *,
    helpdesk_url: str = "",
    matched_code: str = "",
) -> str:
    """Блок «Решение IEK LLM» для верха черновика."""
    g = gap or {}
    tid = str(g.get("source_ticket_id") or "")
    mode = str(g.get("mode") or "new")
    if mode == "skip":
        verdict = "skip — статья достаточна"
    elif mode == "supplement" or g.get("incomplete"):
        verdict = "статья неполная — нужно дополнение"
    else:
        verdict = "новой статьи нет — создать блок"
    url = (helpdesk_url or "").strip()
    src = f"HD#{tid}"
    if url:
        src = f"{src} · [{url}]({url})"
    target_bits = [
        str(g.get("target_title") or "—"),
    ]
    if g.get("target_url"):
        target_bits.append(f"[{g['target_url']}]({g['target_url']})")
    if g.get("target_page_id"):
        target_bits.append(f"pageId={g['target_page_id']}")
    if matched_code:
        target_bits.append(f"блок `{matched_code}`")
    words = str(g.get("words_to_add") or "").strip()
    lines = [
        "## Решение IEK LLM (ревью)",
        "",
        f"- **Источник:** {src}",
        f"- **Вердикт:** {verdict}",
        f"- **Целевая статья:** {' · '.join(target_bits)}",
        f"- **Почему:** {g.get('why_incomplete') or '—'}",
        "",
        "- **Слова для дополнения:**",
        "",
        "<!-- KB_INSERT_START -->",
        words or "_(нет текста — LLM вернул skip/пусто)_",
        "<!-- KB_INSERT_END -->",
        "",
    ]
    if g.get("fallback"):
        lines.append("_Вердикт по эвристике (LLM недоступен или не JSON)._")
        lines.append("")
    return "\n".join(lines)
