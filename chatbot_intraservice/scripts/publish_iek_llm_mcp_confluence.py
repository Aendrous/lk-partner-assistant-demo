# -*- coding: utf-8 -*-
"""Публикация «IEK LLM и Confluence (MCP vs бот)» в WEBKB.

  python scripts/publish_iek_llm_mcp_confluence.py

Родитель: страница проекта (124640056 / ONttBw), раздел 4 API.
Источник: docs/интеграции/iek_llm_owui_mcp.md
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
TITLE = "IEK LLM и Confluence: как бот ищет в KB (MCP vs REST)"
SOURCE_MD = ROOT / "docs" / "интеграции" / "iek_llm_owui_mcp.md"
PROJECT_META = ROOT / "docs" / "confluence" / "intraservice_project_page_id.json"
PROBE_JSON = ROOT / "_probe_llm_tools.json"
OUT_META = ROOT / "docs" / "confluence" / "iek_llm_mcp_page_id.json"

BANNER = """
<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:rich-text-body>
<p>Как чатбот IntraService использует <strong>IEK LLM</strong> и <strong>Confluence</strong>:
LiteLLM API, REST prefetch (аналог MCP), Open WebUI для ручной проверки.</p>
<p>Исходник: <code>chatbot_intraservice/docs/интеграции/iek_llm_owui_mcp.md</code> ·
обновление: <code>python scripts/publish_iek_llm_mcp_confluence.py</code>.</p>
<p>Свод проекта:
<ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Чатбот IntraService: пайплайн, AI-KB и настройки" /></ac:link>
· §4.1 IEK LLM.</p>
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


def _probe_appendix() -> str:
    if not PROBE_JSON.is_file():
        return (
            "<ac:structured-macro ac:name=\"note\"><ac:rich-text-body>"
            "<p>Зонд tools не запускался. Выполните: "
            "<code>python scripts/probe_iek_llm_tools.py</code></p>"
            "</ac:rich-text-body></ac:structured-macro>"
        )
    try:
        data = json.loads(PROBE_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    probes = data.get("probes") or {}
    lt = probes.get("litellm_tools") or {}
    lt_oss = probes.get("litellm_tools_gpt_oss") or {}
    rest = probes.get("rest_confluence_search") or {}
    owui = probes.get("owui_model_support-dep-lk-web-helper") or {}
    mcp_tools = owui.get("meta_tools") or []
    lines = [
        "<h3>Результат зонда (probe_iek_llm_tools)</h3>",
        "<table class=\"wrapped\"><tbody>",
        "<tr><th>Проверка</th><th>Результат</th></tr>",
        f"<tr><td>LiteLLM support model + tools</td>"
        f"<td>tool_calls: <strong>{'да' if lt.get('has_tool_calls') else 'нет'}</strong> "
        f"(см. probe; confluence-agent снят)</td></tr>",
        f"<tr><td>LiteLLM <code>gpt-oss-120b</code> + tools</td>"
        f"<td>tool_calls: <strong>{'да' if lt_oss.get('has_tool_calls') else 'нет'}</strong> "
        f"(прокси не исполняет — нужен agent loop)</td></tr>",
        f"<tr><td>OWUI LK helper MCP</td>"
        f"<td>{', '.join(mcp_tools) if mcp_tools else '—'}</td></tr>",
        f"<tr><td>REST prefetch бота</td>"
        f"<td>hits: {rest.get('hits', '—')}; ok: {rest.get('ok')}</td></tr>",
        "</tbody></table>",
        "<p>Полный JSON: <code>_probe_llm_tools.json</code>. Запуск: "
        "<code>python scripts/probe_iek_llm_tools.py</code></p>",
    ]
    return "\n".join(lines)


def _md_to_body(md: str) -> str:
    parts: list[str] = [BANNER.strip(), _probe_appendix()]
    # mermaid / code fences целиком — иначе markdown_to_storage ломает диаграммы
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
            if lang == "mermaid":
                lang = "text"
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
            message="Sync iek_llm_owui_mcp.md",
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
                "source": "docs/интеграции/iek_llm_owui_mcp.md",
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
