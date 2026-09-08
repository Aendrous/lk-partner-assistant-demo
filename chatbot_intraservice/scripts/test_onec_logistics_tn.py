# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import assistants  # noqa: E402


def test_logistics_tn_detection():
    assert assistants.is_logistics_tn_task(
        {"Name": "Не выгружается транспортная накладная", "Description": ""}
    )
    assert assistants.is_logistics_tn_task(
        {"Name": "Не выгружается ТН на контрагента", "Description": "Оят ТН938310"}
    )
    assert not assistants.is_logistics_tn_task(
        {"Name": "Почему CLP1C попала в НС", "Description": "заказ ХИ01094387"}
    )


def test_scope_routing():
    tn = {"Name": "Не выгружается ТН", "Description": "", "ServiceId": 69}
    ns = {"Name": "Почему попала в НС", "Description": "CLP1C", "ServiceId": 69}
    cfg = {"onec_analyze_scope": "logistics_tn"}
    assert assistants.choose_for_task(tn, cfg).key == "onec_logistics_tn"
    assert assistants.skip_onec_out_of_scope(ns, cfg)
    assert assistants.choose_for_task(ns, {"onec_analyze_scope": "all"}).key == "onec_tickets"


def test_skip_onec_task():
    change = {"Name": "Изменить даты", "ServiceId": 69, "TypeId": 1010, "StatusId": 31}
    in_progress = {"Name": "Провести документ", "ServiceId": 69, "TypeId": 1009, "StatusId": 27}
    ok = {"Name": "Провести документ", "ServiceId": 69, "TypeId": 1009, "StatusId": 38}
    assert assistants.skip_onec_task(change)
    assert assistants.skip_onec_task(in_progress)
    assert not assistants.skip_onec_task(ok)
    # не-1С заявку «изменение» не трогаем
    assert not assistants.skip_onec_task({"Name": "x", "ServiceId": 731, "TypeId": 1010, "StatusId": 31})


if __name__ == "__main__":
    test_logistics_tn_detection()
    test_scope_routing()
    test_skip_onec_task()
    print("ok")
