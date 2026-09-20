# -*- coding: utf-8 -*-
"""Minimal n8n REST client shared by deployment and diagnostic scripts."""
from __future__ import annotations

import os
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def base_url() -> str:
    """Return n8n base URL without a trailing slash."""
    return (os.environ.get("N8N_BASE_URL") or "https://n8n.iek.local").strip().rstrip("/")


def api_key() -> str:
    """Return the n8n public API key, if configured."""
    return (os.environ.get("N8N_API_KEY") or "").strip()


def has_api_key() -> bool:
    return bool(api_key())


def _headers() -> dict[str, str]:
    key = api_key()
    return {"X-N8N-API-KEY": key, "Accept": "application/json"} if key else {"Accept": "application/json"}


def ping() -> dict[str, Any]:
    """Check n8n REST API availability without changing server state."""
    if not has_api_key():
        return {"ok": False, "error": "missing_api_key", "base_url": base_url()}
    try:
        response = requests.get(
            f"{base_url()}/api/v1/workflows",
            headers=_headers(),
            params={"limit": 1},
            timeout=15,
            verify=False,
        )
        return {"ok": response.ok, "status_code": response.status_code, "base_url": base_url()}
    except requests.RequestException as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:200], "base_url": base_url()}


def webhook_map() -> dict[str, str]:
    """Return configured n8n webhook URLs without exposing API credentials."""
    return {
        key: value.strip()
        for key in ("N8N_WEBHOOK_URL", "N8N_WEBHOOK_LK", "N8N_WEBHOOK_HELPDESK", "N8N_WEBHOOK_INTRANET")
        if (value := os.environ.get(key)) and value.strip()
    }
