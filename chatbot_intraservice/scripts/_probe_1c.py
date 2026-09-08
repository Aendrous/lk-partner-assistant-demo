# -*- coding: utf-8 -*-
"""Probe 1C HTTP without printing secrets."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
from gigachat_client import load_env  # noqa: E402

load_env(ROOT / ".env")
load_env(REPO / ".env")
user = (os.environ.get("1C_USER") or "").strip()
password = (os.environ.get("1C_USER_PASSWORD") or "").strip()
base_env = (os.environ.get("1C_BASE_URL") or os.environ.get("ONEC_BASE_URL") or "").strip()
print("has_user", bool(user), "has_password", bool(password), "has_base", bool(base_env))
candidates = [u for u in [base_env] if u] + [
    "https://1c.iek.local",
    "https://erp.iek.local",
    "https://ut.iek.local",
    "https://holding-1c.iek.local",
    "http://1c.iek.local",
]
seen = set()
for url in candidates:
    url = url.rstrip("/")
    if url in seen:
        continue
    seen.add(url)
    for path in ("", "/odata/standard.odata/", "/hs/", "/ut/odata/standard.odata/"):
        try:
            r = requests.get(
                url + path,
                auth=(user, password) if user and password else None,
                timeout=8,
                verify=False,
                allow_redirects=False,
            )
            print(r.status_code, url + path, (r.headers.get("www-authenticate") or "")[:80], (r.headers.get("content-type") or "")[:40])
        except Exception as exc:
            print("ERR", url + path, type(exc).__name__)
