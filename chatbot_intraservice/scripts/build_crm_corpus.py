# -*- coding: utf-8 -*-
"""Сбор Q&A корпуса CRM из Confluence (CRM / CRMRF) для чатбота IntraService.

  python scripts/build_crm_corpus.py
  python scripts/build_crm_corpus.py --publish   # дочерняя страница WEBKB

Источники:
  - CRMRF «База знаний CRM РФ» (https://confluence.dev.iek.ru/x/hQAM)
  - CRM «Поддержка» — проблемы/решения (https://confluence.dev.iek.ru/x/iAFd)
  - CRM «Темы обращений пользователей» (https://confluence.dev.iek.ru/x/-QntAQ)
  - CRM «Разработка» — интеграции и глоссарий (не сущности [account])
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

import confluence_client as cf  # noqa: E402
from env_bootstrap import load_package_env  # noqa: E402

CRMRF_KB_ROOT = "786565"
CRM_DEV_ROOT = "786562"
# CRM «Разработка» → Поддержка (проблемы/решения для 1 линии)
CRM_SUPPORT_PARENT_ID = "6095240"
CRM_SUPPORT_URL = "https://confluence.dev.iek.ru/x/iAFd"
CRM_PROBLEMS_PAGE_ID = "13599811"
# CRM «Разработка» → Темы обращений пользователей
CRM_USER_REQUESTS_PARENT_ID = "32311805"
CRM_USER_REQUESTS_URL = "https://confluence.dev.iek.ru/x/-QntAQ"

# Инструкции и процессы CRM РФ (без dev-сущностей)
CRMRF_PAGE_IDS = (
    "13600012",  # Интеграция в CRM - что это значит?
    "102622433",  # Справочник пользователя "Заявки на спеццену"
    "124620966",  # Справочник пользователя "Специальные условия"
    "39887235",  # Заявки на спеццену
    "114112931",  # Передача цен номенклатуры спеццен после согласования в 1С
    "50015074",  # Передача данных из CRM в IEK+
    "114110433",  # Заявки на согласование/отказ
    "76035275",  # Регистрация в системе
    "788223",  # Глоссарий для CRM (CRM dev space)
    "102619718",  # Интеграционный контур CRM<->IEK+
    "76040712",  # Передача из CRM в дочернюю CRM
)

WEBKB_PARENT = "124630073"
WEBKB_PAGE_TITLE = "Чатбот IntraService: база Q&A CRM (самообучение)"

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
SKIP_TITLE_RE = re.compile(
    r"команда|ответствен|\[[a-z_]+\]|архив|релиз\s*20\d{2}|changelog|маршрут\s+согласован",
    re.I,
)
NOISY_TEXT_RE = re.compile(
    r"Сценарий\s+Условие\s+Формирование\s+шагов|Шаг\s+1\s+Шаг\s+2\s+Шаг\s+3",
    re.I,
)
_TABLE_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.I | re.S)
_TABLE_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)
_STACK_TRACE_RE = re.compile(
    r"(Unhandled Exception|Inner Exception|Microsoft\.Crm\.|System\.Data\.SqlClient).{200,}",
    re.I | re.S,
)


def sanitize(text: str) -> str:
    t = EMAIL_RE.sub("[email]", text or "")
    t = re.sub(r"\b\d{10}(?:\d{2})?\b", "[inn]", t)
    return t.strip()


def html_to_text(html: str, *, max_len: int = 6000) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.I | re.S)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</p>", "\n", t, flags=re.I)
    t = re.sub(r"<li[^>]*>", "\n- ", t, flags=re.I)
    t = re.sub(r"<h[1-6][^>]*>", "\n## ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html_lib.unescape(t)
    t = re.sub(r"\bINLINE\s*", "", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return sanitize(t.strip()[:max_len])


def fetch_page(s: Any, page_id: str) -> dict[str, Any]:
    data = cf.get_page(s, page_id, expand="body.storage,space,version")
    body = ((data.get("body") or {}).get("storage") or {}).get("value") or ""
    return {
        "id": str(data.get("id") or page_id),
        "title": str(data.get("title") or "").strip(),
        "space": str(((data.get("space") or {}).get("key")) or ""),
        "url": cf.view_url(s, page_id),
        "text": html_to_text(body),
        "storage_html": body,
    }


def list_child_page_ids(s: Any, parent_id: str, *, limit: int = 50) -> list[str]:
    resp = s.get(
        f"{s.base}/rest/api/content/{parent_id}/child/page",  # type: ignore[attr-defined]
        params={"limit": limit},
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Confluence children HTTP {resp.status_code}: {resp.text[:400]}")
    return [str(x.get("id") or "") for x in resp.json().get("results") or [] if x.get("id")]


def _cell_text(html_fragment: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html_fragment or "")
    t = html_lib.unescape(re.sub(r"\s+", " ", t)).strip()
    return sanitize(t)


def _trim_answer(text: str, *, max_len: int = 2200) -> str:
    t = _STACK_TRACE_RE.sub("[stack trace обрезан]", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t


def extract_problems_table_qa(
    page: dict[str, Any],
    *,
    seq: list[int],
    prefix: str = "CRM-P",
) -> list[dict[str, str]]:
    """Таблица «Описание | Проблема | Решение» на странице Поддержка."""
    html = page.get("storage_html") or ""
    rows = _TABLE_ROW_RE.findall(html)
    out: list[dict[str, str]] = []
    for tr in rows[1:]:
        cells = [_cell_text(c) for c in _TABLE_CELL_RE.findall(tr)]
        if len(cells) < 2:
            continue
        if len(cells) >= 3:
            desc, problem, solution = cells[0], cells[1], cells[2]
        else:
            desc, problem, solution = "", cells[0], cells[1]
        problem = problem or desc
        solution = solution or problem
        if len(problem) < 25 or len(solution) < 15:
            continue
        if problem.lower() in {"проблема", "описание"} or solution.lower() in {"решение"}:
            continue
        seq[0] += 1
        q = (desc if desc and desc != problem else problem)[:200]
        answer = _trim_answer(
            f"Проблема: {problem}\n\nРешение: {solution}",
            max_len=2800,
        )
        kw = ", ".join(re.findall(r"[А-Яа-яA-Za-z0-9]{4,}", problem)[:8])
        out.append(
            {
                "id": f"{prefix}{seq[0]:03d}",
                "question": q,
                "keywords": kw[:120] or "CRM, поддержка",
                "not_confused_with": "ЛК, БП, 1С (отдельные контуры)",
                "answer": answer,
                "source_url": page.get("url", ""),
                "source_title": page.get("title") or "Проблемы и решения",
            }
        )
    return out


def fetch_section_pages(s: Any, parent_id: str) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for pid in list_child_page_ids(s, parent_id):
        try:
            pages.append(fetch_page(s, pid))
        except Exception as err:
            print(f"skip section child {parent_id}/{pid}: {err}", file=sys.stderr)
    return pages


def fetch_support_pages(s: Any) -> list[dict[str, Any]]:
    return fetch_section_pages(s, CRM_SUPPORT_PARENT_ID)


def fetch_user_request_pages(s: Any) -> list[dict[str, Any]]:
    return fetch_section_pages(s, CRM_USER_REQUESTS_PARENT_ID)


def support_pages_to_qa(
    support_pages: list[dict[str, Any]],
    *,
    seq_start: int = 1,
) -> list[dict[str, str]]:
    """Q&A из раздела CRM «Поддержка» (/x/iAFd)."""
    out: list[dict[str, str]] = []
    seq_h = seq_start
    p_seq = [0]
    seen: set[str] = set()

    for page in support_pages:
        pid = str(page.get("id") or "")
        title = (page.get("title") or "").strip()
        if pid == CRM_PROBLEMS_PAGE_ID or "проблем" in title.lower():
            for item in extract_problems_table_qa(page, seq=p_seq):
                key = (item.get("question") or "")[:120]
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)
            continue
        if pid == CRM_USER_REQUESTS_PARENT_ID:
            continue
        item = page_to_qa(page, seq_h, id_prefix="CRM-H")
        if not item:
            continue
        key = (item.get("question") or "")[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        seq_h += 1
    return out


def user_request_pages_to_qa(
    user_pages: list[dict[str, Any]],
    *,
    seq_start: int = 1,
) -> list[dict[str, str]]:
    """Q&A из «Темы обращений пользователей» (/x/-QntAQ)."""
    out: list[dict[str, str]] = []
    seq_u = seq_start
    p_seq = [0]
    seen: set[str] = set()

    for page in user_pages:
        title = (page.get("title") or "").strip()
        if "проблем" in title.lower():
            for item in extract_problems_table_qa(page, seq=p_seq, prefix="CRM-U"):
                key = (item.get("question") or "")[:120]
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)
            continue
        item = page_to_qa(page, seq_u, id_prefix="CRM-U", min_text=40)
        if not item:
            continue
        key = (item.get("question") or "")[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        seq_u += 1
    return out


def collect_crm_qa(
    s: Any,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """curated + CRMRF + Поддержка + обращения пользователей → единый список Q&A."""
    pages: list[dict[str, Any]] = []
    for pid in CRMRF_PAGE_IDS:
        try:
            p = fetch_page(s, pid)
            if not SKIP_TITLE_RE.search(p["title"]):
                pages.append(p)
        except Exception as err:
            print(f"skip {pid}: {err}", file=sys.stderr)

    support_pages = fetch_support_pages(s)
    user_request_pages = fetch_user_request_pages(s)

    qa_items = curated_qa()
    seq = 1
    for p in pages:
        item = page_to_qa(p, seq)
        if item:
            qa_items.append(item)
            seq += 1

    qa_items.extend(support_pages_to_qa(support_pages, seq_start=seq))
    qa_items.extend(user_request_pages_to_qa(user_request_pages))
    return qa_items, pages, support_pages, user_request_pages


def curated_qa() -> list[dict[str, str]]:
    """Ручная база для 1 линии (приоритет для LLM и исполнителя)."""
    return [
        {
            "id": "CRM-Q00",
            "question": "В чём отличие CRM РФ от CRM (корпоративной)?",
            "keywords": "CRM РФ, crmrf, CRM IEK, Dynamics, отличие, какая CRM",
            "not_confused_with": "ЛК (lk.iek.ru), БП (bp.iek.ru), API каталога",
            "answer": (
                "**CRM РФ** — `crmrf.iek.local`, Dynamics для продаж в РФ: сделки, партнёры, "
                "спеццены, МРК, карточки контрагентов. KB: https://confluence.dev.iek.ru/x/hQAM\n\n"
                "**CRM корпоративная / IEK+** — отдельный контур группы, интеграции с дочерними "
                "юрлицами; в Confluence — пространство CRM «Разработка» (техдок, интеграции).\n\n"
                "**Правило для 1 линии:** смотрите URL в заявке — `crmrf.iek.local` = CRM РФ; "
                "вопросы передачи в IEK+ / «дочернюю CRM» — интеграционный контур (статьи "
                "CRM↔IEK+). Не смешивать с ЛК, БП и 1С (отдельные системы; связь CRM–1С — "
                "спеццены, контрагенты)."
            ),
            "source_url": "https://confluence.dev.iek.ru/x/hQAM",
            "source_title": "База знаний CRM РФ",
        },
        {
            "id": "CRM-01",
            "question": "Спеццены в CRM изменили, в 1С остались старые значения — почему?",
            "keywords": "спеццена, 1С, синхронизация, дата окончания, не ушло в 1С",
            "not_confused_with": "цены в ЛК каталоге, прайс bp.iek.ru",
            "answer": (
                "**Типичная причина:** спеццена уже была передана в 1С; последующие правки "
                "даты/условий в CRM **не синхронизируются автоматически**.\n\n"
                "**Проверки исполнителя:**\n"
                "1. Когда создана и передана спеццена vs когда правили в CRM.\n"
                "2. Актуальные строки в 1С (контрагент, номенклатура).\n"
                "3. Нужна ли повторная передача / ручная корректировка по процессу CRM–1С.\n\n"
                "**Открытый ответ (шаблон):** Спеццены передаются в 1С при создании; изменение "
                "после передачи в 1С автоматически не уходит — сверим значения и при "
                "необходимости скорректируем по процессу интеграции."
            ),
            "source_title": "Заявки на спеццену / опыт HD",
        },
        {
            "id": "CRM-02",
            "question": "Нет доступа к сделке или карточке в CRM РФ",
            "keywords": "доступ, сделка, карточка, права, МРК, crmrf",
            "not_confused_with": "доступ в ЛК партнёра, IEK ID, adm.bp",
            "answer": (
                "**Проверки:**\n"
                "1. Роль пользователя в CRM РФ (не ЛК/БП).\n"
                "2. Территория / команда продаж, владелец записи.\n"
                "3. Открывается ли ссылка `https://crmrf.iek.local/CRM/...` у исполнителя.\n\n"
                "Если права — эскалация владельцу CRM / заявка на изменение AD (роль CRM)."
            ),
        },
        {
            "id": "CRM-03",
            "question": "Нужно ли запрашивать у партнёра финансовую отчётность (ссылка из CRM)?",
            "keywords": "фин отчётность, партнёр, карточка CRM, МРК",
            "answer": (
                "По процессу продаж/комплаенса МРК. В скрытом комментарии: URL карточки CRM, "
                "что спрашивает заявитель. Бот не подменяет решение — при сомнении эскалация "
                "владельцу процесса CRM."
            ),
        },
        {
            "id": "CRM-04",
            "question": "Расхождение данных CRM РФ и 1С (контрагент, заказ)",
            "keywords": "расхождение, CRM, 1С, контрагент, синхронизация",
            "answer": (
                "Определить «мастер» данных: воронка/сделка — CRM РФ; склад/финансы — часто 1С. "
                "Сверить ключевые поля (ИНН, контрагент, номер). При подтверждённом расхождении — "
                "контур интеграции CRM–1С."
            ),
        },
        {
            "id": "CRM-05",
            "question": "Что такое интеграция CRM с IEK+ / передача в дочернюю CRM?",
            "keywords": "IEK+, дочерняя CRM, интеграция, передача данных",
            "not_confused_with": "CRM РФ day-to-day у МРК",
            "answer": (
                "Отдельный **интеграционный контур** между CRM РФ и корпоративной CRM группы "
                "(IEK+). Не путать с ежедневной работой МРК в crmrf.iek.local. Детали — статьи "
                "«Интеграционный контур (CRM<->IEK+)» и «Передача данных из CRM в IEK+» в Confluence."
            ),
            "source_title": "Интеграции CRM",
        },
    ]


def page_to_qa(
    page: dict[str, Any],
    seq: int,
    *,
    id_prefix: str = "CRM-S",
    min_text: int = 120,
) -> dict[str, str] | None:
    title = page.get("title") or ""
    if SKIP_TITLE_RE.search(title):
        return None
    text = page.get("text") or ""
    if len(text) < min_text:
        return None
    # отсечь «таблицы ответственных» и SQL
    if text.count("[email]") > 3:
        return None
    if "[dbo]." in text or "SYCORAX" in text:
        return None
    if NOISY_TEXT_RE.search(text):
        return None
    # осмысленные абзацы (для инструкций — больше текста)
    paras = [p.strip() for p in re.split(r"\n+", text) if len(p.strip()) > (25 if min_text < 120 else 40)]
    if not paras:
        return None
    body = html_lib.unescape(_trim_answer("\n\n".join(paras[:8]), max_len=2800))
    q = title if "?" in title else f"{title} — кратко для исполнителя 1 линии"
    return {
        "id": f"{id_prefix}{seq:02d}",
        "question": q[:200],
        "keywords": ", ".join(re.findall(r"[А-Яа-яA-Za-z0-9]{4,}", title)[:6]),
        "answer": body,
        "source_url": page.get("url", ""),
        "source_title": title,
    }


def format_qa_block(item: dict[str, str]) -> str:
    lines = [
        f"### {item.get('id', 'CRM-Q')}. {item.get('question', '')}",
        "",
        f"**Ключевые слова:** {item.get('keywords', '')}",
    ]
    if item.get("not_confused_with"):
        lines.append(f"**Не путать с:** {item['not_confused_with']}")
    lines.extend(["", item.get("answer", "")])
    if item.get("source_url"):
        lines.append(
            f"\n**Источник:** [{item.get('source_title', 'Confluence')}]({item['source_url']})"
        )
    elif item.get("source_title"):
        lines.append(f"\n**Источник:** {item['source_title']}")
    return "\n".join(lines)


def build_qa_document(
    qa_items: list[dict[str, str]],
    pages: list[dict[str, Any]],
    *,
    support_count: int = 0,
    user_request_count: int = 0,
) -> str:
    parts = [
        "# CRM: база вопросов и ответов (чатбот IntraService)\n\n",
        "> **Контур:** CRM РФ (`crmrf.iek.local`). Быстрые ответы — пространство **CRMRF**.\n\n",
        "**Формат:** вопрос → ключевые слова → ответ для исполнителя 1 линии и IEK LLM.\n\n",
        f"Источники: [База знаний CRM РФ](https://confluence.dev.iek.ru/x/hQAM), "
        f"[CRM Поддержка]({CRM_SUPPORT_URL}) ({support_count} статей), "
        f"[Обращения пользователей]({CRM_USER_REQUESTS_URL}) ({user_request_count} тем), "
        f"[CRM Разработка](https://confluence.dev.iek.ru/pages/viewpage.action?pageId={CRM_DEV_ROOT}) "
        f"({len(pages)} страниц выборочно).\n\n---\n\n",
    ]
    for item in qa_items:
        parts.append(format_qa_block(item) + "\n\n---\n\n")
    return "".join(parts)


def build_corpus_md(
    qa_items: list[dict[str, str]],
    pages: list[dict[str, Any]],
    *,
    support_pages: list[dict[str, Any]] | None = None,
    user_request_pages: list[dict[str, Any]] | None = None,
) -> str:
    support_pages = support_pages or []
    user_request_pages = user_request_pages or []
    parts = [
        "# Корпус CRM для профиля l1_crm\n\n",
        "Не путать с ЛК (lk.iek.ru), БП (bp.iek.ru), API каталога.\n",
        "CRM IEK РФ: `crmrf.iek.local` (Dynamics).\n\n",
        build_qa_document(
            qa_items,
            pages,
            support_count=len(support_pages),
            user_request_count=len(user_request_pages),
        ),
        "\n\n---\n\n# Выдержки из Confluence (справочно)\n",
    ]
    for p in pages + support_pages + user_request_pages:
        if len(p.get("text") or "") < 80:
            continue
        parts.append(
            f"\n## {p['title']}\nURL: {p['url']}\n\n{(p.get('text') or '')[:2500]}\n"
        )
    return "".join(parts)


def build_intro_md(
    pages_count: int,
    *,
    support_count: int = 0,
    user_request_count: int = 0,
) -> str:
    return (
        "# CRM: база вопросов и ответов (чатбот IntraService)\n\n"
        "> **Контур:** CRM РФ (`crmrf.iek.local`). Promote AI-KB → пространство **CRMRF**.\n\n"
        "**Формат:** вопрос → ключевые слова → ответ в блоке «Ответ (копировать)».\n\n"
        f"Источники: [База знаний CRM РФ](https://confluence.dev.iek.ru/x/hQAM), "
        f"[CRM Поддержка]({CRM_SUPPORT_URL}) ({support_count} статей), "
        f"[Обращения пользователей]({CRM_USER_REQUESTS_URL}) ({user_request_count} тем), "
        f"[CRM Разработка](https://confluence.dev.iek.ru/pages/viewpage.action?pageId={CRM_DEV_ROOT}) "
        f"({pages_count} страниц выборочно).\n\n"
    )


def _xml_esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _answer_for_copy(answer: str) -> str:
    """Plain text для code macro (без markdown, удобно копировать)."""
    t = answer or ""
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    return t.replace("]]>", "]] >").strip()


def _qa_item_storage(item: dict[str, str]) -> str:
    qid = item.get("id", "CRM-Q")
    question = item.get("question", "")
    parts = [
        f"<h4>{_xml_esc(qid)}. {_xml_esc(question)}</h4>",
        f"<p><strong>Ключевые слова:</strong> {_xml_esc(item.get('keywords', ''))}</p>",
    ]
    if item.get("not_confused_with"):
        parts.append(
            f"<p><strong>Не путать с:</strong> {_xml_esc(item['not_confused_with'])}</p>"
        )
    answer_plain = _answer_for_copy(item.get("answer", ""))
    parts.append(
        '<ac:structured-macro ac:name="expand" ac:schema-version="1">'
        '<ac:parameter ac:name="title">Ответ (копировать)</ac:parameter>'
        "<ac:rich-text-body>"
        '<ac:structured-macro ac:name="code" ac:schema-version="1">'
        '<ac:parameter ac:name="language">text</ac:parameter>'
        f"<ac:plain-text-body><![CDATA[{answer_plain}]]></ac:plain-text-body>"
        "</ac:structured-macro>"
        "</ac:rich-text-body>"
        "</ac:structured-macro>"
    )
    if item.get("source_url"):
        url = _xml_esc(item["source_url"])
        title = _xml_esc(item.get("source_title", "Confluence"))
        parts.append(f'<p><strong>Источник:</strong> <a href="{url}">{title}</a></p>')
    elif item.get("source_title"):
        parts.append(f'<p><strong>Источник:</strong> {_xml_esc(item["source_title"])}</p>')
    parts.append("<hr />")
    return "\n".join(parts)


def qa_items_to_confluence_storage(qa_items: list[dict[str, str]], intro_md: str) -> str:
    parts = [cf.markdown_to_storage(intro_md)]
    for item in qa_items:
        parts.append(_qa_item_storage(item))
    return "\n".join(parts)


def publish_webkb(
    s: Any,
    qa_items: list[dict[str, str]],
    pages_count: int,
    *,
    support_count: int = 0,
    user_request_count: int = 0,
) -> dict[str, Any]:
    meta_path = ROOT / "docs" / "confluence" / "crm_qa_page_id.json"
    intro = build_intro_md(
        pages_count,
        support_count=support_count,
        user_request_count=user_request_count,
    )
    storage = qa_items_to_confluence_storage(qa_items, intro)
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        pid = str(meta.get("page_id") or "")
        if pid:
            cf.update_page(s, pid, title=WEBKB_PAGE_TITLE, storage=storage, message="build_crm_corpus")
            return {"action": "updated", "page_id": pid, "url": cf.view_url(s, pid)}
    result = cf.create_or_update_child(
        s,
        space="WEBKB",
        title=WEBKB_PAGE_TITLE,
        parent_id=WEBKB_PARENT,
        storage=storage,
        message="build_crm_corpus",
    )
    pid = str(result.get("id") or "")
    meta_path.write_text(
        json.dumps(
            {
                "page_id": pid,
                "title": WEBKB_PAGE_TITLE,
                "parent_page_id": WEBKB_PARENT,
                "url": cf.view_url(s, pid) if pid else "",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"action": "created", "page_id": pid, "url": cf.view_url(s, pid) if pid else ""}


def main() -> int:
    load_package_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    s = cf.session()
    qa_items, pages, support_pages, user_request_pages = collect_crm_qa(s)

    dest = ROOT / "knowledge" / "crm"
    dest.mkdir(parents=True, exist_ok=True)
    qa_md = build_qa_document(
        qa_items,
        pages,
        support_count=len(support_pages),
        user_request_count=len(user_request_pages),
    )
    (dest / "qa.md").write_text(qa_md, encoding="utf-8")
    (dest / "corpus.md").write_text(
        build_corpus_md(
            qa_items,
            pages,
            support_pages=support_pages,
            user_request_pages=user_request_pages,
        ),
        encoding="utf-8",
    )

    meta = {
        "qa_count": len(qa_items),
        "pages_fetched": len(pages),
        "support_pages_fetched": len(support_pages),
        "user_request_pages_fetched": len(user_request_pages),
        "support_parent_id": CRM_SUPPORT_PARENT_ID,
        "support_url": CRM_SUPPORT_URL,
        "user_requests_parent_id": CRM_USER_REQUESTS_PARENT_ID,
        "user_requests_url": CRM_USER_REQUESTS_URL,
        "corpus": "knowledge/crm/corpus.md",
        "qa": "knowledge/crm/qa.md",
        "crmrf_kb": "https://confluence.dev.iek.ru/x/hQAM",
        "crm_dev": f"https://confluence.dev.iek.ru/pages/viewpage.action?pageId={CRM_DEV_ROOT}",
    }
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))

    if args.publish:
        pub = publish_webkb(
            s,
            qa_items,
            len(pages),
            support_count=len(support_pages),
            user_request_count=len(user_request_pages),
        )
        print("publish", json.dumps(pub, ensure_ascii=False))
        meta["webkb"] = pub
        (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
