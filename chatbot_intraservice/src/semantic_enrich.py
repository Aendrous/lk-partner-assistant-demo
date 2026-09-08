# -*- coding: utf-8 -*-
"""Семантическое обогащение разбора: тема заявки, похожие по смыслу, черновики KB."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import intraservice

PKG = Path(__file__).resolve().parents[1]
DRAFTS_DIR = PKG / "docs" / "черновики_статей"

_SUBJECT_NOISE = re.compile(
    r"(?i)^(re|fw|fwd|ответ|aw)\s*:\s*|"
    r"^\[dkim[^\]]*\]\s*"
)
_WS = re.compile(r"\s+")
# шаблонное начало письма — не тема заявки
_BOILERPLATE = re.compile(
    r"(?i)^("
    r"я\s+представляю\s+компанию|"
    r"мы\s+являемся\s+официальным|"
    r"обращаемся\s+к\s+вам|"
    r"просим\s+рассмотреть"
    r")"
)
_LK_API_CATALOG = re.compile(
    r"(?i)products/api|api/join|api\s+каталог|сервис\s+api|"
    r"mailer@iek\.ru|внешн\w*\s+пользовател\w*\s+api|синхронизац\w*\s+каталог"
)
_LK_LOGIN = re.compile(
    r"(?i)не\s+пускает|не\s+могу\s+войти|сброс\s+парол|forgot-password|"
    r"iek\s*id|авторизац\w*|письмо\s+.*(?:логин|парол|доступ)"
)


def infer_intent(*, name: str = "", description: str = "") -> str:
    """Краткая метка сценария для prior/LLM."""
    blob = f"{name}\n{description}"
    if _LK_API_CATALOG.search(blob):
        if re.search(r"(?i)не\s+пришл|не\s+получил|не\s+приходит|mailer", blob):
            return "lk_api_catalog_no_email"
        if re.search(r"(?i)регистрац|join|подключ", blob):
            return "lk_api_catalog_register"
        return "lk_api_catalog"
    if _LK_LOGIN.search(blob):
        return "lk_login_access"
    if re.search(r"(?i)склад", blob) and re.search(r"(?i)лк|каталог|не\s+виж", blob):
        return "lk_warehouses"
    return ""


def intent_label(intent: str) -> str:
    return {
        "lk_api_catalog": "API каталога ЛК (lk.iek.ru/products/api)",
        "lk_api_catalog_register": "регистрация API каталога ЛК",
        "lk_api_catalog_no_email": "нет письма mailer@iek.ru (API каталога ЛК)",
        "lk_login_access": "вход / пароль ЛК (IEK ID)",
        "lk_warehouses": "склады в каталоге ЛК",
    }.get(intent, "")


def _name_is_useful(name: str) -> bool:
    raw = _SUBJECT_NOISE.sub("", (name or "").strip())
    raw = _WS.sub(" ", raw).strip()
    if len(raw) < 12:
        return False
    if _BOILERPLATE.match(raw):
        return False
    if re.match(r"(?i)^\[?dkim", raw):
        return False
    return True


def topic_from_task(
    *,
    name: str = "",
    description: str = "",
    max_len: int = 110,
) -> str:
    """Короткая тема из сути заявки (Name + описание + ключевые URL)."""
    desc = _WS.sub(" ", (description or "").replace("\r\n", "\n")).strip()
    for sep in ("\n---", "\nС уважением", "\nBest regards", "\nFrom:", "\n--"):
        idx = desc.lower().find(sep.lower())
        if idx > 40:
            desc = desc[:idx].strip()
    intent = infer_intent(name=name, description=description)
    label = intent_label(intent)
    # явные URL/ключевые фразы важнее первого предложения
    url_m = re.search(r"https?://lk\.iek\.ru[^\s\)>\"']+", desc, re.I)
    if url_m and "api" in url_m.group(0).lower():
        bit = "API каталога ЛК (" + url_m.group(0).rstrip(".,;") + ")"
        if label and label not in bit:
            bit = label + " · " + bit
        return bit[:max_len]
    sentence = ""
    for part in re.split(r"(?<=[.!?])\s+|\n+", desc):
        p = part.strip()
        if len(p) < 20:
            continue
        if re.match(
            r"(?i)^(добрый\s+день|здравствуйте|уважаем\w*|коллеги|hello|hi)\b",
            p,
        ):
            continue
        p = re.sub(
            r"(?i)^(добрый\s+день|здравствуйте)[,!]?\s*",
            "",
            p,
        ).strip()
        if len(p) < 20:
            continue
        if _BOILERPLATE.match(p):
            continue
        sentence = p
        break
    if not sentence or _BOILERPLATE.match(sentence):
        if _name_is_useful(name):
            sentence = _WS.sub(" ", _SUBJECT_NOISE.sub("", name)).strip()
        elif label:
            sentence = label
        else:
            sentence = _WS.sub(" ", _SUBJECT_NOISE.sub("", (name or ""))).strip()
    elif label and label.lower() not in sentence.lower() and len(sentence) < 70:
        if not re.search(r"(?i)api|каталог|mailer", sentence):
            sentence = f"{label}: {sentence}"
    sentence = _WS.sub(" ", sentence).strip(" .;")
    if len(sentence) > max_len:
        sentence = sentence[: max_len - 1].rstrip() + "…"
    return sentence or "без темы"


def enrich_prior_topics(prior: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    """Подтянуть Description и сформулировать topic для предыдущих обращений."""
    out: list[dict[str, Any]] = []
    for row in (prior or [])[:limit]:
        item = dict(row)
        hid = str(item.get("Id") or "")
        desc = str(item.get("Description") or "")
        if hid and not desc:
            try:
                full = intraservice.get_task(hid)
                desc = str(full.get("Description") or "")
                item["Name"] = full.get("Name") or item.get("Name")
                item["Created"] = full.get("Created") or item.get("Created")
            except Exception:
                desc = ""
        item["Description"] = desc
        item["intent"] = infer_intent(
            name=str(item.get("Name") or ""),
            description=desc,
        )
        item["topic"] = topic_from_task(
            name=str(item.get("Name") or ""),
            description=desc,
        )
        out.append(item)
    return out


def prior_context_for_llm(prior: list[dict[str, Any]], *, limit: int = 3) -> str:
    """Явный контекст prior для LLM — смысл прошлых обращений, не только первая строка."""
    if not prior:
        return ""
    chunks: list[str] = []
    for row in prior[:limit]:
        hid = row.get("Id")
        topic = (row.get("topic") or "").strip()
        intent = (row.get("intent") or "").strip()
        name = str(row.get("Name") or "").strip()[:200]
        desc = str(row.get("Description") or "").strip()[:600]
        bit = f"#{hid}: {topic}"
        if intent:
            bit += f" [intent={intent}]"
        if name and name.lower() not in topic.lower():
            bit += f"\n  Тема письма: {name}"
        if desc:
            bit += f"\n  Описание: {desc[:500]}"
        chunks.append(bit)
    return "\n\n".join(chunks)


def format_prior_lines(prior: list[dict[str, Any]]) -> list[str]:
    if not prior:
        return []
    lines = ["Предыдущие обращения инициатора:"]
    for r in prior[:3]:
        when = (r.get("Created") or "")[:19].replace("T", " ")
        topic = (r.get("topic") or topic_from_task(name=str(r.get("Name") or ""))).strip()
        intent = intent_label(str(r.get("intent") or ""))
        if intent and intent.lower() not in topic.lower()[:40]:
            topic = f"{intent} · {topic}"
        lines.append(f"• #{r.get('Id')} ({when}) · {topic} · {r.get('url')}")
    return lines


def public_thread_snippet(
    lifetime: dict[str, Any] | None,
    *,
    max_chars: int = 2800,
) -> str:
    """Публичная переписка заявки (ответы исполнителя и заявителя) для LLM."""
    if not lifetime:
        return ""
    rows = lifetime.get("TaskLifetimes") or []
    chunks: list[str] = []
    for row in sorted(rows, key=lambda r: str((r or {}).get("Date") or "")):
        if not isinstance(row, dict):
            continue
        if row.get("IsPublic") is False:
            continue
        text = str(row.get("Comments") or "").strip()
        if len(text) < 12:
            continue
        # скрытые разборы бота иногда с IsPublic null/false — отсекаем по маркеру
        if re.search(r"(?i)^(?:сервис\s*hd\s*:|разбор от чатбота iek llm|разбор iek llm)", text):
            continue
        who = (row.get("Editor") or "?").strip()
        when = str(row.get("Date") or "")[:19].replace("T", " ")
        chunks.append(f"[{when}] {who}: {text[:600]}")
    blob = "\n".join(chunks)
    return blob[:max_chars]


def collect_similar_candidates(
    current_task_id: str | int,
    *,
    name: str = "",
    description: str = "",
    service_id: Any = None,
    exclude_ids: set[str] | None = None,
    max_candidates: int = 8,
) -> dict[str, Any]:
    """Широкий пул кандидатов по словам (ранжирует LLM, не этот скор)."""
    from related_tasks import find_similar_tasks, keywords_from_text

    cur = str(current_task_id).strip()
    excl = set(exclude_ids or ())
    excl.add(cur)
    # берём больше кандидатов, без жёсткого порога score
    base = find_similar_tasks(
        cur,
        name=name,
        description=description,
        service_id=service_id,
        page_size=15,
        max_hits=12,
    )
    # ослабить фильтр: пересобрать из keywords вручную если пусто
    rows = list(base.get("similar") or [])
    if len(rows) < 4:
        from related_tasks import keywords_from_text as _kws

        kws = _kws(name, (description or "")[:500], limit=8)
        by_id: dict[str, dict[str, Any]] = {str(r.get("Id")): r for r in rows}
        for q in kws[:5]:
            try:
                hits = intraservice.search_tasks(q, page_size=12)
            except Exception:
                continue
            for hit in hits:
                hid = str(hit.get("Id") or "")
                if not hid or hid in excl or hid in by_id:
                    continue
                by_id[hid] = {
                    "Id": hit.get("Id"),
                    "Name": hit.get("Name"),
                    "Created": hit.get("Created"),
                    "StatusId": hit.get("StatusId"),
                    "ServiceId": hit.get("ServiceId"),
                    "url": hit.get("url") or intraservice.task_url(hid),
                    "matched_by": [q],
                }
        rows = list(by_id.values())
    # фразы-намерения из описания (повышают шанс найти ту же суть)
    intent_qs: list[str] = []
    low = f"{name}\n{description}".lower()
    if re.search(r"склад", low) and re.search(r"(лк|личн\w*\s+кабинет|каталог|не\s+виж|пропал|отображ)", low):
        intent_qs.extend(
            [
                "склады контрагента",
                "не вижу склады ЛК",
                "пропали склады личный кабинет",
                "отображение складов ЛК",
            ]
        )
    if re.search(r"(?i)mailer@iek|products/api|api\s+каталог|сервис\s+api", low):
        intent_qs.extend(
            [
                "API каталога ЛК",
                "mailer@iek.ru",
                "products/api join",
                "регистрация API каталог",
            ]
        )
    by_id2: dict[str, dict[str, Any]] = {str(r.get("Id")): r for r in rows}
    for q in intent_qs:
        try:
            hits = intraservice.search_tasks(q, page_size=10)
        except Exception:
            continue
        for hit in hits:
            hid = str(hit.get("Id") or "")
            if not hid or hid in excl or hid in by_id2:
                continue
            by_id2[hid] = {
                "Id": hit.get("Id"),
                "Name": hit.get("Name"),
                "Created": hit.get("Created"),
                "StatusId": hit.get("StatusId"),
                "ServiceId": hit.get("ServiceId"),
                "url": hit.get("url") or intraservice.task_url(hid),
                "matched_by": [q],
                "score": 3,
            }
    rows = list(by_id2.values())
    # подтянуть описания для LLM
    enriched: list[dict[str, Any]] = []
    for row in rows:
        hid = str(row.get("Id") or "")
        if not hid or hid in excl:
            continue
        item = dict(row)
        try:
            full = intraservice.get_task(hid)
            item["Description"] = str(full.get("Description") or "")[:900]
            item["Name"] = full.get("Name") or item.get("Name")
            item["topic"] = topic_from_task(
                name=str(item.get("Name") or ""),
                description=str(item.get("Description") or ""),
            )
        except Exception:
            item["Description"] = ""
            item["topic"] = topic_from_task(name=str(item.get("Name") or ""))
        enriched.append(item)
        if len(enriched) >= max_candidates:
            break
    return {
        "ok": True,
        "keywords": base.get("keywords") or [],
        "candidates": enriched,
    }


ChatFn = Callable[..., tuple[str, dict[str, Any]]]


def rank_similar_by_llm(
    *,
    model: str,
    chat: ChatFn,
    current: dict[str, Any],
    thread: str,
    candidates: list[dict[str, Any]],
    task_id: str | int,
    profile_key: str = "",
    openwebui_hint: str = "",
) -> dict[str, Any]:
    """LLM выбирает заявки с той же сутью проблемы (не общим словом «склад»)."""
    if not candidates:
        return {"ok": True, "similar": [], "raw": "", "reason": "нет кандидатов"}
    catalog = []
    for c in candidates:
        catalog.append(
            {
                "id": c.get("Id"),
                "name": c.get("Name"),
                "topic": c.get("topic"),
                "description": (c.get("Description") or "")[:500],
                "url": c.get("url"),
            }
        )
    cur_blob = (
        f"#{current.get('Id')} {current.get('Name')}\n"
        f"{(current.get('Description') or '')[:1200]}\n"
        f"Переписка:\n{(thread or '')[:1500]}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "Ты аналитик HelpDesk IEK. Нужны заявки с ТЕМ ЖЕ смыслом проблемы, "
                "не с общим словом в теме. Пример: «не видно складов в каталоге ЛК» "
                "≠ «остатки API» ≠ «инструкция создания пользователя» ≠ «остатки на складе в письме». "
                "Ответ СТРОГО JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                "Текущая заявка:\n"
                f"{cur_blob}\n\n"
                "Кандидаты:\n"
                f"{json.dumps(catalog, ensure_ascii=False)}\n\n"
                "Верни JSON:\n"
                "{\n"
                '  "picks": [\n'
                '    {"id": 123, "topic": "краткая тема своими словами", '
                '"why": "почему та же суть", "same_problem": true}\n'
                "  ]\n"
                "}\n"
                "Только same_problem=true, максимум 3. Если нет совпадений по смыслу — picks=[]."
            ),
        },
    ]
    content, meta = chat(
        model,
        messages,
        task_id=task_id,
        profile_key=profile_key,
        openwebui_hint=openwebui_hint,
        kind="similar_semantic",
    )
    picks: list[dict[str, Any]] = []
    try:
        raw = (content or "").strip()
        if "```" in raw:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if m:
                raw = m.group(1).strip()
        data = json.loads(raw)
        by_id = {str(c.get("Id")): c for c in candidates}
        for p in data.get("picks") or []:
            if not isinstance(p, dict) or not p.get("same_problem", True):
                continue
            pid = str(p.get("id") or "").strip()
            if pid not in by_id:
                continue
            src = by_id[pid]
            picks.append(
                {
                    "Id": src.get("Id"),
                    "Name": src.get("Name"),
                    "url": src.get("url"),
                    "topic": (p.get("topic") or src.get("topic") or "")[:120],
                    "why": (p.get("why") or "")[:160],
                    "Created": src.get("Created"),
                }
            )
            if len(picks) >= 3:
                break
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "similar": [],
            "raw": (content or "")[:800],
            "llm_meta": meta,
            "candidates": candidates,
        }
    return {
        "ok": True,
        "similar": picks,
        "raw": (content or "")[:800],
        "llm_meta": meta,
        "candidates_count": len(candidates),
    }


def format_similar_lines(similar: list[dict[str, Any]]) -> list[str]:
    if not similar:
        return ["Похожие заявки: по смыслу не найдены"]
    lines = ["Похожие заявки (по смыслу):"]
    for r in similar[:3]:
        topic = (r.get("topic") or r.get("Name") or "")[:100]
        why = (r.get("why") or "").strip()
        bit = f"• #{r.get('Id')} · {topic} · {r.get('url')}"
        if why:
            bit += f" — {why}"
        lines.append(bit)
    return lines


def load_draft_snippets(*, hint_text: str = "", limit: int = 4) -> list[dict[str, Any]]:
    """Локальные черновики статей — куски для промпта LLM."""
    if not DRAFTS_DIR.is_dir():
        return []
    words = {
        w.lower().replace("ё", "е")
        for w in re.findall(r"[A-Za-zА-Яа-яЁё0-9]{4,}", hint_text or "")
    }
    scored: list[tuple[int, Path]] = []
    for path in DRAFTS_DIR.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        low = text.lower().replace("ё", "е")
        score = sum(1 for w in words if w in low) if words else 0
        # lk-* чуть приоритетнее при словах про лк/склад
        if path.name.startswith("lk-") and any(w in words for w in ("склад", "лк", "партнер", "партнёр")):
            score += 2
        if path.name.startswith("lk-") and any(
            w in words for w in ("api", "mailer", "каталог", "письм", "авторизац")
        ):
            score += 3
        if score <= 0 and words:
            continue
        scored.append((score, path))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    out: list[dict[str, Any]] = []
    for score, path in scored[:limit]:
        text = path.read_text(encoding="utf-8")
        # title = first heading or filename
        title = path.stem
        m = re.search(r"^#\s+(.+)$", text, re.M)
        if m:
            title = m.group(1).strip()
        out.append(
            {
                "file": path.name,
                "title": title,
                "score": score,
                "excerpt": text[:900],
            }
        )
    return out


def format_kb_answer_lines(
    *,
    draft_text: str = "",
    kb_refs: list[dict[str, Any]] | None = None,
    article_links: list[str] | None = None,
    compact: bool = True,
) -> list[str]:
    """Блок для скрытого комментария: короткий ответ + ссылки (компактно)."""
    draft = (draft_text or "").strip()
    # убрать лишние переносы внутри ответа
    draft = re.sub(r"\s*\n+\s*", " ", draft).strip()
    refs = [r for r in (kb_refs or []) if isinstance(r, dict)]
    links = [u for u in (article_links or []) if str(u).strip()]
    if not draft and not refs and not links:
        return []
    if compact:
        lines: list[str] = []
        if draft:
            lines.append(f"Комментарий для заявителя: {draft[:420]}")
        link_bits: list[str] = []
        for r in refs[:3]:
            title = (r.get("title") or "статья").strip()[:60]
            url = (r.get("url") or "").strip()
            link_bits.append(f"{title} {url}".strip() if url else title)
        if not link_bits:
            for u in links[:3]:
                link_bits.append(u)
        if link_bits:
            lines.append("Ссылки: " + " · ".join(link_bits))
        return lines
    lines = ["Для открытого ответа:"]
    if draft:
        lines.append(f"Текст: «{draft[:500]}»")
    if refs:
        lines.append("Ссылки:")
        for r in refs[:4]:
            title = (r.get("title") or r.get("section") or "статья").strip()
            url = (r.get("url") or "").strip()
            why = (r.get("why") or r.get("section") or "").strip()
            bit = f"• {title}"
            if url:
                bit += f" · {url}"
            if why and why.lower() not in title.lower():
                bit += f" — {why[:120]}"
            lines.append(bit)
    elif links:
        lines.append("Ссылки:")
        for u in links[:4]:
            lines.append(f"• {u}")
    return lines


def compose_compact_digest(
    *,
    model: str,
    chat: ChatFn,
    task: dict[str, Any],
    parsed: dict[str, Any],
    facts: list[str],
    attach_meaning: str = "",
    ocr_text: str = "",
    prior: list[dict[str, Any]] | None = None,
    similar: list[dict[str, Any]] | None = None,
    task_id: str | int = "",
    profile_key: str = "",
    openwebui_hint: str = "",
) -> dict[str, Any]:
    """Один вызов IEK LLM: связная суть (без повторов OCR), урок из prior, короткий ответ."""
    prior = prior or []
    similar = similar or []
    prior_blob = []
    for r in prior[:3]:
        prior_blob.append(
            f"#{r.get('Id')} {(r.get('topic') or r.get('Name') or '')[:120]}"
        )
    similar_blob = []
    for r in similar[:1]:
        similar_blob.append(
            f"#{r.get('Id')} {(r.get('topic') or r.get('Name') or '')[:100]} — {(r.get('why') or '')[:80]}"
        )
    messages = [
        {
            "role": "system",
            "content": (
                "Ты редактор скрытого разбора HelpDesk IEK. Сжимай без потери смысла. "
                "Ответ СТРОГО JSON. Не пиши сырой OCR и UI-кнопки («Действия», «Перейти»). "
                "service_key: lk|bp|edi|other (edi = электронный обмен / заказ поставщику / 1С)."
            ),
        },
        {
            "role": "user",
            "content": (
                "Собери компактный разбор.\n"
                f"ServiceId HD: {task.get('ServiceId')} · профиль: {profile_key or '—'}\n"
                f"Название: {task.get('Name')}\n"
                f"Описание:\n{(task.get('Description') or '')[:1200]}\n"
                f"summary_ru: {parsed.get('summary_ru') or ''}\n"
                f"facts: {json.dumps(facts[:8], ensure_ascii=False)}\n"
                f"Смысл вложений: {(attach_meaning or '')[:800]}\n"
                f"Фрагменты OCR (не копировать дословно): {(ocr_text or '')[:600]}\n"
                f"Черновик ответа: {(parsed.get('public_reply_draft_ru') or '')[:600]}\n"
                f"Ранее: {'; '.join(prior_blob) or '(нет)'}\n"
                f"Похожие: {'; '.join(similar_blob) or '(нет)'}\n\n"
                "JSON:\n"
                "{\n"
                '  "narrative_ru": "2-4 предложения: суть+факты+скрин без повторов",\n'
                '  "prior_lesson_ru": "как решалось ранее: "уже решали/ускоряли … для этого партнёра", без #номеров и без фразы «по аналогичной заявке»; пустая если нет",\n'
                '  "similar_one_ru": "не заполнять (похожие выводим отдельным списком)",\n'
                '  "public_reply_ru": "2-3 предложения открытого ответа без воды",\n'
                '  "service_key": "lk|bp|edi|other"\n'
                "}"
            ),
        },
    ]
    content, meta = chat(
        model,
        messages,
        task_id=task_id,
        profile_key=profile_key,
        openwebui_hint=openwebui_hint,
        kind="compose_digest",
    )
    out: dict[str, Any] = {"ok": False, "llm_meta": meta, "raw": (content or "")[:600]}
    try:
        raw = (content or "").strip()
        if "```" in raw:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if m:
                raw = m.group(1).strip()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return out
        out.update(
            {
                "ok": True,
                "narrative_ru": str(data.get("narrative_ru") or "").strip()[:700],
                "prior_lesson_ru": str(data.get("prior_lesson_ru") or "").strip()[:280],
                "similar_one_ru": str(data.get("similar_one_ru") or "").strip()[:220],
                "public_reply_ru": str(data.get("public_reply_ru") or "").strip()[:420],
                "service_key": str(data.get("service_key") or "").strip().lower(),
            }
        )
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out
