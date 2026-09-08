# -*- coding: utf-8 -*-
"""contour_enabled.watch → ServiceId для watch_new и др."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import service_filter as sf  # noqa: E402


def test_crm_watch_adds_service_29():
    cfg = {
        "contour_enabled": {
            "lk": {"comment": True, "kb_learn": True, "watch": True},
            "bp": {"comment": True, "kb_learn": True, "watch": True},
            "crm": {"comment": True, "kb_learn": True, "watch": True},
            "edi": {"comment": False, "kb_learn": False, "watch": False},
        }
    }
    ids = sf.service_ids_for_contour_action(cfg, "watch")
    assert 29 in ids
    assert 731 in ids and 833 in ids
    assert 69 not in ids


def test_crm_watch_off_excludes_29():
    cfg = {
        "contour_enabled": {
            "lk": {"comment": True, "kb_learn": True, "watch": True},
            "bp": {"comment": True, "kb_learn": True, "watch": True},
            "crm": {"comment": True, "kb_learn": True, "watch": False},
        }
    }
    ids = sf.service_ids_for_contour_action(cfg, "watch")
    assert 29 not in ids


def test_sync_watch_service_ids():
    cfg = {
        "contour_enabled": {
            "lk": {"comment": False, "kb_learn": False, "watch": False},
            "bp": {"comment": False, "kb_learn": False, "watch": False},
            "crm": {"comment": True, "kb_learn": True, "watch": True},
            "edi": {"comment": False, "kb_learn": False, "watch": False},
            "mail": {"comment": False, "kb_learn": False, "watch": False},
            "other": {"comment": False, "kb_learn": False, "watch": False},
        }
    }
    synced = sf.sync_watch_service_ids(cfg)
    assert synced["watch_new_service_ids"] == [29]
    assert synced["watch_service_ids"] == [29]


if __name__ == "__main__":
    test_crm_watch_adds_service_29()
    test_crm_watch_off_excludes_29()
    test_sync_watch_service_ids()
    print("ok")
