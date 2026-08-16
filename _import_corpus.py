# -*- coding: utf-8 -*-
"""Очистить корпус партнёра: убрать Confluence, HelpDesk, .local, Figma, внутренние пометки."""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(r"C:\Users\fetisovaa\ФЗ по ЛК ИЭК\instructions\Справка_партнёра_ЛК\ассистент\knowledge\corpus.md")
DST = Path(r"C:\Users\fetisovaa\AI Assistant IEK\knowledge\corpus.md")

DROP_SUBSTR = (
    "confluence.dev",
    "helpdesk.iek",
    "chatgpt.iek",
    ".local",
    "figma.com",
    "intraservice",
    "webkb",
    "казенников",
    "50016073",
    "50024682",
    "50018362",
    "50032137",
    "instructions/справка",
    "corp.iek.ru",
    "jira",
    "--apply",
    "691975",
)

DROP_LINE_PREFIXES = (
    "**фз:**",
    "**макет:**",
    "**скрин:**",
)

INTRO = """# Корпус помощника партнёра ЛК

Только инструкции пользователя личного кабинета https://lk.iek.ru.
Справка в кабинете: https://lk.iek.ru/lk/help/
Канал видео: https://dzen.ru/lk_iek_ru
Вебинар ЛК 3.0: https://dzen.ru/video/watch/6a0eb54510852e622dabfb6c (13.05.2026)
Технические сбои: hd@iek.ru. Идеи: wishes-lk@iek.ru.

Канон: шаги по экрану ЛК 3.0. Скрины и ролики ЛК 2.0 не используйте как инструкцию.

## Темы справки

| Тема | Раздел меню ЛК 3.0 |
|:---|:---|
| P-00 Вход | https://lk.iek.ru , IEK ID |
| P-01 Новый заказ и каталог | Заказы → + Новый заказ |
| P-02 Склады и кратность | тот же экран каталога |
| P-03 Корзина и оформление | Корзина |
| P-04 Трекинг заказов | Трекинг заказов |
| P-05 Неудовлетворённый спрос | Неудовлетворённый спрос |
| P-06 Подтверждение счетов | Логистические сервисы → Подтверждение счетов |
| P-07 Тендеры | Тендеры, затем корзина «Тендерная» |
| P-08 Куда писать | hd@iek.ru, wishes-lk@iek.ru, справка |
| P-09 Возвраты | Возвраты |
| P-10 Спеццены | Спеццены |
| P-11 Новинки | Новинки / тег «Новинка» |
| P-12 Платная доставка | оформление заказа и подтверждение счетов |
| P-13 Заказы на Контактор | отдельный заказ только с артикулами Контактора |
| P-14 Честный знак | тег в каталоге |
| P-15 Зональные цены | цена после выбора места доставки |
| P-16 Профиль и сотрудники | https://lk.iek.ru/lk/users/ |
| P-17 Школа партнёра | Школа партнёра / https://lk.iek.ru/lk/help/ |

## Что устарело в UI ЛК 2.0

| Было в ролике 2.0 | Сейчас в ЛК 3.0 |
|:---|:---|
| «История заказов» слева | **Трекинг заказов** |
| «Новый заказ» слева | **Заказы → + Новый заказ** |
| Сначала место доставки, потом артикулы | Сначала **плательщик + место доставки + склад** |
| Одна корзина | Вкладки: **базовая / тендерная** (и др.) |
| Галка «многоскладское резервирование» | Склад «Все склады» vs склад инд. кратности |
| Подтверждение счетов в старом разделе | **Логистические сервисы → Подтверждение счетов** |
| НС только из карточки заказа | Раздел **НС**; на вебинаре 13.05.2026 ещё дорабатывался |

## Нарезка вебинара 13.05.2026

Ссылки: `https://dzen.ru/video/watch/6a0eb54510852e622dabfb6c?t=СЕКУНДЫ`

| От | До | t= | Тема |
|:---|:---|:---|:---|
| 02:33 | 09:30 | 153 | P-01 каталог |
| 09:30 | 16:23 | 570 | P-02 склады / кратность |
| 16:23 | 20:36 | 983 | P-03 оформление |
| 20:36 | 22:32 | 1236 | P-05 НС |
| 22:32 | 26:35 | 1352 | P-07 тендеры |
| 28:47 | 41:02 | 1727 | FAQ внутри тем |
| 42:05 | 44:15 | 2525 | P-08 hd@iek.ru |

## FAQ с вебинара

- Спеццены через Excel **пока нельзя** — буфер обмена.
- Автоподтверждение резервов в пути **не по умолчанию**.
- Приоритет складов настраивается.
- Поиск номенклатуры в тендере — в разработке (на дату записи).
- Аналоги в каталоге **пока не отображаются**.
- НС 3.0 на дату записи **не доработан** — пока продукт не снимет оговорку.
"""

SKIP_SECTION_MARKERS = (
    "# карта тем",
    "# не для партнёра",
    "## не для партнёра",
    "## пользовательские фз",
    "## скрины",
    "## что устарело",
    "## нарезка вебинара",
    "## faq с вебинара",
    "# корпус помощника",
)


def bad_line(line: str) -> bool:
    low = line.lower()
    if any(s in low for s in DROP_SUBSTR):
        return True
    stripped = line.strip().lower()
    if any(stripped.startswith(p) for p in DROP_LINE_PREFIXES):
        return True
    if "helpdesk" in low and "партнёру не нужно" not in low:
        # keep the one partner-facing sentence in P-08; drop analyst notes
        if stripped.startswith("|") or "внутренн" in low:
            return True
    return False


def skip_section(header_block: str) -> bool:
    head = "\n".join(header_block.splitlines()[:6]).lower()
    return any(m in head for m in SKIP_SECTION_MARKERS) and not re.search(
        r"# p-\d+", head
    )


def clean_section(text: str) -> str:
    lines = []
    for ln in text.splitlines():
        if bad_line(ln):
            continue
        ln = re.sub(r"\s*\(P-\d+\)", lambda m: m.group(0), ln)
        lines.append(ln)
    body = "\n".join(lines).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    # внутренние формулировки
    body = body.replace("На Confluence текст раздела короткий — шаги по экрану оформления и логистики.", "")
    body = body.replace("Админка размещения — не для партнёра.", "")
    body = body.replace("Заготовка 08.90 в дереве ФЗ **чужая / пустая — не правим**; эта инструкция отдельная.", "")
    body = body.replace("Заготовка 09.90 в дереве ФЗ **чужая / пустая — не правим**.", "")
    body = body.replace("ролевая модель — только то, что видно партнёру (сотрудники, подразделения). ", "")
    body = body.replace(
        "Ждать ответ во внутреннем HelpDesk партнёру не нужно: канал партнёра — почта hd@iek.ru.",
        "Канал партнёра по сбоям — почта hd@iek.ru, не внутренние системы IEK.",
    )
    body = body.replace(
        "Письмо попадает в классификатор ЛК, обработка быстрее. ",
        "",
    )
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def main() -> None:
    raw = SRC.read_text(encoding="utf-8")
    parts = re.split(r"\n---+\n", raw)
    kept: list[str] = []
    for part in parts:
        text = part.strip()
        if not text:
            continue
        if skip_section(text):
            continue
        cleaned = clean_section(text)
        if not cleaned or len(cleaned) < 40:
            continue
        kept.append(cleaned)
    dest = INTRO.rstrip() + "\n\n" + "\n\n---\n\n".join(kept) + "\n"
    # финальный проход
    final_lines = []
    for ln in dest.splitlines():
        if bad_line(ln):
            continue
        final_lines.append(ln)
    dest = "\n".join(final_lines)
    dest = re.sub(r"\n{3,}", "\n\n", dest).strip() + "\n"
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(dest, encoding="utf-8")
    print(f"wrote corpus ({DST.stat().st_size} bytes, {dest.count(chr(10))} lines)")


if __name__ == "__main__":
    main()
