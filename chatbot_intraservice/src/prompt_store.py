# -*- coding: utf-8 -*-
"""Редактируемые промпты и корпуса для HD-бота (файлы на диске + UI Streamlit).

Сборка system/user для IEK LLM: scripts/analyze_and_comment.py → build_messages.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

PKG = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PromptAsset:
    key: str
    title: str
    path: Path
    kind: str  # prompt | corpus | rules
    profile_key: str = ""
    max_chars_hint: int = 0


def _assets() -> list[PromptAsset]:
    return [
        PromptAsset(
            "rules_exec",
            "Правила: разбор заявки для исполнителя",
            PKG / "docs" / "правила" / "разбор_заявки_для_исполнителя.md",
            "rules",
        ),
        PromptAsset(
            "rules_l1",
            "Правила 1 линии (фрагмент в system)",
            PKG / "docs" / "правила" / "правила_1_линии.md",
            "rules",
            max_chars_hint=6000,
        ),
        PromptAsset(
            "system_footer",
            "Хвост system («Важно: …»)",
            PKG / "knowledge" / "prompts" / "system_footer.md",
            "prompt",
        ),
        PromptAsset(
            "user_schema",
            "User: схема JSON-ответа LLM",
            PKG / "knowledge" / "prompts" / "user_schema.md",
            "prompt",
        ),
        PromptAsset(
            "system_l1_web",
            "System extra · ЛК / WEB (l1_web)",
            PKG / "knowledge" / "prompts" / "system_l1_web.md",
            "prompt",
            profile_key="l1_web",
        ),
        PromptAsset(
            "system_bp",
            "System extra · БП (bp_tickets)",
            PKG / "knowledge" / "prompts" / "system_bp_tickets.md",
            "prompt",
            profile_key="bp_tickets",
        ),
        PromptAsset(
            "system_1c",
            "System extra · 1С (onec_tickets)",
            PKG / "knowledge" / "prompts" / "system_onec_tickets.md",
            "prompt",
            profile_key="onec_tickets",
        ),
        PromptAsset(
            "system_1c_logistics_tn",
            "System extra · 1С ТН логистика (onec_logistics_tn)",
            PKG / "knowledge" / "prompts" / "system_onec_logistics_tn.md",
            "prompt",
            profile_key="onec_logistics_tn",
        ),
        PromptAsset(
            "corpus_1c_logistics_tn",
            "Корпус 1С · выгрузка ТН",
            PKG / "knowledge" / "1c" / "corpus_logistics_tn.md",
            "corpus",
            profile_key="onec_logistics_tn",
            max_chars_hint=8000,
        ),
        PromptAsset(
            "system_crm",
            "System extra · CRM (l1_crm)",
            PKG / "knowledge" / "prompts" / "system_l1_crm.md",
            "prompt",
            profile_key="l1_crm",
        ),
        PromptAsset(
            "corpus_lk",
            "Корпус ЛК",
            PKG / "knowledge" / "lk" / "corpus.md",
            "corpus",
            profile_key="l1_web",
            max_chars_hint=12000,
        ),
        PromptAsset(
            "corpus_bp",
            "Корпус БП",
            PKG / "knowledge" / "bp" / "corpus.md",
            "corpus",
            profile_key="bp_tickets",
            max_chars_hint=12000,
        ),
        PromptAsset(
            "corpus_1c",
            "Корпус 1С",
            PKG / "knowledge" / "1c" / "corpus.md",
            "corpus",
            profile_key="onec_tickets",
            max_chars_hint=12000,
        ),
        PromptAsset(
            "corpus_crm",
            "Корпус CRM",
            PKG / "knowledge" / "crm" / "corpus.md",
            "corpus",
            profile_key="l1_crm",
            max_chars_hint=12000,
        ),
    ]


def list_assets(*, kind: str | None = None) -> list[PromptAsset]:
    items = _assets()
    if kind:
        items = [a for a in items if a.kind == kind]
    return items


def get_asset(key: str) -> PromptAsset | None:
    for a in _assets():
        if a.key == key:
            return a
    return None


def read_asset(key: str) -> str:
    a = get_asset(key)
    if a is None or not a.path.is_file():
        return ""
    return a.path.read_text(encoding="utf-8")


def write_asset(key: str, text: str) -> Path:
    a = get_asset(key)
    if a is None:
        raise KeyError(f"unknown prompt asset: {key}")
    a.path.parent.mkdir(parents=True, exist_ok=True)
    a.path.write_text(text.replace("\r\n", "\n"), encoding="utf-8")
    return a.path


def system_extra_for(profile_key: str, fallback: str = "") -> str:
    """Текст system_extra из knowledge/prompts/system_*.md, иначе fallback из кода."""
    for a in _assets():
        if a.kind == "prompt" and a.profile_key == profile_key:
            if a.path.is_file():
                return a.path.read_text(encoding="utf-8").strip()
            break
    return (fallback or "").strip()


def load_system_footer() -> str:
    text = read_asset("system_footer").strip()
    if text:
        return text
    return (
        "Важно:\n"
        "- ServiceId 731/732 = ветка ЛК. EDI / заказ поставщику / электронный обмен → service_key=edi (1С).\n"
        "- «Письмо для API» + mailer@iek.ru = API каталога ЛК, НЕ bp.iek.ru API-ключ.\n"
        "- Учитывай блок «Предыдущие обращения».\n"
        "- public_reply_draft_ru — 2-3 предложения без воды.\n"
        "- kb_refs — только релевантные; similar_picks — только та же суть.\n"
        "- Не включай сырой OCR и UI-кнопки в facts.\n"
    )


def load_user_schema() -> str:
    text = read_asset("user_schema").strip()
    if text:
        return text
    return (
        "Разбери заявку для ИСПОЛНИТЕЛЯ. Учти описание, публичную переписку и предыдущие обращения. "
        "Ответ СТРОГО JSON:\n"
        "{\n"
        '  "understood": true/false,\n'
        '  "summary_ru": "1 короткое предложение — суть проблемы",\n'
        '  "service_key": "bp|lk|edi|kp|vpn|mail|crm|1c|other",\n'
        '  "category": "код категории (NS, ORDER, auth, API, OTHER …)",\n'
        '  "error_stage_ru": "где в БП: этап/раздел (1 фраза)",\n'
        '  "root_cause_ru": "техническая причина (1 фраза)",\n'
        '  "facts": ["2-5 фактов по сути — без #заявки, ServiceId и email (они уже в шапке)"],\n'
        '  "has_kb_solution": true/false,\n'
        '  "solution_steps_ru": ["1-3 шага для исполнителя, если есть KB"],\n'
        '  "public_reply_draft_ru": "готовый текст открытого ответа ИЛИ пустая строка",\n'
        '  "kb_refs": [{"title": "раздел", "url": "https://confluence.dev.iek.ru/...", "why": "..."}],\n'
        '  "article_links": ["только реальные confluence.dev.iek.ru — иначе []"],\n'
        '  "similar_picks": [{"id": 123, "topic": "...", "why": "...", "same_problem": true}] (до 3, только из кандидатов)\n'
        "}\n"
        "Не пиши missing_info / hidden_comment_ru. Нет KB → has_kb_solution=false, "
        "public_reply_draft_ru=\"\", kb_refs=[]. similar_picks: выбери до 3 (только из кандидатов)."
    )


def corpus_label(profile_key: str) -> str:
    return {
        "bp_tickets": "КОРПУС БП",
        "onec_tickets": "КОРПУС 1С",
        "onec_logistics_tn": "КОРПУС ТН 1С",
        "l1_web": "КОРПУС ЛК",
        "l1_crm": "КОРПУС CRM",
    }.get(profile_key, "КОРПУС")


def asset_meta() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for a in _assets():
        exists = a.path.is_file()
        size = a.path.stat().st_size if exists else 0
        out.append(
            {
                "key": a.key,
                "title": a.title,
                "kind": a.kind,
                "path": str(a.path.relative_to(PKG)).replace("\\", "/"),
                "exists": exists,
                "bytes": size,
                "profile_key": a.profile_key,
            }
        )
    return out
