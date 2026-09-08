# -*- coding: utf-8 -*-
"""LK-12 на «Быстрые ответы» + убрать мусор promote #694270 + удалить страницу ревью.

  python scripts/fix_lk12_and_cleanup_694270.py
  python scripts/fix_lk12_and_cleanup_694270.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import confluence_client as cf  # noqa: E402

LK_QUICK_PAGE = "124630014"
REVIEW_PAGE = "124641776"
HD = "694270"
HD_URL = f"https://helpdesk.iek.local/Task/View/{HD}"

LK12_STORAGE = """
<h2>LK-12. Остатки в ЛК &ne; 1С (расхождение и «количество на блоке»)</h2>
<p><em>Источник: HD#""" + HD + """ · <a href=\"""" + HD_URL + """\">""" + HD_URL + """</a></em></p>
<p><strong>Ключевые слова:</strong> остатки, расхождение ЛК и 1С, кол-во 0, количество на блоке, поверка, каталог 3.0, inventory_display, заблокированный остаток, артикул.</p>
<p><strong>Не путать с LK-10:</strong> там про <em>список складов</em> в каталоге (регистр «Склады контрагента»), а не про остаток по артикулу.</p>
<h3>Разновидность A — общее расхождение остатков</h3>
<p><strong>Сценарий:</strong> в ЛК поле «Кол-во» = 0 или неактивно; в 1С по артикулу есть свободный и/или заблокированный остаток (новая версия ЛК vs старая).</p>
<ol>
<li>Сверить в 1С: свободный vs заблокированный остаток по артикулу и складу.</li>
<li>Проверить синхронизацию остатков ЛК &harr; 1С (не только «Склады контрагента»).</li>
<li>Исключить заказную продукцию, кратность, блокировки (LK-06, WEBKB).</li>
</ol>
<h3>Разновидность B — «количество на блоке» (поверка)</h3>
<p><strong>Сценарий:</strong> артикул с <strong>количеством на блоке</strong> (приборы, которые после заказа уходят на поверку). В каталоге <strong>ЛК 2.0</strong> в скобках показывалось кол-во на блоке; в <strong>каталоге 3.0</strong> — нет, хотя товар на складе есть. Заказчик должен видеть наличие: поверка добавляет время, но остаток отображать нужно.</p>
<ol>
<li>Уточнить: артикул с признаком «на блоке» / поверка; сравнить отображение 2.0 vs 3.0.</li>
<li>Сверить остаток в 1С (в т.ч. заблокированный) с карточкой товара в ЛК 3.0.</li>
<li>Если баг UX/синхронизации — эскалация на WEB/1С с артикулом и скринами (без email в KB).</li>
</ol>
<p><strong>Открытый ответ:</strong> только после факта проверки; не обещать «ожидайте обновление» без результата.</p>
<p><em>AI-KB LK-12 · HD#""" + HD + """ · 2026-09-01</em></p>
"""


def _strip_bad_promote(html: str) -> str:
    """Убрать append от ошибочного promote LK-10-SUP-694270."""
    markers = (
        "LK-10-SUP-694270",
        "Спасибо за сообщение. Мы проверим логику отображения остатков",
        "AI-KB дополнение",
        "AI-KB (LK-10-SUP-694270)",
    )
    if not any(m in (html or "") for m in markers):
        return html
    # последний <hr/> — типичный разделитель append
    parts = re.split(r"(<hr\s*/?>)", html or "", flags=re.I)
    if len(parts) >= 3:
        tail = parts[-1]
        if any(m in tail for m in markers):
            return "".join(parts[:-2]).rstrip()
    # fallback: вырезать от info-макроса с AI-KB до конца
    m = re.search(
        r"<ac:structured-macro[^>]*ac:name=\"info\"[^>]*>[\s\S]*?AI-KB[\s\S]*$",
        html or "",
        re.I,
    )
    if m:
        return (html or "")[: m.start()].rstrip()
    return html


def _has_lk12(html: str) -> bool:
    return "LK-12." in (html or "") or "LK-12 " in (html or "")


def delete_page(s, page_id: str) -> dict:
    resp = s.delete(
        f"{s.base}/rest/api/content/{page_id}",  # type: ignore[attr-defined]
        timeout=60,
    )
    if resp.status_code in (200, 204):
        return {"ok": True, "page_id": page_id}
    return {"ok": False, "status": resp.status_code, "body": resp.text[:400]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    s = cf.session()
    page = cf.get_page(s, LK_QUICK_PAGE, expand="body.storage,version,title")
    old = ((page.get("body") or {}).get("storage") or {}).get("value") or ""
    cleaned = _strip_bad_promote(old)
    if _has_lk12(cleaned):
        new_body = cleaned
        lk12_action = "already_present"
    else:
        new_body = cleaned + "\n<hr/>\n" + LK12_STORAGE.strip()
        lk12_action = "appended"

    out: dict = {
        "lk_quick_page": LK_QUICK_PAGE,
        "lk12_action": lk12_action,
        "stripped_bad_promote": len(cleaned) < len(old),
        "review_page": REVIEW_PAGE,
    }

    if args.dry_run:
        out["dry_run"] = True
        out["new_body_chars"] = len(new_body)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if new_body != old:
        cf.update_page(
            s,
            LK_QUICK_PAGE,
            title=str(page.get("title") or ""),
            storage=new_body,
            message=f"LK-12 stock mismatch HD#{HD}; remove bad promote",
        )
        out["lk_quick_url"] = cf.view_url(s, LK_QUICK_PAGE)

    del_res = delete_page(s, REVIEW_PAGE)
    out["review_deleted"] = del_res
    if not del_res.get("ok"):
        out["review_delete_hint"] = (
            f"Удалите вручную страницу ревью: {cf.view_url(s, REVIEW_PAGE)} "
            f"(pageId={REVIEW_PAGE})"
        )

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if del_res.get("ok") or out.get("review_delete_hint") else 1


if __name__ == "__main__":
    raise SystemExit(main())
