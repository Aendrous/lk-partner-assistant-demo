# -*- coding: utf-8 -*-
"""Тест learn_llm: модель и rejection context."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import learn_llm  # noqa: E402


def main() -> int:
    assert learn_llm.learn_kb_model() in {
        "iek/confluence-agent",
        "iek/gpt-oss-120b",
    } or learn_llm.learn_kb_model().startswith("iek/")

    with tempfile.TemporaryDirectory() as tmp:
        idx = Path(tmp) / "index.json"
        learn_llm.INDEX_PATH = idx  # type: ignore[misc]
        idx.write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "task_id": "695558",
                            "code": "HD-09",
                            "status": "rejected",
                            "rejection_reason": "мусор, не про API ключ",
                            "service_key": "other",
                            "gap_reason": "API ключ",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        ctx = learn_llm.rejection_context(
            "заявка про API ключ каталога",
            service_key="other",
            task_id="695558",
        )
        assert "HD-09" in ctx
        assert "мусор" in ctx
        assert learn_llm.is_rejected_code("HD-09")

    print("ok: test_learn_llm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
