# -*- coding: utf-8 -*-
"""Probe which adm.bp search endpoint works with current BP_ADM_COOKIE."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
import urllib3
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import bp_adm  # noqa: E402

PATHS = [
    "/api/roles/v1/all",
    "/api/users/v1",
    "/api/users/v1/all",
    "/api/users/v1/search",
    "/api/user/v1",
    "/api/clients/v1",
    "/api/partners/v1",
    "/api/companies/v1",
    "/api/accounts/v1",
    "/api/registrations/v1",
    "/api/organization/v1",
    "/api/organizations/v1",
]


def main() -> int:
    headers = bp_adm._auth_headers()
    print("auth Cookie:", "Cookie" in headers, "Bearer:", "Authorization" in headers)
    q = "shdi81@mail.ru"
    for path in PATHS:
        try:
            r = requests.get(
                "https://adm.bp.iek.ru" + path,
                headers=headers,
                params={"search": q, "page": 1, "pageSize": 16, "q": q},
                timeout=20,
                verify=False,
            )
            body = (r.text or "").replace("\n", " ")[:140]
            print(f"{r.status_code} {path} {body}")
        except Exception as err:
            print("ERR", path, err)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
