# -*- coding: utf-8 -*-
"""Разбор заявки: выбор ассистента → короткий скрытый комментарий исполнителю.

  python scripts/analyze_and_comment.py 696955
  python scripts/analyze_and_comment.py 696955 --post
"""
from __future__ import annotations

import base64
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests
import urllib3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
# src — первым, иначе затеняется intraservice.py из корня репозитория
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

import assistants  # noqa: E402
import attachments  # noqa: E402
import bp_adm  # noqa: E402
import confluence_tools  # noqa: E402
import lk_adm  # noqa: E402
import intraservice  # noqa: E402
import llm_client  # noqa: E402
import service_routing  # noqa: E402
import kb_learning  # noqa: E402
import settings as bot_settings  # noqa: E402
import onec_client  # noqa: E402
import related_tasks  # noqa: E402
import task_linking  # noqa: E402
import call_history  # noqa: E402
import closure_taxonomy  # noqa: E402
import overdue  # noqa: E402
import watch_common  # noqa: E402
import semantic_enrich  # noqa: E402
import prompt_store  # noqa: E402
import debug_artifacts  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROMPTS = ROOT / "docs" / "prompts"
RULES_L1 = ROOT / "docs" / "правила" / "правила_1_линии.md"
RULES_EXEC = ROOT / "docs" / "правила" / "разбор_заявки_для_исполнителя.md"

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:тел\.?|телефон)[:\s]*([+\d][\d\s\-()]{7,})", re.I)
PHONE_LOOSE_RE = re.compile(
    r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
    r"|\b\d{3}[\s\-]\d{3}[\s\-]\d{2}[\s\-]\d{2}\b"
)
INN_RE = re.compile(r"\b\d{10}(?:\d{2})?\b")  # маскирование в OCR/тексте
# факт про телефон (не цеплять номера заказов ХИ0108…)
_FACT_PHONE_RE = re.compile(
    r"(?i)(?:^|\s)(?:тел\.?|телефон)\b"
    r"|(?:^|[^\dА-ЯA-Z])(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
    r"|\b\d{3}[\s\-]\d{3}[\s\-]\d{2}[\s\-]\d{2}\b"
)
SKIP_EMAILS = {"mailer@iek.ru", "offers@iek.ru", "news@iek.ru"}
INTERNAL_SUFFIXES = ("@iek.ru", "@iek.group")


def is_internal_email(email: str) -> bool:
    low = (email or "").strip().lower()
    return bool(low) and any(low.endswith(s) for s in INTERNAL_SUFFIXES)


def emails_from_text(text: str) -> list[str]:
    out: list[str] = []
    for e in EMAIL_RE.findall(text or ""):
        low = e.lower()
        if low in SKIP_EMAILS or low in out:
            continue
        out.append(low)
    return out


def partner_emails(*blobs: str) -> list[str]:
    """Внешние email партнёра (не @iek.ru / служебные)."""
    out: list[str] = []
    for blob in blobs:
        for e in emails_from_text(blob):
            if is_internal_email(e) or e in out:
                continue
            out.append(e)
    return out


def _mask_secrets(text: str) -> str:
    """Маскировать телефон/ИНН; email партнёра в скрытом комментарии оставляем."""
    t = text or ""
    t = PHONE_RE.sub("[phone]", t)
    t = PHONE_LOOSE_RE.sub("[phone]", t)
    t = INN_RE.sub("[inn]", t)
    return t


def sanitize_fact(item: str) -> str | None:
    """Убрать факты с телефоном; маскировать остальное. Пустой → None."""
    raw = (item or "").strip()
    if not raw:
        return None
    if _FACT_PHONE_RE.search(raw):
        return None
    cleaned = _mask_secrets(raw)
    if not cleaned.strip() or cleaned.strip() in {"[phone]", "тел [phone]", "телефон [phone]"}:
        return None
    if "[phone]" in cleaned.lower() and len(re.sub(r"\[phone\]", "", cleaned, flags=re.I).strip()) < 4:
        return None
    return cleaned[:160]

def _split_file_ids(file_ids: Any) -> list[str]:
    raw = (file_ids or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in str(raw).split(",") if p.strip()]
    return parts


def ocr_task_files(task_id: str | int, file_ids: list[str] | None = None) -> dict[str, Any]:
    """Совместимость: вложения → смысл через IEK LLM (скрин / .msg)."""
    return attachments.analyze_task_attachments(task_id, file_ids=file_ids)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _chat(
    model: str,
    messages: list[dict[str, Any]],
    *,
    task_id: str | int | None = None,
    profile_key: str = "",
    openwebui_hint: str = "",
    kind: str = "analyze",
) -> tuple[str, dict[str, Any]]:
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "stream": False,
    }
    try:
        resp = requests.post(
            f"{llm_client.base_url()}/chat/completions",
            headers=llm_client._headers(),
            json=body,
            timeout=180,
            verify=False,
        )
    except requests.RequestException as exc:
        call_history.record_llm_call(
            task_id=task_id,
            model=model,
            profile_key=profile_key,
            openwebui_hint=openwebui_hint,
            ok=False,
            error=str(exc),
            kind=kind,
        )
        return "", {"error": str(exc)}
    if resp.status_code >= 400:
        call_history.record_llm_call(
            task_id=task_id,
            model=model,
            profile_key=profile_key,
            openwebui_hint=openwebui_hint,
            ok=False,
            error=f"HTTP {resp.status_code}",
            kind=kind,
        )
        return "", {"http": resp.status_code, "body": resp.text[:500]}
    data = resp.json()
    content = (
        (data.get("choices") or [{}])[0].get("message", {}).get("content")
        or (data.get("choices") or [{}])[0].get("text")
        or ""
    )
    content = (content or "").strip()
    call_history.record_llm_call(
        task_id=task_id,
        model=model,
        profile_key=profile_key,
        openwebui_hint=openwebui_hint,
        ok=bool(content),
        response_preview=content,
        kind=kind,
    )
    if "partner-lk-web-helper" in (openwebui_hint or ""):
        call_history.record_partner_lk_probe(
            ok=bool(content),
            response_preview=content,
            source="openwebui_hint",
        )
    return content, {"model": model, "http": resp.status_code, "raw": data}


def parse_json_answer(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    return json.loads(raw)


def extract_emails(task: dict[str, Any], extra_text: str = "") -> list[str]:
    """Внешние email: описание + OCR + CreatorEmail (если не @iek.ru)."""
    blob = f"{task.get('Name') or ''}\n{task.get('Description') or ''}\n{extra_text}"
    found = partner_emails(blob)
    creator = (task.get("CreatorEmail") or "").strip().lower()
    if creator and not is_internal_email(creator) and creator not in SKIP_EMAILS:
        if creator not in found:
            found.insert(0, creator)
    return found


_ACCESS_RE = re.compile(
    r"(?i)"
    r"(?:не\s+)?(?:могу\s+)?(?:войти|авторизац|логин|парол|доступ|"
    r"не\s+пускает|не\s+пришл\w*\s+письм|mailer@iek\.ru|"
    r"products/api|api/join|api\s+каталог|сброс\s+парол|"
    r"iek[\s\-]*id|forgot-password|"
    r"bp\.iek|бизнес[\s-]*платформ|api[\s\-]*ключ|"
    r"личн\w*\s+кабинет|lk\.iek)"
)


def needs_access_admin_check(
    task: dict[str, Any],
    parsed: dict[str, Any] | None = None,
    *,
    attach_meaning: str = "",
) -> dict[str, bool]:
    """Когда смотреть last login: только сценарии доступа/авторизации ЛК / API / BP."""
    blob = "\n".join(
        [
            str(task.get("Name") or ""),
            str(task.get("Description") or ""),
            str(task.get("_ocr_text") or ""),
            str(attach_meaning or task.get("_attach_meaning") or ""),
            str((parsed or {}).get("summary_ru") or ""),
            str((parsed or {}).get("category") or ""),
            " ".join(str(x) for x in ((parsed or {}).get("facts") or [])[:6]),
        ]
    )
    hit = bool(_ACCESS_RE.search(blob))
    sk = str((parsed or {}).get("service_key") or "").lower()
    intent = str(task.get("_ticket_intent") or "")
    lk = hit or sk == "lk" and bool(
        re.search(r"(?i)вход|парол|авториз|api|mailer|доступ", blob)
    )
    if intent.startswith("lk_api") or intent == "lk_login_access":
        lk = True
    # адрес доставки / склады / ТТН — не auth
    if re.search(r"(?i)адрес\s+доставк|ттн|склад|отгрузк", blob) and not re.search(
        r"(?i)вход|парол|авториз|mailer|api\s+каталог|не\s+пускает", blob
    ):
        lk = False
    bp = bool(
        re.search(
            r"(?i)bp\.iek|бизнес[\s-]*платформ|iek[\s\-]*id|api[\s\-]*ключ|цкг|\bdbp\b",
            blob,
        )
    ) or sk == "bp"
    return {"lk": lk, "bp": bp}


def should_adm_check(task: dict[str, Any], profile: assistants.AssistantProfile, parsed: dict[str, Any] | None = None) -> bool:
    """adm.bp — только контур БП / явный bp / IEK ID / auth BP."""
    if profile.key == "bp_tickets":
        return True
    flags = needs_access_admin_check(task, parsed)
    if flags.get("bp"):
        return True
    sid = task.get("ServiceId")
    if isinstance(sid, str) and sid.isdigit():
        sid = int(sid)
    if sid in {827, 833}:
        return True
    return False


def should_lk_admin_check(
    task: dict[str, Any],
    profile: assistants.AssistantProfile,
    parsed: dict[str, Any] | None = None,
) -> bool:
    """lk-admin (в т.ч. last login) — только доступ/авторизация ЛК или API каталога."""
    flags = needs_access_admin_check(task, parsed)
    if flags.get("lk"):
        return True
    # профиль l1 больше не означает «всегда смотреть Bitrix»
    return False


def run_adm_check(emails: list[str]) -> dict[str, Any]:
    if not emails:
        return {"ok": False, "skipped": True, "reason": "email не найден в заявке"}
    email = emails[0]
    result = bp_adm.search_user(email)
    result["email"] = email
    return result


def run_lk_admin_check(emails: list[str]) -> dict[str, Any]:
    if not emails:
        return {"ok": False, "skipped": True, "reason": "email не найден в заявке"}
    email = emails[0]
    result = lk_adm.search_user(email)
    result["email"] = email
    return result


def format_adm_line(adm: dict[str, Any]) -> str:
    url = adm.get("url") or bp_adm.search_user_url(adm.get("email") or adm.get("query") or "")
    if adm.get("skipped"):
        reason = (adm.get("reason") or "").lower()
        if any(
            x in reason
            for x in ("не контур", "не проверяли", "не bp", "не сценарий", "не нуж")
        ):
            return ""
        return f"adm: пропущено ({adm.get('reason')})"
    if adm.get("login_required") or (not adm.get("ok") and adm.get("found") is None):
        return f"adm: нет доступа (нужен/обновить BP_ADM_COOKIE) · {url}"
    found = adm.get("found")
    if found is True:
        match = (adm.get("matches") or [{}])[0] if adm.get("matches") else {}
        bits = ["найден"]
        if match.get("accountType"):
            bits.append(str(match["accountType"]))
        if match.get("inn"):
            bits.append(f"ИНН {match['inn']}")
        if match.get("isBlocked"):
            bits.append("blocked")
        elif match.get("isActive") is False:
            bits.append("inactive")
        return f"adm: {' · '.join(bits)} · {url}"
    if found is False:
        return f"adm: не найден · {url}"
    return f"adm: проверить вручную · {url}"


IEK_LLM_UI_BASE = "https://chatgpt.iek.local"


def snapshot_llm_request(
    messages: list[dict[str, Any]],
    profile: assistants.AssistantProfile,
) -> dict[str, Any]:
    """Снимок промпта для _analysis_*.json / отладки (system усечён, user целиком)."""
    snap_msgs: list[dict[str, Any]] = []
    for m in messages:
        role = str(m.get("role") or "")
        content = str(m.get("content") or "")
        row: dict[str, Any] = {"role": role, "content_len": len(content)}
        if role == "system" and len(content) > 2000:
            row["content"] = content[:2000] + f"\n…[+{len(content) - 2000} симв.]"
        else:
            row["content"] = content
        snap_msgs.append(row)
    user_message = _message_content(messages, "user")
    system_preview = ""
    for m in messages:
        if str(m.get("role") or "") == "system":
            c = str(m.get("content") or "")
            system_preview = c if len(c) <= 2500 else c[:2500] + f"\n…[+{len(c) - 2500} симв.]"
            break
    return {
        "api_base": llm_client.base_url(),
        "model_requested": profile.model,
        "fallback_model": profile.fallback_model,
        "openwebui_hint": profile.openwebui_hint,
        "iek_llm_ui": IEK_LLM_UI_BASE,
        "user_message": user_message,
        "system_preview": system_preview,
        "messages": snap_msgs,
    }


def _message_content(messages: list[dict[str, Any]], role: str) -> str:
    for m in messages:
        if str(m.get("role") or "") == role:
            return str(m.get("content") or "")
    return ""


def _apply_profile_contour(parsed: dict[str, Any], profile_key: str) -> None:
    """Закрепить service_key по профилю роутера (compose не должен уводить в ЛК/БП)."""
    pk = (profile_key or "").strip().lower()
    if pk == "onec_tickets" or pk == "onec_logistics_tn":
        parsed["service_key"] = "edi"
    elif pk == "bp_tickets":
        parsed["service_key"] = "bp"
    elif pk == "l1_crm":
        parsed["service_key"] = "crm"


def build_messages(
    task: dict[str, Any],
    profile: assistants.AssistantProfile,
    adm: dict[str, Any],
    lk_check: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    rules = prompt_store.read_asset("rules_exec") or _read(RULES_EXEC)
    # матрица L1 — только для l1_web; BP/1С раздувают промпт и путают контур
    if profile.key not in {"bp_tickets", "onec_tickets", "onec_logistics_tn"}:
        # только первые ~6k правил L1 — иначе confluence-agent: «Запрос слишком длинный»
        l1 = prompt_store.read_asset("rules_l1") or _read(RULES_L1)
        rules += "\n\n" + (l1[:6000] + "\n[…]" if len(l1) > 6000 else l1)
    corpus = assistants.load_corpus(profile, max_chars=12000)
    system = f"{profile.system_extra}\n\nПРАВИЛА:\n{rules}\n"
    if corpus:
        label = prompt_store.corpus_label(profile.key)
        system += (
            f"\n{label} (локальный, приоритетнее RAG Confluence при совпадении сценария):\n"
            f"{corpus}\n"
            "Если сценарий есть в корпусе — has_kb_solution=true и solution_steps_ru / "
            "public_reply_draft_ru из корпуса; article_links — только реальные URL.\n"
        )
    drafts = task.get("_draft_snippets") or []
    if drafts:
        draft_blob = "\n\n".join(
            f"### {d.get('title')} ({d.get('file')})\n{(d.get('excerpt') or '')[:400]}"
            for d in drafts[:2]
        )
        system += (
            "\nЛОКАЛЬНЫЕ ЧЕРНОВИКИ (если совпадает сценарий):\n"
            f"{draft_blob}\n"
        )
    footer = prompt_store.load_system_footer().strip()
    if footer:
        system += f"\n{footer}\n"
    prefetch_blob = (task.get("_confluence_prefetch_prompt") or "").strip()
    if prefetch_blob:
        system += f"\n{prefetch_blob}\n"
    onec_line = (task.get("_onec_line") or "").strip()
    refs = ", ".join(task.get("_doc_refs") or []) or "нет"
    candidates = task.get("_similar_candidates") or []
    cand_json = json.dumps(
        [
            {
                "id": c.get("Id"),
                "name": c.get("Name"),
                "topic": c.get("topic"),
                "description": (c.get("Description") or "")[:280],
            }
            for c in candidates[:5]
        ],
        ensure_ascii=False,
    )
    thread = (task.get("_public_thread") or "").strip()[:1800]
    desc = str(task.get("Description") or "")[:2500]
    prior_ctx = (task.get("_prior_context") or "").strip()[:2200]
    intent = str(task.get("_ticket_intent") or "").strip()
    intent_human = semantic_enrich.intent_label(intent) if intent else ""
    schema = prompt_store.load_user_schema().rstrip()
    user = (
        f"{schema}\n\n"
        f"adm.bp: {json.dumps(adm, ensure_ascii=False)[:800]}\n"
        f"lk-admin: {json.dumps(lk_check or {}, ensure_ascii=False)[:800]}\n"
        f"1С: {onec_line or 'не выполнялась'} · документы: {refs}\n\n"
        f"Заявка #{task.get('Id')} · ServiceId={task.get('ServiceId')} · "
        f"{task.get('StatusId')} {task.get('StatusName')}\n"
        f"Название: {task.get('Name')}\n"
        f"CreatorEmail: {task.get('CreatorEmail') or 'нет'}\n"
        f"Партнёр email: {', '.join(task.get('_partner_emails') or []) or 'нет'}\n"
        f"Вложения (смысл IEK LLM — приоритетнее сырого OCR):\n"
        f"{(task.get('_attach_meaning') or '(нет)')[:1200]}\n"
        f"Ключевые фрагменты из вложений:\n{(task.get('_ocr_text') or '')[:600]}\n"
        f"Описание:\n{desc}\n\n"
        f"Переписка:\n{thread or '(нет)'}\n\n"
        f"Предыдущие обращения инициатора (полный контекст):\n{prior_ctx or '(нет)'}\n\n"
        + (f"Авто-intent текущей заявки: {intent} ({intent_human})\n\n" if intent else "")
        + f"Кандидаты похожих:\n{cand_json}\n"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def extract_confluence_links(text: str) -> list[str]:
    found = re.findall(r"https://confluence\.dev\.iek\.ru/[^\s\)\]\"']+", text or "")
    return assistants.sanitize_article_links(found)


def extract_doc_refs(*blobs: str) -> list[str]:
    """Номера заказов/заявок/счетов/GUID из OCR и текста — в факты."""
    text = "\n".join(b or "" for b in blobs)
    out: list[str] = []
    seen: set[str] = set()

    def add(label: str, value: str) -> None:
        key = f"{label}:{value.lower()}"
        if key in seen:
            return
        seen.add(key)
        out.append(f"{label} {value}")

    # Счёт раньше общего «заказ», чтобы «СЧЕТ ХИ…» попал как счёт
    for m in re.findall(r"(?:сч[её]т|invoice)\s*[№#]?\s*([А-ЯA-Z]{1,3}\d{6,12})", text, re.I):
        add("счёт", m.upper() if m[:1].isalpha() else m)
    for m in re.findall(r"(?:заказ\s*(?:покупателя)?)\s*[№#]?\s*([А-ЯA-Z]{1,3}\d{6,12})", text, re.I):
        add("заказ", m.upper() if m[:1].isalpha() else m)
    for m in re.findall(r"\b([А-ЯA-Z]{1,3}\d{6,12})\b", text):
        val = m.upper() if m[:1].isalpha() else m
        if f"счёт:{val.lower()}" in seen:
            continue
        add("заказ", val)
    for m in re.findall(r"\b(0000\d{5,})\b", text):
        add("эл.заявка", m)
    for m in re.findall(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        text,
        re.I,
    ):
        add("GUID ЛК", m.lower())
    return out[:10]


def fallback_facts(task: dict[str, Any], parsed: dict[str, Any]) -> list[str]:
    """Факты модели + номера документов из OCR/описания. Телефоны не включаем."""
    facts: list[str] = []
    for x in parsed.get("facts") or []:
        clean = sanitize_fact(str(x))
        if clean and clean not in facts:
            facts.append(clean)
    refs = extract_doc_refs(
        task.get("Name") or "",
        task.get("Description") or "",
        task.get("_ocr_text") or "",
        " ".join(str(x) for x in (task.get("_doc_refs") or [])),
    )
    for ref in refs:
        if ref not in facts:
            facts.append(ref)
    if facts:
        return facts[:8]
    out: list[str] = []
    name = (task.get("Name") or "").strip()
    if name:
        out.append(name[:160])
    emails = extract_emails(task)
    if emails:
        out.append(f"email {emails[0]}")
    # ИНН ок; телефон в факты не пишем
    blob = (task.get("Description") or "").replace("\r\n", "\n")
    m = re.search(r"\bИНН[:\s]*(\d{10,12})", blob, re.I)
    if m:
        out.append(f"ИНН {m.group(1)}")
    for ref in refs:
        if ref not in out:
            out.append(ref)
    return out[:8]


def _fact_is_redundant(
    fact: str,
    *,
    task_id: Any,
    creator_email: str,
    partners: list[str],
    service_id: Any,
) -> bool:
    """Отбросить факты, уже отражённые в шапке разбора."""
    low = (fact or "").strip().lower().replace("ё", "е")
    if not low:
        return True
    tid = str(task_id or "").strip()
    sid = str(service_id or "").strip()
    emails = {creator_email.lower()} | {p.lower() for p in partners if p}
    emails.discard("")
    # «Заявка #698074, ServiceId=732, создатель …»
    if tid and re.search(rf"(?i)(?:заявк\w*|ticket|#)\s*{re.escape(tid)}\b", low) and (
        "serviceid" in low or "service id" in low or "создател" in low
    ):
        return True
    if sid and re.match(rf"(?i)^serviceid\s*[=:]\s*{re.escape(sid)}\b", low):
        return True
    if sid and re.search(rf"(?i)serviceid\s*[=:]\s*{re.escape(sid)}\b", low) and len(low) < 80:
        return True
    for em in emails:
        if low in {em, f"email {em}", f"email: {em}", f"creatormail: {em}", f"creatormail {em}"}:
            return True
        if re.match(rf"(?i)^(creator)?e?mail\s*[=:]?\s*{re.escape(em)}$", low):
            return True
        if low.startswith("creatormail") and em in low and len(low) < len(em) + 30:
            return True
    return False


def _fact_looks_like_raw_ocr(fact: str) -> bool:
    low = (fact or "").lower()
    if re.search(r"(?i)скриншот\s*\(ocr\)|действия\s+перейти|показать\s+данные", low):
        return True
    # длинный мусор с UI
    if len(low) > 160 and re.search(r"(?i)перейти|показать|номер:\s*\d+", low):
        return True
    return False


def _short_task_url(task_id: str | int) -> str:
    try:
        return intraservice.short_task_url(task_id)
    except Exception:
        return intraservice.task_url(task_id)


def _extract_ticket_id(text: str) -> str:
    m = re.search(r"#(\d{4,7})", text or "")
    return m.group(1) if m else ""


def _strip_ticket_refs(text: str) -> str:
    return re.sub(r"#\d{4,7}", "", text or "")


def _compact_prior_similar(task: dict[str, Any]) -> list[str]:
    """«Ранее от заявителя» + «Похожее» одной строкой: ссылки вместо номеров.

    - Контекст: урок LLM без #номеров + короткая ссылка на контекстную заявку
      (id из урока, иначе первый prior).
    - Похожее: до 3 заявок «тема · ссылка», без повтора контекстного id.
    """
    lesson = re.sub(r"\s+", " ", str(task.get("_prior_lesson_ru") or "").strip())
    similar = list((task.get("_similar") or {}).get("similar") or [])
    ctx_id = _extract_ticket_id(lesson)
    if not ctx_id:
        prior = list(((task.get("_prior") or {}).get("prior") or []))
        if prior:
            ctx_id = str(prior[0].get("Id") or "").strip()
    if ctx_id:
        lesson = _strip_ticket_refs(lesson)
    lesson = re.sub(r"\s{2,}", " ", lesson).strip()

    bits: list[str] = []
    if lesson:
        bits.append(lesson)
        if ctx_id:
            bits.append(_short_task_url(ctx_id))
    used: set[str] = {ctx_id} if ctx_id else set()
    sim_bits: list[str] = []
    for r in similar:
        sid = str(r.get("Id") or "").strip()
        if not sid or sid in used:
            continue
        used.add(sid)
        topic = re.sub(r"\s+", " ", str(r.get("topic") or r.get("Name") or "")).strip()[:90]
        if not topic:
            continue
        sim_bits.append(f"{topic} · {_short_task_url(sid)}")
        if len(sim_bits) >= 3:
            break
    if sim_bits:
        bits.append("Похожее: " + " · ".join(sim_bits))
    if not bits:
        return []
    head = "Ранее от заявителя - " if lesson else ""
    return [head + " · ".join(bits)]


def _build_recommendations(service_check: dict[str, Any]) -> list[str]:
    "По рекомендации сервис/тип/важность, только если есть что поправить"
    recs: list[str] = []
    if not service_check.get("service_ok"):
        sug = service_check.get("suggest_service_id")
        if sug:
            bit = f"сервис → {sug}"
            exp = str(service_check.get("contour_expected") or "").strip()
            if exp:
                bit += f" ({exp})"
            recs.append(bit)
        note = str(service_check.get("note") or "").strip()
        if note:
            recs.append(note)
    if not service_check.get("type_ok"):
        sug_t = service_check.get("suggest_type_id")
        if sug_t:
            tname = service_routing.type_name(sug_t)
            bit = f"тип → {sug_t}"
            if tname and str(tname) != str(sug_t):
                bit += f" ({tname})"
            recs.append(bit)
    tnote = str(service_check.get("type_note") or "").strip()
    if tnote:
        recs.append(tnote)
    if not service_check.get("priority_ok"):
        sug_p = service_check.get("suggest_priority_id")
        if sug_p:
            pname = service_routing.priority_name(sug_p)
            bit = f"важность → {sug_p}"
            if pname and str(pname) != str(sug_p):
                bit = f"важность → {pname} ({sug_p})"
            why = str(service_check.get("priority_why") or "").strip()
            if why:
                bit += f" — {why}"
            recs.append(bit)
    seen: set[str] = set()
    out: list[str] = []
    for r in recs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def format_hidden_comment(
    task: dict[str, Any],
    parsed: dict[str, Any],
    adm: dict[str, Any],
    service_check: dict[str, Any],
    *,
    creator_email: str | None = None,
    ocr_text: str | None = None,
    partner_emails_found: list[str] | None = None,
    profile: assistants.AssistantProfile | None = None,
) -> str:
    """Компактный скрытый разбор: мало переносов; хвост — сервис / тип / важность."""
    creator_email = (
        creator_email if creator_email is not None else task.get("CreatorEmail") or ""
    ).strip()
    partners = (
        partner_emails_found
        if partner_emails_found is not None
        else list(task.get("_partner_emails") or [])
    )
    partners_norm = [p.strip() for p in partners if p and p.strip()]
    partners_only = [
        p for p in partners_norm if not creator_email or p.lower() != creator_email.lower()
    ]
    creator_is_partner = bool(
        creator_email
        and any(p.lower() == creator_email.lower() for p in partners_norm)
    )

    narrative = str(task.get("_narrative_ru") or "").strip()
    if not narrative:
        summary = str(parsed.get("summary_ru") or "").strip()
        facts = [
            f
            for f in fallback_facts(task, parsed)
            if not _fact_is_redundant(
                f,
                task_id=task.get("Id"),
                creator_email=creator_email,
                partners=partners_norm,
                service_id=task.get("ServiceId"),
            )
            and not _fact_looks_like_raw_ocr(f)
        ]
        attach = str(task.get("_attach_meaning") or "").strip()
        bits = [summary] + facts[:4]
        if attach:
            bits.append(attach[:220])
        narrative = " ".join(b for b in bits if b).strip()
        narrative = re.sub(r"\s+", " ", narrative)
    pred_header = "Преданализ чатбота"
    lines: list[str] = (
        [f"{pred_header}: {narrative[:650]}"] if narrative else [pred_header]
    )

    contour = str(parsed.get("service_key") or task.get("_contour") or "").strip().lower()
    if not contour:
        import service_filter

        contour = service_filter.resolve_task_contour(task, parsed)

    # заявитель/партнёр — только контур ЛК (МРК ищет email партнёра в OCR/письме)
    if contour == "lk":
        if creator_email and is_internal_email(creator_email):
            if partners_only:
                lines.append(
                    f"Заявитель: {creator_email} (МРК) · партнёр: {', '.join(partners_only)}"
                )
            else:
                lines.append(f"Заявитель: {creator_email} (МРК) · партнёр email не найден")
        elif creator_email and partners_only and not creator_is_partner:
            lines.append(f"Заявитель: {creator_email} · партнёр: {', '.join(partners_only)}")
        # заявитель сам партнёр (тот же email) — поля не дублируем

    stage = re.sub(r"\s+", " ", str(parsed.get("error_stage_ru") or "").strip())
    cause = re.sub(r"\s+", " ", str(parsed.get("root_cause_ru") or "").strip())
    stage_parts: list[str] = []
    if stage:
        stage_parts.append(f"Этап бизнеспроцесса: {stage}")
    if cause:
        stage_parts.append(f"Причина ошибки: {cause}")
    if stage_parts:
        lines.append(" · ".join(stage_parts))

    # проверки одной строкой
    check_bits: list[str] = []
    onec_line = (task.get("_onec_line") or "").strip()
    if onec_line:
        check_bits.append(onec_line.replace("1С:", "1С").strip())
    for rel_line in task.get("_related_lines") or []:
        s = str(rel_line).strip().lstrip("• ").strip()
        if s:
            check_bits.append(s[:120])
    adm_line = format_adm_line(adm)
    if adm_line:
        check_bits.append(adm_line)
    lk_line = lk_adm.format_lk_line(task.get("_lk_admin") or {})
    if lk_line:
        check_bits.append(lk_line)
    if check_bits:
        lines.append("Проверки: " + " · ".join(check_bits[:4]))

    for ctx in _compact_prior_similar(task):
        lines.append(ctx)

    esc = task.get("_overdue_escalation") or {}
    if esc.get("Comments") or esc.get("Date"):
        lines.append(
            "Просрочка: эскалация «До просрочки»"
            + (f" ({esc.get('Date')})" if esc.get("Date") else "")
        )

    links = assistants.sanitize_article_links(parsed.get("article_links"))
    paste = str(parsed.get("public_reply_draft_ru") or "").strip()
    paste = re.sub(r"\s*\n+\s*", " ", paste).strip()
    kb_lines = list(task.get("_kb_hint_lines") or [])
    if not kb_lines and (paste or links):
        kb_lines = semantic_enrich.format_kb_answer_lines(
            draft_text=paste,
            kb_refs=list(parsed.get("kb_refs") or []),
            article_links=links,
            compact=True,
        )
    for line in kb_lines:
        lines.append(str(line))

    # рекомендации по сервису / типу / важности — только если есть что поправить
    recs = _build_recommendations(service_check)
    if recs:
        lines.append("Рекомендации: " + " · ".join(recs))

    # компактно: без пустых строк
    return "\n".join(x for x in lines if str(x).strip()).strip()


def run_pipeline(
    task_id: str,
    post: bool,
    learn: bool = False,
    *,
    learn_mode: str = "off",
    trigger: str = "cli",
    pipeline_run: Any = None,
    take_in_work: bool = False,
) -> dict[str, Any]:
    cfg = bot_settings.load_settings()
    task = intraservice.get_task(task_id)
    import service_filter

    skip_comment = service_filter.skip_for_task(task, "comment", cfg)
    skip_kb = service_filter.skip_for_task(task, "kb_learn", cfg)
    want_take = bool(take_in_work) or bool(cfg.get("auto_take_in_work"))

    onec_skip = assistants.skip_onec_task(task) or (
        assistants.skip_onec_out_of_scope(task, cfg) if learn_mode != "force" else None
    )
    if onec_skip:
        scope_early: dict[str, Any] = {
            "ok": True,
            "skipped": True,
            "reason": onec_skip,
            "task_id": task.get("Id"),
            "task_name": task.get("Name"),
            "comment_preview": "",
            "post": {"ok": False, "skipped": True, "reason": onec_skip},
            "parsed": {},
            "kb_gap": {"has_gap": False, "reason": "onec scope"},
            "auto_learn_decision": {"run": False, "reason": onec_skip},
            "kb_learning": {"ok": False, "skipped": True, "reason": onec_skip},
        }
        path = debug_artifacts.analysis_path(task_id)
        path.write_text(json.dumps(scope_early, ensure_ascii=False, indent=2), encoding="utf-8")
        scope_early["file"] = path.name
        return scope_early

    if skip_comment and post and learn_mode == "off":
        early: dict[str, Any] = {
            "ok": True,
            "skipped": True,
            "reason": skip_comment,
            "task_id": task.get("Id"),
            "task_name": task.get("Name"),
            "comment_preview": "",
            "post": {"ok": False, "skipped": True, "reason": skip_comment},
            "parsed": {},
            "kb_gap": {"has_gap": False, "reason": "skip contour"},
            "auto_learn_decision": {"run": False, "reason": skip_kb or skip_comment},
            "kb_learning": {"ok": False, "skipped": True, "reason": skip_kb or "comment skip"},
        }
        path = debug_artifacts.analysis_path(task_id)
        path.write_text(json.dumps(early, ensure_ascii=False, indent=2), encoding="utf-8")
        early["file"] = path.name
        return early

    task["_skip_kb_learn"] = bool(skip_kb)
    overdue_hit = None
    apply_status_skip = bool(cfg.get("skip_if_in_progress_or_awaiting", True)) and (
        want_take or trigger == "watch_overdue"
    )
    gate = intraservice.status_blocks_take_in_work(task) if apply_status_skip else {"blocked": False}
    need_overdue_check = trigger == "watch_overdue" or (apply_status_skip and gate.get("blocked"))
    if need_overdue_check:
        marker = str(cfg.get("watch_overdue_marker") or overdue.DEFAULT_MARKER)
        max_age = float(cfg.get("watch_overdue_max_age_hours") or 6)
        try:
            overdue_hit = overdue.detect_overdue_escalation(
                task_id, marker=marker, max_age_hours=max_age
            )
        except Exception:
            overdue_hit = None
    if apply_status_skip and gate.get("blocked") and not overdue_hit:
        skip_result: dict[str, Any] = {
            "ok": True,
            "skipped": True,
            "reason": gate.get("reason"),
            "task_id": task.get("Id"),
            "task_name": task.get("Name"),
            "StatusId": gate.get("StatusId"),
            "StatusName": gate.get("StatusName") or task.get("StatusName"),
            "comment_preview": "",
            "post": {"ok": False, "skipped": True, "reason": gate.get("reason")},
            "take_in_work": {"ok": True, "skipped": True, "reason": gate.get("reason")},
            "link_related": {"ok": False, "skipped": True, "reason": "skip: статус уже обработан"},
            "parsed": {},
            "kb_gap": {"has_gap": False, "reason": "skip"},
            "auto_learn_decision": {"run": False, "reason": "skip: статус уже обработан"},
            "kb_learning": {"ok": False, "skipped": True, "reason": "skip"},
        }
        path = debug_artifacts.analysis_path(task_id)
        path.write_text(json.dumps(skip_result, ensure_ascii=False, indent=2), encoding="utf-8")
        skip_result["file"] = path.name
        if pipeline_run is not None and cfg.get("pipeline_save_runs", True):
            run_dir = getattr(pipeline_run, "dir", None)
            if run_dir:
                (Path(run_dir) / "analysis.json").write_text(
                    json.dumps(skip_result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        return skip_result
    if overdue_hit:
        task["_overdue_escalation"] = overdue_hit
        if gate.get("blocked"):
            want_take = False
        # антидубль: робот уже обработан (скрытый разбор / продление / открытый ответ)
        try:
            lt0 = intraservice.get_task_lifetime(task_id, page_size=50)
            if overdue.already_handled_for_escalation(lt0, overdue_hit.get("Date")):
                skip_dup: dict[str, Any] = {
                    "ok": True,
                    "skipped": True,
                    "reason": "эскалация робота уже обработана (антидубль комментария)",
                    "task_id": task.get("Id"),
                    "task_name": task.get("Name"),
                    "overdue_escalation": overdue_hit,
                    "comment_preview": "",
                    "post": {"ok": False, "skipped": True, "reason": "антидубль"},
                    "take_in_work": {"ok": True, "skipped": True, "reason": "антидубль"},
                }
                path = debug_artifacts.analysis_path(task_id)
                path.write_text(json.dumps(skip_dup, ensure_ascii=False, indent=2), encoding="utf-8")
                skip_dup["file"] = path.name
                return skip_dup
        except Exception:
            pass

    profile = assistants.choose_for_task(task, cfg)

    ocr: dict[str, Any] = {"text": "", "emails": [], "meaning": "", "items": []}
    try:
        if task.get("FileIds"):
            ocr = ocr_task_files(task_id) or ocr
    except Exception:
        ocr = {"text": "", "emails": [], "meaning": "", "items": []}
    ocr_text = (ocr.get("text") or "").strip()
    attach_meaning = (ocr.get("meaning") or "").strip()
    emails = extract_emails(task, extra_text=f"{ocr_text}\n{attach_meaning}")
    for e in ocr.get("emails") or []:
        if e not in emails:
            emails.append(e)
    task["_ocr_text"] = ocr_text
    task["_attachments"] = ocr
    task["_attach_meaning"] = attach_meaning
    task["_partner_emails"] = emails
    refs = extract_doc_refs(
        task.get("Name") or "",
        task.get("Description") or "",
        ocr_text,
        attach_meaning,
    )
    for hit in onec_client.match_overrides_from_text(ocr_text + "\n" + (task.get("Description") or "")):
        order = hit.get("order") or ""
        if order:
            refs.append(f"заказ {order}")
        if hit.get("related_order"):
            refs.append(f"заказ {hit['related_order']}")
        if hit.get("eapp"):
            refs.append(f"эл.заявка {hit['eapp']}")
    # unique refs
    uniq: list[str] = []
    for r in refs:
        if r not in uniq:
            uniq.append(r)
    refs = uniq
    task["_doc_refs"] = refs
    # 1С только если есть номер заказа и тема про резерв/ЛК-заказ (иначе молчим — без строки в комментарии)
    onec_check: dict[str, Any] = {"skipped": True, "reason": "нет номера заказа"}
    blob_low = f"{task.get('Name') or ''}\n{task.get('Description') or ''}\n{ocr_text}".lower()
    sid_onec = assistants.service_id_from_task(task)
    want_onec = sid_onec in {14, 69} or bool(
        re.search(
            r"резерв|в\s+пути|заказ\s+покупател|лк\.iek|подтверд|солярис|"
            r"эл\.?\s*заявк|сч[её]т\s+хи|выгрузк",
            blob_low,
        )
    )
    if want_onec:
        for item in refs:
            if item.lower().startswith("заказ "):
                onec_check = onec_client.resolve_reserve_in_transit(item.split(" ", 1)[1])
                break
    task["_onec"] = onec_check
    task["_onec_line"] = onec_client.format_onec_line(onec_check)

    link_tokens = task_linking.tokens_for_linking(
        refs,
        task,
        None,
        task.get("Name") or "",
        task.get("Description") or "",
        ocr_text,
    )
    related_info = related_tasks.find_related_tasks(task_id, link_tokens)
    related_list = related_info.get("related") or []
    task["_related"] = related_info
    task["_link_tokens"] = link_tokens
    link_filtered, link_filter_meta = task_linking.filter_for_linking(task, related_list, cfg)
    task["_link_filter"] = link_filter_meta
    display_related = link_filtered if link_filtered else related_list[:8]
    task["_related_lines"] = related_tasks.format_related_lines(task, display_related)
    if len(related_list) > len(link_filtered):
        task["_related_lines"].append(
            f"Совпадений по токену всего: {len(related_list)}; "
            f"к подчинению отобрано: {len(link_filtered)} "
            f"(тот же день, открытый статус, тот же ServiceId)"
        )
    link_plan = task_linking.plan_link(task, related_list, cfg)
    task["_link_plan"] = link_plan

    prior_info = related_tasks.find_creator_prior_tasks(
        task_id,
        creator_id=task.get("CreatorId"),
        creator_email=str(task.get("CreatorEmail") or ""),
    )
    prior_enriched = semantic_enrich.enrich_prior_topics(prior_info.get("prior") or [])
    prior_info = {**prior_info, "prior": prior_enriched}
    task["_prior"] = prior_info
    task["_prior_lines"] = semantic_enrich.format_prior_lines(prior_enriched)
    task["_prior_context"] = semantic_enrich.prior_context_for_llm(prior_enriched)
    task["_ticket_intent"] = semantic_enrich.infer_intent(
        name=str(task.get("Name") or ""),
        description=str(task.get("Description") or ""),
    )

    # публичная переписка + черновики + кандидаты похожих (ранжирует основной LLM)
    lifetime_for_thread: dict[str, Any] | None = None
    try:
        lifetime_for_thread = intraservice.get_task_lifetime(task_id, page_size=40)
    except Exception:
        lifetime_for_thread = None
    task["_public_thread"] = semantic_enrich.public_thread_snippet(lifetime_for_thread)
    task["_draft_snippets"] = semantic_enrich.load_draft_snippets(
        hint_text=f"{task.get('Name') or ''}\n{task.get('Description') or ''}\n{ocr_text}"
    )
    known_ids = {str(r.get("Id")) for r in related_list} | {
        str(r.get("Id")) for r in prior_enriched
    }
    cand_info = semantic_enrich.collect_similar_candidates(
        task_id,
        name=str(task.get("Name") or ""),
        description=str(task.get("Description") or ""),
        service_id=task.get("ServiceId"),
        exclude_ids=known_ids,
        max_candidates=8,
    )
    task["_similar_candidates"] = cand_info.get("candidates") or []
    task["_similar"] = {"ok": True, "candidates": task["_similar_candidates"], "similar": []}
    task["_similar_lines"] = []  # заполним после LLM

    adm: dict[str, Any] = {"ok": False, "skipped": True, "reason": "не проверяли — не сценарий доступа BP"}
    lk_check: dict[str, Any] = {
        "ok": False,
        "skipped": True,
        "reason": "не проверяли — не сценарий доступа/авторизации ЛК или API",
    }
    # до LLM — только по эвристике текста (после LLM уточним)
    if should_adm_check(task, profile, parsed=None):
        if emails:
            adm = run_adm_check(emails)
        else:
            adm = {"ok": False, "skipped": True, "reason": "email партнёра не найден"}
    if should_lk_admin_check(task, profile, parsed=None):
        if emails:
            lk_check = run_lk_admin_check(emails)
        else:
            lk_check = {"ok": False, "skipped": True, "reason": "email партнёра не найден"}
    task["_lk_admin"] = lk_check
    confluence_prefetch: dict[str, Any] = {"ok": False, "skipped": True, "reason": "выключено"}
    if cfg.get("confluence_prefetch_enabled", True):
        try:
            confluence_prefetch = confluence_tools.prefetch_for_ticket(
                task, profile_key=profile.key
            )
            task["_confluence_prefetch"] = confluence_prefetch
            task["_confluence_prefetch_prompt"] = confluence_tools.format_prefetch_for_prompt(
                confluence_prefetch
            )
        except Exception as exc:
            confluence_prefetch = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "mode": "rest_prefetch",
            }
            task["_confluence_prefetch"] = confluence_prefetch
    messages = build_messages(task, profile, adm, lk_check)
    llm_request = snapshot_llm_request(messages, profile)

    primary_model, fallback_model = assistants.resolved_models(profile)
    llm_request["model_requested"] = profile.model
    llm_request["model_resolved"] = primary_model
    llm_request["fallback_model"] = profile.fallback_model
    llm_request["fallback_resolved"] = fallback_model

    content, meta = _chat(
        primary_model,
        messages,
        task_id=task_id,
        profile_key=profile.key,
        openwebui_hint=profile.openwebui_hint,
    )
    used_model = primary_model
    low_content = (content or "").lower()
    body_text = str(meta.get("body") or "")
    need_fallback = (
        primary_model != fallback_model
        and (
            (not content)
            or llm_client.is_invalid_model_error(meta.get("http"), body_text)
            or ("{" not in content)
            or ("слишком длинн" in low_content or "сократите" in low_content)
        )
    )
    if need_fallback:
        content2, meta2 = _chat(
            fallback_model,
            messages,
            task_id=task_id,
            profile_key=profile.key,
            openwebui_hint=profile.openwebui_hint,
            kind="analyze_fallback",
        )
        if content2 and ("{" in content2 or not content):
            content, meta, used_model = content2, meta2, fallback_model

    analysis: dict[str, Any] = {
        "task_id": task.get("Id"),
        "task_name": task.get("Name"),
        "profile": {
            "key": profile.key,
            "title": profile.title,
            "model": used_model,
            "openwebui_hint": profile.openwebui_hint,
        },
        "adm": adm,
        "lk_admin": lk_check,
        "partner_emails": emails,
        "doc_refs": refs,
        "onec": onec_check,
        "related": related_info,
        "prior_creator": prior_info,
        "similar": task.get("_similar"),
        "draft_snippets": [
            {"file": d.get("file"), "title": d.get("title"), "score": d.get("score")}
            for d in (task.get("_draft_snippets") or [])
        ],
        "link_plan": link_plan,
        "confluence_prefetch": confluence_prefetch,
        "ocr": {
            "emails": ocr.get("emails") or [],
            "text_preview": ocr_text[:500],
            "meaning": attach_meaning[:800],
            "items": [
                {
                    "filename": it.get("filename"),
                    "kind": it.get("kind"),
                    "app": it.get("app"),
                    "meaning_ru": (it.get("meaning_ru") or "")[:300],
                }
                for it in (ocr.get("items") or [])
                if isinstance(it, dict)
            ],
        },
        "overdue_escalation": overdue_hit or task.get("_overdue_escalation"),
        "llm_request": llm_request,
        "llm_meta": meta,
        "raw": content,
    }
    try:
        parsed = parse_json_answer(content)
    except Exception:
        parsed = {}
        analysis["parse_fallback"] = True

    # если основной ответ без нормального JSON — ещё раз на fallback-модели
    if analysis.get("parse_fallback") or not isinstance(parsed.get("facts"), list):
        if used_model != fallback_model:
            content2, meta2 = _chat(
                fallback_model,
                messages,
                task_id=task_id,
                profile_key=profile.key,
                openwebui_hint=profile.openwebui_hint,
                kind="analyze_fallback_json",
            )
            if content2 and "{" in content2:
                try:
                    parsed = parse_json_answer(content2)
                    content, meta, used_model = content2, meta2, fallback_model
                    analysis["raw"] = content
                    analysis["llm_meta"] = meta
                    analysis["profile"]["model"] = used_model
                    analysis["llm_request"]["model_used"] = used_model
                    analysis["llm_request"]["fallback_used"] = True
                    analysis.pop("parse_fallback", None)
                except Exception:
                    pass
    if not parsed or not isinstance(parsed, dict):
        parsed = {
            "understood": True,
            "summary_ru": task.get("Name"),
            "service_key": (
                "bp"
                if profile.key == "bp_tickets"
                else "edi"
                if profile.key in {"onec_tickets", "onec_logistics_tn"}
                else "other"
            ),
            "category": "OTHER",
            "facts": [],
            "has_kb_solution": False,
            "solution_steps_ru": [],
            "article_links": [],
        }
        analysis["parse_fallback"] = True

    analysis["llm_request"]["model_used"] = used_model
    if "fallback_used" not in analysis["llm_request"]:
        analysis["llm_request"]["fallback_used"] = used_model != primary_model

    # гарантировать ключи нового формата
    parsed.setdefault("public_reply_draft_ru", "")
    parsed.setdefault("kb_refs", [])
    parsed.setdefault("similar_picks", [])
    parsed.setdefault("error_stage_ru", "")
    parsed.setdefault("root_cause_ru", "")
    _apply_profile_contour(parsed, profile.key)

    # после LLM: догнать lk-admin / adm, если смысл заявки — доступ/авторизация
    access_flags = needs_access_admin_check(task, parsed, attach_meaning=attach_meaning)
    analysis["access_admin_flags"] = access_flags
    if access_flags.get("lk") and (lk_check.get("skipped") or not lk_check.get("ok")):
        if emails:
            lk_check = run_lk_admin_check(emails)
        else:
            lk_check = {"ok": False, "skipped": True, "reason": "email партнёра не найден"}
        task["_lk_admin"] = lk_check
        analysis["lk_admin"] = lk_check
    elif not access_flags.get("lk") and not lk_check.get("ok"):
        lk_check = {
            "ok": False,
            "skipped": True,
            "reason": "не проверяли — не сценарий доступа/авторизации ЛК или API",
        }
        task["_lk_admin"] = lk_check
        analysis["lk_admin"] = lk_check
    if access_flags.get("bp") and (adm.get("skipped") or not adm.get("ok")):
        if emails:
            adm = run_adm_check(emails)
        else:
            adm = {"ok": False, "skipped": True, "reason": "email партнёра не найден"}
        analysis["adm"] = adm

    parsed["article_links"] = assistants.sanitize_article_links(
        list(parsed.get("article_links") or []) + extract_confluence_links(content)
    )
    parsed["article_links"] = [
        u
        for u in parsed["article_links"]
        if "confluence.dev.iek.ru" in u or "corp.iek.ru" in u
    ]
    if not parsed["article_links"]:
        parsed["has_kb_solution"] = False
        parsed["solution_steps_ru"] = []

    # Локальные факты 1С/корпус важнее «пустого» RAG Confluence
    onec = task.get("_onec") or {}
    if onec.get("reserve_in_transit") is True and onec.get("order"):
        parsed["has_kb_solution"] = True
        sk_default = "edi" if profile.key in {"onec_tickets", "onec_logistics_tn"} else "lk"
        parsed["service_key"] = (
            parsed.get("service_key")
            if parsed.get("service_key") not in ("", "other")
            else sk_default
        )
        parsed["solution_steps_ru"] = [
            f"В 1С у заказа {onec.get('order')} галка «Резервировать товары в пути» уже стоит — "
            "подтверждать резерв в ЛК не требуется.",
            "Если в ЛК нет статуса «уже зарезервировано» — это отображение; на резерв в 1С не влияет.",
        ]
        parsed["public_reply_draft_ru"] = (
            parsed.get("public_reply_draft_ru")
            or parsed["solution_steps_ru"][0]
        )
        # LK-06 / 1C-01 из локального корпуса
        for u in (
            "https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124630014",
            "https://confluence.dev.iek.ru/pages/viewpage.action?pageId=50007807",
        ):
            if u not in parsed["article_links"]:
                parsed["article_links"].append(u)

    # Похожие по смыслу — из ответа LLM (кандидаты были в промпте)
    cand_by_id = {str(c.get("Id")): c for c in (task.get("_similar_candidates") or [])}
    similar_picked: list[dict[str, Any]] = []
    for p in parsed.get("similar_picks") or []:
        if not isinstance(p, dict) or p.get("same_problem") is False:
            continue
        pid = str(p.get("id") or "").strip()
        if pid not in cand_by_id:
            continue
        src = cand_by_id[pid]
        similar_picked.append(
            {
                "Id": src.get("Id"),
                "Name": src.get("Name"),
                "url": src.get("url"),
                "Created": src.get("Created"),
                "topic": (p.get("topic") or src.get("topic") or "")[:120],
                "why": (p.get("why") or "")[:160],
            }
        )
        if len(similar_picked) >= 3:
            break
    # fallback: отдельный semantic-pass, если основной LLM не выбрал
    if not similar_picked and task.get("_similar_candidates"):
        ranked = semantic_enrich.rank_similar_by_llm(
            model=used_model,
            chat=_chat,
            current=task,
            thread=str(task.get("_public_thread") or ""),
            candidates=list(task.get("_similar_candidates") or []),
            task_id=task_id,
            profile_key=profile.key,
            openwebui_hint=profile.openwebui_hint,
        )
        analysis["similar_rank"] = {
            "ok": ranked.get("ok"),
            "error": ranked.get("error"),
            "candidates_count": ranked.get("candidates_count"),
        }
        similar_picked = list(ranked.get("similar") or [])
    task["_similar"] = {
        "ok": True,
        "candidates": task.get("_similar_candidates") or [],
        "similar": similar_picked,
    }
    task["_similar_lines"] = semantic_enrich.format_similar_lines(similar_picked)
    analysis["similar"] = task["_similar"]

    # KB-ответ: текст из LLM + точечные ссылки (не intro CQL-страниц)
    kb_refs: list[dict[str, Any]] = []
    for r in parsed.get("kb_refs") or []:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or "").strip()
        title = str(r.get("title") or r.get("section") or "").strip()
        if not url and not title:
            continue
        if url and "confluence.dev.iek.ru" not in url and "corp.iek.ru" not in url:
            continue
        kb_refs.append(
            {
                "title": title or "статья",
                "url": url,
                "why": str(r.get("why") or "")[:160],
            }
        )
        if url and url not in parsed["article_links"]:
            parsed["article_links"].append(url)
    parsed["kb_refs"] = kb_refs
    draft_reply = str(parsed.get("public_reply_draft_ru") or "").strip()
    if not draft_reply and parsed.get("has_kb_solution"):
        steps = [str(s).strip() for s in (parsed.get("solution_steps_ru") or []) if str(s).strip()]
        draft_reply = " ".join(steps[:2])
    # отсечь мусорные шапки «быстрых ответов»
    if re.search(
        r"(?i)назначение:\s*быстрые\s+ответы|скопируйте\s+текст\s+в\s+комментарий|"
        r"локальный\s+полный\s+черновик\s*\(все\s+группы\)",
        draft_reply,
    ):
        draft_reply = ""
        parsed["public_reply_draft_ru"] = ""
    parsed["public_reply_draft_ru"] = draft_reply

    # компактный narrative + короткий ответ + урок из prior (IEK LLM)
    facts_for_compose = [
        f
        for f in fallback_facts(task, parsed)
        if not _fact_looks_like_raw_ocr(f)
        and not _fact_is_redundant(
            f,
            task_id=task.get("Id"),
            creator_email=str(task.get("CreatorEmail") or ""),
            partners=list(task.get("_partner_emails") or []),
            service_id=task.get("ServiceId"),
        )
    ]
    composed = semantic_enrich.compose_compact_digest(
        model=fallback_model or primary_model,
        chat=_chat,
        task=task,
        parsed=parsed,
        facts=facts_for_compose,
        attach_meaning=str(task.get("_attach_meaning") or ""),
        ocr_text=str(task.get("_ocr_text") or ""),
        prior=list((task.get("_prior") or {}).get("prior") or []),
        similar=list((task.get("_similar") or {}).get("similar") or []),
        task_id=task_id,
        profile_key=profile.key,
        openwebui_hint=profile.openwebui_hint,
    )
    analysis["compose"] = {
        "ok": composed.get("ok"),
        "service_key": composed.get("service_key"),
        "narrative_preview": (composed.get("narrative_ru") or "")[:240],
    }
    if composed.get("ok"):
        if composed.get("narrative_ru"):
            task["_narrative_ru"] = composed["narrative_ru"]
        if composed.get("prior_lesson_ru"):
            task["_prior_lesson_ru"] = composed["prior_lesson_ru"]
        if composed.get("similar_one_ru"):
            task["_similar_one_ru"] = composed["similar_one_ru"]
        if composed.get("public_reply_ru"):
            draft_reply = composed["public_reply_ru"]
            parsed["public_reply_draft_ru"] = draft_reply
        _apply_profile_contour(parsed, profile.key)

    if draft_reply or kb_refs:
        parsed["has_kb_solution"] = True
        if draft_reply and not (parsed.get("solution_steps_ru") or []):
            parsed["solution_steps_ru"] = [draft_reply[:400]]
    task["_kb_hint_lines"] = semantic_enrich.format_kb_answer_lines(
        draft_text=draft_reply,
        kb_refs=kb_refs,
        article_links=list(parsed.get("article_links") or []),
        compact=True,
    )
    analysis["confluence_search"] = {
        "ok": True,
        "mode": "llm_kb_refs",
        "kb_refs": kb_refs,
        "public_reply_draft_ru": draft_reply[:400],
    }

    # контур после LLM (включая edi)
    contour = str(parsed.get("service_key") or "")
    if not contour or contour == "other":
        contour = service_routing.infer_contour(
            f"{task.get('Name') or ''}\n{task.get('Description') or ''}\n{task.get('_narrative_ru') or ''}",
            service_key=contour,
        )
        if contour != "other":
            parsed["service_key"] = contour
    service_check = service_routing.check_service(
        task,
        contour=parsed.get("service_key") or "",
        adm_found=adm.get("found") if adm.get("found") is not None else None,
        prior=list((task.get("_prior") or {}).get("prior") or []),
    )
    ocr_text = (task.get("_ocr_text") or "").strip()
    emails = list(task.get("_partner_emails") or [])

    comment = format_hidden_comment(
        task,
        parsed,
        adm,
        service_check,
        ocr_text=ocr_text or None,
        partner_emails_found=emails,
        profile=profile,
    )
    analysis["service_check"] = service_check
    analysis["parsed"] = parsed
    closure_plan = closure_taxonomy.build_hd_field_payload(parsed, settings=cfg)
    analysis["closure_fields_plan"] = closure_plan
    analysis["comment_preview"] = comment

    kb_gap = kb_learning.assess_kb_gap(analysis)
    analysis["kb_gap"] = kb_gap

    if learn_mode == "force" or learn:
        mode = "force"
    elif learn_mode == "auto":
        mode = "auto"
    else:
        mode = "off"

    auto_decision = kb_learning.should_auto_learn(
        task, analysis, trigger=trigger, force=(mode == "force"), settings=cfg
    )
    analysis["auto_learn_decision"] = auto_decision

    lifetime: dict[str, Any] | None = None
    do_learn = mode == "force" or (mode == "auto" and auto_decision.get("run"))
    if task.get("_skip_kb_learn") and mode != "force":
        do_learn = False
        analysis["kb_learning"] = {
            "ok": False,
            "skipped": True,
            "reason": skip_kb or "контур: самообучение выключено",
        }
    elif do_learn:
        try:
            lifetime = intraservice.get_task_lifetime(task_id)
        except Exception:
            lifetime = None
        learn_result = kb_learning.learn_from_task_data(
            task, analysis, lifetime=lifetime, post_note=False
        )
        analysis["kb_learning"] = learn_result
        if learn_result.get("ok") and learn_result.get("note_preview"):
            comment = (comment.rstrip() + "\n" + str(learn_result["note_preview"])).strip()
            analysis["comment_preview"] = comment
            learn_result["note_in_comment"] = True
        call_history.record_kb_learn(
            task_id=task_id,
            ok=bool(learn_result.get("ok")),
            draft_path=str(learn_result.get("draft_path") or ""),
            reason=str(learn_result.get("reason") or learn_result.get("error") or ""),
            code=str(learn_result.get("code") or ""),
        )
    else:
        analysis["kb_learning"] = {
            "ok": False,
            "skipped": True,
            "reason": auto_decision.get("reason") or kb_gap.get("reason") or "обучение не запускалось",
        }
        if auto_decision.get("run") is False and mode != "off":
            call_history.record_kb_learn(
                task_id=task_id,
                ok=False,
                reason=str(auto_decision.get("reason") or "не запущено"),
            )

    if post:
        if skip_comment:
            analysis["post"] = {"ok": False, "skipped": True, "reason": skip_comment}
        elif cfg.get("link_related_on_post", True):
            analysis["link_related"] = task_linking.apply_link_on_post(
                task,
                related_list,
                cfg,
                parsed=parsed,
                add_observer=bool(cfg.get("add_parent_creator_as_observer", True)),
            )
            if analysis["link_related"].get("actions"):
                refreshed = related_tasks.find_related_tasks(task_id, task.get("_link_tokens") or link_tokens)
                task["_related"] = refreshed
                link_filtered, _ = task_linking.filter_for_linking(
                    task, refreshed.get("related") or [], cfg
                )
                display_related = link_filtered if link_filtered else (refreshed.get("related") or [])[:8]
                task["_related_lines"] = related_tasks.format_related_lines(task, display_related)
                comment = format_hidden_comment(
                    task,
                    parsed,
                    adm,
                    service_check,
                    creator_email=task.get("CreatorEmail"),
                    ocr_text=ocr_text or None,
                    partner_emails_found=emails,
                    profile=profile,
                )
                learn_note = (analysis.get("kb_learning") or {}).get("note_preview") or ""
                if (analysis.get("kb_learning") or {}).get("ok") and learn_note:
                    comment = (comment.rstrip() + "\n" + str(learn_note)).strip()
                analysis["comment_preview"] = comment
        else:
            analysis["link_related"] = {
                **link_plan,
                "skipped": True,
                "reason": "link_related_on_post=false",
            }
        if not skip_comment:
            # антидубль: не писать тот же скрытый разбор повторно (петля watch_new / Changed)
            try:
                lt_post = lifetime if isinstance(lifetime, dict) else intraservice.get_task_lifetime(task_id, page_size=40)
                prior = watch_common.find_recent_bot_digest(lt_post, max_age_hours=72)
                if watch_common.is_duplicate_digest(comment, prior):
                    analysis["post"] = {
                        "ok": False,
                        "skipped": True,
                        "reason": "антидубль: такой же скрытый комментарий уже есть",
                        "prior_date": (prior or {}).get("Date"),
                    }
                    analysis["comment_preview"] = comment
                elif prior and watch_common.is_hidden_digest(comment):
                    # тот же формат разбора уже есть — не плодить копии (#699825)
                    analysis["post"] = {
                        "ok": False,
                        "skipped": True,
                        "reason": "антидубль: скрытый разбор уже есть (новый формат преданализа)",
                        "prior_date": (prior or {}).get("Date"),
                    }
                    analysis["comment_preview"] = comment
                else:
                    analysis["post"] = intraservice.add_private_comment(task_id, comment)
            except Exception as exc:
                analysis["post"] = intraservice.add_private_comment(task_id, comment)
                analysis["post_dedup_check_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            if cfg.get("auto_fill_closure_fields", True) and (closure_plan.get("fields") or {}):
                try:
                    analysis["closure_fields"] = intraservice.update_task_fields(
                        task_id, closure_plan["fields"]
                    )
                except Exception as exc:
                    analysis["closure_fields"] = {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                    }
            if (
                cfg.get("auto_set_priority_on_analyze", True)
                and service_check.get("can_auto_priority")
                and (analysis.get("post") or {}).get("ok")
            ):
                sug_p = service_check.get("suggest_priority_id")
                try:
                    analysis["priority_set"] = intraservice.update_task_priority(task_id, int(sug_p))
                    analysis["priority_set"]["why"] = service_check.get("priority_why")
                except Exception as exc:
                    analysis["priority_set"] = {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                    }
            if want_take:
                analysis["take_in_work"] = intraservice.take_task_in_work(
                    task_id, comment="Взято в работу (чатбот 1 линии)"
                )
            esc = task.get("_overdue_escalation") or overdue_hit
            if esc and (cfg.get("overdue_shift_deadline", True) or cfg.get("overdue_post_public", True)):
                try:
                    lifetime = intraservice.get_task_lifetime(task_id, page_size=50)
                    if overdue.already_handled_for_escalation(lifetime, esc.get("Date")):
                        analysis["overdue_followup"] = {
                            "ok": True,
                            "skipped": True,
                            "reason": "уже обработана эта эскалация робота (антидубль)",
                            "escalation_date": esc.get("Date"),
                        }
                    else:
                        days = int(cfg.get("overdue_shift_deadline_days") or 1)
                        if cfg.get("overdue_shift_deadline", True):
                            analysis["deadline_shift"] = intraservice.shift_deadline(task_id, days=days)
                        prior = overdue.extract_prior_public_answer(lifetime)
                        facts = list(fallback_facts(task, parsed))
                        if task.get("_onec_line"):
                            facts.append(str(task.get("_onec_line")))
                        only_kb = bool(cfg.get("public_reply_only_if_kb", True))
                        public = overdue.format_overdue_public_comment(
                            new_deadline=str((analysis.get("deadline_shift") or {}).get("Deadline") or ""),
                            parsed=parsed,
                            prior_public=prior,
                            hidden_facts=facts,
                            only_if_kb=only_kb,
                        )
                        analysis["public_comment_preview"] = public
                        post_public_enabled = bool(
                            cfg.get("auto_post_public_comment", False)
                            and cfg.get("overdue_post_public", False)
                        )
                        if post_public_enabled:
                            if public.strip():
                                analysis["post_public"] = intraservice.add_public_comment(task_id, public)
                            else:
                                analysis["post_public"] = {
                                    "ok": False,
                                    "skipped": True,
                                    "reason": "public_reply_only_if_kb: нет уверенного KB/ответа — только скрытый",
                                }
                        else:
                            analysis["post_public"] = {
                                "ok": False,
                                "skipped": True,
                                "reason": "auto_post_public_comment=false или overdue_post_public=false",
                            }
                except Exception as exc:
                    analysis["overdue_followup_error"] = f"{type(exc).__name__}: {str(exc)[:240]}"
    else:
        analysis["post"] = {"ok": False, "skipped": True, "reason": "нет флага --post"}
        analysis["link_related"] = link_plan
        if want_take and not post:
            analysis["take_in_work"] = {
                "ok": False,
                "skipped": True,
                "reason": "take_in_work только вместе с --post / auto_post",
            }

    path = debug_artifacts.analysis_path(task_id)
    path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    analysis["file"] = path.name

    if pipeline_run is not None and cfg.get("pipeline_save_runs", True):
        run_dir = getattr(pipeline_run, "dir", None)
        if run_dir:
            (Path(run_dir) / "analysis.json").write_text(
                json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    return analysis


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("--post", action="store_true", help="Записать скрытый комментарий в заявку")
    parser.add_argument(
        "--learn",
        action="store_true",
        help="Если в KB не было ответа — создать черновик для Confluence (kb_learning)",
    )
    parser.add_argument(
        "--take-in-work",
        action="store_true",
        help="После --post перевести в «В процессе» и назначить себя исполнителем",
    )
    args = parser.parse_args()
    if not intraservice.has_credentials():
        raise SystemExit("Нет IntraService credentials")
    if not llm_client.has_credentials():
        raise SystemExit("Нет IEK_LLM_TOKEN")
    cfg = bot_settings.load_settings()
    if args.learn:
        learn_mode = "force"
    elif cfg.get("auto_learn_kb") and cfg.get("auto_learn_on_analyze"):
        learn_mode = "auto"
    else:
        learn_mode = "off"
    result = run_pipeline(
        args.task_id,
        post=args.post,
        learn=args.learn,
        learn_mode=learn_mode,
        trigger="cli",
        take_in_work=bool(args.take_in_work),
    )
    out = {
        "skipped": result.get("skipped"),
        "reason": result.get("reason"),
        "StatusId": result.get("StatusId"),
        "profile": result.get("profile"),
        "service_check": result.get("service_check"),
        "adm": result.get("adm"),
        "parsed": result.get("parsed"),
        "kb_gap": result.get("kb_gap"),
        "auto_learn_decision": result.get("auto_learn_decision"),
        "kb_learning": result.get("kb_learning"),
        "post": result.get("post"),
        "take_in_work": result.get("take_in_work"),
        "link_related": result.get("link_related"),
        "comment_preview": result.get("comment_preview"),
        "file": result.get("file"),
    }
    debug_artifacts.analysis_summary_path(args.task_id).write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    preview = result.get("comment_preview") or ""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        if result.get("skipped"):
            print(f"SKIP: {result.get('reason')}")
            print("---")
            print("ok skipped= True StatusId=", result.get("StatusId"))
            return 0
        print(preview)
        print("---")
        print("ok post=", (result.get("post") or {}).get("ok"), "profile=", (result.get("profile") or {}).get("key"))
    except UnicodeEncodeError:
        sys.stdout.buffer.write((preview + "\n---\n").encode("utf-8", errors="replace"))
    return 0 if (result.get("post") or {}).get("ok") or not args.post else 1


if __name__ == "__main__":
    raise SystemExit(main())
