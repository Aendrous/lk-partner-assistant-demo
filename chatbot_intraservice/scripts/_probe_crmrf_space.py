# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from env_bootstrap import load_package_env

load_package_env()
import confluence_client as cf

s = cf.session()
pat = os.environ.get("CONFLUENCE_PAT", "")

for q in ("IntraService", "быстрые", "чатбот", "ИИ"):
    r = s.get(
        f"{s.base}/rest/api/content/search",
        params={"cql": f'space = CRMRF AND title ~ "{q}"', "limit": 10},
        timeout=60,
    )
    print("---", q, r.status_code)
    if r.ok:
        for x in r.json().get("results", []):
            print(" ", x["id"], x["title"])

for slug in ("ggAM", "hQAM"):
    url = f"https://confluence.dev.iek.ru/x/{slug}"
    r = requests.get(
        url,
        allow_redirects=True,
        verify=False,
        headers={"Authorization": f"Bearer {pat}"},
        timeout=30,
    )
    print(slug, "->", r.url)
