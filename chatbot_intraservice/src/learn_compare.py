# -*- coding: utf-8 -*-
"""Сравнение скрытого разбора чатбота с ответом исполнителя (для самообучения)."""
from __future__ import annotations

import json
import os
import re
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_BOT_MARK = re.compile(
    r"(?i)разбор от чатбота iek llm|сервис\s*hd\s*:|сервис:\s*\d+",
)


def split_bot_and_human(lifetime: dict[str, Any] | None) -> dict[str, Any]:
    """Разделить lifetime на скрытый разбор бота и открытые ответы человека."""
    rows = (lifetime or {}).get("TaskLifetimes") or []
    bot_hidden: list[str] = []
    human_public: list[str] = []
    for row in sorted(rows, key=lambda r: str((r or {}).get("Date") or "")):
        if not isinstance(row, dict):
            continue
        text = str(row.get("Comments") or row.get("Description") or "").strip()
        if len(text) < 20:
            continue
        is_public = row.get("IsPublic") is True
        if _BOT_MARK.search(text) and not is_public:
            bot_hidden.append(text[:2500])
            continue
        if is_public is False and _BOT_MARK.search(text):
            bot_hidden.append(text[:2500])
            continue
        if is_public is False:
            continue
        # публичный ответ исполнителя (не заявитель — грубо по длине/маркерам)
        if re.search(r"(?i)^сервис\s*hd|^разбор от чатбота", text):
            continue
        human_public.append(text[:2500])
    return {
        "bot_hidden": bot_hidden[-2:],
        "human_public": human_public[-3:],
        "has_both": bool(bot_hidden) and bool(human_public),
    }


def compare_via_llm(
    *,
    task_name: str,
    bot_text: str,
    human_text: str,
    model: str = "",
    rejection_context: str = "",
) -> dict[str, Any]:
    """IEK LLM: чем ответ человека лучше/отличается → чему учить KB."""
    import llm_client

    model = (
        model
        or __import__("learn_llm").learn_kb_model()
    )
    model = llm_client.resolve_model(
        model,
        fallback=os.environ.get("IEK_LLM_SUPPORT_FALLBACK_MODEL") or llm_client.DEFAULT_SUPPORT_MODEL,
    )
    prompt = (
        "Ты методист HelpDesk IEK. Сравни скрытый разбор чатбота и итоговый открытый ответ исполнителя.\n"
        "Верни СТРОГО JSON:\n"
        "{\n"
        '  "aligned": true/false,\n'
        '  "what_bot_missed_ru": ["..."],\n'
        '  "what_bot_got_right_ru": ["..."],\n'
        '  "kb_lesson_ru": "1-3 предложения — чему добавить в KB/корпус",\n'
        '  "suggested_public_reply_ru": "улучшенный шаблон ответа на похожие заявки"\n'
        "}\n\n"
        f"Заявка: {task_name}\n\n"
        + (f"{rejection_context.strip()}\n\n" if (rejection_context or "").strip() else "")
        + f"Разбор чатбота:\n{bot_text[:2000]}\n\n"
        f"Ответ исполнителя:\n{human_text[:2000]}\n"
    )
    try:
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
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc)[:300]}
    if resp.status_code >= 400:
        return {"ok": False, "error": f"HTTP {resp.status_code}"}
    content = (
        (resp.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    ).strip()
    raw = content
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return {"ok": False, "error": "не JSON", "raw": content[:500]}
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {"ok": False, "error": "не JSON", "raw": content[:500]}
    data["ok"] = True
    data["model"] = model
    return data


def learn_compare_block(
    task: dict[str, Any],
    analysis: dict[str, Any] | None,
    lifetime: dict[str, Any] | None,
) -> dict[str, Any]:
    """Для черновика AI-KB: сравнение бот vs человек."""
    parts = split_bot_and_human(lifetime)
    bot_from_analysis = str((analysis or {}).get("comment_preview") or "").strip()
    if bot_from_analysis and not parts["bot_hidden"]:
        parts["bot_hidden"] = [bot_from_analysis]
        parts["has_both"] = bool(parts["human_public"])
    if not parts["has_both"]:
        return {
            "ok": True,
            "skipped": True,
            "reason": "нет пары «разбор бота + публичный ответ исполнителя»",
            "split": parts,
        }
    import kb_dedup
    import learn_llm

    parsed = (analysis or {}).get("parsed") or {}
    sk = str(parsed.get("service_key") or "other")
    q = kb_dedup.query_blob(task, analysis, resolution="")
    rej_ctx = learn_llm.rejection_context(
        q, service_key=sk, task_id=str(task.get("Id") or "")
    )
    cmp = compare_via_llm(
        task_name=str(task.get("Name") or task.get("Id") or ""),
        bot_text=parts["bot_hidden"][-1],
        human_text=parts["human_public"][-1],
        rejection_context=rej_ctx,
    )
    cmp["split"] = {
        "bot_preview": parts["bot_hidden"][-1][:400],
        "human_preview": parts["human_public"][-1][:400],
    }
    return cmp


def format_compare_markdown(cmp: dict[str, Any] | None) -> str:
    if not cmp or cmp.get("skipped") or not cmp.get("ok"):
        return ""
    lines = ["## Урок самообучения (бот vs исполнитель)", ""]
    if cmp.get("aligned") is True:
        lines.append("Разбор чатбота и ответ исполнителя **согласованы**.")
    elif cmp.get("aligned") is False:
        lines.append("Есть расхождения — учесть в KB.")
    for title, key in (
        ("Что бот упустил", "what_bot_missed_ru"),
        ("Что бот сделал верно", "what_bot_got_right_ru"),
    ):
        items = cmp.get(key) or []
        if not items:
            continue
        lines.append(f"**{title}:**")
        for it in items[:5]:
            lines.append(f"- {it}")
    if cmp.get("kb_lesson_ru"):
        lines.append("")
        lines.append(f"**Урок для KB:** {cmp['kb_lesson_ru']}")
    if cmp.get("suggested_public_reply_ru"):
        lines.append("")
        lines.append("**Шаблон ответа:**")
        lines.append("```text")
        lines.append(str(cmp["suggested_public_reply_ru"]).strip())
        lines.append("```")
    return "\n".join(lines).strip()
