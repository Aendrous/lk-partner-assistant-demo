# -*- coding: utf-8 -*-
import re
import requests
import urllib3

urllib3.disable_warnings()
base = "https://adm.bp.iek.ru"
js = ""
for path in [
    "/build/auth/iek-ckg_admin_auth.js",
    "/build/common/iek-ckg-admin-common.js?version=b1eb6ff4",
    "/build/api-clients/api-clients.umd.js?version=b1eb6ff4",
]:
    js += requests.get(base + path, timeout=60, verify=False).text + "\n"

print("kc cookies", sorted(set(re.findall(r"kc-[a-zA-Z0-9_-]+", js))))
print("auth routes", sorted(set(re.findall(r"/api/auth/[a-zA-Z0-9_./-]+", js)))[:40])
for m in re.finditer(r"/api/auth[^\"']{0,60}", js):
    s = m.group(0)
    if "refresh" in s or "token" in s or "login" in s:
        print("route", s)
