# -*- coding: utf-8 -*-
"""Сбор Q&A корпуса 1С Солярис для чатбота IntraService.

  python scripts/build_1c_corpus.py
  python scripts/build_1c_corpus.py --publish   # устар.: дубль в WEBKB; основная база — publish_1c_l1_confluence.py

Источники: Confluence (процессы Солярис, резерв в пути, заказы) + ручная база 1 линии.
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

# Статьи WEBKB / техдок по заказам и Солярис
ONEC_PAGE_IDS = (
    "102599443",  # Процесс обработки заказа в системе 1С Солярис
    "50007807",  # Резервирование в пути
    "72224867",  # Инструкция по ведению заказов клиентов
    "50006143",  # Описание механизма Заказ покупателя
    "76054339",  # Резерв в пути — заказная продукция в ЛК
    "124638779",  # 2026-08-18 1С очередь и всплеск заявок
    "72222277",  # Закрытие резервов в пути
)

WEBKB_PARENT = "124630073"
WEBKB_PAGE_TITLE = "Чатбот IntraService: база Q&A 1С Солярис"

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
SKIP_TITLE_RE = re.compile(r"архив|changelog|релиз\s*20\d{2}", re.I)


def sanitize(text: str) -> str:
    t = EMAIL_RE.sub("[email]", text or "")
    t = re.sub(r"\b\d{10}(?:\d{2})?\b", "[inn]", t)
    return t.strip()


def html_to_text(html: str, *, max_len: int = 5000) -> str:
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
    return sanitize(t.strip()[:max_len])


def fetch_page(s: Any, page_id: str) -> dict[str, Any]:
    data = cf.get_page(s, page_id, expand="body.storage,space,version")
    body = ((data.get("body") or {}).get("storage") or {}).get("value") or ""
    return {
        "id": str(data.get("id") or page_id),
        "title": str(data.get("title") or "").strip(),
        "url": cf.view_url(s, page_id),
        "text": html_to_text(body),
    }


def curated_qa() -> list[dict[str, str]]:
    return [
        {
            "id": "1C-Q00",
            "question": "Заявка в HelpDesk на сервисе «Солярис» — это про что?",
            "keywords": "Солярис, ServiceId 69, 1С Предприятие, HelpDesk",
            "not_confused_with": "ЛК (lk.iek.ru), БП (bp.iek.ru), CRM",
            "answer": (
                "**Солярис** — конфигурация **1С:Предприятие** (продажи, заказы покупателя, "
                "эл.заявки, резервы, счета, обмен с ЛК).\n\n"
                "**HelpDesk:** сервис **Солярис** (ServiceId **69**), родитель **1С Предприятие** (14).\n\n"
                "**Правило 1 линии:** заказы/счета/резерв в пути/выгрузка в 1С — контур **edi/1С**; "
                "интерфейс партнёра в ЛК — часто смежный кейс (сверка ЛК↔1С, не подмена системы)."
            ),
            "source_url": "https://helpdesk.iek.local/",
            "source_title": "IntraService ServiceId 69",
        },
        {
            "id": "1C-01",
            "question": "Галка «Резервировать товары в пути» — нужно ли подтверждать в ЛК?",
            "keywords": "резерв в пути, галка, заказ покупателя, ЛК",
            "answer": (
                "Если в **заказе покупателя** в 1С Солярис галка **«Резервировать товары в пути»** "
                "уже стоит — в ЛК **подтверждать резерв не требуется**.\n\n"
                "**Проверка:** заказ в 1С → галка; при необходимости связанная эл.заявка / GUID ЛК.\n"
                "См. также LK-06 в быстрых ответах ЛК (pageId 124630014)."
            ),
            "source_url": "https://confluence.dev.iek.ru/pages/viewpage.action?pageId=50007807",
            "source_title": "Резервирование в пути",
        },
        {
            "id": "1C-02",
            "question": "Остатки или количество в ЛК не совпадают с 1С Солярис",
            "keywords": "остатки, расхождение, ЛК, 1С, склад, заблокированный",
            "not_confused_with": "только «не видит склад» без артикула (LK-10)",
            "answer": (
                "**Проверки исполнителя:**\n"
                "1. Артикул и склад в 1С: свободный vs заблокированный остаток.\n"
                "2. Регистр «Склады контрагента» (видимость склада в каталоге ЛК).\n"
                "3. Кратность, мин. партия, заказная продукция.\n\n"
                "В комментарий — **вывод**, не сырой OCR кнопок 1С."
            ),
        },
        {
            "id": "1C-03",
            "question": "Заказ / счёт ХИ… или эл.заявка не находится в 1С",
            "keywords": "ХИ, эл.заявка, заказ покупателя, не найден, Солярис",
            "answer": (
                "**Проверки:** полный номер (`ХИ…`, `0000…`), база (Srvr/Ref), права доступа.\n"
                "Без номера заказа **не писать** в скрытый комментарий строку «1С: проверено».\n"
                "Если заявка с ЛК — сверить трекинг ЛК и документ в Солярис."
            ),
        },
        {
            "id": "1C-04",
            "question": "Электронный обмен / EDI / заказ поставщику — расхождение с Контур EDI",
            "keywords": "EDI, ADI, электронный обмен, заказ поставщику, Контур",
            "not_confused_with": "API каталога ЛК",
            "answer": (
                "Контур **EDI/ADI** — обмен данными в **1С**, не интерфейс ЛК.\n"
                "Сверить статус пакета в 1С и в Контур EDI; при расхождении — эскалация на контур 1С, "
                "не обещать срок без факта проверки.\n"
                "Если заявка на ветке ЛК (732), но тема EDI — указать mismatch в конце комментария."
            ),
        },
        {
            "id": "1C-05",
            "question": "Очередь обмена 1С / заявки «висят» после сбоя",
            "keywords": "очередь, обмен, зависло, не проводится, Солярис",
            "answer": (
                "Типично: отложенное проведение, регламент обмена, пик нагрузки.\n"
                "**Проверки:** номер документа, время создания, есть ли дубль в очереди, "
                "повторяется ли у одного контрагента.\n"
                "Эскалация на 2 линию 1С при массовом сбое — по процессу DIT/1С (не чинить из WEB вручную)."
            ),
            "source_url": "https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124638779",
            "source_title": "1С очередь",
        },
        {
            "id": "1C-06",
            "question": "Выгрузка в 1С / документ не проведён — что спросить у заявителя",
            "keywords": "выгрузка, проведение, 1С, Солярис, не ушло",
            "answer": (
                "Уточнить: **тип документа**, **номер**, **дата**, **контрагент**, **ошибка из 1С** (текст).\n"
                "Проверить в Солярис статус документа и связанные эл.заявки.\n"
                "Не копировать в KB переписку HD целиком — только шаги проверки и итог."
            ),
        },
    ]


def format_qa_block(item: dict[str, str]) -> str:
    lines = [
        f"### {item.get('id', '1C-Q')}. {item.get('question', '')}",
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
    return "\n".join(lines)


def build_qa_document(qa_items: list[dict[str, str]], pages: list[dict[str, Any]]) -> str:
    parts = [
        "# 1С Солярис: база вопросов и ответов (чатбот IntraService)\n\n",
        "> **Контур:** 1С Солярис (HelpDesk ServiceId **69**). "
        "Профиль `onec_tickets`, корпус `knowledge/1c/`.\n\n",
        f"Источники Confluence: {len(pages)} страниц выборочно.\n\n---\n\n",
    ]
    for item in qa_items:
        parts.append(format_qa_block(item) + "\n\n---\n\n")
    return "".join(parts)


def build_corpus_md(qa_items: list[dict[str, str]], pages: list[dict[str, Any]]) -> str:
    parts = [
        "# Корпус 1С Солярис для профиля onec_tickets\n\n",
        "HelpDesk: **Солярис** (ServiceId 69) · родитель 1С Предприятие (14).\n",
        "Связан с ЛК (трекинг, резерв) и CRM (спеццены). Не путать API каталога ЛК с 1С.\n\n",
        build_qa_document(qa_items, pages),
        "\n\n---\n\n# Выдержки из Confluence (справочно)\n",
    ]
    for p in pages:
        if len(p.get("text") or "") < 80:
            continue
        parts.append(f"\n## {p['title']}\nURL: {p['url']}\n\n{(p.get('text') or '')[:2800]}\n")
    parts.append(
        "\n\n## Ручные overrides\n\n"
        "Пока нет живого `1C_BASE_URL`: см. `knowledge/learned/1c_overrides.json`.\n"
    )
    return "".join(parts)


def qa_items_to_confluence_storage(qa_items: list[dict[str, str]], intro: str) -> str:
    blocks = [
        "<p>"
        + cf._inline_md(intro.replace("\n", " ").strip())  # type: ignore[attr-defined]
        + "</p>"
    ]
    for item in qa_items:
        title = f"{item.get('id', '')}. {item.get('question', '')}"
        body = item.get("answer", "")
        kw = item.get("keywords", "")
        code_block = f"**Ключевые слова:** {kw}\n\n{body}".strip()
        if item.get("not_confused_with"):
            code_block = f"**Не путать с:** {item['not_confused_with']}\n\n{code_block}"
        blocks.append(
            f'<h4>{cf._inline_md(title)}</h4>'
            f'<p><strong>Ключевые слова:</strong> {cf._inline_md(kw)}</p>'
            f'<ac:structured-macro ac:name="expand" ac:schema-version="1">'
            f'<ac:parameter ac:name="title">Ответ (копировать)</ac:parameter>'
            f"<ac:rich-text-body>"
            f'<ac:structured-macro ac:name="code" ac:schema-version="1">'
            f'<ac:parameter ac:name="language">text</ac:parameter>'
            f"<ac:plain-text-body><![CDATA[{code_block}]]></ac:plain-text-body>"
            f"</ac:structured-macro></ac:rich-text-body></ac:structured-macro>"
        )
    return "\n".join(blocks)


def publish_webkb(s: Any, qa_md: str, qa_items: list[dict[str, str]]) -> dict[str, Any]:
    meta_path = ROOT / "docs" / "confluence" / "onec_qa_page_id.json"
    intro = (
        "База Q&A для разбора заявок **1С Солярис** (ServiceId 69). "
        "Для чатбота IntraService и ревью оператора."
    )
    storage = qa_items_to_confluence_storage(qa_items, intro)
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        pid = str(meta.get("page_id") or "")
        if pid:
            cf.update_page(s, pid, title=WEBKB_PAGE_TITLE, storage=storage, message="build_1c_corpus")
            return {"action": "updated", "page_id": pid, "url": cf.view_url(s, pid)}
    result = cf.create_or_update_child(
        s,
        space="WEBKB",
        title=WEBKB_PAGE_TITLE,
        parent_id=WEBKB_PARENT,
        storage=storage,
        message="build_1c_corpus",
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

    pages: list[dict[str, Any]] = []
    s = cf.session()
    for pid in ONEC_PAGE_IDS:
        try:
            p = fetch_page(s, pid)
            if not SKIP_TITLE_RE.search(p["title"]):
                pages.append(p)
        except Exception as err:
            print(f"skip {pid}: {err}", file=sys.stderr)

    qa_items = curated_qa()
    dest = ROOT / "knowledge" / "1c"
    dest.mkdir(parents=True, exist_ok=True)
    qa_md = build_qa_document(qa_items, pages)
    (dest / "qa.md").write_text(qa_md, encoding="utf-8")
    (dest / "corpus.md").write_text(build_corpus_md(qa_items, pages), encoding="utf-8")

    meta = {
        "qa_count": len(qa_items),
        "pages_fetched": len(pages),
        "corpus": "knowledge/1c/corpus.md",
        "qa": "knowledge/1c/qa.md",
        "hd_service_id": 69,
        "hd_parent_service_id": 14,
    }
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))

    if args.publish:
        pub = publish_webkb(s, qa_md, qa_items)
        print("publish", json.dumps(pub, ensure_ascii=False))
        meta["webkb"] = pub
        (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
