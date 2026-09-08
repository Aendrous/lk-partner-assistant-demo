# -*- coding: utf-8 -*-
"""Скопировать N8N_* из корневого .env в chatbot_intraservice/.env (без перезаписи).

  python scripts/sync_n8n_env_from_root.py
  python scripts/sync_n8n_env_from_root.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_PKG = Path(__file__).resolve().parents[1]
REPO = ROOT_PKG.parent

N8N_KEYS = (
    "N8N_BASE_URL",
    "N8N_API_KEY",
    "N8N_WEBHOOK_URL",
    "N8N_WEBHOOK_LK",
    "N8N_WEBHOOK_HELPDESK",
    "N8N_WEBHOOK_INTRANET",
    "N8N_BOT_CALLBACK_URL",
    "N8N_BOT_HTTP_PORT",
)


def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, val = raw.split("=", 1)
        out[key.strip()] = val.strip()
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root_env = REPO / ".env"
    pkg_env = ROOT_PKG / ".env"
    root_vals = _parse_env(root_env)
    pkg_vals = _parse_env(pkg_env)

    added: list[str] = []
    for key in N8N_KEYS:
        if key in pkg_vals and pkg_vals[key]:
            continue
        if key not in root_vals or not root_vals[key]:
            continue
        added.append(f"{key}={root_vals[key]}")

    if not added:
        print(json_dumps({"ok": True, "added": [], "message": "нечего копировать"}))
        return 0

    if args.dry_run:
        print(json_dumps({"ok": True, "dry_run": True, "would_add": [k.split("=")[0] for k in added]}))
        return 0

    text = pkg_env.read_text(encoding="utf-8") if pkg_env.is_file() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    if "# --- n8n (из корневого .env) ---" not in text:
        text += "\n# --- n8n (из корневого .env) ---\n"
    text += "\n".join(added) + "\n"
    pkg_env.write_text(text, encoding="utf-8")
    print(json_dumps({"ok": True, "added": [k.split("=")[0] for k in added], "target": str(pkg_env)}))
    return 0


def json_dumps(obj: object) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
