# -*- coding: utf-8 -*-
"""Диагностика связки n8n → n8n_http_server (connection refused и т.п.).

  python scripts/n8n_diag_bot_url.py
  python scripts/n8n_diag_bot_url.py --workflow-id paYsXt1HK1ZSAHXt
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import urllib3

REPO = Path(__file__).resolve().parents[2]
PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(PKG / "src"))

from env_bootstrap import load_package_env  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

WORKFLOW_NAME = "IntraService HelpDesk Bot"


def _fetch_workflow_urls(workflow_id: str = "") -> list[dict[str, str]]:
    import n8n_client

    headers = {"X-N8N-API-KEY": n8n_client.api_key(), "Accept": "application/json"}
    if workflow_id:
        resp = requests.get(
            f"{n8n_client.base_url()}/api/v1/workflows/{workflow_id}",
            headers=headers,
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        wf = resp.json().get("data") or resp.json()
        wfs = [wf]
    else:
        resp = requests.get(
            f"{n8n_client.base_url()}/api/v1/workflows",
            headers=headers,
            params={"limit": 100},
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        wfs = [
            w
            for w in resp.json().get("data") or []
            if (w.get("name") or "").strip() == WORKFLOW_NAME
        ]
    out: list[dict[str, str]] = []
    for wf in wfs:
        for node in wf.get("nodes") or []:
            url = str((node.get("parameters") or {}).get("url") or "").strip()
            if url:
                out.append({"workflow_id": str(wf.get("id") or ""), "node": node.get("name") or "", "url": url})
    return out


def _probe_health(base_url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    health = f"{base_url.rstrip('/')}/health"
    try:
        resp = requests.get(health, timeout=timeout, verify=False)
        body = resp.text[:300]
        ok_json = False
        try:
            data = resp.json()
            ok_json = bool(data.get("ok"))
        except Exception:
            data = None
        return {
            "ok": resp.status_code == 200 and (ok_json or resp.status_code == 200),
            "status_code": resp.status_code,
            "body_preview": body,
            "health_url": health,
        }
    except requests.ConnectionError as exc:
        return {
            "ok": False,
            "error": "connection_refused",
            "detail": str(exc)[:200],
            "health_url": health,
            "hint": "Запустите на хосте n8n: python scripts/n8n_http_server.py (порт 8765)",
        }
    except requests.Timeout:
        return {"ok": False, "error": "timeout", "health_url": health}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:200], "health_url": health}


def main() -> int:
    load_package_env()
    parser = argparse.ArgumentParser(description="Диагностика n8n → bot HTTP API")
    parser.add_argument("--workflow-id", default="", help="например paYsXt1HK1ZSAHXt")
    args = parser.parse_args()

    import n8n_client
    import os

    env_callback = (os.environ.get("N8N_BOT_CALLBACK_URL") or "").strip()
    out: dict[str, Any] = {
        "n8n_base": n8n_client.base_url(),
        "env_N8N_BOT_CALLBACK_URL": env_callback,
        "workflow_nodes": [],
        "health_checks": {},
        "ok": True,
    }

    try:
        nodes = _fetch_workflow_urls(args.workflow_id)
        out["workflow_nodes"] = nodes
    except Exception as exc:
        out["workflow_fetch_error"] = f"{type(exc).__name__}: {exc}"
        out["ok"] = False

    bases: set[str] = set()
    if env_callback:
        bases.add(env_callback.rstrip("/"))
    for row in out.get("workflow_nodes") or []:
        u = urlparse(str(row.get("url") or ""))
        if u.scheme and u.netloc:
            bases.add(f"{u.scheme}://{u.netloc}")

    for base in sorted(bases):
        out["health_checks"][base] = _probe_health(base)

    any_ok = any(v.get("ok") for v in out["health_checks"].values())
    if bases and not any_ok:
        out["ok"] = False
        out["fix"] = (
            "Co-located: на сервере n8n развернуть пакет, systemd для n8n_http_server, "
            "затем: python scripts/n8n_setup_helpdesk_watch.py --co-located"
        )

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
