# -*- coding: utf-8 -*-
"""Smoke: draft markdown без PII + contour pageId + KB_INSERT extract."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import kb_gap_llm  # noqa: E402
import kb_learning  # noqa: E402


def test_sanitize_facts() -> None:
    facts = [
        "CreatorEmail: tugusheva@smart-shop.pro",
        "Партнёр (email): tugusheva@smart-shop.pro",
        "ServiceId: 732",
        "Невозможно зайти в ЛК",
        "user@iek.ru пишет от имени партнёра",
    ]
    clean = kb_gap_llm.sanitize_facts(facts)
    assert clean == ["Невозможно зайти в ЛК"], clean
    assert "@" not in " ".join(clean)


def test_build_draft_no_email_contour_lk() -> None:
    task = {
        "Id": "695751",
        "Name": "не могу зайти в ЛК",
        "url": "https://helpdesk.iek.local/Task/View/695751",
        "Description": "Пишет tugusheva@smart-shop.pro",
    }
    analysis = {
        "parsed": {
            "service_key": "lk",
            "category": "auth",
            "summary_ru": "Не вход в ЛК",
            "facts": [
                "CreatorEmail: tugusheva@smart-shop.pro",
                "ServiceId: 732",
                "Невозможно зайти в ЛК",
            ],
        }
    }
    gap = {
        "mode": "supplement",
        "incomplete": True,
        "words_to_add": "Проверить логин/пароль и ссылку «Забыли пароль?» на странице входа.",
        "why_incomplete": "В статье нет шагов восстановления доступа.",
        "source_ticket_id": "695751",
    }
    dedup = {
        "mode": "supplement",
        "action": "create",
        "match_kind": "published",
        "code": "HD-09",
        "title": "Личный кабинет",
        "page_id": "124630073",  # junk — must be ignored
        "score": 0.25,
        "reason": "test",
        "source": "corpus:lk",
    }
    md, meta = kb_learning.build_draft_markdown(
        task,
        analysis,
        resolution_text="Пользователь не может войти. Написать: tugusheva@x.ru",
        service_key="lk",
        dedup=dedup,
        gap_judgment=gap,
    )
    assert "tugusheva@" not in md, "email leaked into draft"
    assert "CreatorEmail" not in md
    assert "ServiceId: 732" not in md
    assert "pageId=124630014" in md or meta["target_page_id"] == "124630014"
    assert meta["target_page_id"] == "124630014"
    assert "124630073" not in str(meta["target_page_id"])
    assert "KB_INSERT_START" in md
    assert "Решение IEK LLM" in md
    insert = kb_learning.extract_insert_sections(md)
    assert insert.strip()
    assert "**" in insert
    assert "@" not in insert


def test_merge_in_place() -> None:
    old = "# Черновик: HD-09 — Fwd: Личный кабинет\n\nСтарое тело.\n"
    task = {"Id": "695751", "url": "https://helpdesk.iek.local/Task/View/695751"}
    gap = {
        "mode": "supplement",
        "incomplete": True,
        "words_to_add": "Добавить шаг: восстановление пароля.",
        "why_incomplete": "Нет шага восстановления.",
        "source_ticket_id": "695751",
    }
    new = kb_learning.merge_into_existing_draft(old, task=task, gap_judgment=gap, dedup={"reason": "x"})
    assert "Дополнение из HD#695751" in new
    assert "восстановление пароля" in new
    assert new.count("<!-- KB_INSERT_START -->") <= 1


if __name__ == "__main__":
    test_sanitize_facts()
    test_build_draft_no_email_contour_lk()
    test_merge_in_place()
    print("ok: test_kb_draft_quality")
