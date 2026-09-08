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

base = "https://adm.bp.iek.ru"
root = requests.get(base + "/iek-ckg-admin-root.js?version=b1eb6ff4", timeout=40, verify=False).text
print("root size", len(root))
for needle in ("refresh", "kc-", "auth/v1", "token", "id.iek", "openid", "portal-ckg"):
    print(needle, root.lower().count(needle.lower()))
for m in re.findall(r"https://id[^\"'\s]+", root):
    print("ID", m[:150])
for m in re.findall(r"[\"'](/api/auth[^\"']+)[\"']", root):
    print("AUTH", m)
