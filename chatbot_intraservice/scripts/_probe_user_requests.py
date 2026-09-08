# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from env_bootstrap import load_package_env

load_package_env()
import confluence_client as cf

s = cf.session()
for q in ("обращения", "обращений", "пользовател"):
    r = s.get(
        f"{s.base}/rest/api/content/search",
        params={"cql": f'space = CRM AND title ~ "{q}"', "limit": 20},
        timeout=60,
    )
    print("---", q, r.status_code)
    for x in r.json().get("results", []):
        print(" ", x["id"], x["title"])
