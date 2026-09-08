# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import task_linking as tl  # noqa: E402


def test_crm_link_disabled():
    ok, reason = tl.link_enabled_for_task(
        {"link_related_by_contour": {"crm": False}},
        {"ServiceId": 29, "Name": "тендер"},
        {"service_key": "crm"},
    )
    assert not ok
    assert "CRM" in (reason or "")


def test_filter_same_day_open():
    current = {
        "Id": 700017,
        "Created": "2026-09-02T08:00:00",
        "ServiceId": 29,
        "StatusId": 38,
    }
    related = [
        {
            "Id": 700018,
            "Created": "2026-09-02T09:00:00",
            "ServiceId": 29,
            "StatusId": 38,
        },
        {
            "Id": 511706,
            "Created": "2024-09-10T13:33:04",
            "ServiceId": 29,
            "StatusId": 38,
        },
    ]
    kept, meta = tl.filter_for_linking(current, related, {})
    assert len(kept) == 1
    assert kept[0]["Id"] == 700018
    assert meta["rejected"] == 1


def test_crm_tokens_skip_guid():
    task = {"ServiceId": 29, "Name": "CRM"}
    refs = ["GUID ЛК 90fb26e1-7b6e-ef11-a308-00155d05e7de", "заказ Т260831"]
    toks = tl.tokens_for_linking(refs, task, {"service_key": "crm"})
    assert "90fb26e1-7b6e-ef11-a308-00155d05e7de" not in toks
    assert "Т260831" not in toks


if __name__ == "__main__":
    test_crm_link_disabled()
    test_filter_same_day_open()
    test_crm_tokens_skip_guid()
    print("ok")
