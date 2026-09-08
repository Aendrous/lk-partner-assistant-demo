# -*- coding: utf-8 -*-
"""Классификация HD: тип заявки, сервис, важность (идея Качанова)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import service_routing as sr  # noqa: E402


def test_incident_on_request_branch() -> None:
    task = {
        "ServiceId": 732,
        "TypeId": 1009,
        "PriorityId": 11,
        "Name": "ЛК",
        "Description": "Трекинг заказов не грузится, бесконечная загрузка",
    }
    check = sr.check_service(task, contour="lk")
    assert check["type_key"] == "incident"
    assert check["suggest_type_id"] == 1008
    assert check["suggest_service_id"] == 731
    assert check["service_ok"] is False
    assert check["suggest_priority_id"] == 10
    assert check["can_auto_priority"] is True
    line = sr.format_service_line(check)
    assert "инцидент" in line
    assert "731" in line
    assert "авто" in line


def test_prior_same_contour_no_contradiction() -> None:
    task = {
        "ServiceId": 732,
        "TypeId": 1009,
        "PriorityId": 11,
        "Name": "ЛК",
        "Description": "Не отображается счёт по заказу",
    }
    prior = [
        {"Id": 1, "ServiceId": 732, "TypeId": 1009, "PriorityId": 11},
        {"Id": 2, "ServiceId": 732, "TypeId": 1009, "PriorityId": 11},
    ]
    check = sr.check_service(task, contour="lk", prior=prior)
    assert check["contradiction"] is False
    assert check["type_ok"] is True
    assert check["service_ok"] is True


def test_prior_contradiction_lk_vs_bp() -> None:
    task = {
        "ServiceId": 732,
        "TypeId": 1009,
        "PriorityId": 11,
        "Name": "ЛК трекинг",
        "Description": "личный кабинет партнера трекинг заказов",
    }
    prior = [
        {"ServiceId": 833, "TypeId": 1009, "PriorityId": 11},
        {"ServiceId": 833, "TypeId": 1009, "PriorityId": 11},
    ]
    check = sr.check_service(task, contour="lk", prior=prior)
    assert check["contradiction"] is True
    assert check["can_auto_priority"] is False
    assert "prior" in (check.get("note") or "")


def test_never_downgrade_priority() -> None:
    task = {
        "ServiceId": 732,
        "TypeId": 1009,
        "PriorityId": 12,
        "Name": "вопрос",
        "Description": "как выгрузить отчёт",
    }
    check = sr.check_service(task, contour="lk")
    assert check["suggest_priority_id"] == 11
    assert check["can_auto_priority"] is False


def test_change_type() -> None:
    task = {
        "ServiceId": 833,
        "TypeId": 1009,
        "PriorityId": 11,
        "Name": "БП",
        "Description": "Добавить пользователя в бизнес-платформу и выдать права",
    }
    check = sr.check_service(task, contour="bp")
    assert check["type_key"] == "change"
    assert check["suggest_type_id"] == 1010


def test_critical_mass_outage() -> None:
    pid, why = sr.infer_priority_id("Глобальный сбой ЛК, у всех не работает", type_key="incident")
    assert pid == 12
    assert "критич" in why


def main() -> int:
    test_incident_on_request_branch()
    test_prior_same_contour_no_contradiction()
    test_prior_contradiction_lk_vs_bp()
    test_never_downgrade_priority()
    test_change_type()
    test_critical_mass_outage()
    print("ok: test_service_classification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
