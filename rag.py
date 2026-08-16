# -*- coding: utf-8 -*-
"""Простой RAG: релевантные разделы корпуса P-00…P-17 по ключевым словам."""
from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPT_PATH = HERE / "prompt.md"
CORPUS_PATH = HERE / "knowledge" / "corpus.md"

ALWAYS_INCLUDE = ("P-08",)


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def load_corpus() -> str:
    if not CORPUS_PATH.exists():
        return ""
    return CORPUS_PATH.read_text(encoding="utf-8")


def split_sections(corpus: str) -> list[tuple[str, str]]:
    parts = re.split(r"\n---+\n", corpus)
    sections: list[tuple[str, str]] = []
    for part in parts:
        text = part.strip()
        if not text:
            continue
        title = text.splitlines()[0].lstrip("# ").strip()[:80]
        sections.append((title, text))
    return sections


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[а-яёa-z0-9]{3,}", text.lower()) if t}


ALIASES = {
    "история": "трекинг",
    "новыйзаказ": "каталог",
    "неудовлетворенный": "нс",
    "неудовлетворённый": "нс",
    "отгрузк": "подтвержден",
    "счета": "подтвержден",
    "пароль": "вход",
    "логин": "вход",
    "сотрудник": "профиль",
    "маркиров": "честный",
}


def retrieve(question: str, k: int = 5) -> str:
    corpus = load_corpus()
    sections = split_sections(corpus)
    if not sections:
        return corpus
    q = question.lower()
    for src, dst in ALIASES.items():
        if src in q:
            q += " " + dst
    q_tokens = _tokens(q)
    scored: list[tuple[float, str, str]] = []
    for title, body in sections:
        blob = (title + "\n" + body).lower()
        score = 0.0
        for tok in q_tokens:
            if tok in blob:
                score += 2.0 if tok in title.lower() else 1.0
        if any(tag.lower() in title.lower() for tag in ALWAYS_INCLUDE):
            score += 0.5
        scored.append((score, title, body))
    scored.sort(key=lambda x: x[0], reverse=True)
    picked: list[str] = []
    for score, title, body in scored:
        if score <= 0 and len(picked) >= 2:
            continue
        picked.append(body)
        if len(picked) >= k:
            break
    if not picked:
        return "\n\n".join(s[1] for s in sections[:k])
    return "\n\n---\n\n".join(picked)


def system_prompt(question: str) -> str:
    context = retrieve(question)
    return (
        load_prompt()
        + "\n\n--- КОРПУС ИНСТРУКЦИЙ (отвечай только по нему) ---\n\n"
        + context
    )
