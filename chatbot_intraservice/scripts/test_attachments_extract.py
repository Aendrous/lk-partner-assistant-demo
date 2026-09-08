# -*- coding: utf-8 -*-
"""Smoke-тест извлечения текста из вложений (без LLM / IntraService)."""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import attachments  # noqa: E402


def _mini_pdf() -> bytes:
  import pymupdf as fitz

  doc = fitz.open()
  page = doc.new_page()
  page.insert_text((72, 72), "Заявка на подключение к ЛК. ИНН 7701234567.")
  return doc.tobytes()


def _mini_docx() -> bytes:
  from docx import Document

  doc = Document()
  doc.add_paragraph("Карточка партнёра ООО Тест. Email: partner@example.com")
  buf = io.BytesIO()
  doc.save(buf)
  return buf.getvalue()


def main() -> int:
  pdf = _mini_pdf()
  docx = _mini_docx()

  assert attachments._kind_for("a.pdf", pdf) == "document"
  assert attachments._kind_for("b.docx", docx) == "document"
  assert attachments._kind_for("c.msg", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"x" * 200) == "mail"
  assert attachments._kind_for("d.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"x" * 200) == "document"

  pdf_text = attachments.extract_pdf_text(pdf)
  assert "7701234567" in pdf_text, pdf_text

  docx_text = attachments.extract_docx_text(docx)
  assert "partner@example.com" in docx_text, docx_text

  pngs = attachments.pdf_pages_as_png(pdf)
  assert len(pngs) == 1 and pngs[0][:8] == b"\x89PNG\r\n\x1a\n"

  print("ok: test_attachments_extract")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
