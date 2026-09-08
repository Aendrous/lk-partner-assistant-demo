# -*- coding: utf-8 -*-
"""Создать карточки Open WebUI support-dep-bp-web-helper и support-dep-1c-web-helper.

Auth: IEK_LLM_API_KEY → https://chatgpt.iek.local/api/v1/…
(IEK_LLM_TOKEN — только llm.iek.local LiteLLM, не Open WebUI.)

Usage:
  python scripts/create_owui_bp_1c_models.py
  python scripts/create_owui_bp_1c_models.py --dry-run
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

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))

from gigachat_client import load_env  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OWUI_BASE = (os.environ.get("IEK_LLM_OWUI_BASE_URL") or "https://chatgpt.iek.local").rstrip("/")
BASE_MODEL = os.environ.get("IEK_LLM_OWUI_BASE_MODEL") or "iek/gpt-oss-120b"

EXEC_RULES = (ROOT / "docs" / "правила" / "разбор_заявки_для_исполнителя.md").read_text(
    encoding="utf-8"
)[:6000]

BP_SYSTEM = f"""Ты — ассистент отдела технической поддержки IEK по бизнес-платформе bp.iek.ru (ЦКГ / DBP).

{EXEC_RULES}

Дополнительно для БП:
- Не путай с lk.iek.ru (ЛК партнёра). ServiceId HelpDesk для БП — 833.
- Проверяй регистрацию: https://adm.bp.iek.ru/main?search=<email>&page=1&pageSize=16
- API-ключ bp: https://bp.iek.ru/profile#api-keys (username=ticket, password=ключ).
- Отвечай по корпусу Knowledge и Confluence WEBKB. Не выдумывай URL.
- Для разбора заявки HelpDesk — коротко: факты, adm, решение только если есть в KB.
"""

ONEC_SYSTEM = f"""Ты — ассистент отдела технической поддержки IEK по 1С (заказы покупателя, резервы в пути, счета, эл.заявки).

{EXEC_RULES}

Дополнительно для 1С:
- Галка «Резервировать товары в пути» в заказе покупателя: если стоит — в ЛК подтверждать не нужно.
- Номера заказов/счетов формата ХИ…, эл.заявки 0000…
- Отвечай по корпусу Knowledge и Confluence WEBKB. Не выдумывай URL.
"""

SPECS: list[dict[str, Any]] = [
    {
        "model_id": "support-dep-bp-web-helper",
        "model_name": "Отд ТП. Бизнес-платформа (БП)",
        "description": "Разбор заявок bp.iek.ru / IEK ID / API ЦКГ. Knowledge: support-bp-webkb-safe.",
        "knowledge_name": "support-bp-webkb-safe",
        "knowledge_desc": "Обезличенный корпус БП (WEBKB + закрытые заявки ServiceId=833). Без ПДн.",
        "corpus": ROOT / "knowledge" / "bp" / "corpus.md",
        "system": BP_SYSTEM,
    },
    {
        "model_id": "support-dep-1c-web-helper",
        "model_name": "Отд ТП. 1С (резерв в пути, заказы)",
        "description": "Разбор заявок 1С: заказ покупателя, резерв в пути, счета. Knowledge: support-1c-webkb-safe.",
        "knowledge_name": "support-1c-webkb-safe",
        "knowledge_desc": "Корпус 1С: резерв в пути, связка с ЛК. Без ПДн.",
        "corpus": ROOT / "knowledge" / "1c" / "corpus.md",
        "system": ONEC_SYSTEM,
    },
]


def api_key() -> str:
    load_env()
    key = (os.environ.get("IEK_LLM_API_KEY") or "").strip()
    if not key:
        raise SystemExit("Нет IEK_LLM_API_KEY в .env")
    return key


def headers(*, json_body: bool = True) -> dict[str, str]:
    h = {"Authorization": f"Bearer {api_key()}"}
    if json_body:
        h["Content-Type"] = "application/json"
        h["Accept"] = "application/json"
    return h


def get_model(model_id: str) -> dict[str, Any] | None:
    r = requests.get(
        f"{OWUI_BASE}/api/v1/models/model",
        params={"id": model_id},
        headers=headers(json_body=False),
        timeout=30,
        verify=False,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def list_knowledge() -> list[dict[str, Any]]:
    r = requests.get(
        f"{OWUI_BASE}/api/v1/knowledge/",
        headers=headers(json_body=False),
        timeout=30,
        verify=False,
    )
    r.raise_for_status()
    return (r.json() or {}).get("items") or []


def create_knowledge(name: str, description: str) -> dict[str, Any]:
    r = requests.post(
        f"{OWUI_BASE}/api/v1/knowledge/create",
        headers=headers(),
        json={"name": name, "description": description, "access_control": None},
        timeout=30,
        verify=False,
    )
    r.raise_for_status()
    return r.json()


def upload_file(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        r = requests.post(
            f"{OWUI_BASE}/api/v1/files/",
            headers={"Authorization": f"Bearer {api_key()}"},
            files={"file": (path.name, fh, "text/markdown")},
            timeout=120,
            verify=False,
        )
    r.raise_for_status()
    return r.json()


def attach_file(knowledge_id: str, file_id: str) -> dict[str, Any]:
    r = requests.post(
        f"{OWUI_BASE}/api/v1/knowledge/{knowledge_id}/file/add",
        headers=headers(),
        json={"file_id": file_id},
        timeout=60,
        verify=False,
    )
    r.raise_for_status()
    return r.json()


def list_knowledge_files(knowledge_id: str) -> list[dict[str, Any]]:
    r = requests.get(
        f"{OWUI_BASE}/api/v1/knowledge/{knowledge_id}/files",
        headers=headers(json_body=False),
        timeout=30,
        verify=False,
    )
    r.raise_for_status()
    return (r.json() or {}).get("items") or []


def remove_file(knowledge_id: str, file_id: str) -> None:
    r = requests.post(
        f"{OWUI_BASE}/api/v1/knowledge/{knowledge_id}/file/remove",
        headers=headers(),
        json={"file_id": file_id},
        timeout=60,
        verify=False,
    )
    # 404/405 — ignore, файл мог уже отсутствовать
    if r.status_code >= 500:
        r.raise_for_status()


def ensure_knowledge(
    spec: dict[str, Any], *, dry_run: bool, refresh: bool = False
) -> dict[str, Any]:
    name = spec["knowledge_name"]
    corpus: Path = spec["corpus"]
    if not corpus.is_file():
        raise FileNotFoundError(corpus)

    existing_id = None
    for item in list_knowledge():
        if (item.get("name") or "").strip() == name:
            existing_id = item.get("id")
            break

    if existing_id and not refresh:
        return {"ok": True, "existed": True, "id": existing_id, "name": name}

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "would_create": name if not existing_id else None,
            "would_refresh": bool(existing_id and refresh),
            "corpus": str(corpus),
            "id": existing_id,
        }

    if not existing_id:
        kb = create_knowledge(name, spec["knowledge_desc"])
        kid = kb.get("id")
        if not kid:
            raise RuntimeError(f"Knowledge create без id: {kb}")
        uploaded = upload_file(corpus)
        fid = uploaded.get("id")
        if not fid:
            raise RuntimeError(f"Upload без id: {uploaded}")
        attach_file(str(kid), str(fid))
        return {"ok": True, "created": True, "id": kid, "name": name, "file_id": fid}

    # refresh: удалить старые corpus.md и залить новый
    kid = str(existing_id)
    for f in list_knowledge_files(kid):
        fname = str((f.get("meta") or {}).get("name") or f.get("filename") or "")
        if fname.lower() in {"corpus.md", "corpus.txt"} or fname.endswith("corpus.md"):
            remove_file(kid, str(f.get("id")))
    uploaded = upload_file(corpus)
    fid = uploaded.get("id")
    if not fid:
        raise RuntimeError(f"Upload без id: {uploaded}")
    attach_file(kid, str(fid))
    return {"ok": True, "refreshed": True, "id": kid, "name": name, "file_id": fid}


def default_capabilities() -> dict[str, bool]:
    return {
        "file_context": True,
        "vision": False,
        "file_upload": True,
        "web_search": False,
        "image_generation": False,
        "code_interpreter": False,
        "terminal": False,
        "citations": True,
        "status_updates": True,
        "builtin_tools": True,
    }


def create_model(spec: dict[str, Any], knowledge_id: str, *, dry_run: bool) -> dict[str, Any]:
    model_id = spec["model_id"]
    existing = get_model(model_id)
    if existing:
        return {
            "ok": True,
            "existed": True,
            "id": model_id,
            "url": f"{OWUI_BASE}/?model={model_id}",
        }

    payload = {
        "id": model_id,
        "name": spec["model_name"],
        "base_model_id": BASE_MODEL,
        "params": {"system": spec["system"]},
        "meta": {
            "profile_image_url": "/static/favicon.png",
            "description": spec["description"],
            "capabilities": default_capabilities(),
            "knowledge": [{"id": knowledge_id, "name": spec["knowledge_name"]}],
        },
        "access_control": None,
        "is_active": True,
    }

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "would_create": model_id,
            "base_model_id": BASE_MODEL,
            "knowledge_id": knowledge_id,
        }

    r = requests.post(
        f"{OWUI_BASE}/api/v1/models/create",
        headers=headers(),
        json=payload,
        timeout=60,
        verify=False,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"models/create HTTP {r.status_code}: {r.text[:800]}")
    return {
        "ok": True,
        "created": True,
        "id": model_id,
        "url": f"{OWUI_BASE}/?model={model_id}",
        "response": r.json() if r.content else {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create BP/1C Open WebUI models via IEK_LLM_API_KEY")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--refresh-knowledge",
        action="store_true",
        help="Перезалить corpus.md в существующие Knowledge BP/1C",
    )
    args = parser.parse_args()

    out: dict[str, Any] = {
        "ok": True,
        "owui_base": OWUI_BASE,
        "base_model": BASE_MODEL,
        "refresh_knowledge": args.refresh_knowledge,
        "items": [],
    }

    for spec in SPECS:
        item: dict[str, Any] = {"model_id": spec["model_id"]}
        try:
            kb = ensure_knowledge(spec, dry_run=args.dry_run, refresh=args.refresh_knowledge)
            item["knowledge"] = kb
            kid = kb.get("id") or "dry-run-knowledge-id"
            item["model"] = create_model(spec, str(kid), dry_run=args.dry_run)
        except Exception as exc:
            item["ok"] = False
            item["error"] = f"{type(exc).__name__}: {exc}"
        else:
            item["ok"] = True
        out["items"].append(item)

    path = ROOT / "_owui_models_create.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)
    print(f"Saved: {path.name}", file=sys.stderr, flush=True)
    return 0 if all(x.get("ok") for x in out["items"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
