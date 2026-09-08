# -*- coding: utf-8 -*-
"""Тесты маппинга closure_taxonomy."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import closure_taxonomy as ct  # noqa: E402


def test_ns_maps_to_order():
    parsed = {"category": "NS", "service_key": "1c", "has_kb_solution": False}
    opt, _ = ct.map_closure_type_id(parsed)
    assert opt == "2031"


def test_kb_prefers_instruction_type():
    parsed = {"category": "NS", "service_key": "1c", "has_kb_solution": True}
    opt, _ = ct.map_closure_type_id(parsed)
    assert opt == "1460"


def test_contour_line_with_stage_cause():
    parsed = {
        "category": "STOCK_NEGATIVE",
        "error_stage_ru": "при проведении УПД",
        "root_cause_ru": "асинхронность создания резервирований",
        "has_kb_solution": False,
    }
    line = ct.build_contour_line("edi", parsed, contour_label="EDI / 1С")
    assert "этап: при проведении УПД" in line
    assert "причина: асинхронность" in line


def test_field3061_instruction_over_category():
    parsed = {
        "category": "NS",
        "has_kb_solution": True,
        "kb_refs": [{"url": "https://confluence.dev.iek.ru/x", "title": "t"}],
    }
    plan = ct.build_hd_field_payload(parsed)
    assert plan["fields"]["Field3061"].startswith("https://confluence")
    assert plan["fields"]["Field2229"] == "1460"


def test_field3061_category_without_url():
    parsed = {"category": "NS", "has_kb_solution": False, "kb_refs": []}
    plan = ct.build_hd_field_payload(parsed)
    assert plan["fields"]["Field3061"] == "NS"
    assert plan["fields"]["Field2229"] == "2031"


if __name__ == "__main__":
    test_ns_maps_to_order()
    test_kb_prefers_instruction_type()
    test_contour_line_with_stage_cause()
    test_field3061_instruction_over_category()
    test_field3061_category_without_url()
    print("ok")
