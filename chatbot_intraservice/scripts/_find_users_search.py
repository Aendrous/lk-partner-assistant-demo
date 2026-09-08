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
    base + "/build/user-manager/iek-ckg_admin_user_manager.js",
    headers=headers,
    timeout=60,
    verify=False,
).text
api = requests.get(
    base + "/build/api-clients/api-clients.umd.js?version=b1eb6ff4",
    headers=headers,
    timeout=60,
    verify=False,
).text
bundle = js + "\n" + api

for needle in ("users/search", "pageSize", "usersSuggestions", "/user/v1", "lk-users"):
    idxs = [m.start() for m in re.finditer(re.escape(needle), bundle)]
    print(needle, "count", len(idxs))
    for i in idxs[:5]:
        print("---", bundle[max(0, i - 120) : i + 160].replace("\n", " "))

# try candidate URLs
cands = [
    "/api/users/search",
    "/api/user/users/search",
    "/api/lk/users/search",
    "/users/search",
    "/api/v1/users/search",
    "/api/user/v1",
    "/api/user/v1/search",
    "/api/users/v1/search",
    "/gateway/api/users/search",
    "/api/gateway/users/search",
]
# also extract base URLs from env-like strings
bases = sorted(set(re.findall(r"https://[a-z0-9.\-]+(?:/[a-z0-9.\-/_]*)?", bundle, flags=re.I)))
print("https bases sample:")
for b in bases:
    if "iek" in b.lower() or "ckg" in b.lower() or "bp" in b.lower():
        print(b)

q = "shdi81@mail.ru"
for path in cands:
    for host in (base, "https://bp.iek.ru", "https://api.bp.iek.ru", "https://adm.bp.iek.ru"):
        url = path if path.startswith("http") else host + path
        if not url.startswith("http"):
            continue
        try:
            r = requests.get(
                url,
                headers=headers,
                params={"search": q, "page": 1, "pageSize": 16, "q": q},
                timeout=12,
                verify=False,
            )
        except Exception as err:
            print("ERR", url, err)
            continue
        if r.status_code == 404:
            continue
        print("HIT", r.status_code, url, (r.text or "")[:120].replace("\n", " "))
