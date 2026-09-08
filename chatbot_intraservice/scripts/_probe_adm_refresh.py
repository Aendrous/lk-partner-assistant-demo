# -*- coding: utf-8 -*-
"""Discover Keycloak refresh flow for adm.bp."""
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
for path in [
    "/build/auth/remoteEntry.js?version=b1eb6ff4",
    "/build/auth/iek-ckg_admin_auth.js",
]:
    url = base + path if not path.startswith("http") else path
    r = requests.get(url, headers=headers, timeout=40, verify=False)
    js = r.text or ""
    print("===", path, "size", len(js), "status", r.status_code)
    for needle in ("refresh", "kc-refresh", "kc-access", "token", "iekid", "keycloak", "portal-ckg"):
        print(needle, js.lower().count(needle.lower()))
    for m in re.findall(r"https://[^\"'\s]+", js):
        if any(x in m.lower() for x in ("auth", "token", "refresh", "iek", "keycloak", "id.")):
            print("URL", m[:120])
    for m in re.findall(r"[\"'](/api/[^\"']+)[\"']", js):
        if "auth" in m.lower() or "token" in m.lower() or "refresh" in m.lower():
            print("API", m)

# try common refresh endpoints on adm
raw = bp_adm._raw_env()
cookie = bp_adm._cookie()
print("cookie sample", cookie[:80], "...")
for path in [
    "/api/auth/v1/refresh",
    "/api/auth/refresh",
    "/api/auth/v1/token",
    "/api/auth/v1/token/refresh",
    "/api/user/v1/token/refresh",
    "/build/auth/refresh",
]:
    r = requests.post(
        base + path,
        headers={**headers, "Content-Type": "application/json"},
        json={},
        timeout=20,
        verify=False,
    )
    if r.status_code != 404:
        print("POST", path, r.status_code, (r.text or "")[:120])
