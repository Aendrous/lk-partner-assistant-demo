# -*- coding: utf-8 -*-
"""L0 smoke: вопрос → ответ KB / уточнения / черновик заявки.

  python scripts/l0_ask.py "Как войти в ЛК партнёра?"
  python scripts/l0_ask.py "Не открывается bp.iek.ru" --create --email user@iek.ru
  python scripts/l0_ask.py --task-id 699802
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

from env_bootstrap import load_package_env  # noqa: E402
import l0_chat  # noqa: E402
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def main() -> int:
    load_package_env()
    parser = argparse.ArgumentParser(description="L0 ask / review ticket")
    parser.add_argument("question", nargs="*", help="Текст вопроса")
    parser.add_argument("--email", default="", help="UserEmail для create")
    parser.add_argument(
        "--create",
        action="store_true",
        help="Реально POST /api/task (нужны ServiceId + --email)",
    )
    parser.add_argument(
        "--task-id",
        default="",
        help="Разбор существующей заявки HD + уточняющие вопросы (без поста)",
    )
    parser.add_argument(
        "--no-l1",
        action="store_true",
        help="С --task-id: не гонять полный L1 preview",
    )
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if args.task_id.strip():
        result = l0_chat.review_ticket(
            args.task_id.strip(),
            user_email=args.email,
            run_l1_preview=not args.no_l1,
        )
    else:
        q = " ".join(args.question).strip()
        if not q:
            parser.error("укажите вопрос или --task-id")
        result = l0_chat.ask(q, user_email=args.email, create=args.create)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
