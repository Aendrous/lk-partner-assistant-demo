# -*- coding: utf-8 -*-
"""Чтение артефакта _analysis_*.json для UI и отладки."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import debug_artifacts

HERE = Path(__file__).resolve().parent
PKG = HERE.parent


def load_analysis(task_id: str | int) -> dict[str, Any] | None:
    # Сначала ищем в новой папке debug/, затем в корне (legacy), потом в pipeline/runs/
    path = debug_artifacts.find_analysis(task_id)
    if path is None or not path.is_file():
        run_dir = PKG / "pipeline" / "runs"
        if run_dir.is_dir():
            for d in sorted(run_dir.iterdir(), reverse=True):
                if not d.name.startswith(f"{task_id}_"):
                    continue
                alt = d / "analysis.json"
                if alt.is_file():
                    path = alt
                    break
        else:
            return None
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _message_content(messages: list[dict[str, Any]], role: str) -> str:
    for m in messages:
        if str(m.get("role") or "") == role:
            return str(m.get("content") or "")
    return ""


def extract_user_prompt(analysis: dict[str, Any]) -> tuple[str, str]:
    """Текст user-промпта и метка источника (full / legacy)."""
    lr = analysis.get("llm_request") or {}
    if lr.get("user_message"):
        return str(lr["user_message"]), "llm_request.user_message"
    msgs = lr.get("messages") or []
    user = _message_content(msgs, "user")
    if user.strip():
        return user, "llm_request.messages"

    return _legacy_prompt_preview(analysis), "legacy (переразберите заявку для полного промпта)"


def extract_system_prompt(analysis: dict[str, Any]) -> tuple[str, str]:
    lr = analysis.get("llm_request") or {}
    if lr.get("system_preview"):
        return str(lr["system_preview"]), "llm_request.system_preview"
    msgs = lr.get("messages") or []
    system = _message_content(msgs, "system")
    if system.strip():
        return system, "llm_request.messages"
    return "", "нет (legacy артефакт)"


def extract_assistant_content(analysis: dict[str, Any]) -> str:
    meta = analysis.get("llm_meta") or {}
    raw = meta.get("raw") or {}
    choices = raw.get("choices") or []
    if choices:
        content = (choices[0].get("message") or {}).get("content") or ""
        if content:
            return str(content)
    return str(analysis.get("raw") or "")


def _legacy_prompt_preview(analysis: dict[str, Any]) -> str:
    """Собрать частичный вид входа для старых _analysis_*.json без llm_request."""
    lines: list[str] = [
        f"Заявка #{analysis.get('task_id')} · {analysis.get('task_name') or ''}",
    ]
    prof = analysis.get("profile") or {}
    if prof.get("model"):
        lines.append(f"Модель: {prof.get('model')} ({prof.get('key') or ''})")

    ocr = analysis.get("ocr") or {}
    items = ocr.get("items") or []
    if items:
        lines.append("\n--- Вложения (смысл IEK LLM) ---")
        for it in items:
            if not isinstance(it, dict):
                continue
            fn = it.get("filename") or "?"
            meaning = it.get("meaning_ru") or ""
            lines.append(f"• {fn}: {meaning}")
    if ocr.get("meaning"):
        lines.append(str(ocr["meaning"])[:1200])
    if ocr.get("text_preview"):
        lines.append(f"\nOCR/текст:\n{ocr['text_preview']}")

    cp = analysis.get("confluence_prefetch") or {}
    if cp.get("hits"):
        lines.append("\n--- Confluence prefetch ---")
        lines.append(f"Запрос: {cp.get('query') or ''}")
        for h in (cp.get("hits") or [])[:3]:
            if isinstance(h, dict):
                lines.append(f"• {h.get('title')} · {h.get('url')}")
                ex = (h.get("excerpt") or "")[:300]
                if ex:
                    lines.append(f"  {ex}")

    emails = analysis.get("partner_emails") or []
    if emails:
        lines.append(f"\nПартнёр email: {', '.join(str(e) for e in emails)}")
    refs = analysis.get("doc_refs") or []
    if refs:
        lines.append(f"Документы: {', '.join(str(r) for r in refs)}")

    prior = analysis.get("prior_creator") or {}
    prior_list = prior.get("prior") or []
    if prior_list:
        lines.append("\n--- Предыдущие обращения (фрагмент) ---")
        for p in prior_list[:2]:
            if isinstance(p, dict):
                lines.append(
                    f"#{p.get('Id')} {p.get('Name')}: "
                    f"{str(p.get('Description') or '')[:200]}…"
                )

    lines.append(
        "\n---\n"
        "Полный system+user промпт в этом файле не сохранён (старый артефакт).\n"
        "Запустите разбор заново: вкладка «Запуск» или "
        "`python scripts/analyze_and_comment.py <id>`."
    )
    return "\n".join(lines)
