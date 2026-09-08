# -*- coding: utf-8 -*-
"""Проверка BP_ADM_COOKIE и авто-refresh kc-access."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

import bp_adm  # noqa: E402


def main() -> int:
    cookies = bp_adm.load_cookies()
    print("cookie names:", sorted(cookies.keys()))
    exp = bp_adm._access_exp(cookies)
    if exp:
        print("access ttl_sec:", exp - int(time.time()))
    auth = bp_adm.ensure_fresh_auth()
    print("auth:", json.dumps(auth, ensure_ascii=False, indent=2))
    result = bp_adm.search_user(sys.argv[1] if len(sys.argv) > 1 else "shdi81@mail.ru")
    safe = {k: result[k] for k in result if k != "matches"}
    if result.get("matches"):
        safe["matches"] = result["matches"][:2]
    print("search:", json.dumps(safe, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
