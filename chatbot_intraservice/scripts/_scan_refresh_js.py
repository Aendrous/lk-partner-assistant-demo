# -*- coding: utf-8 -*-
from __future__ import annotations

import re
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
js = requests.get(
    base + "/build/api-clients/api-clients.umd.js?version=b1eb6ff4",
    headers=headers,
    timeout=60,
    verify=False,
).text
auth = requests.get(base + "/build/auth/iek-ckg_admin_auth.js", headers=headers, timeout=60, verify=False).text
common = requests.get(
    base + "/build/common/iek-ckg-admin-common.js?version=b1eb6ff4",
    headers=headers,
    timeout=60,
    verify=False,
).text
bundle = js + "\n" + auth + "\n" + common
for needle in ("kc-refresh", "kc-access", "refreshToken", "refresh_token", "/auth/v1", "token/refresh", "id.iek"):
    idx = 0
    hits = []
    while True:
        i = bundle.lower().find(needle.lower(), idx)
        if i < 0:
            break
        hits.append(bundle[max(0, i - 80) : i + 120].replace("\n", " "))
        idx = i + len(needle)
        if len(hits) >= 8:
            break
    print("===", needle, "count", bundle.lower().count(needle.lower()))
    for h in hits[:5]:
        print(h)

# parse cookie names from env
raw = bp_adm._raw_env()
names = [p.split("=", 1)[0].strip() for p in raw.split(";") if "=" in p]
print("cookie names in env:", names)

# try refresh with full cookie if kc-refresh present
for path in ["/api/auth/v1/refresh", "/api/auth/v1/token/refresh"]:
    for method in ("POST", "GET"):
        r = requests.request(
            method,
            base + path,
            headers={**headers, "Accept": "application/json"},
            timeout=20,
            verify=False,
        )
        print(method, path, r.status_code, (r.text or "")[:200])
        if r.status_code == 200:
            print("SET-COOKIE", r.headers.get("set-cookie", "")[:200])
