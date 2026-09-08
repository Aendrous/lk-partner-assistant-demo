# -*- coding: utf-8 -*-
"""Публикация «дополнительные настройки и идеи» в WEBKB.

  python scripts/publish_features_confluence.py

Родитель: страница проекта (124640056).
Источник: docs/настройки_дополнительных_возможностей.md
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
TITLE = "Чатбот IntraService: дополнительные настройки и идеи развития"
SOURCE_MD = ROOT / "docs" / "настройки_дополнительных_возможностей.md"
PROJECT_META = ROOT / "docs" / "confluence" / "intraservice_project_page_id.json"
OUT_META = ROOT / "docs" / "confluence" / "features_settings_page_id.json"

BANNER = """
<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:rich-text-body>
<p><strong>Для руководителя:</strong> что уже внедрено в чатботе 1 линии HelpDesk,
как включается/отключается, и какие идеи можно развивать дальше.</p>
<p>Исходник: <code>chatbot_intraservice/docs/настройки_дополнительных_возможностей.md</code> ·
обновление: <code>python scripts/publish_features_confluence.py</code>.</p>
<p>См. также:
<ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Чатбот IntraService: баги и исправления" /></ac:link>,
<ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Чатбот IntraService: пайплайн, AI-KB и настройки" /></ac:link>,
<ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Чатбот IntraService: самообучение AI-KB (Corrective RAG)" /></ac:link>.</p>
</ac:rich-text-body></ac:structured-macro>
"""


def _parent_id() -> str:
    if PROJECT_META.is_file():
        try:
            pid = json.loads(PROJECT_META.read_text(encoding="utf-8")).get("page_id")
            if pid:
                return str(pid)
        except json.JSONDecodeError:
            pass
    return "124640056"


def _md_to_body(md: str) -> str:
    parts: list[str] = [BANNER.strip()]
    chunks = re.split(r"(```[\s\S]*?```)", md)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("```"):
            lang = "text"
            m = re.match(r"^```(\w+)?", chunk)
            if m and m.group(1):
                lang = m.group(1)
            inner = re.sub(r"^```\w*\s*", "", chunk)
            inner = re.sub(r"\s*```$", "", inner).strip()
            parts.append(
                '<ac:structured-macro ac:name="code" ac:schema-version="1">'
                f'<ac:parameter ac:name="language">{lang}</ac:parameter>'
                f"<ac:plain-text-body><![CDATA[{inner}]]></ac:plain-text-body>"
                "</ac:structured-macro>"
            )
        else:
            parts.append(cf.markdown_to_storage(chunk))
    return "\n".join(parts)


def main() -> int:
    load_package_env()
    if not SOURCE_MD.is_file():
        raise SystemExit(f"Нет {SOURCE_MD}")
    md = SOURCE_MD.read_text(encoding="utf-8")
    body = _md_to_body(md)
    parent_id = _parent_id()

    s = cf.session()
    existing = cf.find_page_by_title(s, space=SPACE, title=TITLE, parent_id=parent_id)
    if existing:
        page_id = str(existing["id"])
        result = cf.update_page(
            s,
            page_id,
            title=TITLE,
            storage=body,
            message="Sync настройки_дополнительных_возможностей.md",
        )
    else:
        result = cf.create_page(
            s,
            space=SPACE,
            title=TITLE,
            parent_id=parent_id,
            storage=body,
        )
        page_id = str(result.get("id") or "")

    link = cf.view_url(s, page_id)
    OUT_META.parent.mkdir(parents=True, exist_ok=True)
    OUT_META.write_text(
        json.dumps(
            {
                "page_id": page_id,
                "title": TITLE,
                "parent_id": parent_id,
                "space": SPACE,
                "url": link,
                "source": "docs/настройки_дополнительных_возможностей.md",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(json.dumps({"page_id": page_id, "url": link}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
