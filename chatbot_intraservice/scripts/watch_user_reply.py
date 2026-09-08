# -*- coding: utf-8 -*-
"""Watch: ответ заявителя / nudge исполнителя в статусе «Ожидание ответа» (46/120).

Сигналы:

1. Заявитель «спасибо / помогло / можно закрывать» → **29** «Выполнена»
   + скрытый «Пользователь подтвердил решение».
2. Уточнение / «не помогло» / доп. вопрос (из 46 или 120) → **38**
   «Передано исполнителю» + скрытый комментарий с правилом.
3. Повторный вопрос исполнителя про актуальность (≥сутки после первого ответа)
   при статусе 46 → **120** + скрытый комментарий с правилом.

  python scripts/watch_user_reply.py
  python scripts/watch_user_reply.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import urllib3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

import call_history  # noqa: E402
import intraservice  # noqa: E402
import watch_common  # noqa: E402
from settings import load_settings  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SEEN_PATH = ROOT / "pipeline" / "seen_reply.json"
_AUTOCLOSE_STATUS = "awaiting_reply_autoclose"
_AUTOCLOSE_STATUS_ID = intraservice.STATUS_KEYS[_AUTOCLOSE_STATUS]
_TRANSFERRED_STATUS = "transferred"
_TRANSFERRED_STATUS_ID = intraservice.STATUS_KEYS[_TRANSFERRED_STATUS]
_DONE_STATUS = "done"
_DONE_STATUS_ID = intraservice.STATUS_KEYS[_DONE_STATUS]
_AWAITING_REPLY_STATUS_ID = intraservice.STATUS_KEYS["awaiting_reply"]
_REOPEN_FROM_STATUS_IDS = frozenset({_AUTOCLOSE_STATUS_ID, _AWAITING_REPLY_STATUS_ID})

_PRIVATE_CONFIRMED = (
    "Пользователь подтвердил решение. "
    "Правило: подтверждение заявителем («спасибо/помогло/можно закрывать» и подобное) "
    "→ статус «Выполнена»."
)
_PRIVATE_REOPEN = (
    "Заявитель задал дополнительный вопрос / проблема не решена — возврат исполнителю. "
    "Правило: при статусе «Ожидание ответа» (46) или «…с автозакрытием» (120) "
    "уточнение заявителя → «Передано исполнителю»."
)


def private_autoclose_nudge_comment(*, hours: float = 24.0, days: int = 2) -> str:
    h = max(1, int(round(float(hours))))
    d = max(1, int(days))
    day_word = (
        "день"
        if d == 1
        else ("дня" if 2 <= d % 10 <= 4 and not (12 <= d % 100 <= 14) else "дней")
    )
    return (
        f"Автозакрытие по правилу: спустя ≥{h} ч после первого ответа исполнителя "
        "повторный вопрос («требуется ли ещё что-то / актуальна ли заявка») "
        f"→ статус «Ожидание ответа с автозакрытием» (закрытие HD через ~{d} {day_word}). "
        "Если заявитель ответит уточнением — вернём в «Передано исполнителю»."
    )


def classify_user_reply(text: str) -> str:
    """gratitude | needs_executor | ignore"""
    if watch_common.is_needs_executor_attention(text):
        return "needs_executor"
    if watch_common.is_gratitude_resolved(text):
        return "gratitude"
    return "ignore"


def _mark_seen(
    seen: dict[str, Any],
    *,
    tid: str,
    hit: dict[str, Any],
    action: str,
    signal: str,
    task: dict[str, Any],
    task_row: dict[str, Any],
    status_res: dict[str, Any] | None,
    private_res: dict[str, Any] | None,
    cur_status: int,
) -> None:
    text = str(hit.get("Comments") or "")
    seen.setdefault("tasks", {})[tid] = {
        "comment_date": hit.get("Date"),
        "handled": True,
        "action": action,
        "signal": signal,
        "at": watch_common.utc_now_iso(),
        "name": task.get("Name") or task_row.get("Name"),
        "ServiceId": task.get("ServiceId") or task_row.get("ServiceId"),
        "StatusId": (status_res or {}).get("StatusId") or cur_status,
        "url": intraservice.task_url(tid),
        "comment_preview": text[:200],
        "status_change": status_res,
        "private_comment": private_res,
    }


def process_task(
    task_row: dict[str, Any],
    *,
    dry_run: bool,
    settings: dict[str, Any],
    seen: dict[str, Any],
) -> dict[str, Any]:
    tid = str(task_row.get("Id") or "").strip()
    if not tid:
        return {"ok": False, "error": "no id"}

    task = intraservice.get_task(tid)
    lifetime = intraservice.get_task_lifetime(tid, page_size=50)
    max_age = float(settings.get("watch_user_reply_max_age_hours") or 72)
    prev = (seen.get("tasks") or {}).get(tid) or {}
    creator_kw = dict(
        creator_id=task.get("CreatorId"),
        creator_name=str(task.get("Creator") or ""),
        executor_ids=task.get("ExecutorIds"),
    )
    hit = watch_common.find_new_user_comment(
        lifetime,
        after_date=prev.get("comment_date"),
        max_age_hours=max_age,
        requester_only=False,
        client_side_only=True,
        **creator_kw,
    )
    auto_close = bool(settings.get("watch_user_reply_auto_close", True))
    reopen = bool(settings.get("watch_user_reply_reopen_enabled", True))
    days = int(settings.get("watch_user_reply_autoclose_days") or 2)
    nudge_hours = float(settings.get("watch_user_reply_relevance_nudge_hours") or 20)
    cur_status = int(task.get("StatusId") or 0)

    import service_routing

    branch = service_routing.branch_for_service_id(task.get("ServiceId"))
    contour = str((branch or {}).get("key") or "")
    crm_status_locked = contour == "crm" and not bool(
        settings.get("watch_user_reply_crm_status_changes", False)
    )

    # --- путь A: комментарий заявителя / клиентской стороны ---
    if hit:
        if prev.get("comment_date") == hit.get("Date") and prev.get("handled"):
            return {"task_id": tid, "skipped": True, "reason": "этот комментарий уже обработан"}

        text = str(hit.get("Comments") or "")
        signal = classify_user_reply(text)

        # нейтральный текст не блокирует nudge исполнителя
        if signal != "ignore":
            if crm_status_locked:
                _mark_seen(
                    seen,
                    tid=tid,
                    hit=hit,
                    action="skipped_crm_status_change",
                    signal=signal,
                    task=task,
                    task_row=task_row,
                    status_res=None,
                    private_res=None,
                    cur_status=cur_status,
                )
                call_history.append_event(
                    {
                        "type": "watch_user_reply",
                        "task_id": tid,
                        "ok": True,
                        "action": "skipped_crm_status_change",
                        "signal": signal,
                        "comment_date": hit.get("Date"),
                        "StatusId": cur_status,
                        "previous_StatusId": cur_status,
                    }
                )
                return {
                    "task_id": tid,
                    "ok": True,
                    "action": "skipped_crm_status_change",
                    "signal": signal,
                    "comment": hit,
                    "status_change": None,
                    "private_comment": None,
                    "url": intraservice.task_url(tid),
                }
            if dry_run:
                action = "would_ignore"
                target_status: int | None = None
                private_comment: str | None = None
                if signal == "needs_executor" and reopen and cur_status in _REOPEN_FROM_STATUS_IDS:
                    action = "would_move_transferred"
                    target_status = _TRANSFERRED_STATUS_ID
                    private_comment = _PRIVATE_REOPEN
                elif signal == "gratitude" and auto_close:
                    action = "would_close_done"
                    target_status = _DONE_STATUS_ID
                    private_comment = _PRIVATE_CONFIRMED
                return {
                    "task_id": tid,
                    "dry_run": True,
                    "action": action,
                    "signal": signal,
                    "comment": hit,
                    "StatusId": cur_status,
                    "target_StatusId": target_status,
                    "private_comment": private_comment,
                    "url": intraservice.task_url(tid),
                }

            action = "ignored_not_matched"
            status_res: dict[str, Any] | None = None
            private_res: dict[str, Any] | None = None

            if signal == "needs_executor" and reopen and cur_status in _REOPEN_FROM_STATUS_IDS:
                status_res = intraservice.update_task_status(tid, _TRANSFERRED_STATUS, comment="")
                private_res = (
                    intraservice.add_private_comment(tid, _PRIVATE_REOPEN)
                    if status_res.get("ok")
                    else None
                )
                ok = bool(status_res.get("ok")) and bool((private_res or {}).get("ok"))
                action = "moved_transferred" if ok else "transfer_failed"
            elif signal == "gratitude" and auto_close:
                if cur_status != _DONE_STATUS_ID:
                    status_res = intraservice.update_task_status(tid, _DONE_STATUS, comment="")
                else:
                    status_res = {"ok": True, "StatusId": _DONE_STATUS_ID, "skipped_status": True}
                private_res = (
                    intraservice.add_private_comment(tid, _PRIVATE_CONFIRMED)
                    if status_res.get("ok")
                    else None
                )
                ok = bool((status_res or {}).get("ok")) and bool((private_res or {}).get("ok"))
                action = "closed_done" if ok else "close_done_failed"

            _mark_seen(
                seen,
                tid=tid,
                hit=hit,
                action=action,
                signal=signal,
                task=task,
                task_row=task_row,
                status_res=status_res,
                private_res=private_res,
                cur_status=cur_status,
            )
            call_history.append_event(
                {
                    "type": "watch_user_reply",
                    "task_id": tid,
                    "ok": action in ("closed_done", "moved_transferred")
                    or action.startswith("ignored"),
                    "action": action,
                    "signal": signal,
                    "comment_date": hit.get("Date"),
                    "StatusId": (status_res or {}).get("StatusId"),
                    "previous_StatusId": cur_status,
                    "private_comment_ok": (private_res or {}).get("ok"),
                    "error": (status_res or {}).get("error") or (private_res or {}).get("error"),
                }
            )
            return {
                "task_id": tid,
                "ok": True,
                "action": action,
                "signal": signal,
                "comment": hit,
                "status_change": status_res,
                "private_comment": private_res,
                "url": intraservice.task_url(tid),
            }

    # --- путь B: nudge исполнителя → автозакрытие (только из 46) ---
    if not auto_close or cur_status != _AWAITING_REPLY_STATUS_ID:
        return {
            "task_id": tid,
            "skipped": True,
            "reason": "нет сигнала заявителя и нет условий для автозакрытия",
        }

    nudge = watch_common.find_executor_relevance_nudge(
        lifetime,
        after_date=prev.get("comment_date"),
        max_age_hours=max_age,
        min_hours_after_first_reply=nudge_hours,
        **creator_kw,
    )
    if not nudge:
        return {
            "task_id": tid,
            "skipped": True,
            "reason": "нет сигнала заявителя и нет nudge исполнителя",
        }
    if prev.get("comment_date") == nudge.get("Date") and prev.get("handled"):
        return {"task_id": tid, "skipped": True, "reason": "этот nudge уже обработан"}

    if crm_status_locked:
        return {"task_id": tid, "skipped": True, "reason": "CRM: смена статуса отключена"}

    priv_nudge = private_autoclose_nudge_comment(hours=nudge_hours, days=days)
    if dry_run:
        return {
            "task_id": tid,
            "dry_run": True,
            "action": "would_move_autoclose",
            "signal": "relevance_nudge",
            "comment": nudge,
            "StatusId": cur_status,
            "target_StatusId": _AUTOCLOSE_STATUS_ID,
            "private_comment": priv_nudge,
            "url": intraservice.task_url(tid),
        }

    status_res = intraservice.update_task_status(tid, _AUTOCLOSE_STATUS, comment="")
    private_res = (
        intraservice.add_private_comment(tid, priv_nudge) if status_res.get("ok") else None
    )
    ok = bool(status_res.get("ok")) and bool((private_res or {}).get("ok"))
    action = "moved_autoclose" if ok else "autoclose_failed"

    _mark_seen(
        seen,
        tid=tid,
        hit=nudge,
        action=action,
        signal="relevance_nudge",
        task=task,
        task_row=task_row,
        status_res=status_res,
        private_res=private_res,
        cur_status=cur_status,
    )
    call_history.append_event(
        {
            "type": "watch_user_reply",
            "task_id": tid,
            "ok": action == "moved_autoclose",
            "action": action,
            "signal": "relevance_nudge",
            "comment_date": nudge.get("Date"),
            "StatusId": status_res.get("StatusId"),
            "previous_StatusId": cur_status,
            "private_comment_ok": (private_res or {}).get("ok"),
            "error": status_res.get("error") or (private_res or {}).get("error"),
        }
    )
    return {
        "task_id": tid,
        "ok": True,
        "action": action,
        "signal": "relevance_nudge",
        "comment": nudge,
        "status_change": status_res,
        "private_comment": private_res,
        "url": intraservice.task_url(tid),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Watch requester replies: close on thanks, transfer on reopen, autoclose on nudge"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    if not intraservice.has_credentials():
        raise SystemExit("Нет IntraService credentials")

    settings = load_settings()
    if not settings.get("watch_user_reply_enabled", True):
        print(
            json.dumps(
                {"ok": True, "skipped": True, "reason": "watch_user_reply_enabled=false"},
                ensure_ascii=False,
            )
        )
        return 0

    import service_filter

    service_ids = service_filter.effective_watch_service_ids(
        settings,
        legacy_key="watch_user_reply_service_ids",
        default=[731, 732, 833, 827],
        action="watch",
    )
    status_ids = list(settings.get("watch_user_reply_status_ids") or [46, 120])
    page_size = max(args.limit * 4, 40)

    candidates = watch_common.list_tasks(
        service_ids=service_ids, status_ids=status_ids, page_size=page_size
    )
    candidates.sort(key=lambda r: str((r or {}).get("Changed") or ""), reverse=True)

    seen = watch_common.load_seen(SEEN_PATH)
    results: list[dict] = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        if len(results) >= args.limit:
            break
        try:
            results.append(
                process_task(row, dry_run=args.dry_run, settings=settings, seen=seen)
            )
        except Exception as exc:
            results.append({"task_id": row.get("Id"), "ok": False, "error": str(exc)[:300]})

    if not args.dry_run:
        watch_common.save_seen(SEEN_PATH, seen)

    autoclose_actions = ("moved_autoclose", "would_move_autoclose")
    done_actions = ("closed_done", "would_close_done")
    transfer_actions = ("moved_transferred", "would_move_transferred")
    out = {
        "ok": True,
        "dry_run": args.dry_run,
        "candidates": len(candidates),
        "checked": len(results),
        "closed_done": len([r for r in results if r.get("action") in done_actions]),
        "moved_autoclose": len([r for r in results if r.get("action") in autoclose_actions]),
        "moved_transferred": len([r for r in results if r.get("action") in transfer_actions]),
        "ignored": len(
            [
                r
                for r in results
                if r.get("action") in ("ignored_not_matched", "would_ignore")
                or r.get("skipped")
            ]
        ),
        "results": results,
    }
    watch_common.dump_json(ROOT / "_watch_user_reply.json", out)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
