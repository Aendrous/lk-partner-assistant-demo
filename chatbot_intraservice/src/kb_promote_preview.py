# -*- coding: utf-8 -*-
"""Превью Promote: куда и какой текст попадёт в «Быстрые ответы»."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import kb_learning

ROOT = Path(__file__).resolve().parents[1]


def _read_md(entry: dict[str, Any]) -> str:
    rel = str(entry.get("draft_path") or "").strip()
    if not rel:
        return ""
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def build_promote_plan(entry: dict[str, Any], md: str | None = None) -> dict[str, Any]:
    """План публикации для UI / dry-run."""
    body = md if md is not None else _read_md(entry)
    code = str(entry.get("code") or "HD-00")
    tid = str(entry.get("task_id") or "")
    mode = str(entry.get("mode") or "new")
    supplement_of = str(entry.get("supplement_of") or "").strip()

    m = re.search(r"\*\*Контур:\*\*\s*(\w+)", body)
    contour = (
        (m.group(1) if m else "")
        or str(entry.get("service_key") or "")
        or "other"
    ).lower()
    profile_key = str(entry.get("profile_key") or entry.get("assistant_profile") or "").strip()
    target = kb_learning.target_for_contour(contour, profile_key=profile_key)
    page_id = str(target.get("page_id") or target.get("fallback_page_id") or "")
    target_title = str(target.get("title") or "Быстрые ответы")

    insert = kb_learning.extract_insert_sections(body)
    insert_src = "kb_insert" if insert else "full_md_fallback"
    warnings: list[str] = []
    if not insert:
        warnings.append(
            "Нет блока KB_INSERT — при Promote уйдёт весь текст черновика (риск PII). "
            "Добавьте <!-- KB_INSERT_START -->…<!-- KB_INSERT_END -->."
        )
    else:
        import kb_insert_builder

        if kb_insert_builder.is_weak_kb_insert(insert):
            warnings.append(
                "Текст KB_INSERT похож на отписку заявителю, без сценария и ключевых слов. "
                "Перед Promote допишите **Сценарий:** / **Ключевые слова:** / шаги — "
                "или отклоните черновик."
            )
    if supplement_of and mode == "supplement":
        action = "append_supplement"
        action_ru = f"дополнить блок «{supplement_of}»"
    else:
        action = "append_new"
        action_ru = f"добавить новый блок «{code}»"

    review_id = str(entry.get("confluence_draft_page_id") or "")
    review_url = str(entry.get("confluence_draft_url") or "")

    return {
        "task_id": tid,
        "code": code,
        "mode": mode,
        "supplement_of": supplement_of,
        "contour": contour,
        "action": action,
        "action_ru": action_ru,
        "target_page_id": page_id,
        "target_title": target_title,
        "target_url": kb_learning.confluence_view_url(page_id),
        "insert_text": insert or "(весь черновик — см. предупреждение)",
        "insert_src": insert_src,
        "insert_chars": len(insert or body),
        "review_page_id": review_id,
        "review_url": review_url,
        "warnings": warnings,
    }


def format_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        f"**Куда:** [{plan.get('target_title')}]({plan.get('target_url')}) "
        f"(pageId `{plan.get('target_page_id')}`)",
        f"**Действие:** {plan.get('action_ru')}",
    ]
    if plan.get("supplement_of"):
        lines.append(f"**Дополняем:** `{plan.get('supplement_of')}`")
    chars = int(plan.get("insert_chars") or 0)
    lines.append(f"**Текст:** {chars} симв. — правьте в поле выше; в Confluence уйдёт только он.")
    for w in plan.get("warnings") or []:
        lines.append(f"⚠ {w}")
    return "\n".join(lines)


def format_success_message(plan: dict[str, Any], publish_url: str = "") -> str:
    code = plan.get("code") or "статья"
    target = plan.get("target_title") or "Быстрые ответы"
    action = plan.get("action_ru") or "обновлены"
    url = publish_url or plan.get("target_url") or ""
    bit = f" [{target}]({url})" if url else f" «{target}»"
    return (
        f"Инструкция **{code}** — {action} на странице{bit}. "
        f"Спасибо — чатбот IEK LLM стал умнее."
    )
