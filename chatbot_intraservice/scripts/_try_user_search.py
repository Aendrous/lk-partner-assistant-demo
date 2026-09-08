# -*- coding: utf-8 -*-
from __future__ import annotations

import json
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

headers = bp_adm._auth_headers()
base = "https://adm.bp.iek.ru"
email = "shdi81@mail.ru"
paths = [
    "/api/user/v1/users/search",
    "/api/user/v1/users",
    "/api/user/v1/profiles",
    "/api/user/v1/profile",
    "/api/user/v1/getProfiles",
    "/api/roles/v1/all",
    "/api/company/v1/companies",
    "/api/company/v1/search",
    "/api/admin/v1/users",
    "/api/admin/v1/users/search",
]
params_list = [
    {"email": email},
    {"email": email, "page": 1, "pageSize": 16},
    {"search": email, "page": 1, "pageSize": 16},
    {"iamId": None},
]

for path in paths:
    for params in params_list:
        p = {k: v for k, v in params.items() if v is not None}
        r = requests.get(base + path, headers=headers, params=p, timeout=20, verify=False)
        ctype = (r.headers.get("content-type") or "")[:40]
        body = (r.text or "").replace("\n", " ")[:180]
        if r.status_code == 404 and "html" in ctype:
            continue
        print(r.status_code, path, p, body)
