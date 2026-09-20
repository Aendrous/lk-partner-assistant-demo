# -*- coding: utf-8 -*-
"""Публикация runbook production VM chatbot.iek.local в WEBKB.

    python scripts/publish_chatbot_vm_deployment_confluence.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import confluence_client as cf  # noqa: E402
from env_bootstrap import load_package_env  # noqa: E402

SPACE = "WEBKB"
TITLE = "Чатбот IntraService: production на chatbot.iek.local (эксплуатация)"
SOURCE_MD = ROOT / "docs" / "deployment_chatbot_iek_local.md"
PROJECT_META = ROOT / "docs" / "confluence" / "intraservice_project_page_id.json"
OUT_META = ROOT / "docs" / "confluence" / "chatbot_vm_deployment_page_id.json"

BANNER = """
<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:rich-text-body>
<p><strong>Production runbook:</strong> L0/L1, HTTPS reverse proxy, systemd, n8n и безопасный процесс доработок для <code>chatbot.iek.local</code>.</p>
<p>Секреты, токены и закрытые ключи в страницу не добавляются. Исходник: <code>chatbot_intraservice/docs/deployment_chatbot_iek_local.md</code> · обновление: <code>python scripts/publish_chatbot_vm_deployment_confluence.py</code>.</p>
</ac:rich-text-body></ac:structured-macro>
"""


def _parent_id() -> str:
    if PROJECT_META.is_file():
        try:
            return str(json.loads(PROJECT_META.read_text(encoding="utf-8"))["page_id"])
        except (KeyError, json.JSONDecodeError):
            pass
    return "124640056"


def _md_to_body(md: str) -> str:
    parts: list[str] = [BANNER.strip()]
    for chunk in re.split(r"(```[\s\S]*?```)", md):
        chunk = chunk.strip()
        if not chunk:
            continue
        if not chunk.startswith("```"):
            parts.append(cf.markdown_to_storage(chunk))
            continue
        lang_match = re.match(r"^```(\w+)?", chunk)
        lang = lang_match.group(1) if lang_match and lang_match.group(1) else "text"
        code = re.sub(r"^```\w*\s*", "", chunk)
        code = re.sub(r"\s*```$", "", code).strip()
        parts.append(
            '<ac:structured-macro ac:name="code" ac:schema-version="1">'
            f'<ac:parameter ac:name="language">{lang}</ac:parameter>'
            f"<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )
    return "\n".join(parts)


def main() -> int:
    load_package_env()
    if not SOURCE_MD.is_file():
        raise SystemExit(f"Нет {SOURCE_MD}")
    parent_id = _parent_id()
    storage = _md_to_body(SOURCE_MD.read_text(encoding="utf-8"))
    session = cf.session()
    existing = cf.find_page_by_title(session, space=SPACE, title=TITLE, parent_id=parent_id)
    if existing:
        page_id = str(existing["id"])
        cf.update_page(session, page_id, title=TITLE, storage=storage, message="Sync VM deployment runbook")
    else:
        result = cf.create_page(session, space=SPACE, title=TITLE, parent_id=parent_id, storage=storage)
        page_id = str(result.get("id") or "")
    url = cf.view_url(session, page_id)
    OUT_META.parent.mkdir(parents=True, exist_ok=True)
    OUT_META.write_text(
        json.dumps(
            {
                "page_id": page_id,
                "title": TITLE,
                "parent_id": parent_id,
                "space": SPACE,
                "url": url,
                "source": "docs/deployment_chatbot_iek_local.md",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"page_id": page_id, "url": url}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
