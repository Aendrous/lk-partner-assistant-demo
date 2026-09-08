# -*- coding: utf-8 -*-
"""Публикация страницы «Самообучение AI-KB (Corrective RAG)» в WEBKB.

  python scripts/publish_learning_confluence.py

Родитель: страница проекта (124640056 / ONttBw). Источник: pipeline/IDEA_RAG_LEARNING.md
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests
import urllib3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import confluence_client as cf  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SPACE = "WEBKB"
TITLE = "Самообучение AI-KB (Corrective RAG)"
IDEA_MD = ROOT / "pipeline" / "IDEA_RAG_LEARNING.md"
PROJECT_META = ROOT / "docs" / "confluence" / "intraservice_project_page_id.json"
OUT_META = ROOT / "docs" / "confluence" / "learning_rag_page_id.json"

BANNER = """
<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:rich-text-body>
<p>Схема <strong>Corrective RAG</strong> для чатбота IntraService: обучение из закрытых заявок HelpDesk.
Исходник в git: <code>chatbot_intraservice/pipeline/IDEA_RAG_LEARNING.md</code>.
Обновление: <code>python scripts/publish_learning_confluence.py</code>.</p>
<p>Кратко для операторов: <code>docs/pipeline/самообучение.md</code> · свод проекта:
<ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Чатбот IntraService: пайплайн, AI-KB и настройки" /></ac:link>.</p>
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
    """Markdown → storage; mermaid-блоки оставляем как code."""
    parts: list[str] = [BANNER.strip()]
    chunks = re.split(r"(```mermaid[\s\S]*?```)", md)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("```mermaid"):
            inner = re.sub(r"^```mermaid\s*", "", chunk)
            inner = re.sub(r"\s*```$", "", inner).strip()
            parts.append(
                '<ac:structured-macro ac:name="code" ac:schema-version="1">'
                '<ac:parameter ac:name="language">text</ac:parameter>'
                f"<ac:plain-text-body><![CDATA[{inner}]]></ac:plain-text-body>"
                "</ac:structured-macro>"
            )
        else:
            parts.append(cf.markdown_to_storage(chunk))
    return "\n".join(parts)


def main() -> int:
    _load_env()
    if not IDEA_MD.is_file():
        raise SystemExit(f"Нет файла {IDEA_MD}")
    md = IDEA_MD.read_text(encoding="utf-8")
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
            message="Sync IDEA_RAG_LEARNING.md",
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
                "source": "pipeline/IDEA_RAG_LEARNING.md",
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
