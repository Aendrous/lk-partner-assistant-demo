# -*- coding: utf-8 -*-
"""Проверка n8n.iek.local (ключ и webhooks из корневого .env).

  python scripts/n8n_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(PKG / "src"))

from env_bootstrap import load_package_env  # noqa: E402

import n8n_client  # noqa: E402


def _probe_bot_health(base_url: str) -> dict:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    if not base_url:
        return {"skipped": True}
    import requests

    health = f"{base_url.rstrip('/')}/health"
    try:
        resp = requests.get(health, timeout=5, verify=False)
        return {"ok": resp.status_code == 200, "status_code": resp.status_code, "url": health}
    except requests.ConnectionError:
        return {"ok": False, "error": "connection_refused", "url": health}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "url": health}


def main() -> int:
    load_package_env()
    bot_callback = (__import__("os").environ.get("N8N_BOT_CALLBACK_URL") or "").strip()
    out = {
        "n8n": n8n_client.ping(),
        "webhooks": n8n_client.webhook_map(),
        "bot_callback": bot_callback,
        "bot_health": _probe_bot_health(bot_callback),
        "env_files": {
            "repo": str(REPO / ".env"),
            "package": str(PKG / ".env"),
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    ok = out["n8n"].get("ok")
    if bot_callback and not out["bot_health"].get("ok"):
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
