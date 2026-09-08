# -*- coding: utf-8 -*-
"""Структурированный KB_INSERT: сценарий + ключевые слова + шаги (не отписка заявителю)."""
from __future__ import annotations

import re
from typing import Any

import kb_gap_llm

# Фразы «открытого ответа», не годятся как единственное содержимое KB
_PUBLIC_REPLY_MARKERS = re.compile(
    r"спасибо\s+за\s+сообщен|благодарим\s+за\s+сообщен|ожидайте\s+обновлен|"
    r"мы\s+проверим\s+логику|в\s+ближайшее\s+время|с\s+уважением|служба\s+поддержки",
    re.I,
)

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "price_question": [
        "цена в ЛК",
        "прайс-лист",
        "постоплата",
        "скидка",
        "базовая цена",
        "расхождение цены",
    ],
    "inventory_display": [
        "остатки",
        "расхождение ЛК и 1С",
        "кол-во 0",
        "неактивно поле количество",
        "заблокированный остаток",
        "синхронизация остатков",
        "количество на блоке",
        "поверка",
        "каталог 3.0",
        "каталог 2.0",
    ],
    "ns_reserve": ["резерв в пути", "галка", "подтверждение ЛК"],
    "order_issue": ["трекинг", "счёт", "счет", "заказ", "1С", "null", "ЭКС-"],
    "login": ["вход", "пароль", "IEK ID"],
    "warehouse": ["склады контрагента", "не видит склад", "каталог складов"],
}

_CATEGORY_SCENARIO: dict[str, str] = {
    "inventory_display": (
        "В ЛК количество 0 / поле «Кол-во» неактивно, при этом в 1С по артикулу "
        "есть свободный и/или заблокированный остаток."
    ),
    "warehouse": (
        "Партнёр не видит нужные склады в каталоге ЛК (настройка складов не помогает)."
    ),
    "price_question": (
        "Партнёр спрашивает, корректна ли цена артикула в ЛК (часто путает цену "
        "по постоплате/скидке и базовую цену в прайсе)."
    ),
}


_MENTION_LINE = re.compile(r"^\s*@\S+", re.M)
_INTERNAL_HD_LINE = re.compile(
    r"(?i)^(?:добавляю в заявку|проверяю в\s+(?:лк|1с|1c)|партнер\s+\S+|"
    r"добрый день[!,.]?|здравствуйте[!,.]?|спасибо[,!]?|ticket is automatically)\s*$"
)


_SKIP_LINE = re.compile(
    r"(?i)(?:^|\s)(?:добрый день|здравствуйте|проверяю\s+в\s+(?:лк|1с|1c)|"
    r"партнер\s+\S+|добавляю\s+в\s+заявку|ticket is automatically|спасибо[!,.]?|"
    r"если больше не напишу)"
)
_NOISE_LINE = re.compile(
    r"(?i)(?:внимание,?\s*внешнее сообщение|угрозами шифрования|"
    r"не переходите по ссылкам|не открывайте вложения|"
    r"^отбой!?$|без моей личной просьбы|заказы не проводите)"
)


def sanitize_resolution_for_kb(text: str) -> str:
    """Обезличить сырой публичный комментарий HD для блока KB (без @, ФИО, служебного)."""
    t = kb_gap_llm.strip_emails((text or "").strip())
    if not t:
        return ""
    kept: list[str] = []
    for line in t.splitlines():
        s = line.strip()
        if not s:
            continue
        if _MENTION_LINE.match(s):
            continue
        if _NOISE_LINE.search(s):
            continue
        if "@" in s:
            s = re.sub(r"@\S+", "", s).strip(" ,;")
            if not s:
                continue
        if _INTERNAL_HD_LINE.match(s) or _SKIP_LINE.search(s):
            continue
        s = re.sub(r'^[-•]\s*', '', s).strip()
        if len(s) < 12 and not re.search(r"\d", s):
            continue
        kept.append(s)
    if not kept:
        return ""
    # Кратко: маркированный список, не сплошной абзац
    return "\n".join(f"- {s}" for s in kept[:6])


def sanitize_kb_insert_for_promote(insert: str) -> str:
    """Финальная очистка KB_INSERT перед append в «Быстрые ответы»."""
    text = (insert or "").strip()
    if not text:
        return text
    # Секция «Из решения исполнителя» — не тащить сырой тред
    m = re.search(
        r"(?is)(^\*\*Из решения исполнителя:\*\*\s*\n)(.+?)(?=\n\*\*|\n_Источник:|$)",
        text,
    )
    if m:
        head, body = m.group(1), m.group(2)
        clean = sanitize_resolution_for_kb(body)
        if clean:
            text = text[: m.start()] + head + clean + text[m.end() :]
        else:
            text = text[: m.start()] + text[m.end() :]
    # Убрать оставшиеся @строки и служебные реплики в любом месте
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if _MENTION_LINE.match(s):
            continue
        if _INTERNAL_HD_LINE.match(s) or _SKIP_LINE.search(s):
            continue
        if "@" in line:
            line = re.sub(r"@\S+", "", line).rstrip()
            s = line.strip()
            if not s:
                continue
        lines.append(line)
    return "\n".join(lines).strip()


def is_weak_kb_insert(text: str) -> bool:
    """Отписка заявителю или пустой текст — не годится в «Быстрые ответы»."""
    t = (text or "").strip()
    if not t or t == "_(нет текста — LLM вернул skip/пусто)_":
        return True
    if len(t) < 120 and _PUBLIC_REPLY_MARKERS.search(t):
        return True
    # одна вежливая фраза без структуры сценария
    has_structure = any(
        x in t.lower()
        for x in (
            "**сценарий:**",
            "**проблема:**",
            "**ключевые слова:**",
            "**проверка",
            "**не путать",
            "1.",
            "- ",
        )
    )
    if _PUBLIC_REPLY_MARKERS.search(t) and not has_structure:
        return True
    return False


def _keywords(category: str, facts: list[str], summary: str) -> list[str]:
    cat = (category or "").strip().lower()
    base = list(_CATEGORY_KEYWORDS.get(cat, []))
    blob = " ".join(facts + [summary]).lower()
    if "1с" in blob or "1c" in blob:
        base.append("1С")
    if "остат" in blob:
        base.append("остатки")
    if "артикул" in blob or re.search(r"[a-z]{2,}\d{2,}", blob, re.I):
        base.append("артикул")
    if "склад" in blob and cat != "inventory_display":
        base.append("склады")
    # уникальные, до 8
    out: list[str] = []
    for w in base:
        w = w.strip()
        if w and w.lower() not in {x.lower() for x in out}:
            out.append(w)
        if len(out) >= 8:
            break
    return out or ["личный кабинет", "ЛК"]


def _scenario_line(
    *,
    summary: str,
    category: str,
    facts: list[str],
    supplement_of: str,
) -> str:
    cat = (category or "").strip().lower()
    if cat in _CATEGORY_SCENARIO:
        line = _CATEGORY_SCENARIO[cat]
    elif summary:
        line = kb_gap_llm.strip_emails(summary)[:300]
    elif facts:
        line = kb_gap_llm.strip_emails(facts[0])[:300]
    else:
        line = "См. факты заявки и категорию."
    if supplement_of:
        return (
            f"{line} "
            f"(дополнение к {supplement_of}; проверьте, что это тот же сценарий, "
            f"а не другой кейс с похожими словами)."
        )
    return line


def _not_confused_with(supplement_of: str, category: str) -> str:
    if supplement_of.upper() == "LK-10" and category == "inventory_display":
        return (
            "**Не путать с LK-10:** там про список складов в каталоге (регистр "
            "«Склады контрагента»), а не про расхождение остатков по артикулу."
        )
    if supplement_of:
        return f"**Не путать с {supplement_of}:** убедитесь, что сценарий совпадает."
    return ""


def _executor_steps(category: str, facts: list[str]) -> list[str]:
    cat = (category or "").strip().lower()
    blob = " ".join(facts).lower()
    if cat == "inventory_display":
        steps = [
            "Сверить в 1С: свободный vs заблокированный остаток по артикулу и складу.",
            "Проверить синхронизацию остатков ЛК ↔ 1С (не только «Склады контрагента»).",
            "Исключить заказную продукцию, кратность, блокировки (LK-06, WEBKB).",
        ]
        if "блок" in blob or "поверк" in blob or "2.0" in blob or "3.0" in blob:
            steps.insert(
                1,
                "Если артикул с «количеством на блоке» (поверка): сравнить отображение "
                "каталога ЛК 2.0 (в скобках) vs 3.0 — остаток должен быть виден.",
            )
        steps.append(
            "Партнёру отвечать только после факта проверки, не обещать «скоро исправим» без результата.",
        )
        return steps
    if cat == "warehouse":
        return [
            "Проверить регистр «Склады контрагента» в 1С для контрагента партнёра.",
            "Сверить список складов в заявке с регистром; при необходимости — МРК.",
        ]
    if cat == "price_question":
        return [
            "Сверить цену артикула в ЛК (каталог) и в 1С: постоплата/скидка vs базовая в прайсе.",
            "Партнёру объяснить разницу, если цены разные по условиям — не копировать сырой тред HD.",
            "Не эскалировать без проверки: часто ошибки нет, нужно пояснение по прайсу.",
        ]
    if cat == "order_issue":
        return [
            "Сверить заказ в ЛК (трекинг) и статус/счёт в 1С — номер счёта не должен быть null.",
            "Проверить кэш браузера, смену учётки; при сбое отображения — перезагрузка/инкогнито.",
            "Если счёт в 1С не сформирован — эскалация по процессу ЛК↔1С, не обещать срок без факта.",
        ]
    steps: list[str] = []
    for f in facts[:3]:
        s = kb_gap_llm.strip_emails(f)
        if s and len(s) > 20:
            steps.append(f"Учесть факт: {s[:180]}")
    if not steps:
        steps.append("Сверить описание заявки с решением исполнителя и Confluence.")
    return steps[:5]


def build_structured_insert(
    *,
    summary: str = "",
    category: str = "",
    facts: list[str] | None = None,
    supplement_of: str = "",
    resolution: str = "",
    learn_lesson: str = "",
    code: str = "",
) -> str:
    """Текст для KB_INSERT: понятен человеку и индексируется по ключевым словам."""
    clean_facts = kb_gap_llm.sanitize_facts(facts or [])
    scenario = _scenario_line(
        summary=summary,
        category=category,
        facts=clean_facts,
        supplement_of=supplement_of,
    )
    kw = _keywords(category, clean_facts, summary)
    lines = [
        f"**Сценарий:** {scenario}",
        f"**Ключевые слова:** {', '.join(kw)}.",
    ]
    nc = _not_confused_with(supplement_of, category)
    if nc:
        lines.append(nc)
    lines.append("")
    lines.append("**Проверка исполнителя:**")
    for i, step in enumerate(_executor_steps(category, clean_facts), 1):
        lines.append(f"{i}. {step}")
    res = sanitize_resolution_for_kb((resolution or "").strip())
    if res and not is_weak_kb_insert(res):
        lines.append("")
        lines.append("**Из решения исполнителя:**")
        lines.append(res[:800])
    elif res and is_weak_kb_insert(res):
        lines.append("")
        lines.append(
            "**Открытый ответ:** не копировать шаблон «спасибо, проверим» в KB — "
            "только после факта проверки, конкретика по результату."
        )
    lesson = kb_gap_llm.strip_emails((learn_lesson or "").strip())
    if lesson:
        lines.append("")
        lines.append(f"**Урок:** {lesson[:400]}")
    if code:
        lines.append("")
        lines.append(f"_Источник: {code}._")
    return "\n".join(lines).strip()


def enrich_insert_from_draft(md: str, insert: str) -> str:
    """Если insert слабый — собрать из секции «Контекст заявки» черновика."""
    if not is_weak_kb_insert(insert):
        return insert.strip()
    meta = parse_draft_context(md)
    return build_structured_insert(
        summary=meta.get("summary", ""),
        category=meta.get("category", ""),
        facts=meta.get("facts") or [],
        supplement_of=meta.get("supplement_of", ""),
        resolution=insert,
        learn_lesson=meta.get("learn_lesson", ""),
        code=meta.get("code", ""),
    )


def parse_draft_context(md: str) -> dict[str, Any]:
    """Вытащить метаданные из markdown черновика для enrich."""
    out: dict[str, Any] = {}
    m = re.search(r"(?im)^#\s+(?:Черновик|Дополнение):\s*([A-Z0-9+-]+)", md or "")
    if m:
        out["code"] = m.group(1).strip()
    m = re.search(r"\*\*Контур:\*\*\s*(\w+).*?\*\*Категория:\*\*\s*(\S+)", md or "")
    if m:
        out["contour"] = m.group(1)
        out["category"] = m.group(2)
    m = re.search(r"дополнение к\s+([A-Z0-9-]+)", md or "", re.I)
    if m:
        out["supplement_of"] = m.group(1).upper()
    facts: list[str] = []
    in_facts = False
    for line in (md or "").splitlines():
        if line.strip().startswith("**Проблема / факты:**"):
            in_facts = True
            continue
        if in_facts:
            if line.startswith("**") and not line.strip().startswith("- "):
                break
            if line.strip().startswith("- "):
                facts.append(line.strip()[2:].strip())
    out["facts"] = facts
    if facts:
        out["summary"] = facts[0]
    m = re.search(r"\*\*Урок для KB:\*\*\s*(.+)", md or "")
    if m:
        out["learn_lesson"] = m.group(1).strip()
    return out
