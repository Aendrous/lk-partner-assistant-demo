# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import kb_drafts_ui as ui  # noqa: E402


def test_resolve_team():
    assert ui.resolve_team("lk") == "lk"
    assert ui.resolve_team("1c") == "edi"
    assert ui.resolve_team("mail") == "other"


def test_filter_team():
    rows = [
        ui.enrich_entry({"service_key": "lk", "code": "LK-1"}),
        ui.enrich_entry({"service_key": "bp", "code": "BP-1"}),
    ]
    assert len(ui.filter_team(rows, "lk")) == 1
    assert len(ui.filter_team(rows, "all")) == 2


if __name__ == "__main__":
    test_resolve_team()
    test_filter_team()
    print("ok")
