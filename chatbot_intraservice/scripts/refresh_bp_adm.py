# -*- coding: utf-8 -*-
"""Обновить kc-access для adm.bp и сохранить в .env + .bp_adm_session.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

import bp_adm  # noqa: E402


def main() -> int:
    cookies = bp_adm.load_cookies()
    print("cookies:", sorted(cookies.keys()))
    exp = bp_adm._access_exp(cookies)
    if exp:
        import time

        print("access ttl_sec:", exp - int(time.time()))
    result = bp_adm.refresh_cookies(cookies)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
