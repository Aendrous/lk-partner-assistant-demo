# -*- coding: utf-8 -*-
"""Smoke: публичный ответ при просрочке не цитирует «спасибо» заявителя."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import overdue


def test_skips_user_thanks_as_prior() -> None:
    prior = "спасибо, завершаем тогда, надеюсь исправят ошибку…"
    assert overdue._is_user_closing_message(prior)
    out = overdue.format_overdue_public_comment(
        parsed={"has_kb_solution": True, "solution_steps_ru": ["Очистите кеш браузера."]},
        prior_public=prior,
        only_if_kb=True,
    )
    assert "спасибо" not in out.lower()
    assert "очистите кеш" in out.lower()


def test_bot_public_detected_for_antidup() -> None:
    text = "Добрый день!\n\nспасибо, завершаем тогда"
    assert overdue._is_bot_overdue_public(text)


if __name__ == "__main__":
    test_skips_user_thanks_as_prior()
    test_bot_public_detected_for_antidup()
    print("ok")
