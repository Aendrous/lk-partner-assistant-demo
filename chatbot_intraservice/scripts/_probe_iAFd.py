# -*- coding: utf-8 -*-
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from env_bootstrap import load_package_env

load_package_env()
import confluence_client as cf

pat = os.environ.get("CONFLUENCE_PAT", "")
slug = "iAFd"
r = requests.get(
    f"https://confluence.dev.iek.ru/x/{slug}",
    allow_redirects=True,
    verify=False,
    headers={"Authorization": f"Bearer {pat}"},
    timeout=30,
)
print("redirect:", r.url)
m = re.search(r"pageId=(\d+)", r.url)
page_id = m.group(1) if m else ""
if not page_id:
    m2 = re.search(r"/pages/(\d+)/", r.url)
    page_id = m2.group(1) if m2 else ""
print("page_id:", page_id)

s = cf.session()
if page_id:
    p = cf.get_page(s, page_id, expand="body.storage,space,version")
    title = p.get("title")
    space = (p.get("space") or {}).get("key")
    body = ((p.get("body") or {}).get("storage") or {}).get("value") or ""
    print("title:", title)
    print("space:", space)
    print("body_len:", len(body))
    # plain text snippet
    t = re.sub(r"<[^>]+>", " ", body)
    t = re.sub(r"\s+", " ", t).strip()
    print("snippet:", t[:500])

# check if page_id in CRMRF_PAGE_IDS
sys.path.insert(0, str(ROOT / "scripts"))
import importlib.util
spec = importlib.util.spec_from_file_location("b", ROOT / "scripts" / "build_crm_corpus.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
print("in CRMRF_PAGE_IDS:", page_id in b.CRMRF_PAGE_IDS)

if page_id:
    fp = b.fetch_page(s, page_id)
    print("fetch title:", fp["title"])
    print("text_len:", len(fp["text"]))
    print("text preview:\n", fp["text"][:1500])
    item = b.page_to_qa(fp, 99)
    print("page_to_qa accepted:", item is not None)
    if item:
        print("qa id:", item.get("id"), "q:", item.get("question")[:80])

    r2 = s.get(f"{s.base}/rest/api/content/{page_id}/child/page", params={"limit": 40}, timeout=60)
    print("children:", r2.status_code, len(r2.json().get("results", [])))
    for x in r2.json().get("results", [])[:20]:
        print(" ", x["id"], x["title"])

# check published QA page for title keywords
qa_id = "124642256"
qa = cf.get_page(s, qa_id, expand="body.storage")
qa_body = ((qa.get("body") or {}).get("storage") or {}).get("value") or ""
print("qa_page title:", qa.get("title"))
# search for words from source title in qa body
if page_id and title:
    words = [w for w in re.findall(r"\w{4,}", title, re.U) if len(w) > 3][:5]
    for w in words:
        print(f"  '{w}' in QA:", w.lower() in qa_body.lower())
