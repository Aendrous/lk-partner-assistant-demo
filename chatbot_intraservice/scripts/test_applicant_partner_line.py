# -*- coding: utf-8 -*-
"""Строка «Заявитель / партнёр» только для контура ЛК."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def _load_analyze():
    spec = importlib.util.spec_from_file_location(
        "analyze_and_comment", ROOT / "scripts" / "analyze_and_comment.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_mrk_partner_line_only_for_lk():
    ac = _load_analyze()
    task = {"Id": 1, "ServiceId": 69, "_partner_emails": []}
    parsed_edi = {"service_key": "edi", "summary_ru": "Не выгружается ТН"}
    comment_edi = ac.format_hidden_comment(
        task,
        parsed_edi,
        {},
        {},
        creator_email="pajmushkinams@iek.ru",
        partner_emails_found=[],
    )
    assert "партнёр email не найден" not in comment_edi
    assert "Заявитель:" not in comment_edi

    parsed_lk = {"service_key": "lk", "summary_ru": "Резерв в пути"}
    comment_lk = ac.format_hidden_comment(
        task,
        parsed_lk,
        {},
        {},
        creator_email="pajmushkinams@iek.ru",
        partner_emails_found=[],
    )
    assert "Заявитель: pajmushkinams@iek.ru (МРК) · партнёр email не найден" in comment_lk


if __name__ == "__main__":
    test_mrk_partner_line_only_for_lk()
    print("ok")
