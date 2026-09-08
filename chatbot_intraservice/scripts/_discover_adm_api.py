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
targets = [
    "/iek-ckg-admin-root.js?version=b1eb6ff4",
    "/build/user-manager/remoteEntry.js?version=b1eb6ff4",
    "/build/api-clients/api-clients.umd.js?version=b1eb6ff4",
    "/build/common/iek-ckg-admin-common.js?version=b1eb6ff4",
    "/build/distributors-manager/remoteEntry.js?version=b1eb6ff4",
]
# collect more chunks referenced by remoteEntry
api_paths: set[str] = set()
queue = list(targets)
seen: set[str] = set()
while queue:
    path = queue.pop(0)
    if path in seen:
        continue
    seen.add(path)
    url = path if path.startswith("http") else base + path
    try:
        js = requests.get(url, headers=headers, timeout=40, verify=False).text or ""
    except Exception as err:
        print("fail", path, err)
        continue
    print("ok", path.split("?")[0][-50:], "size", len(js))
    for p in re.findall(r"/api/[A-Za-z0-9_./\-]+", js):
        api_paths.add(p.rstrip(".,);'\""))
    # webpack chunk urls
    for chunk in re.findall(r"[\"'](\./[^\"']+\.js)[\"']", js):
        # relative to folder
        folder = "/".join(path.split("?")[0].split("/")[:-1])
        rel = chunk[1:]  # drop leading .
        queue.append(folder + rel + ("?" + path.split("?", 1)[1] if "?" in path else ""))
    for chunk in re.findall(r"[\"'](/build/[^\"']+\.js)[\"']", js):
        queue.append(chunk)

print("apis", len(api_paths))
for p in sorted(api_paths):
    if any(x in p.lower() for x in ("user", "account", "search", "regist", "compan", "partner", "client", "person")):
        print(p)

q = "shdi81@mail.ru"
# test interesting ones
cands = [p for p in sorted(api_paths) if not p.endswith("/")]
# de-dup templates
for p in cands:
    if any(x in p for x in ("{", ":id", ":uuid")):
        continue
    r = requests.get(
        base + p,
        headers=headers,
        params={"search": q, "page": 1, "pageSize": 16, "q": q},
        timeout=15,
        verify=False,
    )
    if r.status_code == 404:
        continue
    body = (r.text or "").replace("\n", " ")[:140]
    print("HIT", r.status_code, p, body)
