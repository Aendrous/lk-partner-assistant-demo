# -*- coding: utf-8 -*-
import json
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
base = (os.environ.get("CONFLUENCE_BASE_URL") or "").rstrip("/")
pat = (os.environ.get("CONFLUENCE_PAT") or "").strip()
s = requests.Session()
s.verify = False
s.headers.update({"Authorization": f"Bearer {pat}", "Accept": "application/json"})
queries = [
    'text ~ "резервировать товары в пути" AND type = page',
    'text ~ "Резервы в пути" AND type = page AND space = WEBKB',
    'text ~ "подтвердить" AND text ~ "в пути" AND type = page AND space = WEBKB',
]
out = []
for cql in queries:
    r = s.get(base + "/rest/api/content/search", params={"cql": cql, "limit": 8}, timeout=45)
    rows = []
    if r.ok:
        for item in r.json().get("results") or []:
            rows.append({"id": item.get("id"), "title": item.get("title")})
    out.append({"cql": cql, "http": r.status_code, "rows": rows, "err": "" if r.ok else r.text[:300]})
Path(ROOT / "_cql_search.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("saved", ROOT / "_cql_search.json")
