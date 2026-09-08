# -*- coding: utf-8 -*-
"""Загрузка .env: корень монорепо (N8N, LK API) + chatbot_intraservice/.env."""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parent

_LOADED = False


def load_package_env(*, force: bool = False) -> None:
    """Сначала корневой .env (N8N_*), затем пакетный (IntraService, LLM)."""
    global _LOADED
    if _LOADED and not force:
        return
    paths = [REPO / ".env", PKG / ".env"]
    try:
        from dotenv import load_dotenv

        for p in paths:
            if p.is_file():
                load_dotenv(p, override=True)
    except ImportError:
        for p in paths:
            if not p.is_file():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip("'\"").strip()
    _LOADED = True


def repo_env_path() -> Path:
    return REPO / ".env"


def package_env_path() -> Path:
    return PKG / ".env"
