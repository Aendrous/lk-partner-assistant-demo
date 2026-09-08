# -*- coding: utf-8 -*-
"""L0: встречающий чат — ответ из KB, уточнения или черновик заявки IntraService.

Разбор уже созданной заявки (preview L1 без поста) + уточняющие вопросы —
для сотрудника/оператора в чате. Пост скрытого комментария / take / learn —
только через «Запуск» / analyze_and_comment.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import assistants
import confluence_tools
import intraservice
import llm_client
import service_routing

PKG = Path(__file__).resolve().parents[1]
_CLARIFY_MD = PKG / "docs" / "prompts" / "уточняющие_вопросы.md"
_MATRIX_MD = PKG / "docs" / "prompts" / "матрица_уточнений.md"

_CONFIDENT_RE = re.compile(
    r"(?i)(has_answer\"?\s*:\s*true|\"confident\"\s*:\s*true)",
)
_TASK_ID_RE = re.compile(r"(?i)^\s*(?:#|hd[#\s-]*)?(\d{5,7})\s*$")


def load_clarify_guide(*, max_chars: int = 4500) -> str:
    """Краткий гайд по уточнениям для промпта L0."""
    parts: list[str] = []
    for path in (_CLARIFY_MD, _MATRIX_MD):
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    blob = "\n\n".join(parts).strip()
    return blob[:max_chars] if blob else ""


def _profile_for_question(text: str) -> assistants.AssistantProfile:
    contour = service_routing.infer_contour(text)
    key = {
        "lk": "l1_web",
        "kp": "l1_web",
        "bp": "bp_tickets",
        "edi": "onec_tickets",
        "crm": "l1_crm",
    }.get(contour, "l1_web")
    return assistants.profiles()[key]


def _service_key_for_create(contour: str, text: str = "") -> str:
    blob = f"{contour}\n{text}".lower()
    if "инцидент" in blob or "упал" in blob or "недоступ" in blob:
        if contour == "lk":
            return "lk_incident"
    if re.search(r"logistic\.iek|перевозчик", blob):
        return "logistics"
    if re.search(r"экспедитор|expd\.iek", blob):
        return "expeditors"
    if re.search(r"\bquart\b|ткп", blob):
        return "quart"
    if re.search(r"iprice", blob):
        return "iprice"
    if contour == "kp":
        return "kp"
    if contour == "bp":
        return "bp"
    if contour in {"edi", "1c"}:
        return "edi"
    if contour == "lk":
        return "lk"
    return "other"


def ask(
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    user_email: str = "",
    create: bool = False,
    ticket_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ответ L0: KB-first, уточнения по заявке, иначе черновик (и опционально POST)."""
    q = (question or "").strip()
    if len(q) < 3:
        return {"ok": False, "error": "пустой вопрос"}

    ctx = ticket_context if isinstance(ticket_context, dict) else {}
    ctx_blob = str(ctx.get("prompt_blob") or "").strip()
    seed_q = str(ctx.get("seed_text") or q)
    profile = _profile_for_question(seed_q)
    contour = service_routing.infer_contour(seed_q)
    service_key = _service_key_for_create(contour, seed_q)
    resolved = intraservice.resolve_service(service_key)

    prefetch = confluence_tools.prefetch_for_ticket(
        {
            "Name": (ctx.get("task_name") or q)[:120],
            "Description": ctx_blob[:2000] or q,
        },
        profile_key=profile.key,
    )
    prefetch_prompt = confluence_tools.format_prefetch_for_prompt(prefetch)
    corpus = assistants.load_corpus(profile, max_chars=8000)
    clarify = load_clarify_guide()

    hist_blob = ""
    for turn in (history or [])[-8:]:
        role = turn.get("role") or "user"
        hist_blob += f"{role}: {(turn.get('content') or '')[:400]}\n"

    system = (
        "Ты помощник 0 линии поддержки IEK. "
        "Отвечай кратко по-русски. Используй корпус, prefetch Confluence и матрицу уточнений. "
        "Не выдумывай URL. Если ответа нет — has_answer=false.\n"
        "Если в контексте уже есть заявка HelpDesk — помогай разобрать её и задавай "
        "уточняющие вопросы (1–3 за ход) по матрице; не дублируй то, что уже в заявке/чате.\n"
        "Верни СТРОГО JSON:\n"
        "{\n"
        '  "has_answer": true/false,\n'
        '  "confident": true/false,\n'
        '  "answer_ru": "текст сотруднику (можно с вопросами) или пусто",\n'
        '  "clarifying_questions": ["вопрос 1", "вопрос 2"],\n'
        '  "article_links": ["https://confluence.dev.iek.ru/..."],\n'
        '  "need_ticket": true/false,\n'
        '  "need_more_info": true/false,\n'
        '  "ticket_name": "название ≤120",\n'
        '  "ticket_description": "суть + факты (+ ответы на уточнения)",\n'
        '  "service_key": "lk|lk_incident|bp|kp|logistics|expeditors|quart|iprice|edi|other"\n'
        "}\n"
        f"Контур эвристики: {contour} · профиль: {profile.key}\n"
        f"{prefetch_prompt}\n"
    )
    if clarify:
        system += f"\nМАТРИЦА УТОЧНЕНИЙ (фрагмент):\n{clarify}\n"
    if corpus:
        system += f"\nКОРПУС:\n{corpus[:5000]}\n"
    if ctx_blob:
        system += f"\nКОНТЕКСТ ЗАЯВКИ HD:\n{ctx_blob[:3500]}\n"

    user = f"История:\n{hist_blob}\nСообщение:\n{q}"
    model, fallback = assistants.resolved_models(profile)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    content, meta = _chat(model, messages)
    used = model
    if not content or "{" not in content:
        content2, meta2 = _chat(fallback, messages)
        if content2:
            content, meta, used = content2, meta2, fallback

    parsed = _parse_json(content)
    has_answer = bool(parsed.get("has_answer") and parsed.get("answer_ru"))
    confident = bool(parsed.get("confident", has_answer))
    clarifying = [
        str(x).strip()
        for x in (parsed.get("clarifying_questions") or [])
        if str(x).strip()
    ][:5]
    need_more = bool(parsed.get("need_more_info")) or bool(clarifying and not confident)
    # если уже есть заявка в контексте — не предлагать создать новую по умолчанию
    has_existing = bool(ctx.get("task_id"))
    need_ticket = (
        False
        if has_existing
        else (bool(parsed.get("need_ticket")) or not has_answer or not confident)
    )
    if has_existing and need_more:
        need_ticket = False

    sk = str(parsed.get("service_key") or service_key).strip().lower()
    if sk not in {
        "lk",
        "lk_incident",
        "bp",
        "kp",
        "logistics",
        "expeditors",
        "quart",
        "iprice",
        "edi",
        "other",
        "vpn",
        "mail",
    }:
        sk = service_key
    resolved = intraservice.resolve_service(sk)

    answer_ru = (parsed.get("answer_ru") or "").strip()
    if clarifying and answer_ru:
        # дописать вопросы в ответ, если LLM не включил их в answer_ru
        missing = [c for c in clarifying if c not in answer_ru]
        if missing:
            answer_ru = answer_ru.rstrip() + "\n\n**Уточните, пожалуйста:**\n" + "\n".join(
                f"{i}. {c}" for i, c in enumerate(missing, 1)
            )
    elif clarifying and not answer_ru:
        answer_ru = "**Уточните, пожалуйста:**\n" + "\n".join(
            f"{i}. {c}" for i, c in enumerate(clarifying, 1)
        )
        has_answer = True

    draft = {
        "Name": (parsed.get("ticket_name") or ctx.get("task_name") or q)[:120],
        "Description": parsed.get("ticket_description")
        or f"## Суть\n{q}\n\n## Контекст чата\n{hist_blob or '(нет)'}",
        "ServiceKey": sk,
        "ServiceId": resolved.get("ServiceId") or ctx.get("service_id"),
        "ServiceName": resolved.get("name") or ctx.get("service_name"),
        "UserEmail": user_email or ctx.get("creator_email") or None,
        "ExistingTaskId": ctx.get("task_id"),
    }

    created: dict[str, Any] | None = None
    if create and need_ticket and draft.get("ServiceId") and user_email:
        created = intraservice.create_task(
            name=str(draft["Name"]),
            description=str(draft["Description"]),
            service_key=sk,
            user_email=user_email,
            service_id=int(draft["ServiceId"]),
        )

    return {
        "ok": True,
        "question": q,
        "profile": profile.key,
        "contour": contour,
        "model": used,
        "has_answer": has_answer or bool(answer_ru),
        "confident": confident,
        "answer_ru": answer_ru if (has_answer or clarifying) else "",
        "clarifying_questions": clarifying,
        "need_more_info": need_more,
        "article_links": assistants.sanitize_article_links(parsed.get("article_links") or []),
        "need_ticket": need_ticket,
        "ticket_draft": draft,
        "ticket_context": {
            "task_id": ctx.get("task_id"),
            "task_name": ctx.get("task_name"),
            "url": ctx.get("url"),
        }
        if ctx.get("task_id")
        else None,
        "created": created,
        "prefetch": {
            "ok": prefetch.get("ok"),
            "hits": len(prefetch.get("hits") or []),
            "query": prefetch.get("query"),
        },
        "llm_meta": {"http": meta.get("http"), "model": used},
    }


def review_ticket(
    task_id: str | int,
    *,
    user_email: str = "",
    run_l1_preview: bool = True,
) -> dict[str, Any]:
    """Разбор существующей заявки HD + уточняющие вопросы (без поста в HD)."""
    tid = str(task_id).strip()
    m = _TASK_ID_RE.match(tid)
    if m:
        tid = m.group(1)
    if not tid.isdigit():
        return {"ok": False, "error": "нужен числовой Id заявки"}

    try:
        task = intraservice.get_task(tid)
    except Exception as exc:
        return {"ok": False, "error": f"get_task: {type(exc).__name__}: {exc}"}

    analysis: dict[str, Any] = {}
    if run_l1_preview:
        try:
            import pipeline as pipe

            analysis = pipe.run_ticket_pipeline(
                tid,
                post=False,
                learn=False,
                take_in_work=False,
                trigger="l0_ui",
            )
        except Exception as exc:
            analysis = {
                "ok": False,
                "error": f"l1_preview: {type(exc).__name__}: {exc}",
                "comment_preview": "",
            }

    parsed = analysis.get("parsed") or {}
    comment = str(analysis.get("comment_preview") or "").strip()
    summary = str(parsed.get("summary_ru") or task.get("Name") or "").strip()
    facts = [str(f).strip() for f in (parsed.get("facts") or []) if str(f).strip()][:6]
    desc = str(task.get("Description") or "")[:1500]
    creator = str(task.get("CreatorEmail") or user_email or "").strip()
    url = str(task.get("url") or f"https://helpdesk.iek.local/Task/View/{tid}")

    facts_json = json.dumps(facts, ensure_ascii=False)
    prompt_blob = (
        f"Заявка #{tid}\n"
        f"Название: {task.get('Name') or ''}\n"
        f"ServiceId: {task.get('ServiceId')} · TypeId: {task.get('TypeId')} · "
        f"PriorityId: {task.get('PriorityId')} · StatusId: {task.get('StatusId')}\n"
        f"CreatorEmail: {creator}\n"
        f"URL: {url}\n"
        f"Описание:\n{desc}\n"
        f"Summary L1: {summary}\n"
        f"Facts: {facts_json}\n"
        f"Скрытый разбор (preview):\n{comment[:2000]}\n"
    )
    ticket_context = {
        "task_id": tid,
        "task_name": task.get("Name"),
        "service_id": task.get("ServiceId"),
        "service_name": task.get("ServiceName"),
        "creator_email": creator,
        "url": url,
        "seed_text": f"{task.get('Name') or ''}\n{desc}",
        "prompt_blob": prompt_blob,
        "comment_preview": comment,
        "summary_ru": summary,
    }

    # уточнения на основе заявки (отдельный ход L0)
    follow = ask(
        "Разбери заявку для сотрудника: кратко суть и 1–3 уточняющих вопроса "
        "(матрица), не обещай сроки. need_ticket=false.",
        history=[],
        user_email=creator,
        create=False,
        ticket_context=ticket_context,
    )

    reply_parts = [
        f"**Заявка [{tid}]({url})** — {task.get('Name') or 'без названия'}",
    ]
    if summary:
        reply_parts.append(f"**Суть:** {summary}")
    if comment:
        reply_parts.append(
            "**Преданализ (как для исполнителя, без публикации):**\n```\n"
            + comment[:1200]
            + "\n```"
        )
    if follow.get("answer_ru"):
        reply_parts.append(follow["answer_ru"])
    elif follow.get("clarifying_questions"):
        qs = follow["clarifying_questions"]
        reply_parts.append(
            "**Уточните, пожалуйста:**\n"
            + "\n".join(f"{i}. {c}" for i, c in enumerate(qs, 1))
        )

    return {
        "ok": True,
        "task_id": tid,
        "url": url,
        "task": {
            "Id": task.get("Id"),
            "Name": task.get("Name"),
            "ServiceId": task.get("ServiceId"),
            "StatusId": task.get("StatusId"),
            "CreatorEmail": creator,
        },
        "l1_preview": {
            "skipped": analysis.get("skipped"),
            "reason": analysis.get("reason"),
            "comment_preview": comment,
            "parsed": {
                "summary_ru": summary,
                "facts": facts,
                "has_kb_solution": parsed.get("has_kb_solution"),
            },
            "service_check": analysis.get("service_check"),
            "pipeline_run_id": analysis.get("pipeline_run_id"),
        },
        "answer_ru": "\n\n".join(reply_parts),
        "clarifying_questions": follow.get("clarifying_questions") or [],
        "article_links": follow.get("article_links") or [],
        "need_ticket": False,
        "need_more_info": True,
        "ticket_context": ticket_context,
        "ticket_draft": follow.get("ticket_draft"),
        "model": follow.get("model"),
        "follow": follow,
    }


def _chat(model: str, messages: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    import requests

    try:
        resp = requests.post(
            f"{llm_client.base_url()}/chat/completions",
            headers=llm_client._headers(),
            json={"model": model, "messages": messages, "temperature": 0.1, "stream": False},
            timeout=120,
            verify=False,
        )
    except requests.RequestException as exc:
        return "", {"error": str(exc)}
    if resp.status_code >= 400:
        return "", {"http": resp.status_code, "body": resp.text[:400]}
    content = (
        (resp.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    ).strip()
    return content, {"http": resp.status_code, "model": model}


def _parse_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        # эвристика без JSON
        if _CONFIDENT_RE.search(text or ""):
            return {"has_answer": True, "confident": True, "answer_ru": text[:800]}
        return {
            "has_answer": False,
            "confident": False,
            "need_ticket": True,
            "answer_ru": "",
            "ticket_description": (text or "")[:1500],
        }
