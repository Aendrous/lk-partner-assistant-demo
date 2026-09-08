"""Probe Bitrix admin login — one-off diagnostic."""
import os
import re
import sys
from pathlib import Path

import requests
import urllib3
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
urllib3.disable_warnings()

user = os.environ.get("LK_USER", "")
pwd = os.environ.get("LK_PASSWORD", "")
base = os.environ.get("LK_BASE_URL", "https://lk.iek.ru").rstrip("/")

s = requests.Session()
s.verify = False

for path in ("/bitrix/admin/index.php?logout=yes", "/bitrix/admin/"):
    r = s.get(f"{base}{path}", timeout=30, allow_redirects=True)
    print("GET", path, "->", r.status_code, r.url[:120])
    if "USER_LOGIN" in r.text:
        sm = re.search(r'name="sessid"\s+value="([^"]+)"', r.text)
        sessid = sm.group(1) if sm else ""
        print("sessid", sessid[:20] if sessid else "none")
        data = {
            "AUTH_FORM": "Y",
            "TYPE": "AUTH",
            "USER_LOGIN": user,
            "USER_PASSWORD": pwd,
            "Login": "Войти",
        }
        if sessid:
            data["sessid"] = sessid
        r = s.post(
            f"{base}/bitrix/admin/index.php",
            data=data,
            timeout=30,
            allow_redirects=True,
        )
        print("POST auth+sessid", r.status_code, r.url[:100])
        print("cookies", {k: v[:20] + "..." for k, v in s.cookies.get_dict().items()})
        print("auth err?", "Неверный логин" in r.text or "incorrect" in r.text.lower())
        break

# variants
for variant in [user, f"IEK\\{user}", f"{user}@iek.ru", f"{user}@iek.local"]:
    s2 = requests.Session()
    s2.verify = False
    r0 = s2.get(f"{base}/bitrix/admin/index.php?logout=yes", timeout=30, allow_redirects=True)
    sm = re.search(r'name="sessid"\s+value="([^"]+)"', r0.text)
    data = {
        "AUTH_FORM": "Y",
        "TYPE": "AUTH",
        "USER_LOGIN": variant,
        "USER_PASSWORD": pwd,
        "Login": "Войти",
    }
    if sm:
        data["sessid"] = sm.group(1)
    r = s2.post(f"{base}/bitrix/admin/index.php", data=data, timeout=30, allow_redirects=True)
    ok = "USER_LOGIN" not in s2.get(f"{base}/bitrix/admin/user_admin.php?lang=ru", timeout=20).text[:3000]
    print("variant", variant, "admin_ok?", ok)
    if ok:
        s = s2
        break

r2 = s.get(f"{base}/bitrix/admin/user_admin.php?lang=ru", timeout=30)
print("user_admin", r2.status_code, len(r2.text))
print("auth page?", "USER_LOGIN" in r2.text or "authorize" in r2.text.lower()[:3000])

email = sys.argv[1] if len(sys.argv) > 1 else "89245042044@mail.ru"
from urllib.parse import quote

url = (
    f"{base}/bitrix/admin/user_admin.php"
    f"?PAGEN_1=1&SIZEN_1=100&lang=ru&set_filter=Y&adm_filter_applied=0"
    f"&find={quote(email)}&find_type=email"
)
r3 = s.get(url, timeout=30)
print("search", r3.status_code, email)
if "Найдено" in r3.text or "adm-list-table" in r3.text:
    print("table found")
    for m in re.finditer(r"user_edit\.php\?ID=(\d+)[^\"']*[^>]*>([^<]+)", r3.text):
        print(" user", m.group(1), m.group(2).strip()[:60])
else:
    print(r3.text[:800])
