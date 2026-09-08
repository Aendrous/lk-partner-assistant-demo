# -*- coding: utf-8 -*-
"""Таксономия закрытия заявок: category LLM → поля HelpDesk + строка «Контур:»."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
TAXONOMY_PATH = PKG / "config" / "closure_taxonomy.json"


@lru_cache(maxsize=1)
def load_taxonomy() -> dict[str, Any]:
    if not TAXONOMY_PATH.is_file():
        return {}
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def _norm_category(category: str) -> str:
    return (category or "").strip()


def _category_key(category: str) -> str:
    raw = _norm_category(category)
    if not raw:
        return ""
    return raw.upper().replace(" ", "_").replace("-", "_")


def instruction_url_from_parsed(parsed: dict[str, Any]) -> str:
    for ref in parsed.get("kb_refs") or []:
        if not isinstance(ref, dict):
            continue
        url = str(ref.get("url") or "").strip()
        if "confluence.dev.iek.ru" in url:
            return url
    for url in parsed.get("article_links") or []:
        u = str(url or "").strip()
        if "confluence.dev.iek.ru" in u:
            return u
    return ""


def map_closure_type_id(
    parsed: dict[str, Any],
    *,
    taxonomy: dict[str, Any] | None = None,
) -> tuple[str | None, str]:
    """Вернуть (option_id, reason)."""
    tax = taxonomy or load_taxonomy()
    cat = _norm_category(str(parsed.get("category") or ""))
    if not cat:
        return None, "нет category"

    if parsed.get("has_kb_solution"):
        kb_map = tax.get("category_to_closure_type_with_kb") or {}
        if kb_map.get("*"):
            return str(kb_map["*"]), "has_kb_solution → инструкция"

    mapping = tax.get("category_to_closure_type") or {}
    key = _category_key(cat)
    for probe in (cat, key, cat.lower(), key.lower()):
        if probe in mapping:
            return str(mapping[probe]), f"category={cat}"
        if probe.upper() in mapping:
            return str(mapping[probe.upper()]), f"category={cat}"

    sk = str(parsed.get("service_key") or "").lower()
    if sk in {"1c", "edi"} and key in (tax.get("onec_categories") or {}):
        return "2031", "1С без явного маппинга → Заказ"
    if sk == "lk":
        return "2031", "ЛК без явного маппинга → Заказ"
    if sk == "bp":
        return "2042", "БП без явного маппинга → API"
    return None, "нет маппинга Field2229"


def map_closure_code_catalog_id(
    category: str,
    *,
    taxonomy: dict[str, Any] | None = None,
) -> str | None:
    tax = taxonomy or load_taxonomy()
    mapping = tax.get("field2711_by_category") or {}
    key = _category_key(category)
    for probe in (category, key, key.lower()):
        if probe in mapping:
            return str(mapping[probe])
    return None


def build_contour_line(
    contour: str,
    parsed: dict[str, Any],
    *,
    contour_label: str | None = None,
    taxonomy: dict[str, Any] | None = None,
) -> str:
    """Строка «Контур: … · этап · причина» (+ category, если нет маппинга в Field*)."""
    tax = taxonomy or load_taxonomy()
    label = (contour_label or contour or "?").strip()
    parts: list[str] = [f"Контур: {label}"]

    category = _norm_category(str(parsed.get("category") or ""))
    stage = re.sub(r"\s+", " ", str(parsed.get("error_stage_ru") or "").strip())
    cause = re.sub(r"\s+", " ", str(parsed.get("root_cause_ru") or "").strip())

    instruction = instruction_url_from_parsed(parsed)
    closure_type_id, _ = map_closure_type_id(parsed, taxonomy=tax)
    catalog_id = map_closure_code_catalog_id(category, taxonomy=tax) if category else None
    category_in_field3061 = bool(category) and not instruction
    show_category_on_line = bool(category) and not category_in_field3061 and not catalog_id and not closure_type_id

    if show_category_on_line:
        parts.append(category)

    if stage:
        parts.append(f"этап: {stage}")
    if cause:
        parts.append(f"причина: {cause}")

    return " · ".join(parts)


def build_hd_field_payload(
    parsed: dict[str, Any],
    *,
    settings: dict[str, Any] | None = None,
    taxonomy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Собрать Field* для PUT /api/task/{id}."""
    tax = taxonomy or load_taxonomy()
    cfg_fields = (settings or {}).get("hd_closure_fields") or tax.get("hd_fields") or {}
    out: dict[str, Any] = {}
    meta: dict[str, Any] = {
        "category": _norm_category(str(parsed.get("category") or "")),
        "closure_type_id": None,
        "closure_type_mapped": False,
        "instruction_url": "",
        "field3061_value": "",
        "category_on_contour": False,
    }

    category = meta["category"]
    instruction = instruction_url_from_parsed(parsed)
    meta["instruction_url"] = instruction

    field_type = str(cfg_fields.get("closure_type") or "Field2229")
    closure_type_id, reason = map_closure_type_id(parsed, taxonomy=tax)
    meta["closure_type_reason"] = reason
    if closure_type_id:
        out[field_type] = closure_type_id
        meta["closure_type_id"] = closure_type_id
        meta["closure_type_mapped"] = True

    field_url = str(cfg_fields.get("instruction_url") or "Field3061")
    if instruction:
        out[field_url] = instruction[:500]
        meta["field3061_value"] = instruction[:500]
    elif category:
        out[field_url] = category[:100]
        meta["field3061_value"] = category[:100]
        meta["category_on_contour"] = False
    else:
        meta["category_on_contour"] = bool(category)

    field_catalog = str(cfg_fields.get("closure_code_catalog") or "Field2711")
    catalog_id = map_closure_code_catalog_id(category, taxonomy=tax)
    if catalog_id:
        out[field_catalog] = catalog_id
        meta["closure_code_catalog_id"] = catalog_id

    if category and not catalog_id and not instruction:
        meta["category_on_contour"] = True

    return {"fields": out, "meta": meta}


def closure_type_label(option_id: str | int | None, *, taxonomy: dict[str, Any] | None = None) -> str:
    if option_id is None:
        return ""
    tax = taxonomy or load_taxonomy()
    opts = tax.get("closure_type_options") or {}
    return str(opts.get(str(option_id)) or "")
