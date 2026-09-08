# -*- coding: utf-8 -*-
"""Краткая статья KB (LK-NN формат) через IEK LLM — для learn и Promote."""
from __future__ import annotations

import json
import re
from typing import Any

import kb_gap_llm
import kb_insert_builder


def _parse_json(content: str) -> dict[str, Any] | None:
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


def compose_kb_article(
    *,
    code: str,
    task_id: str,
    task_name: str = "",
    category: str = "",
    facts: list[str] | None = None,
    resolution: str = "",
    supplement_of: str = "",
    learn_lesson: str = "",
    helpdesk_url: str = "",
    model: str = "",
) -> dict[str, Any]:
    """Собрать лаконичный markdown-блок для KB_INSERT (IEK LLM → fallback builder)."""
    clean_facts = kb_gap_llm.sanitize_facts(facts or [])
    hd_url = helpdesk_url or f"https://helpdesk.iek.local/Task/View/{task_id}"
    fallback_md = kb_insert_builder.build_structured_insert(
        summary=task_name,
        category=category,
        facts=clean_facts,
        supplement_of=supplement_of,
        resolution=resolution,
        learn_lesson=learn_lesson,
        code=code,
    )
    fallback_title = f"{code}. {task_name[:80] or 'Сценарий из заявки'}"

    try:
        import llm_client
        import requests

        if not llm_client.has_credentials():
            raise RuntimeError("no LLM credentials")

        mdl = model or __import__("learn_llm").learn_kb_model()
        prompt = (
            "Ты методист KB HelpDesk IEK. Напиши КОРОТКУЮ инструкцию для «Быстрых ответов» "
            "(markdown), без email и ServiceId.\n\n"
            "Формат (лаконично, как в корпусе LK-06/LK-10):\n"
            f"## {code}. <заголовок одной строкой>\n"
            f"*Источник: HD#{task_id} · {hd_url}*\n"
            "**Ключевые слова:** …\n"
            "**Не путать с:** … (если есть)\n"
            "### Разновидность A — … (если несколько типов кейса)\n"
            "**Сценарий:** …\n"
            "1. шаг …\n"
            "### Разновидность B — … (опционально)\n"
            "**Открытый ответ:** только после проверки, без «ожидайте обновление».\n\n"
            "НЕ пиши длинный «Контекст заявки», «Урок», JSON. Только инструкция.\n"
            "НЕ копируй отписку заявителю как единственный текст.\n\n"
            f"Заявка: {kb_gap_llm.strip_emails(task_name)[:300]}\n"
            f"Категория: {category}\n"
            f"Факты: {json.dumps(clean_facts, ensure_ascii=False)}\n"
            f"Решение исполнителя (обезлич.): {kb_insert_builder.sanitize_resolution_for_kb(kb_gap_llm.strip_emails(resolution))[:1200]}\n"
            f"Дополнение к: {supplement_of or '— (новая статья)'}\n"
            f"Урок: {kb_gap_llm.strip_emails(learn_lesson)[:400]}\n"
        )
        resp = requests.post(
            f"{llm_client.base_url()}/chat/completions",
            headers=llm_client._headers(),
            json={
                "model": mdl,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.15,
                "stream": False,
            },
            timeout=120,
            verify=False,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}")
        content = (
            (resp.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
        ).strip()
        data = _parse_json(content)
        if data and data.get("markdown"):
            md = str(data["markdown"]).strip()
        elif content.startswith("##"):
            md = content
        else:
            raise RuntimeError("unexpected LLM shape")
        if kb_insert_builder.is_weak_kb_insert(md):
            raise RuntimeError("weak LLM output")
        title_m = re.search(r"^##\s+(.+)$", md, re.M)
        return {
            "ok": True,
            "markdown": md,
            "title": title_m.group(1).strip() if title_m else fallback_title,
            "model": mdl,
            "fallback": False,
        }
    except Exception as exc:
        return {
            "ok": True,
            "markdown": f"## {fallback_title}\n\n{fallback_md}",
            "title": fallback_title,
            "fallback": True,
            "error": str(exc)[:200],
        }


def markdown_to_kb_insert(md: str) -> str:
    """Вырезать тело для KB_INSERT (без дубля ## если нужен только insert)."""
    t = (md or "").strip()
    # для insert храним полный блок ## … — в корпусе так же
    return t
