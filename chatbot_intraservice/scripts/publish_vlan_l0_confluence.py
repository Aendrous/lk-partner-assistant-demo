# -*- coding: utf-8 -*-
"""Публикация «VLAN / VM + L0: сеть и доступы» в WEBKB.

Свёрнутые блоки: чеклист VLAN/VM, спека L0, черновик сети (заявка ДИТ).

  python scripts/publish_vlan_l0_confluence.py
  python scripts/publish_vlan_l0_confluence.py --dry-run

Родитель: страница проекта (124640056).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import confluence_client as cf  # noqa: E402
from env_bootstrap import load_package_env  # noqa: E402

SPACE = "WEBKB"
TITLE = "Чатбот IntraService: VLAN / VM + L0 (сеть и доступы)"
PROJECT_META = ROOT / "docs" / "confluence" / "intraservice_project_page_id.json"
OUT_META = ROOT / "docs" / "confluence" / "vlan_l0_page_id.json"

CHECKLIST_MD = ROOT / "docs" / "заявки" / "vlan_vm_l0_checklist.md"
L0_SPEC_MD = ROOT / "docs" / "specs" / "L0_employee_chatbot.md"
DIT_NET_MD = ROOT / "docs" / "заявки" / "дит_деплой_чатбота_n8n.md"


def _parent_id() -> str:
    if PROJECT_META.is_file():
        try:
            pid = json.loads(PROJECT_META.read_text(encoding="utf-8")).get("page_id")
            if pid:
                return str(pid)
        except json.JSONDecodeError:
            pass
    return "124640056"


def _expand(title: str, inner_html: str) -> str:
    safe = (
        title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return (
        '<ac:structured-macro ac:name="expand" ac:schema-version="1">'
        f'<ac:parameter ac:name="title">{safe}</ac:parameter>'
        f"<ac:rich-text-body>\n{inner_html}\n</ac:rich-text-body>"
        "</ac:structured-macro>"
    )


def _md_chunk_to_storage(md: str) -> str:
    """Markdown → storage; fenced code → Confluence code macro."""
    import re

    parts: list[str] = []
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


def build_body() -> str:
    checklist = CHECKLIST_MD.read_text(encoding="utf-8")
    l0 = L0_SPEC_MD.read_text(encoding="utf-8")
    dit = DIT_NET_MD.read_text(encoding="utf-8")

    banner = """
<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:rich-text-body>
<p><strong>VLAN / VM + L0.</strong> Чеклист для ДИТ при выдаче виртуалки в отдельном VLAN:
на машине — фоновый бот HelpDesk (L1) <em>и</em> чат для диалога с сотрудниками (L0).</p>
<p>Родитель:
<ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Чатбот IntraService: пайплайн, AI-KB и настройки" /></ac:link>.
Обновление: <code>python scripts/publish_vlan_l0_confluence.py</code>.</p>
</ac:rich-text-body></ac:structured-macro>
"""

    dit_reply = """
<h2>Коротко для ДИТ</h2>
<blockquote>
<p>Отдельный VLAN для ботов — ок. На машине будет и фоновый разбор заявок HelpDesk, и чат для сотрудников.
Нужно: исходящий 443 на <code>helpdesk.iek.local</code>, <code>llm.iek.local</code>, <code>confluence.dev.iek.ru</code>;
входящий 443 (HTTPS + DNS) с офиса/VPN на UI чата; порт операторской панели — только операторам;
8765 (если n8n) — только с хоста n8n. Интернет с VLAN не обязателен.</p>
</blockquote>
<table class="wrapped"><tbody>
<tr><th>Направление</th><th>Что</th></tr>
<tr><td>Egress</td><td>443 → helpdesk / llm / confluence (+ DNS/NTP)</td></tr>
<tr><td>Ingress L0</td><td>443 HTTPS с офиса+VPN → чат сотрудников</td></tr>
<tr><td>Ingress ops</td><td>8502 или path на 443 — узкий круг</td></tr>
<tr><td>Ingress n8n</td><td>8765 только с IP n8n (опционально)</td></tr>
</tbody></table>
"""

    expands = [
        _expand("Чеклист VLAN / VM (полный)", _md_chunk_to_storage(checklist)),
        _expand(
            "Спека L0 — встречающий чат (docs/specs/L0_employee_chatbot.md)",
            _md_chunk_to_storage(l0),
        ),
        _expand(
            "Черновик сети / деплой ДИТ (docs/заявки/дит_деплой_чатбота_n8n.md)",
            _md_chunk_to_storage(dit),
        ),
    ]

    note = """
<ac:structured-macro ac:name="note" ac:schema-version="1"><ac:rich-text-body>
<p>Источники в git: <code>docs/заявки/vlan_vm_l0_checklist.md</code>,
<code>docs/specs/L0_employee_chatbot.md</code>,
<code>docs/заявки/дит_деплой_чатбота_n8n.md</code>.</p>
<p>Планировщик Windows на ноутбуке — пилот; прод — VM + (Scheduler или n8n → :8765).</p>
</ac:rich-text-body></ac:structured-macro>
"""

    return "\n".join([banner.strip(), dit_reply.strip(), *expands, note.strip()])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_package_env()
    for p in (CHECKLIST_MD, L0_SPEC_MD, DIT_NET_MD):
        if not p.is_file():
            raise SystemExit(f"Нет {p}")

    body = build_body()
    parent_id = _parent_id()

    if args.dry_run:
        out = ROOT / "_vlan_l0_preview.html"
        out.write_text(body, encoding="utf-8")
        print(json.dumps({"dry_run": True, "chars": len(body), "preview": str(out)}, ensure_ascii=False))
        return 0

    s = cf.session()
    existing = cf.find_page_by_title(s, space=SPACE, title=TITLE, parent_id=parent_id)
    if existing:
        page_id = str(existing["id"])
        result = cf.update_page(
            s,
            page_id,
            title=TITLE,
            storage=body,
            message="Sync VLAN/VM L0 checklist + L0 spec + DIT network draft (expand)",
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
                "sources": [
                    "docs/заявки/vlan_vm_l0_checklist.md",
                    "docs/specs/L0_employee_chatbot.md",
                    "docs/заявки/дит_деплой_чатбота_n8n.md",
                ],
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
