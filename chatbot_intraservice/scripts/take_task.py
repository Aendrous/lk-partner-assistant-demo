# -*- coding: utf-8 -*-
"""Взять заявку в работу или сменить статус (IntraService PUT).

Usage:
  python scripts/take_task.py 123456
  python scripts/take_task.py 123456 --awaiting-reply --comment "Уточните URL и время МСК"
  python scripts/take_task.py 123456 --status transferred
  python scripts/take_task.py --list-statuses
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import intraservice  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="IntraService: взять в работу / сменить статус")
    parser.add_argument("task_id", nargs="?", help="Id заявки")
    parser.add_argument("--awaiting-reply", action="store_true", help="Ожидание ответа пользователя")
    parser.add_argument("--status", help="Ключ/Id/имя статуса (вместо take-in-work)")
    parser.add_argument("--comment", default="", help="Комментарий")
    parser.add_argument("--assign-self", action="store_true", help="Добавить себя в исполнители")
    parser.add_argument("--list-statuses", action="store_true", help="Показать справочник статусов")
    parser.add_argument("--dry-run", action="store_true", help="Только показать, какой StatusId будет")
    args = parser.parse_args()

    if not intraservice.has_credentials():
        raise SystemExit("Нет INTRASERVICE_USER / INTRASERVICE_PASSWORD в chatbot_intraservice/.env")

    if args.list_statuses:
        for item in intraservice.list_task_statuses():
            print(f"{item.get('Id')}\t{item.get('Name')}")
        return 0

    if not args.task_id:
        raise SystemExit("Укажите task_id или --list-statuses")

    if args.dry_run:
        key = "awaiting_reply" if args.awaiting_reply else (args.status or "in_progress")
        print(json.dumps(intraservice.resolve_status(key), ensure_ascii=False, indent=2))
        print(json.dumps(intraservice.current_user(), ensure_ascii=False, indent=2))
        return 0

    if args.awaiting_reply:
        if not args.comment.strip():
            raise SystemExit("Для --awaiting-reply нужен --comment")
        result = intraservice.set_task_awaiting_reply(args.task_id, args.comment)
    elif args.status:
        result = intraservice.update_task_status(
            args.task_id,
            args.status,
            comment=args.comment,
            assign_self=args.assign_self,
        )
    else:
        result = intraservice.take_task_in_work(args.task_id, comment=args.comment)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
