# -*- coding: utf-8 -*-
"""Smoke: watch_user_reply — подтверждение → 29, reopen → 38, nudge → 120."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import watch_common
import watch_user_reply


def test_gratitude_positive() -> None:
    assert watch_common.is_gratitude_resolved("спасибо, всё заработало")
    assert watch_common.is_gratitude_resolved("благодарю, проблема решена")
    assert watch_common.is_gratitude_resolved("ok thanks")
    assert watch_common.is_gratitude_resolved("Все провелось!Спасибо!")
    assert watch_common.is_gratitude_resolved("Спасибо, провели.")
    assert watch_common.is_gratitude_resolved("Спасибо, заявку можно закрывать. Заранее благодарю.")
    assert watch_common.is_gratitude_resolved("можно закрывать")
    assert watch_common.is_gratitude_resolved("Сергей заявку можно закрывать")


def test_gratitude_negative() -> None:
    assert not watch_common.is_gratitude_resolved("не помогло, ошибка осталась")
    assert not watch_common.is_gratitude_resolved("просто письмо")


def test_needs_executor() -> None:
    assert watch_common.is_needs_executor_attention("не помогло, ошибка осталась")
    assert watch_common.is_needs_executor_attention("заявка ещё актуальна, нужна помощь")
    assert not watch_common.is_needs_executor_attention("спасибо, всё заработало")
    assert not watch_common.is_needs_executor_attention("можно закрывать")
    # уточняющий вопрос НЕ возвращает исполнителю (#701381)
    assert not watch_common.is_needs_executor_attention("уточните, пожалуйста, срок поставки")
    assert not watch_common.is_needs_executor_attention("дополнительный вопрос по заявке")


def test_relevance_nudge() -> None:
    assert watch_common.is_relevance_nudge(
        "Добрый день\nподскажите, пожалуйста, по данной заявке требуются какие-то действия?"
    )
    assert watch_common.is_relevance_nudge("заявка ещё актуальна?")
    assert not watch_common.is_relevance_nudge("Добрый день\nпрошу попробовать провести")


def test_classify_priority() -> None:
    assert watch_user_reply.classify_user_reply("не помогло") == "needs_executor"
    assert watch_user_reply.classify_user_reply("спасибо, заработало") == "gratitude"
    assert watch_user_reply.classify_user_reply("можно закрывать") == "gratitude"
    assert watch_user_reply.classify_user_reply("просто письмо без сигнала") == "ignore"


def test_private_comments() -> None:
    assert "Пользователь подтвердил решение" in watch_user_reply._PRIVATE_CONFIRMED
    assert "Передано исполнителю" in watch_user_reply._PRIVATE_REOPEN
    text = watch_user_reply.private_autoclose_nudge_comment(hours=24, days=2)
    assert "24" in text
    assert "автозакрытием" in text.lower() or "Автозакрытие" in text


def test_find_nudge_gap() -> None:
    lifetime = {
        "TaskLifetimes": [
            {
                "Date": "2026-09-03T16:40:50",
                "IsPublic": True,
                "Editor": "Executor",
                "EditorId": 2,
                "Comments": "Добрый день по заказу нет остатков",
            },
            {
                "Date": "2026-09-04T13:01:44",
                "IsPublic": True,
                "Editor": "Executor",
                "EditorId": 2,
                "Comments": "подскажите, по данной заявке требуются какие-то действия?",
            },
        ]
    }
    hit = watch_common.find_executor_relevance_nudge(
        lifetime,
        min_hours_after_first_reply=20,
        max_age_hours=0,
        creator_id=1,
        creator_name="Requester",
        executor_ids="2",
    )
    assert hit is not None
    assert "требуются" in (hit.get("Comments") or "")

    too_soon = watch_common.find_executor_relevance_nudge(
        lifetime,
        min_hours_after_first_reply=48,
        max_age_hours=0,
        creator_id=1,
        creator_name="Requester",
        executor_ids="2",
    )
    assert too_soon is None


def test_client_side_not_only_creator() -> None:
    row = {
        "EditorId": 99,
        "Editor": "Жиганова Мария",
        "IsPublic": True,
        "Comments": "Все провелось!Спасибо!",
    }
    assert watch_common.is_client_side_comment(
        row, creator_id=1, creator_name="Пекут", executor_ids="2,3"
    )
    assert not watch_common.is_client_side_comment(
        row, creator_id=1, creator_name="Пекут", executor_ids="99"
    )


if __name__ == "__main__":
    test_gratitude_positive()
    test_gratitude_negative()
    test_needs_executor()
    test_relevance_nudge()
    test_classify_priority()
    test_private_comments()
    test_find_nudge_gap()
    test_client_side_not_only_creator()
    print("ok")
