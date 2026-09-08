# -*- coding: utf-8 -*-
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from env_bootstrap import load_package_env

load_package_env()
import confluence_client as cf

spec = importlib.util.spec_from_file_location("b", ROOT / "scripts" / "build_crm_corpus.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

s = cf.session()
parent = "6095240"
r = s.get(
    f"{s.base}/rest/api/content/{parent}/child/page",
    params={"limit": 50, "expand": "page"},
    timeout=60,
)
kids = r.json().get("results", [])
rows = []
for x in kids:
    pid = str(x["id"])
    try:
        p = b.fetch_page(s, pid)
        item = b.page_to_qa(p, 1)
        rows.append(
            {
                "id": pid,
                "title": p["title"],
                "text_len": len(p["text"]),
                "accepted": item is not None,
                "url": p["url"],
            }
        )
    except Exception as e:
        rows.append({"id": pid, "title": x.get("title"), "error": str(e)[:80]})

rows.sort(key=lambda r: r.get("text_len", 0), reverse=True)
out = ROOT / "_crm_support_children.json"
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
accepted = [r for r in rows if r.get("accepted")]
print(f"children={len(rows)} accepted_by_page_to_qa={len(accepted)}")
for r in rows[:12]:
    print(r.get("id"), r.get("text_len", 0), r.get("accepted"), (r.get("title") or "")[:70])

# check QA corpus ids
qa = (ROOT / "knowledge" / "crm" / "qa.md").read_text(encoding="utf-8")
kid_ids = {r["id"] for r in rows}
in_corpus = [i for i in kid_ids if i in qa or any(t in qa for t in [r.get("title","") for r in rows if r["id"]==i])]
print("any child title in qa.md:", sum(1 for r in rows if r.get("title") and r["title"] in qa))
