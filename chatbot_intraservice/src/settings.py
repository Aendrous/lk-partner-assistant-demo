# -*- coding: utf-8 -*-
"""Настройки чатбота IntraService: defaults + settings.local.json + env."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
DEFAULT_PATH = PKG / "config" / "settings.default.json"
LOCAL_PATH = PKG / "config" / "settings.local.json"

_SETTING_KEYS = (
    "auto_learn_kb",
    "auto_learn_on_close",
    "auto_learn_on_analyze",
    "auto_post_comment",
    "auto_post_public_comment",
    "auto_take_in_work",
    "public_reply_only_if_kb",
    "ui_mode",
    "post_learn_note",
    "auto_push_confluence_draft",
    "semantic_dedup_enabled",
    "semantic_duplicate_threshold",
    "semantic_supplement_threshold",
    "skip_semantic_duplicate",
    "auto_supplement_existing",
    "skip_if_in_progress_or_awaiting",
    "link_related_on_post",
    "add_parent_creator_as_observer",
    "skip_if_kb_found",
    "skip_if_draft_exists",
    "require_closed_for_auto_learn",
    "pipeline_save_runs",
    "watch_service_ids",
    "watch_closed_status_ids",
    "watch_new_enabled",
    "watch_new_service_ids",
    "watch_new_status_ids",
    "watch_new_max_age_hours",
    "watch_user_reply_enabled",
    "watch_user_reply_auto_close",
    "watch_user_reply_reopen_enabled",
    "watch_user_reply_service_ids",
    "watch_user_reply_status_ids",
    "watch_user_reply_max_age_hours",
    "watch_user_reply_autoclose_days",
    "gap_digest_enabled",
    "drafts_review_digest_enabled",
    "watch_overdue_enabled",
    "watch_overdue_service_ids",
    "watch_overdue_status_ids",
    "watch_overdue_marker",
    "watch_overdue_max_age_hours",
    "overdue_shift_deadline",
    "overdue_shift_deadline_days",
    "overdue_post_public",
    "onec_analyze_scope",
    "watch_user_reply_crm_status_changes",
)

_BOOL_ENV = {
    "INTRASERVICE_AUTO_LEARN_KB": "auto_learn_kb",
    "INTRASERVICE_AUTO_LEARN_ON_CLOSE": "auto_learn_on_close",
    "INTRASERVICE_AUTO_LEARN_ON_ANALYZE": "auto_learn_on_analyze",
    "INTRASERVICE_AUTO_POST_COMMENT": "auto_post_comment",
    "INTRASERVICE_AUTO_POST_PUBLIC_COMMENT": "auto_post_public_comment",
    "INTRASERVICE_AUTO_TAKE_IN_WORK": "auto_take_in_work",
    "INTRASERVICE_PUBLIC_REPLY_ONLY_IF_KB": "public_reply_only_if_kb",
    "INTRASERVICE_POST_LEARN_NOTE": "post_learn_note",
    "INTRASERVICE_AUTO_PUSH_CONFLUENCE_DRAFT": "auto_push_confluence_draft",
    "INTRASERVICE_SEMANTIC_DEDUP_ENABLED": "semantic_dedup_enabled",
    "INTRASERVICE_SKIP_SEMANTIC_DUPLICATE": "skip_semantic_duplicate",
    "INTRASERVICE_AUTO_SUPPLEMENT_EXISTING": "auto_supplement_existing",
    "INTRASERVICE_SKIP_IF_IN_PROGRESS_OR_AWAITING": "skip_if_in_progress_or_awaiting",
    "INTRASERVICE_LINK_RELATED_ON_POST": "link_related_on_post",
    "INTRASERVICE_ADD_PARENT_CREATOR_AS_OBSERVER": "add_parent_creator_as_observer",
    "INTRASERVICE_SKIP_IF_KB_FOUND": "skip_if_kb_found",
    "INTRASERVICE_SKIP_IF_DRAFT_EXISTS": "skip_if_draft_exists",
    "INTRASERVICE_PIPELINE_SAVE_RUNS": "pipeline_save_runs",
    "INTRASERVICE_WATCH_OVERDUE_ENABLED": "watch_overdue_enabled",
    "INTRASERVICE_WATCH_NEW_ENABLED": "watch_new_enabled",
    "INTRASERVICE_WATCH_USER_REPLY_ENABLED": "watch_user_reply_enabled",
    "INTRASERVICE_WATCH_USER_REPLY_AUTO_CLOSE": "watch_user_reply_auto_close",
    "INTRASERVICE_GAP_DIGEST_ENABLED": "gap_digest_enabled",
    "INTRASERVICE_OVERDUE_SHIFT_DEADLINE": "overdue_shift_deadline",
    "INTRASERVICE_OVERDUE_POST_PUBLIC": "overdue_post_public",
    "INTRASERVICE_WATCH_USER_REPLY_CRM_STATUS_CHANGES": "watch_user_reply_crm_status_changes",
}

def _parse_bool(val: str) -> bool:
    return val.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> dict[str, Any]:
    try:
        from env_bootstrap import load_package_env

        load_package_env()
    except ImportError:
        pass
    data: dict[str, Any] = {}
    if DEFAULT_PATH.is_file():
        data = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    data.pop("_comment", None)
    if LOCAL_PATH.is_file():
        local = json.loads(LOCAL_PATH.read_text(encoding="utf-8"))
        local.pop("_comment", None)
        data.update(local)
    for env_key, field in _BOOL_ENV.items():
        raw = os.environ.get(env_key)
        if raw is not None and str(raw).strip() != "":
            data[field] = _parse_bool(str(raw))
    return data


def save_local_settings(updates: dict[str, Any]) -> Path:
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = load_settings()
    merged = deepcopy(current)
    for key, val in updates.items():
        if key.startswith("_"):
            continue
        merged[key] = val
    # не тащим _comment из defaults в local
    merged.pop("_comment", None)
    LOCAL_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return LOCAL_PATH


def settings_summary() -> dict[str, Any]:
    s = load_settings()
    out: dict[str, Any] = {k: s.get(k) for k in _SETTING_KEYS}
    out["local_file"] = str(LOCAL_PATH) if LOCAL_PATH.is_file() else None
    return out
