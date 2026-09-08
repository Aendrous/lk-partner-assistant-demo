# -*- coding: utf-8 -*-
"""Публикация глоссария AI-KB в WEBKB.

  python scripts/publish_ai_kb_glossary_confluence.py

Родитель: страница проекта (124640056).
Источник: docs/pipeline/глоссарий_ai_kb.md
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import urllib3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import confluence_client as cf  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SPACE = "WEBKB"
TITLE = "Справочник терминов: AI-KB, Promote, PII"
SOURCE_MD = ROOT / "docs" / "pipeline" / "глоссарий_ai_kb.md"
PROJECT_META = ROOT / "docs" / "confluence" / "intraservice_project_page_id.json"
OUT_META = ROOT / "docs" / "confluence" / "ai_kb_glossary_page_id.json"

BANNER = """
<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:rich-text-body>
<p>Глоссарий для ревью черновиков самообучения: <strong>Promote</strong>, <strong>KB_INSERT</strong>,
<strong>PII / без PII email</strong>, supplement, корпус.</p>
<p>Исходник: <code>chatbot_intraservice/docs/pipeline/глоссарий_ai_kb.md</code> ·
<code>python scripts/publish_ai_kb_glossary_confluence.py</code>.</p>
<p>Свод:
<ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Чатбот IntraService: пайплайн, AI-KB и настройки" /></ac:link>
· <ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Самообучение AI-KB (Corrective RAG)" /></ac:link></p>
</ac:rich-text-body></ac:structured-macro>
"""


def _load_env() -> None:
    for p in (ROOT / ".env", REPO / ".env"):
        if not p.is_file():
            continue
        try:
            from dotenv import load_dotenv

            load_dotenv(p, override=False)
        except ImportError:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))


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
    _load_env()
    if not SOURCE_MD.is_file():
        raise SystemExit(f"Нет {SOURCE_MD}")
    body = _md_to_body(SOURCE_MD.read_text(encoding="utf-8"))
    parent_id = _parent_id()
    s = cf.session()
    existing = cf.find_page_by_title(s, space=SPACE, title=TITLE, parent_id=parent_id)
    if existing:
        page_id = str(existing["id"])
        cf.update_page(
            s,
            page_id,
            title=TITLE,
            storage=body,
            message="Sync глоссарий_ai_kb.md",
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
    OUT_META.write_text(
        json.dumps(
            {
                "page_id": page_id,
                "title": TITLE,
                "parent_id": parent_id,
                "space": SPACE,
                "url": link,
                "source": "docs/pipeline/глоссарий_ai_kb.md",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"page_id": page_id, "url": link}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
