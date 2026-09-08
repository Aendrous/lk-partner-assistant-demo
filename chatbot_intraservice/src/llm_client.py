# -*- coding: utf-8 -*-
"""Лёгкий HTTP-клиент внутреннего LLM-шлюза https://llm.iek.local/v1.

Экспортирует минимум, который используют модули проекта:
  - DEFAULT_SUPPORT_MODEL  — fallback-модель по умолчанию.
  - base_url()            — корень API (без trailing slash).
  - token()               — токен из IEK_LLM_TOKEN.
  - _headers()            — заголовки Authorization + Content-Type.
  - resolve_model(model, fallback=None) — подставляет живую модель из /v1/models.
  - is_invalid_model_error(http, body) — эвристика «модель снята/неизвестна».
"""
from __future__ import annotations

import os
import time
from typing import Any

DEFAULT_SUPPORT_MODEL: str = os.environ.get("IEK_LLM_MODEL", "iek/gpt-oss-120b")


def base_url() -> str:
    """Базовый URL шлюза LLM (без конечного слеша)."""
    return os.environ.get("IEK_LLM_BASE_URL", "https://llm.iek.local/v1").rstrip("/")


def token() -> str:
    """Bearer-токен для LLM API."""
    t = os.environ.get("IEK_LLM_TOKEN")
    if not t:
        raise RuntimeError("IEK_LLM_TOKEN не задан в .env")
    return t


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Заголовки для запросов к LLM."""
    h: dict[str, str] = {
        "Authorization": f"Bearer {token()}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


_ALLOWED_CACHE: tuple[set | None, float] | None = None
_ALLOWED_TTL = 300


def _allowed_models() -> set:
    """Лениво читаем GET /v1/models и кэшируем (TTL 300 сек). Пусто вместо падения."""
    global _ALLOWED_CACHE
    now = time.time()
    if _ALLOWED_CACHE is not None and now - _ALLOWED_CACHE[1] < _ALLOWED_TTL:
        cached = _ALLOWED_CACHE[0]
        return cached if cached is not None else set()
    try:
        import requests
        r = requests.get(
            f"{base_url()}/models",
            headers=_headers(),
            timeout=15,
            verify=False,
        )
        names: set = set()
        if r.status_code == 200:
            for m in (r.json().get("data") or []):
                if isinstance(m, dict) and m.get("id"):
                    names.add(str(m["id"]))
        _ALLOWED_CACHE = (names, now)
        return names
    except Exception:
        _ALLOWED_CACHE = (set(), now)
        return set()


def resolve_model(model: str | None, fallback: str | None = None) -> str:
    """Вернуть первую «живую» модель: model -> fallback -> DEFAULT_SUPPORT_MODEL."""

    def _pick(c: str | None) -> str | None:
        candidate = (c or "").strip()
        if not candidate:
            return None
        avail = _allowed_models()
        if not avail or candidate in avail:
            return candidate
        return None

    return _pick(model) or _pick(fallback) or DEFAULT_SUPPORT_MODEL


def is_invalid_model_error(http, body: str | None) -> bool:
    """Эвриристика: плохой/снятый model -> HTTP 400 + упоминание model в тексте."""
    b = (body or "").lower()
    if http != 400:
        return False
    keywords = ("invalid", "not found", "does not exist", "unknown", "disabled")
    return "model" in b and any(k in b for k in keywords)


__all__ = [
    "DEFAULT_SUPPORT_MODEL",
    "base_url",
    "token",
    "_headers",
    "resolve_model",
    "is_invalid_model_error",
]
