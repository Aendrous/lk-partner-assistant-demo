# -*- coding: utf-8 -*-
"""Зонд: поддерживает ли LiteLLM / OWUI tools (MCP Confluence) в API.

  python scripts/probe_iek_llm_tools.py
  python scripts/probe_iek_llm_tools.py --model iek/confluence-agent

Результат: chatbot_intraservice/_probe_llm_tools.json (без секретов).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
import urllib3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OUT = ROOT / "_probe_llm_tools.json"
OWUI_BASE = (os.environ.get("IEK_LLM_OWUI_BASE_URL") or "https://chatgpt.iek.local").rstrip("/")

CONFLUENCE_TOOL = {
    "type": "function",
    "function": {
        "name": "confluence_search",
        "description": "Search Confluence pages by text query",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text"},
                "limit": {"type": "integer", "description": "Max results"},
            },
            "required": ["query"],
        },
    },
}


def _load_env() -> None:
    for p in (ROOT / ".env", REPO / ".env"):
        if not p.is_file():
            continue
        try:
            from dotenv import load_dotenv

            load_dotenv(p, override=False)
        except ImportError:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def _probe_litellm_models(base: str, token: str) -> dict[str, Any]:
    try:
        r = requests.get(
            f"{base.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
            verify=False,
        )
        data = r.json() if r.content else {}
        ids = [m.get("id") for m in (data.get("data") or []) if isinstance(m, dict)]
        confluence_models = [i for i in ids if i and "confluence" in str(i).lower()]
        return {
            "ok": r.status_code < 400,
            "http": r.status_code,
            "count": len(ids),
            "confluence_models": confluence_models,
            "sample": ids[:15],
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _probe_chat_with_tools(base: str, token: str, model: str) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Найди в Confluence статью про «нет счета в ЛК». "
                    "Вызови confluence_search если доступен."
                ),
            }
        ],
        "tools": [CONFLUENCE_TOOL],
        "tool_choice": "auto",
        "temperature": 0,
        "stream": False,
    }
    try:
        r = requests.post(
            f"{base.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=120,
            verify=False,
        )
        raw = r.json() if r.content else {}
        msg = ((raw.get("choices") or [{}])[0].get("message") or {})
        return {
            "ok": r.status_code < 400,
            "http": r.status_code,
            "model": model,
            "has_tool_calls": bool(msg.get("tool_calls")),
            "tool_calls": msg.get("tool_calls"),
            "finish_reason": (raw.get("choices") or [{}])[0].get("finish_reason"),
            "content_preview": (msg.get("content") or "")[:400],
            "error_body": raw.get("error") if r.status_code >= 400 else None,
            "body_preview": r.text[:500] if r.status_code >= 400 else None,
        }
    except Exception as exc:
        return {"ok": False, "model": model, "error": f"{type(exc).__name__}: {exc}"}


def _probe_owui_model(model_id: str, api_key: str) -> dict[str, Any]:
    try:
        r = requests.get(
            f"{OWUI_BASE}/api/v1/models/model",
            params={"id": model_id},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=45,
            verify=False,
        )
        if r.status_code >= 400:
            return {"ok": False, "http": r.status_code, "body": r.text[:600]}
        data = r.json() if r.content else {}
        meta = data.get("meta") or {}
        caps = meta.get("capabilities") or {}
        tools = meta.get("tools") or meta.get("toolIds") or meta.get("builtin_tools")
        return {
            "ok": True,
            "model_id": model_id,
            "base_model_id": data.get("base_model_id"),
            "capabilities": caps,
            "meta_tools": tools,
            "has_builtin_tools_flag": bool(caps.get("builtin_tools")),
            "knowledge": meta.get("knowledge"),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _probe_owui_chat(model_id: str, api_key: str) -> dict[str, Any]:
    """POST /api/chat/completions (OWUI) — если endpoint есть."""
    for path in ("/api/chat/completions", "/api/v1/chat/completions"):
        try:
            r = requests.post(
                f"{OWUI_BASE}{path}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": "ping"}],
                    "stream": False,
                },
                timeout=90,
                verify=False,
            )
            return {
                "path": path,
                "ok": r.status_code < 400,
                "http": r.status_code,
                "preview": r.text[:400],
            }
        except Exception as exc:
            last = {"path": path, "ok": False, "error": str(exc)}
    return last  # type: ignore[return-value]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default=os.environ.get("IEK_LLM_SUPPORT_MODEL") or "iek/gpt-oss-120b",
    )
    args = parser.parse_args()
    _load_env()

    import llm_client  # noqa: E402

    base = llm_client.base_url()
    token = llm_client.token()

    out: dict[str, Any] = {
        "litellm_base": base,
        "owui_base": OWUI_BASE,
        "probes": {},
    }

    if token:
        out["probes"]["litellm_models"] = _probe_litellm_models(base, token)
        out["probes"]["litellm_tools"] = _probe_chat_with_tools(base, token, args.model)
        out["probes"]["litellm_tools_gpt_oss"] = _probe_chat_with_tools(
            base, token, "iek/gpt-oss-120b"
        )
    else:
        out["probes"]["litellm"] = {"ok": False, "error": "нет IEK_LLM_TOKEN"}

    api_key = (os.environ.get("IEK_LLM_API_KEY") or "").strip()
    if api_key:
        for mid in (
            "support-dep-lk-web-helper",
            "support-dep-bp-web-helper",
            "support-dep-1c-web-helper",
        ):
            out["probes"][f"owui_model_{mid}"] = _probe_owui_model(mid, api_key)
        out["probes"]["owui_chat_lk"] = _probe_owui_chat("support-dep-lk-web-helper", api_key)
    else:
        out["probes"]["owui"] = {"ok": False, "error": "нет IEK_LLM_API_KEY"}

    # REST prefetch smoke
    try:
        import confluence_tools as ct  # noqa: E402

        pf = ct.confluence_search("нет счета в ЛК", limit=2)
        out["probes"]["rest_confluence_search"] = {
            "ok": pf.get("ok"),
            "hits": len(pf.get("hits") or []),
            "sample_titles": [(h.get("title") or "")[:60] for h in (pf.get("hits") or [])[:2]],
        }
    except Exception as exc:
        out["probes"]["rest_confluence_search"] = {"ok": False, "error": str(exc)}

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nSaved: {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
