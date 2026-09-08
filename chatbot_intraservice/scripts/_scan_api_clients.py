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
out = ROOT / "knowledge" / "bp" / "_api_strings.txt"
# remoteEntry often lists chunk filenames
um = requests.get(
    base + "/build/user-manager/remoteEntry.js?version=b1eb6ff4",
    headers=headers,
    timeout=30,
    verify=False,
).text
chunks = re.findall(r'["\']([^"\']+\.js)["\']', um)
print("user-manager chunks", chunks[:40])

# pull user-manager chunks
bundle = js
for ch in chunks:
    if ch.startswith("http"):
        url = ch
    elif ch.startswith("/"):
        url = base + ch
    else:
        url = base + "/build/user-manager/" + ch.lstrip("./")
    try:
        bundle += "\n" + requests.get(url, headers=headers, timeout=40, verify=False).text
        print("chunk ok", url[-60:], "total", len(bundle))
    except Exception as err:
        print("chunk fail", url, err)

patterns = [
    r"https?://[^\"'\s]+/api/[^\"'\s]+",
    r"/api/[A-Za-z0-9_./\-]+",
    r"[\"']([A-Za-z0-9_\-/]*user[A-Za-z0-9_\-/]*)[\"']",
    r"[\"']([A-Za-z0-9_\-/]*account[A-Za-z0-9_\-/]*)[\"']",
    r"[\"']([A-Za-z0-9_\-/]*search[A-Za-z0-9_\-/]*)[\"']",
]
found: set[str] = set()
for pat in patterns:
    for m in re.findall(pat, bundle, flags=re.I):
        found.add(m if isinstance(m, str) else m)
lines = sorted(found)
out.write_text("\n".join(lines), encoding="utf-8")
print("wrote", out, "count", len(lines))
for line in lines:
    if any(k in line.lower() for k in ("api", "user", "account", "search", "page")):
        print(line)

# Also look for baseURL style: "accounts" + "/v1"
for m in re.findall(r"[\"']([a-z][a-z0-9\-]{2,40})[\"']\s*\+\s*[\"']/v1", bundle):
    print("BASE+v1", m)
