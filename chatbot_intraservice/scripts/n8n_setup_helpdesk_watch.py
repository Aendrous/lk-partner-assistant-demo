# -*- coding: utf-8 -*-
"""Создать/обновить workflow n8n для чатбота IntraService.

Режимы:
  --mode http     — POST на n8n_http_server :8765 (по умолчанию)
  --mode execute  — Execute Command на хосте n8n (без HTTP, рекомендуется для автономии)

  python scripts/n8n_setup_helpdesk_watch.py --dry-run
  python scripts/n8n_setup_helpdesk_watch.py --co-located
  python scripts/n8n_setup_helpdesk_watch.py --mode execute --bot-path /opt/iek-chatbot-intraservice
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
import urllib3

REPO = Path(__file__).resolve().parents[2]
PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(PKG / "src"))

from env_bootstrap import load_package_env  # noqa: E402

import n8n_client  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

WORKFLOW_NAME = "IntraService HelpDesk Bot"
WEBHOOK_PATH = "helpdesk-bot"


def _headers() -> dict[str, str]:
    return {
        "X-N8N-API-KEY": n8n_client.api_key(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _find_workflow() -> dict[str, Any] | None:
    resp = requests.get(
        f"{n8n_client.base_url()}/api/v1/workflows",
        headers=_headers(),
        params={"limit": 100},
        timeout=30,
        verify=False,
    )
    resp.raise_for_status()
    for item in resp.json().get("data") or []:
        if (item.get("name") or "").strip() == WORKFLOW_NAME:
            return item
    return None


def _schedule_node(nid: str, name: str, minutes: int, x: int, y: int) -> dict[str, Any]:
    return {
        "id": nid,
        "name": name,
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [x, y],
        "parameters": {
            "rule": {"interval": [{"field": "minutes", "minutesInterval": minutes}]}
        },
    }


def _http_node(
    nid: str,
    name: str,
    path: str,
    bot_base: str,
    api_key: str,
    x: int,
    y: int,
) -> dict[str, Any]:
    url = f"{bot_base.rstrip('/')}{path}"
    return {
        "id": nid,
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [x, y],
        "parameters": {
            "method": "POST",
            "url": url,
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Authorization", "value": f"Bearer {api_key}"},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "options": {"timeout": 120000},
        },
    }


def _exec_node(
    nid: str,
    name: str,
    action: str,
    bot_path: str,
    python_bin: str,
    x: int,
    y: int,
) -> dict[str, Any]:
    root = bot_path.rstrip("/")
    py = python_bin or f"{root}/.venv/bin/python"
    cmd = f"cd {root} && {py} scripts/n8n_run.py {action}"
    return {
        "id": nid,
        "name": name,
        "type": "n8n-nodes-base.executeCommand",
        "typeVersion": 1,
        "position": [x, y],
        "parameters": {"command": cmd},
    }


def build_workflow_http(bot_base: str, api_key: str) -> dict[str, Any]:
    nodes = [
        _schedule_node("sch-new", "Every 15m — watch new", 15, 0, 0),
        _http_node("http-new", "POST watch-new", "/run/watch-new", bot_base, api_key, 280, 0),
        _schedule_node("sch-overdue", "Every 15m — overdue", 15, 0, 200),
        _http_node("http-overdue", "POST watch-overdue", "/run/watch-overdue", bot_base, api_key, 280, 200),
        _schedule_node("sch-reply", "Every 15m — user reply", 15, 0, 400),
        _http_node("http-reply", "POST watch-user-reply", "/run/watch-user-reply", bot_base, api_key, 280, 400),
        _schedule_node("sch-learn", "Every 30m — pipeline", 30, 0, 600),
        _http_node("http-learn", "POST pipeline-watch", "/run/pipeline-watch", bot_base, api_key, 280, 600),
    ]
    connections = {
        "Every 15m — watch new": {"main": [[{"node": "POST watch-new", "type": "main", "index": 0}]]},
        "Every 15m — overdue": {"main": [[{"node": "POST watch-overdue", "type": "main", "index": 0}]]},
        "Every 15m — user reply": {"main": [[{"node": "POST watch-user-reply", "type": "main", "index": 0}]]},
        "Every 30m — pipeline": {"main": [[{"node": "POST pipeline-watch", "type": "main", "index": 0}]]},
    }
    return {
        "name": WORKFLOW_NAME,
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
    }


def build_workflow_execute(bot_path: str, python_bin: str = "") -> dict[str, Any]:
    nodes = [
        _schedule_node("sch-new", "Every 15m — watch new", 15, 0, 0),
        _exec_node("exec-new", "Exec watch-new", "watch_new", bot_path, python_bin, 280, 0),
        _schedule_node("sch-overdue", "Every 15m — overdue", 15, 0, 200),
        _exec_node("exec-overdue", "Exec watch-overdue", "watch_overdue", bot_path, python_bin, 280, 200),
        _schedule_node("sch-reply", "Every 15m — user reply", 15, 0, 400),
        _exec_node("exec-reply", "Exec watch-user-reply", "watch_user_reply", bot_path, python_bin, 280, 400),
        _schedule_node("sch-learn", "Every 30m — pipeline", 30, 0, 600),
        _exec_node("exec-learn", "Exec pipeline-watch", "pipeline_watch", bot_path, python_bin, 280, 600),
    ]
    connections = {
        "Every 15m — watch new": {"main": [[{"node": "Exec watch-new", "type": "main", "index": 0}]]},
        "Every 15m — overdue": {"main": [[{"node": "Exec watch-overdue", "type": "main", "index": 0}]]},
        "Every 15m — user reply": {"main": [[{"node": "Exec watch-user-reply", "type": "main", "index": 0}]]},
        "Every 30m — pipeline": {"main": [[{"node": "Exec pipeline-watch", "type": "main", "index": 0}]]},
    }
    return {
        "name": WORKFLOW_NAME,
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
    }


def activate(workflow_id: str) -> None:
    resp = requests.post(
        f"{n8n_client.base_url()}/api/v1/workflows/{workflow_id}/activate",
        headers=_headers(),
        timeout=30,
        verify=False,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"activate HTTP {resp.status_code}: {resp.text[:400]}")


def upsert_env_helpdesk_webhook(url: str) -> None:
    """Опционально: если позже добавим webhook-триггер — URL в корневой .env."""
    env_path = REPO / ".env"
    if not env_path.is_file():
        return
    text = env_path.read_text(encoding="utf-8")
    key = "N8N_WEBHOOK_HELPDESK"
    line = f"{key}={url}"
    if key in text:
        import re

        text = re.sub(rf"^{key}=.*$", line, text, flags=re.M)
    else:
        text = text.rstrip() + f"\n{line}\n"
    env_path.write_text(text, encoding="utf-8")


def upsert_env_bot_callback(url: str) -> None:
    """Обновить N8N_BOT_CALLBACK_URL в корневом .env (co-located preset)."""
    env_path = REPO / ".env"
    if not env_path.is_file():
        return
    import re

    text = env_path.read_text(encoding="utf-8")
    key = "N8N_BOT_CALLBACK_URL"
    line = f"{key}={url}"
    if re.search(rf"^{key}=", text, flags=re.M):
        text = re.sub(rf"^{key}=.*$", line, text, flags=re.M)
    else:
        text = text.rstrip() + f"\n{line}\n"
    env_path.write_text(text, encoding="utf-8")


def main() -> int:
    load_package_env()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("http", "execute"),
        default="http",
        help="http = POST :8765; execute = Execute Command на сервере n8n (без n8n_http_server)",
    )
    parser.add_argument(
        "--bot-path",
        default=(os.environ.get("N8N_BOT_DEPLOY_PATH") or "/opt/iek-chatbot-intraservice").strip(),
        help="Каталог пакета на сервере n8n (для --mode execute)",
    )
    parser.add_argument(
        "--python-bin",
        default=(os.environ.get("N8N_BOT_PYTHON") or "").strip(),
        help="Python на сервере (по умолчанию <bot-path>/.venv/bin/python)",
    )
    parser.add_argument(
        "--bot-url",
        default="",
        help="Базовый URL n8n_http_server (без /run/…). По умолчанию — N8N_BOT_CALLBACK_URL или http://127.0.0.1:8765",
    )
    parser.add_argument(
        "--co-located",
        action="store_true",
        help="HTTP preset: --bot-url http://127.0.0.1:8765",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.co_located:
        args.bot_url = "http://127.0.0.1:8765"
    elif not (args.bot_url or "").strip():
        args.bot_url = (os.environ.get("N8N_BOT_CALLBACK_URL") or "http://127.0.0.1:8765").strip()

    if not n8n_client.has_api_key():
        raise SystemExit("Нет N8N_API_KEY — задайте в корневом .env (см. .env.example)")

    api_key = n8n_client.api_key()
    if args.mode == "execute":
        payload = build_workflow_execute(args.bot_path, args.python_bin)
        mode_meta = {"mode": "execute", "bot_path": args.bot_path, "python_bin": args.python_bin or f"{args.bot_path.rstrip('/')}/.venv/bin/python"}
    else:
        payload = build_workflow_http(args.bot_url, api_key)
        mode_meta = {"mode": "http", "bot_url": args.bot_url}

    if args.dry_run:
        safe = json.loads(json.dumps(payload))
        for node in safe.get("nodes") or []:
            params = node.get("parameters") or {}
            hdrs = (params.get("headerParameters") or {}).get("parameters") or []
            for h in hdrs:
                if h.get("name") == "Authorization":
                    h["value"] = "Bearer ***"
        print(
            json.dumps(
                {"ok": True, "dry_run": True, **mode_meta, "workflow": safe},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    existing = _find_workflow()
    if existing:
        wid = str(existing["id"])
        resp = requests.put(
            f"{n8n_client.base_url()}/api/v1/workflows/{wid}",
            headers=_headers(),
            json=payload,
            timeout=60,
            verify=False,
        )
        action = "updated"
    else:
        resp = requests.post(
            f"{n8n_client.base_url()}/api/v1/workflows",
            headers=_headers(),
            json=payload,
            timeout=60,
            verify=False,
        )
        action = "created"
        wid = str((resp.json().get("data") or resp.json()).get("id") or "")

    if resp.status_code >= 400:
        print(resp.text[:1200])
        return 1

    try:
        activate(wid)
    except RuntimeError as exc:
        if args.mode == "execute":
            print(
                json.dumps(
                    {
                        "ok": False,
                        "action": action,
                        "workflow_id": wid,
                        "activate_error": str(exc),
                        "hint": (
                            "Execute Command отключён на n8n v2 (NODES_EXCLUDE). "
                            'Админам: NODES_EXCLUDE="[n8n-nodes-base.localFileTrigger]" на main+worker. '
                            "Временно: --co-located + n8n_http_server на сервере."
                        ),
                        **mode_meta,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        raise

    if args.mode == "http" and args.co_located:
        upsert_env_bot_callback(args.bot_url)
    hint = (
        f"На сервере n8n: пакет в {args.bot_path}, .env с секретами; "
        "после правок Streamlit — push config/settings.local.json (scripts/push_deploy_settings.ps1)"
        if args.mode == "execute"
        else "Запустите на хосте бота: python scripts/n8n_http_server.py"
    )
    out = {
        "ok": True,
        "action": action,
        "workflow_id": wid,
        "workflow_name": WORKFLOW_NAME,
        "n8n_base": n8n_client.base_url(),
        "hint": hint,
        **mode_meta,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
