# -*- coding: utf-8 -*-
"""Публикация обзора проекта chatbot_intraservice в Confluence (WEBKB).

  python scripts/publish_project_overview_confluence.py

Требует CONFLUENCE_BASE_URL + CONFLUENCE_PAT в .env.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
import urllib3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SPACE = "WEBKB"
PARENT_ID = "124630073"  # "Чатбот ИИЭК: схема 1 линии и заявка в HelpDesk"
TITLE = "Обзор проекта chatbot_intraservice"
META = ROOT / "docs" / "confluence" / "project_overview_page_id.json"

BODY = r"""
<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:rich-text-body>
<p><strong>Документ:</strong> Обзор проекта «IEK: Помощник сотрудника» — архитектура, текущий статус, ключевые команды и планы развития.</p>
<p><strong>Обновлено:</strong> 2026-09-08</p>
<p><strong>GitHub:</strong> <code>Aendrous/iek-chatbot-intraservice</code></p>
</ac:rich-text-body></ac:structured-macro>

<h2>📊 Что это</h2>
<p>Чатбот IntraService для 1-й линии HelpDesk — <strong>ассистент исполнителя</strong>, который анализирует заявки и помогает решать их быстрее.</p>

<h3>Текущий этап (L1 HD)</h3>
<p><strong>✅ Работает сейчас:</strong></p>
<ul>
<li>Автоматическое отслеживание заявок (<code>watch_new</code>, <code>watch_overdue</code>, <code>watch_user_reply</code>)</li>
<li>Анализ заявок с извлечением текста из вложений (PDF, DOC, скрины, .msg)</li>
<li>Скрытые комментарии для исполнителей с фактами и ссылками на KB</li>
<li>Самообучение AI-KB из закрытых заявок</li>
<li>Streamlit UI для настроек и управления (порт 8502)</li>
<li>Windows Task Scheduler для автономной работы</li>
</ul>

<h3>Следующий этап (L0)</h3>
<p><strong>🚀 В разработке:</strong></p>
<ul>
<li>Встречающий чат для сотрудников: вопрос → ответ из KB <strong>или</strong> создание заявки</li>
<li>Спека: <code>docs/specs/L0_employee_chatbot.md</code></li>
<li>MVP уже есть: <code>l0_ask.py</code> + вкладка в Streamlit</li>
</ul>

<h2>🏗️ Архитектура</h2>

<h3>Технологический стек</h3>
<ul>
<li><strong>Python 3.x</strong> + Streamlit (UI)</li>
<li><strong>LLM:</strong> <code>llm.iek.local/v1</code> (<code>iek/gpt-oss-120b</code>, <code>confluence-agent</code>)</li>
<li><strong>IntraService API:</strong> <code>helpdesk.iek.local</code></li>
<li><strong>Confluence REST API:</strong> WEBKB, AI-KB</li>
<li><strong>Внешние системы:</strong> 1С API, BP API, CRM</li>
</ul>

<h3>Ключевые модули src/</h3>
<table class="wrapped"><tbody>
<tr><th>Модуль</th><th>Назначение</th></tr>
<tr><td><code>intraservice.py</code></td><td>API HelpDesk</td></tr>
<tr><td><code>assistants.py</code></td><td>Роутинг профилей (ЛК/БП/1С/CRM)</td></tr>
<tr><td><code>attachments.py</code></td><td>Извлечение текста из файлов</td></tr>
<tr><td><code>kb_learning.py</code></td><td>Самообучение AI-KB</td></tr>
<tr><td><code>pipeline.py</code></td><td>Артефакты прогонов</td></tr>
<tr><td><code>llm_client.py</code></td><td>Работа с LLM</td></tr>
<tr><td><code>confluence_*</code></td><td>REST API Confluence</td></tr>
<tr><td><code>service_routing.py</code></td><td>Определение контура/сервиса</td></tr>
</tbody></table>

<h3>Контуры</h3>
<ul>
<li><strong>ЛК</strong> (личный кабинет) — <code>knowledge/lk/</code></li>
<li><strong>БП</strong> (бизнес-партнеры) — <code>knowledge/bp/</code></li>
<li><strong>1С</strong> (Солярис, заказы, ТН) — <code>knowledge/1c/</code></li>
<li><strong>CRM</strong> — <code>knowledge/crm/</code></li>
</ul>

<h2>⚙️ Основные команды</h2>

<h3>UI оператора</h3>
<ac:structured-macro ac:name="code" ac:schema-version="1">
<ac:parameter ac:name="language">powershell</ac:parameter>
<ac:plain-text-body><![CDATA[streamlit run app.py --server.port 8502]]></ac:plain-text-body>
</ac:structured-macro>

<h3>Разбор заявки</h3>
<ac:structured-macro ac:name="code" ac:schema-version="1">
<ac:parameter ac:name="language">powershell</ac:parameter>
<ac:plain-text-body><![CDATA[python scripts/analyze_and_comment.py 696955 --post]]></ac:plain-text-body>
</ac:structured-macro>

<h3>Watch (автозапуск)</h3>
<ac:structured-macro ac:name="code" ac:schema-version="1">
<ac:parameter ac:name="language">powershell</ac:parameter>
<ac:plain-text-body><![CDATA[python scripts/watch_new.py
python scripts/watch_overdue.py
python scripts/watch_user_reply.py
python scripts/pipeline_watch.py]]></ac:plain-text-body>
</ac:structured-macro>

<h3>L0 чат</h3>
<ac:structured-macro ac:name="code" ac:schema-version="1">
<ac:parameter ac:name="language">powershell</ac:parameter>
<ac:plain-text-body><![CDATA[python scripts/l0_ask.py "как проверить резерв в пути?"]]></ac:plain-text-body>
</ac:structured-macro>

<h2>📋 Текущее состояние</h2>

<h3>✅ Работает</h3>
<ul>
<li>Windows Scheduler — 4 задачи watch + UI</li>
<li>Разбор заявок с преданализом (тип/сервис/важность)</li>
<li>Компактный формат скрытых комментариев + short URL</li>
<li>AI-KB: черновики → ревью в Streamlit → Promote в Confluence</li>
<li>Контуры ЛК/БП/1С/EDI/Mail включены; CRM выключен</li>
</ul>

<h3>⚠️ Known Issues</h3>
<ul>
<li>n8n опционален (ECONNREFUSED :8765 если не запущен)</li>
<li><code>confluence-agent</code> снят с прокси → fallback на <code>gpt-oss-120b</code></li>
<li>Длинные промпты → fallback</li>
<li><code>_analysis_*.json</code> в корне — отладочные, не коммитить</li>
</ul>

<h3>Следующие шаги</h3>
<ol>
<li>Открыть <code>http://localhost:8502</code> для проверки UI</li>
<li>Не тащить probe-скрипты <code>_*.py</code> в коммиты</li>
<li>Решить: синхронизировать ROADMAP на Confluence?</li>
</ol>

<h2>📚 Документация</h2>

<table class="wrapped"><tbody>
<tr><th>Файл</th><th>Назначение</th></tr>
<tr><td><code>AGENTS.md</code></td><td>Памятка для агента (правила, команды, pitfalls)</td></tr>
<tr><td><code>README.md</code></td><td>Старт для человека</td></tr>
<tr><td><code>docs/ARCHITECTURE.md</code></td><td>Карта модулей и границ</td></tr>
<tr><td><code>docs/ROADMAP.md</code></td><td>Итерации L1 → L0</td></tr>
<tr><td><code>docs/handoff.md</code></td><td>Статус последней сессии</td></tr>
<tr><td><code>docs/scripts_map.md</code></td><td>Карта всех 37 скриптов</td></tr>
<tr><td><code>docs/specs/L0_employee_chatbot.md</code></td><td>Спека встречающего чата</td></tr>
</tbody></table>

<h2>🔗 Связанные страницы</h2>
<ul>
<li><ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Чатбот ИИЭК: схема 1 линии и заявка в HelpDesk" /></ac:link> — схема работы</li>
<li><ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Чатбот IntraService: пайплайн, AI-KB и настройки" /></ac:link> — детальная настройка</li>
<li><ac:link><ri:page ri:space-key="WEBKB" ri:content-title="Чатбот IntraService: VLAN / VM + L0 (сеть и доступы)" /></ac:link> — инфраструктура</li>
</ul>

<h2>💡 Итоги</h2>
<p><strong>Проект хорошо структурирован</strong> — есть чёткие правила кодирования, разделение на контуры, документация по архитектуре и итерациям.</p>
<p><strong>Текущий фокус:</strong> стабильность L1 HD + подготовка к L0 MVP встречающего чата для сотрудников.</p>

<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:rich-text-body>
<p><strong>Обновление этой страницы:</strong> <code>python scripts/publish_project_overview_confluence.py</code></p>
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


def _session() -> requests.Session:
    _load_env()
    base = (os.environ.get("CONFLUENCE_BASE_URL") or "").rstrip("/")
    pat = (os.environ.get("CONFLUENCE_PAT") or "").strip()
    if not base or not pat:
        raise SystemExit("Задайте CONFLUENCE_BASE_URL и CONFLUENCE_PAT в .env")
    session = requests.Session()
    session.verify = False
    session.headers.update(
        {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )
    session.base = base  # type: ignore[attr-defined]
    return session


def find_page(session: requests.Session) -> dict | None:
    """Поиск существующей страницы по названию."""
    cql = f'space = {SPACE} AND type = page AND title = "{TITLE}"'
    resp = session.get(
        f"{session.base}/rest/api/content/search",  # type: ignore[attr-defined]
        params={"cql": cql, "limit": 5},
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    return results[0] if results else None


def create_or_update(session: requests.Session) -> dict:
    """Создание или обновление страницы в Confluence."""
    existing = find_page(session)
    payload = {
        "type": "page",
        "title": TITLE,
        "space": {"key": SPACE},
        "ancestors": [{"id": PARENT_ID}],
        "body": {"storage": {"value": BODY.strip(), "representation": "storage"}},
    }
    if existing:
        page_id = existing["id"]
        meta = session.get(
            f"{session.base}/rest/api/content/{page_id}",  # type: ignore[attr-defined]
            params={"expand": "version"},
            timeout=30,
        )
        meta.raise_for_status()
        version = int((meta.json().get("version") or {}).get("number") or 1)
        payload["version"] = {
            "number": version + 1,
            "message": "Обновление обзора проекта: архитектура, статус, команды",
        }
        resp = session.put(
            f"{session.base}/rest/api/content/{page_id}",  # type: ignore[attr-defined]
            json=payload,
            timeout=90,
        )
        print(f"Обновление существующей страницы {page_id}...")
    else:
        resp = session.post(
            f"{session.base}/rest/api/content",  # type: ignore[attr-defined]
            json=payload,
            timeout=90,
        )
        print("Создание новой страницы...")
    
    if resp.status_code >= 400:
        raise SystemExit(f"Confluence HTTP {resp.status_code}: {resp.text[:1200]}")
    return resp.json()


def main() -> int:
    """Основная функция."""
    session = _session()
    data = create_or_update(session)
    page_id = data.get("id")
    link = f"{session.base}/pages/viewpage.action?pageId={page_id}"  # type: ignore[attr-defined]
    
    # Сохранение метаданных
    META.parent.mkdir(parents=True, exist_ok=True)
    META.write_text(
        json.dumps(
            {
                "page_id": str(page_id),
                "title": TITLE,
                "parent_id": PARENT_ID,
                "parent_title": "Чатбот ИИЭК: схема 1 линии и заявка в HelpDesk",
                "space": SPACE,
                "url": link,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    
    print(f"\n✅ Страница успешно опубликована!")
    print(f"📄 Название: {TITLE}")
    print(f"🔗 URL: {link}")
    print(f"📋 Page ID: {page_id}")
    print(f"💾 Метаданные сохранены: {META}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
