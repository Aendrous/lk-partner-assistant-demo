# -*- coding: utf-8 -*-
"""pick_resolution: приоритет ответа исполнителя, не заявителя."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import kb_learning as kl  # noqa: E402


def test_requester_vs_executor() -> None:
    lifetime = {
        "TaskLifetimes": [
            {
                "Date": "2026-09-01T12:18:28",
                "IsPublic": True,
                "Editor": "Гребенников Александр Николаевич",
                "Comments": "Здравствуйте!\r\nБыл глобальный сбой - проверьте сейчас.",
            },
            {
                "Date": "2026-09-01T12:26:23",
                "IsPublic": True,
                "Editor": "nesterova.d_favorit-el.ru",
                "Comments": "Внимание, внешнее сообщение!\r\nНет, так и не работает. Перезагружала",
            },
            {
                "Date": "2026-09-01T15:57:56",
                "IsPublic": True,
                "Editor": "Фетисов Андрей Анатольевич",
                "Comments": "Проблема передана на разработку",
            },
        ]
    }
    task = {"CreatorEmail": "nesterova.d@favorit-el.ru", "Description": "трекинг не грузится"}
    picked = kl.pick_resolution_text(task, [], None, lifetime=lifetime)
    assert "разработк" in picked.lower(), picked
    assert "не работает" not in picked.lower() or "разработк" in picked.lower()


def test_dev_transfer_short_wins() -> None:
    lifetime = {
        "TaskLifetimes": [
            {
                "Date": "2026-09-01T15:57:56",
                "IsPublic": True,
                "Editor": "Исполнитель IEK",
                "Comments": "Проблема передана на разработку",
            },
        ]
    }
    task = {"CreatorEmail": "partner@example.com", "Description": "x"}
    picked = kl.pick_resolution_text(task, [], None, lifetime=lifetime)
    assert "разработк" in picked.lower()


def test_performer_resolution_present() -> None:
    lifetime_with = {
        "TaskLifetimes": [
            {
                "Date": "2026-09-01T15:57:56",
                "IsPublic": True,
                "Editor": "Исполнитель IEK",
                "Comments": "Проблема передана на разработку",
            }
        ]
    }
    task = {"CreatorEmail": "partner@example.com", "Description": "x"}
    assert kl.performer_resolution_present(task, lifetime_with)
    assert not kl.performer_resolution_present(task, None)


def main() -> int:
    test_requester_vs_executor()
    test_dev_transfer_short_wins()
    test_performer_resolution_present()
    print("ok: test_pick_resolution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
