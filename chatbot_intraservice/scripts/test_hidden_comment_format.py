# -*- coding: utf-8 -*-
"""Smoke: формат преданализа — Контекст/Похожее одной строкой, Рекомендации только при проблемах."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sys
import types

# llm_client.py потерян локально — подставляем stub только для unit-теста
def _make_llm_client_stub() -> None:
    if "llm_client" in sys.modules:
        return
    m = types.ModuleType("llm_client")
    m.has_credentials = lambda: False
    m.base_url = lambda: "http://localhost:9999"
    m._headers = lambda: {}
    m.resolve_model = lambda model=None, **kw: model or "iek/gpt-oss-120b"
    m.DEFAULT_SUPPORT_MODEL = "iek/gpt-oss-120b"
    m.is_invalid_model_error = lambda *a, **k: False
    sys.modules["llm_client"] = m

_make_llm_client_stub()

import analyze_and_comment as ac  # noqa: E402


def _task(lesson="По аналогичной заявке ранее уже ускоряли сроки для ЭТМ"):
    return {
        "_prior_lesson_ru": lesson,
        "_prior": {"prior": [{"Id": 684543, "topic": "сроки ЭТМ"}]},
        "_similar": {
            "similar": [
                {"Id": 684543, "topic": "прокачать сроки ЭТМ"},
                {"Id": 697548, "topic": "прокачать сроки ЭТМ"},
                {"Id": 657359, "topic": "сроки по заказам ЭТМ"},
                {"Id": 664441, "topic": "Сроки по заказам ЭТМ"},
            ]
        },
    }


def test_compact_prior_similar() -> None:
    (line,) = ac._compact_prior_similar(_task())
    # одна строка, без #номеров в тексте, 4 ссылки (1 контекст + 3 похожие)
    assert line.count("hd.iek.group/Task/View") == 4, line
    assert "#684543" not in line, line
    assert line.startswith("Ранее от заявителя - "), line
    assert "Похожее:" in line, line
    assert line.count("View/684543") == 1, line


def test_no_duplicate_with_context() -> None:
    t = _task(lesson="ранее уже ускоряли сроки для другого партнёра")
    t["_prior"]["prior"] = [{"Id": 111111, "topic": "x"}]
    t["_similar"]["similar"] = [
        {"Id": 697548, "topic": "a"},
        {"Id": 657359, "topic": "b"},
        {"Id": 664441, "topic": "c"},
    ]
    (line,) = ac._compact_prior_similar(t)
    assert "View/111111" in line, line
    for i in (697548, 657359, 664441):
        assert f"View/{i}" in line, line


def test_recommendations_empty_when_ok() -> None:
    recs = ac._build_recommendations({
        "service_ok": True, "type_ok": True, "priority_ok": True,
        "suggest_service_id": None, "suggest_type_id": None, "suggest_priority_id": None,
    })
    assert recs == []


def test_recommendations_when_mismatch() -> None:
    recs = ac._build_recommendations({
        "service_ok": True, "type_ok": False, "priority_ok": False,
        "suggest_service_id": None, "suggest_type_id": 1008, "type_note": "",
        "suggest_priority_id": 11, "priority_why": "стандартный",
    })
    assert any("тип →" in r for r in recs), recs
    assert any("важность →" in r for r in recs), recs

    recs2 = ac._build_recommendations({
        "service_ok": False, "type_ok": True, "priority_ok": True,
        "suggest_service_id": 69, "contour_expected": "edi", "note": "по смыслу 1С",
        "suggest_type_id": None, "suggest_priority_id": None,
    })
    assert any("сервис → 69" in r for r in recs2), recs2


if __name__ == "__main__":
    test_compact_prior_similar()
    test_no_duplicate_with_context()
    test_recommendations_empty_when_ok()
    test_recommendations_when_mismatch()
    print("ok: test_hidden_comment_format")
