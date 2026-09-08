# -*- coding: utf-8 -*-
"""Обучение ассистента из заявок: gap в KB → черновик → Confluence → rebuild corpus."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PKG = HERE.parent

CLOSED_STATUS_IDS = {28, 29}  # Закрыта, Выполнена
INDEX_PATH = PKG / "knowledge" / "learned" / "index.json"
DRAFTS_DIR = PKG / "docs" / "черновики_статей"
KB_PAGES_PATH = PKG / "docs" / "confluence" / "kb_assistant_pages.json"

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


# Import centralized debug artifacts module
sys.path.insert(0, str(HERE))
try:
    import debug_artifacts
finally:
    sys.path.pop(0)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_kb_pages() -> dict[str, Any]:
    if not KB_PAGES_PATH.is_file():
        return {}
    return json.loads(KB_PAGES_PATH.read_text(encoding="utf-8"))


def load_index() -> dict[str, Any]:
    if not INDEX_PATH.is_file():
        return {"entries": []}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def save_index(data: dict[str, Any]) -> Path:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return INDEX_PATH


def analysis_path(task_id: str | int) -> Path:
    """Путь к _analysis_{task_id}.json — использует debug_artifacts для новой структуры."""
    return debug_artifacts.analysis_path(task_id)


def load_analysis(task_id: str | int) -> dict[str, Any] | None:
    """Загрузить артефакт разбора (ищет в debug/, затем в корне для legacy)."""
    path = debug_artifacts.find_analysis(task_id)
    if not path or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_closed_task(task: dict[str, Any]) -> bool:
    sid = task.get("StatusId")
    if isinstance(sid, str) and sid.isdigit():
        sid = int(sid)
    return isinstance(sid, int) and sid in CLOSED_STATUS_IDS


def humanize_gap_reason(reason: str) -> str:
    """Короткая подпись для UI вместо технического gap_reason."""
    r = (reason or "").strip()
    if not r:
        return ""
    if "has_kb_solution=false" in r or "нет ссылок на Confluence" in r:
        return "В KB не нашлось готового ответа при разборе заявки."
    if r.startswith("разбор не выполнялся"):
        return "Разбор заявки ещё не выполнялся."
    if "уже были статьи KB" in r:
        return "При разборе уже нашлись статьи в KB."
    return r


def assess_kb_gap(analysis: dict[str, Any] | None) -> dict[str, Any]:
    """Был ли ответ в KB на момент разбора."""
    if not analysis:
        return {"gap": True, "reason": "разбор не выполнялся — нужен analyze_and_comment"}
    parsed = analysis.get("parsed") or {}
    has = bool(parsed.get("has_kb_solution"))
    links = [u for u in (parsed.get("article_links") or []) if str(u).strip()]
    if not has or not links:
        return {
            "gap": True,
            "reason": "при разборе has_kb_solution=false или нет ссылок на Confluence",
            "has_kb_solution": has,
            "article_links": links,
        }
    return {
        "gap": False,
        "reason": "в разборе уже были статьи KB",
        "has_kb_solution": has,
        "article_links": links,
    }


def draft_exists_for_task(task_id: str | int) -> dict[str, Any] | None:
    tid = str(task_id).strip()
    for entry in load_index().get("entries") or []:
        if str(entry.get("task_id")) == tid:
            status = str(entry.get("status") or "draft")
            # in_review = уже выгружен в Confluence-папку ревью
            # merged_into = уже влили в чужой черновик (не плодить -SUP-)
            if status in {"draft", "in_review", "reviewed", "published", "merged_into", "duplicate_of"}:
                return entry
    return None


def should_auto_learn(
    task: dict[str, Any],
    analysis: dict[str, Any] | None,
    *,
    trigger: str = "analyze",
    force: bool = False,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Решение: создавать черновик AI-KB или пропустить.

    Правила (зафиксированы в docs/pipeline/решения.md):
    - master switch auto_learn_kb
    - skip если чатбот уже нашёл KB (has_kb_solution + links)
    - skip если черновик/статья уже в index
    - on_close: только закрытые заявки (если require_closed)
    - force (--learn / UI) обходит skip_if_kb_found, но не duplicate draft
    """
    if settings is None:
        from settings import load_settings

        settings = load_settings()

    import assistants

    onec_skip = assistants.skip_onec_task(task)
    if onec_skip:
        return {"run": False, "reason": onec_skip}

    if force:
        existing = draft_exists_for_task(task.get("Id") or "")
        if existing and settings.get("skip_if_draft_exists", True):
            return {
                "run": False,
                "reason": f"черновик уже есть ({existing.get('code')}) — обновите вручную",
                "existing": existing,
            }
        return {"run": True, "reason": "принудительно (force)"}

    if not settings.get("auto_learn_kb"):
        return {"run": False, "reason": "auto_learn_kb выключен в настройках чатбота"}

    import service_filter

    parsed = (analysis or {}).get("parsed") or {}
    skip_contour = service_filter.skip_for_task(task, "kb_learn", settings, parsed=parsed)
    if skip_contour:
        return {"run": False, "reason": skip_contour}

    gap = assess_kb_gap(analysis)
    if settings.get("skip_if_kb_found", True) and not gap.get("gap"):
        return {
            "run": False,
            "reason": "чатбот нашёл ответ в KB — обучение не требуется",
            "gap": gap,
        }

    if settings.get("skip_if_draft_exists", True):
        existing = draft_exists_for_task(task.get("Id") or "")
        if existing:
            return {
                "run": False,
                "reason": f"инструкция уже создана ({existing.get('code')}, {existing.get('status')})",
                "existing": existing,
            }

    if trigger in {"watch_close", "close"}:
        if not settings.get("auto_learn_on_close", True):
            return {"run": False, "reason": "auto_learn_on_close выключен"}
        if settings.get("require_closed_for_auto_learn", True) and not is_closed_task(task):
            return {"run": False, "reason": "заявка ещё не закрыта — ждём статус 28/29"}
    elif trigger in {"analyze", "cli", "ui", "manual"}:
        if not settings.get("auto_learn_on_analyze", False):
            return {
                "run": False,
                "reason": "auto_learn_on_analyze выключен (обучение при закрытии через watch)",
                "gap": gap,
            }

    if not gap.get("gap"):
        return {"run": False, "reason": "нет gap в KB", "gap": gap}

    return {"run": True, "reason": gap.get("reason") or "gap в KB — нужен черновик", "gap": gap}


def eligible_for_learning(
    task: dict[str, Any],
    analysis: dict[str, Any] | None,
    *,
    force: bool = False,
    require_closed: bool = False,
) -> dict[str, Any]:
    gap = assess_kb_gap(analysis)
    closed = is_closed_task(task)
    if require_closed and not closed:
        return {
            "eligible": False,
            "reason": "заявка ещё не закрыта (нужен статус 28/29)",
            "gap": gap,
            "closed": closed,
        }
    if force:
        return {"eligible": True, "reason": "принудительно (--force)", "gap": gap, "closed": closed}
    if gap.get("gap"):
        return {
            "eligible": True,
            "reason": gap.get("reason"),
            "gap": gap,
            "closed": closed,
        }
    if closed:
        return {
            "eligible": True,
            "reason": "закрыта, но при разборе не было KB — зафиксировать решение исполнителя",
            "gap": gap,
            "closed": closed,
        }
    return {
        "eligible": False,
        "reason": "ответ в KB уже был; черновик не нужен (или --force)",
        "gap": gap,
        "closed": closed,
    }


def target_for_contour(service_key: str, *, profile_key: str = "") -> dict[str, Any]:
    pages = load_kb_pages()
    key = (service_key or "other").strip().lower()
    if key in {"1c", "onec", "solaris"}:
        key = "edi"
    targets = pages.get("targets_by_contour") or {}
    row = dict(targets.get(key) or targets.get("other") or {})
    pk = (profile_key or "").strip().lower()
    if key == "edi" and pk == "onec_logistics_tn":
        tn_id = str(row.get("qa_logistics_tn_page_id") or "").strip()
        if tn_id:
            row["page_id"] = tn_id
            row["title"] = str(
                row.get("qa_logistics_tn_title") or "Быстрые ответы: 1С · Выгрузка ТН (ОП-2765)"
            )
    row["contour"] = key
    return row


def next_code_prefix(service_key: str, task_id: str | int | None = None) -> str:
    index = load_index()
    if task_id is not None:
        for entry in index.get("entries") or []:
            if str(entry.get("task_id")) == str(task_id).strip() and entry.get("code"):
                return str(entry["code"])
    target = target_for_contour(service_key)
    prefix = str(target.get("code_prefix") or "HD").upper()
    nums: list[int] = []
    for entry in index.get("entries") or []:
        code = str(entry.get("code") or "")
        m = re.match(rf"^{re.escape(prefix)}-(\d+)", code)
        if m:
            nums.append(int(m.group(1)))
    n = max(nums) + 1 if nums else 6  # BP-01..05 уже в WEBKB; новые с 06
    return f"{prefix}-{n:02d}"


def _slug(text: str, max_len: int = 48) -> str:
    t = re.sub(r"[^\w\s-]", "", (text or "").lower(), flags=re.UNICODE)
    t = re.sub(r"[\s_]+", "_", t.strip())
    return (t[:max_len] or "ticket").strip("_")


_HIDDEN_LIFETIME_RE = re.compile(
    r"(?i)^(?:сервис\s*hd\s*:|разбор от чатбота iek llm|разбор iek llm|"
    r"результат преданализа iek llm|ai-kb:)"
)


def extract_lifetime_comments(lifetime: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    """Комментарии из lifetime IntraService (поле Comments, не Description)."""
    items = lifetime
    if isinstance(lifetime, dict):
        items = lifetime.get("TaskLifetimes") or []
    out: list[dict[str, Any]] = []
    for row in items or []:
        if not isinstance(row, dict):
            continue
        text = str(
            row.get("Comments")
            or row.get("Description")
            or row.get("Comment")
            or ""
        ).strip()
        if not text or len(text) < 20:
            continue
        is_public = row.get("IsPublic")
        out.append(
            {
                "date": row.get("Date"),
                "editor": row.get("Editor"),
                "status_id": row.get("StatusId"),
                "is_public": is_public,
                "text": text[:2000],
            }
        )
    return out


_HIDDEN_LIFETIME_RE = re.compile(
    r"(?i)^(?:сервис\s*hd\s*:|разбор от чатбота iek llm|разбор iek llm|"
    r"результат преданализа iek llm|ai-kb:)"
)
_CLOSING_REPLY_RE = re.compile(
    r"(?i)^(?:спасибо|благодарим|принято|ожидаем|ожидаю|ждём|ждем|хорошо|"
    r"принял|ок)[!.…,\s]*$|^@\S+(?:\s+@\S+)*\s*$"
)
_DEV_TRANSFER_RE = re.compile(
    r"(?i)передан[ао]?\s+на\s+разработ|проблема\s+передан|эскалац.*разработ|"
    r"на\s+разработку"
)
_EXECUTOR_HINT_RE = re.compile(
    r"(?i)глобальн.*сбой|проверьте\s+сейчас|инцидент|сервис\s+восстанов"
)
_EXTERNAL_MSG_RE = re.compile(r"(?i)внимание,\s*внешнее\s+сообщение")


def _editor_is_requester(editor: str, creator_email: str) -> bool:
    """Публичный комментарий от заявителя (не исполнителя IEK)."""
    ed = (editor or "").strip().lower()
    if not ed or ed == "intraservice":
        return False
    ce = (creator_email or "").strip().lower()
    if not ce:
        return False
    local = ce.split("@", 1)[0].replace(".", "_")
    if local and local in ed.replace(".", "_"):
        return True
    # HelpDesk: nesterova.d_favorit-el.ru
    domain = ce.split("@", 1)[-1].replace(".", "-")
    if domain and domain in ed:
        return True
    return False


def _resolution_score(text: str, editor: str, *, creator_email: str) -> int:
    """Выше = лучше кандидат resolution для learn (ответ исполнителя, не заявителя)."""
    t = (text or "").strip()
    if not t or len(t) < 12:
        return -100
    if _EXTERNAL_MSG_RE.search(t):
        return -80
    if _editor_is_requester(editor, creator_email):
        return -50
    score = 10
    if _DEV_TRANSFER_RE.search(t):
        score += 100
    if _EXECUTOR_HINT_RE.search(t):
        score += 60
    if _CLOSING_REPLY_RE.match(t.strip()):
        score -= 40
    score += min(len(t), 200) // 20
    return score


def _public_resolution_candidates(
    lifetime: dict[str, Any] | None,
    *,
    task_description: str = "",
    creator_email: str = "",
) -> list[str]:
    """Публичные ответы исполнителя (без скрытых разборов и вежливых закрытий)."""
    if not lifetime:
        return []
    init = (task_description or "").strip()[:200]
    rows = lifetime.get("TaskLifetimes") or []
    scored: list[tuple[int, str]] = []
    for row in sorted(rows, key=lambda r: str((r or {}).get("Date") or "")):
        if not isinstance(row, dict):
            continue
        if row.get("IsPublic") is not True:
            continue
        text = str(row.get("Comments") or "").strip()
        if len(text) < 12:
            continue
        low = text.lower()
        if _HIDDEN_LIFETIME_RE.search(text):
            continue
        if "ticket is automatically transferred" in low:
            continue
        if init and text[:120] == init[:120]:
            continue
        if _CLOSING_REPLY_RE.match(text.strip()):
            continue
        if len(text) < 50 and re.search(r"(?i)спасибо|принято|ожида", text):
            continue
        editor = str(row.get("Editor") or "")
        sc = _resolution_score(text, editor, creator_email=creator_email)
        if sc < 0:
            continue
        scored.append((sc, text))
    if not scored:
        return []
    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored]


def pick_resolution_text(
    task: dict[str, Any],
    lifetime_comments: list[dict[str, Any]],
    analysis: dict[str, Any] | None,
    lifetime: dict[str, Any] | None = None,
) -> str:
    """Публичный ответ исполнителя; не путать со скрытым разбором бота / AI-KB."""
    creator_email = str(task.get("CreatorEmail") or "")
    candidates = _public_resolution_candidates(
        lifetime,
        task_description=str(task.get("Description") or ""),
        creator_email=creator_email,
    )
    if candidates:
        return candidates[0][:1200]

    if lifetime:
        try:
            import overdue

            prior = overdue.extract_prior_public_answer(lifetime).strip()
            if prior and not _CLOSING_REPLY_RE.match(prior.strip()):
                return prior[:1200]
        except Exception:
            pass

    init = (task.get("Description") or "").strip()[:200]
    for row in reversed(lifetime_comments):
        if row.get("is_public") is False:
            continue
        text = row.get("text") or ""
        if init and text[:120] == init[:120]:
            continue
        low = text.lower()
        if "внешнее сообщение" in low:
            continue
        if _HIDDEN_LIFETIME_RE.search(text):
            continue
        editor = str(row.get("editor") or "").lower()
        if "intraservice" in editor and "ticket is automatically" in low:
            continue
        if _CLOSING_REPLY_RE.match(text.strip()):
            continue
        return text[:1200]

    parsed = (analysis or {}).get("parsed") or {}
    steps = [str(s).strip() for s in (parsed.get("solution_steps_ru") or []) if str(s).strip()]
    if steps:
        return "; ".join(steps[:4])
    summary = (parsed.get("summary_ru") or task.get("Name") or "").strip()
    return summary


def performer_resolution_present(
    task: dict[str, Any],
    lifetime: dict[str, Any] | None,
) -> bool:
    """Есть ли публичный ответ исполнителя с решением (не fallback на summary/название)."""
    creator_email = str(task.get("CreatorEmail") or "")
    if _public_resolution_candidates(
        lifetime,
        task_description=str(task.get("Description") or ""),
        creator_email=creator_email,
    ):
        return True
    if lifetime:
        try:
            import overdue

            prior = overdue.extract_prior_public_answer(lifetime).strip()
            if prior and not _CLOSING_REPLY_RE.match(prior.strip()):
                return True
        except Exception:
            pass
    return False


def confluence_view_url(page_id: str | None) -> str:
    pid = str(page_id or "").strip()
    if not pid:
        return ""
    return f"https://confluence.dev.iek.ru/pages/viewpage.action?pageId={pid}"


KB_INSERT_START = "<!-- KB_INSERT_START -->"
KB_INSERT_END = "<!-- KB_INSERT_END -->"
_INSERT_RE = re.compile(
    r"<!--\s*KB_INSERT_START\s*-->([\s\S]*?)<!--\s*KB_INSERT_END\s*-->",
    re.I,
)


def extract_insert_sections(md: str) -> str:
    """Текст для Promote — только первый блок KB_INSERT (дополнения не дублируют)."""
    parts = [m.group(1).strip() for m in _INSERT_RE.finditer(md or "")]
    parts = [p for p in parts if p and p != "_(нет текста — LLM вернул skip/пусто)_"]
    if parts:
        return parts[0]
    # fallback: fenced text после «Слова для дополнения» / «Текст для вставки»
    m = re.search(
        r"(?is)(?:Слова для дополнения|Текст для вставки[^\n]*)\s*:?\s*```(?:text)?\s*([\s\S]*?)```",
        md or "",
    )
    if m:
        return m.group(1).strip()
    return ""


def replace_kb_insert_in_markdown(md: str, insert: str) -> str:
    """Подставить новый текст между KB_INSERT_START/END (один блок на черновик)."""
    body = (insert or "").strip()
    new_block = f"{KB_INSERT_START}\n{body}\n{KB_INSERT_END}"
    if _INSERT_RE.search(md or ""):
        md2, _ = _INSERT_RE.subn(new_block, md, count=1)
        idx = 0

        def _drop_extra(m: re.Match[str]) -> str:
            nonlocal idx
            idx += 1
            return m.group(0) if idx == 1 else ""

        return _INSERT_RE.sub(_drop_extra, md2)
    block = f"\n{KB_INSERT_START}\n{body}\n{KB_INSERT_END}\n"
    if "Слова для дополнения" in (md or ""):
        return re.sub(
            r"(?im)(-\s*\*\*Слова для дополнения:\*\*\s*\n)",
            r"\1" + block,
            md,
            count=1,
        )
    return (md or "").rstrip() + "\n\n" + block


def save_draft_kb_insert(draft_path: Path | str, insert: str) -> Path:
    """Записать отредактированный KB_INSERT в локальный .md черновика."""
    path = Path(draft_path)
    if not path.is_absolute():
        path = PKG / path
    if not path.is_file():
        raise FileNotFoundError(str(path))
    md = path.read_text(encoding="utf-8")
    path.write_text(replace_kb_insert_in_markdown(md, insert), encoding="utf-8")
    return path


def build_draft_markdown(
    task: dict[str, Any],
    analysis: dict[str, Any] | None,
    *,
    resolution_text: str = "",
    service_key: str = "",
    code: str = "",
    dedup: dict[str, Any] | None = None,
    learn_compare_md: str = "",
    gap_judgment: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    # lazy import avoids circular deps
    import kb_gap_llm
    import service_routing

    parsed = (analysis or {}).get("parsed") or {}
    sk = (service_key or parsed.get("service_key") or "other").strip().lower()
    target = target_for_contour(sk)
    dedup = dedup or {}
    mode = str((gap_judgment or {}).get("mode") or dedup.get("mode") or "new")
    if mode == "update_in_place":
        mode = "supplement" if dedup.get("match_kind", "").endswith("supplement") else "new"
    if mode not in {"new", "supplement", "skip"}:
        mode = "new"
    base_code = str(dedup.get("code") or dedup.get("supplement_of") or "").upper()
    if mode == "supplement" and not base_code and dedup.get("supplement_of"):
        base_code = str(dedup.get("supplement_of")).upper()
    task_id = task.get("Id")
    name = kb_gap_llm.strip_emails((task.get("Name") or f"Заявка {task_id}").strip())
    category = (parsed.get("category") or "OTHER").strip()
    facts = kb_gap_llm.sanitize_facts(parsed.get("facts") or [])
    summary = kb_gap_llm.strip_emails(str(parsed.get("summary_ru") or name))
    service_check = (analysis or {}).get("service_check") or {}
    adm = (analysis or {}).get("adm") or {}

    # ВСЕГДА contour mapping — не pageId из matched draft (корень 124630073 и т.п.)
    page_id = str(target.get("page_id") or target.get("fallback_page_id") or "").strip()
    page_title = str(target.get("title") or "Confluence WEBKB")
    matched_title = str(dedup.get("title") or "").strip()
    if mode == "supplement" and (matched_title or base_code):
        display_title = matched_title or base_code
    else:
        display_title = page_title
    confluence_url = confluence_view_url(page_id) or confluence_view_url(
        str(load_kb_pages().get("chatbot_root_page_id") or "")
    )

    gap = dict(gap_judgment or {})
    if not gap.get("target_page_id"):
        gap["target_page_id"] = page_id
    if not gap.get("target_url"):
        gap["target_url"] = confluence_url
    if not gap.get("target_title"):
        gap["target_title"] = display_title if mode == "supplement" else page_title
    if not gap.get("source_ticket_id"):
        gap["source_ticket_id"] = str(task_id or "")
    if not gap.get("mode"):
        gap["mode"] = mode

    if mode == "supplement" and base_code:
        code = code or f"{base_code}-SUP-{task_id}"
    else:
        code = code or next_code_prefix(sk, task.get("Id"))

    formulations: list[str] = []
    low_name = name.lower()
    if "api" in low_name or "ключ" in low_name:
        formulations.extend(["доступ к api", "api ключ", "где взять api ключ"])
    formulations.append(name[:80])

    if mode == "supplement":
        head = f"# Дополнение: {code} — к {base_code or 'существующей статье'}"
    else:
        head = f"# Черновик: {code} — {name}"

    hd_url = str(task.get("url") or "").strip()

    # words: LLM → иначе resolution (sanitized)
    words = str(gap.get("words_to_add") or "").strip()
    resolution = kb_gap_llm.strip_emails((resolution_text or "").strip())
    import kb_insert_builder
    import kb_article_compose

    resolution = kb_insert_builder.sanitize_resolution_for_kb(resolution)
    if not words:
        if not resolution:
            resolution = kb_insert_builder.sanitize_resolution_for_kb(
                kb_gap_llm.strip_emails(pick_resolution_text(task, [], analysis))
            )
        blob = f"{task.get('Name') or ''}\n{task.get('Description') or ''}".lower()
        if "api" in blob or "ключ" in blob:
            hint = service_routing.api_key_hint(sk)
            if hint and hint not in resolution:
                resolution = f"{hint}\n\n{resolution}".strip()
            if sk == "bp" and service_check.get("contour_hd") == "lk":
                resolution = (
                    "Клиент часто путает lk.iek.ru (ЛК партнёра) и bp.iek.ru (БП/API). "
                    "Ключ API товаров — на bp, не в ЛК.\n\n" + resolution
                )
        words = resolution
        gap["words_to_add"] = words

    lesson = ""
    if (learn_compare_md or "").strip():
        m = re.search(r"\*\*Урок для KB:\*\*\s*(.+)", learn_compare_md)
        if m:
            lesson = m.group(1).strip()

    composed = kb_article_compose.compose_kb_article(
        code=code,
        task_id=str(task_id),
        task_name=name,
        category=category,
        facts=facts,
        resolution=resolution or words,
        supplement_of=base_code if mode == "supplement" else "",
        learn_lesson=lesson,
        helpdesk_url=hd_url,
    )
    words = kb_article_compose.markdown_to_kb_insert(composed.get("markdown") or "")
    words = kb_insert_builder.sanitize_kb_insert_for_promote(words)
    if kb_insert_builder.is_weak_kb_insert(words):
        words = kb_insert_builder.build_structured_insert(
            summary=summary,
            category=category,
            facts=facts,
            supplement_of=base_code if mode == "supplement" else "",
            resolution=resolution,
            learn_lesson=lesson,
            code=code,
        )
    gap["words_to_add"] = words
    gap["compose_fallback"] = composed.get("fallback")
    if composed.get("model"):
        gap["compose_model"] = composed.get("model")

    judgment_md = kb_gap_llm.format_judgment_markdown(
        gap, helpdesk_url=hd_url, matched_code=base_code if mode == "supplement" else ""
    )

    body: list[str] = [
        head,
        "",
        judgment_md.rstrip(),
        "",
        "## Контекст заявки (без PII email)",
        "",
        f"**Контур:** {sk} · **Категория:** {category}",
        f"**Dedup:** {dedup.get('reason') or mode}"
        + (f" · match_kind={dedup.get('match_kind')}" if dedup.get("match_kind") else ""),
        f"**Создан:** {_now_iso()}",
        "",
        "**Проблема / факты:**",
        "",
    ]
    if facts:
        for f in facts[:4]:
            body.append(f"- {f}")
    else:
        body.append(f"- {summary}")
    body.append("")

    if adm.get("found") is True:
        match = (adm.get("matches") or [{}])[0]
        bits = ["adm: найден"]
        if match.get("accountType"):
            bits.append(str(match["accountType"]))
        body.append(f"**Проверка adm:** {' · '.join(bits)}.")
        body.append("")

    if service_check.get("note") and not service_check.get("service_ok"):
        # без сырого ServiceId в шаблоне — только note
        note = kb_gap_llm.strip_emails(str(service_check.get("note") or ""))
        if note:
            body.append(f"**Сервис HD:** {note}")
            body.append("")

    body.append(f"**Варианты формулировок:** {'; '.join(dict.fromkeys(formulations))}.")
    body.append("")
    if mode == "supplement":
        body.append(
            f"**Публикация:** ревью → Promote → append только блок KB_INSERT "
            f"к `{base_code}` на pageId={page_id} (не silent-edit published)."
        )
    else:
        body.append(
            f"**Публикация:** ревью → Promote → append KB_INSERT на pageId={page_id}."
        )
    body.append("")
    body.append(
        f"_Автогенерация kb_learning из заявки #{task_id}. Режим: {mode}. Статус: draft._"
    )
    if (learn_compare_md or "").strip():
        body.append("")
        body.append(learn_compare_md.strip())

    text = "\n".join(body)
    meta = {
        "task_id": task_id,
        "code": code,
        "service_key": sk,
        "target_page_id": page_id,
        "target_title": page_title,
        "category": category,
        "mode": mode,
        "supplement_of": base_code if mode == "supplement" else "",
        "match_score": dedup.get("score"),
        "match_source": dedup.get("source"),
        "match_title": dedup.get("title"),
        "match_kind": dedup.get("match_kind"),
        "dedup_action": dedup.get("action"),
        "dedup_reason": dedup.get("reason"),
        "gap_judgment": {
            "mode": gap.get("mode"),
            "incomplete": gap.get("incomplete"),
            "why_incomplete": gap.get("why_incomplete"),
            "fallback": gap.get("fallback"),
        },
    }
    return text, meta


def merge_into_existing_draft(
    existing_md: str,
    *,
    task: dict[str, Any],
    gap_judgment: dict[str, Any],
    dedup: dict[str, Any] | None = None,
) -> str:
    """Дописать insert + источник в существующий in_review/draft (без нового файла)."""
    import kb_gap_llm

    tid = str(task.get("Id") or gap_judgment.get("source_ticket_id") or "")
    url = str(task.get("url") or "").strip()
    why = kb_gap_llm.strip_emails(str(gap_judgment.get("why_incomplete") or ""))
    words = kb_gap_llm.strip_emails(str(gap_judgment.get("words_to_add") or ""))
    mode = str(gap_judgment.get("mode") or "supplement")
    note = (
        f"\n\n---\n\n## Дополнение из HD#{tid}\n"
        f"- Источник: {f'[{url}]({url})' if url else f'HD#{tid}'}\n"
        f"- Вердикт LLM: {mode}"
        + (" · статья неполная" if gap_judgment.get("incomplete") else "")
        + "\n"
        f"- Почему: {why or '—'}\n"
        f"- Dedup: {(dedup or {}).get('reason') or 'update_in_place'}\n"
        f"- Создано: {_now_iso()}\n"
    )
    if words and words.strip() and words.strip() != "_(пусто)_":
        note += f"- Фрагмент из закрытия (добавьте в KB_INSERT вручную при необходимости):\n\n{words.strip()[:1200]}\n"
    md = (existing_md or "").rstrip()
    # обновить/вставить шапку «Решение IEK LLM» если её ещё нет
    if "## Решение IEK LLM" not in md:
        judgment = kb_gap_llm.format_judgment_markdown(
            gap_judgment,
            helpdesk_url=url,
            matched_code=str((dedup or {}).get("code") or ""),
        )
        # после первого # заголовка
        m = re.search(r"^#\s+.+$", md, re.M)
        if m:
            pos = m.end()
            md = md[:pos] + "\n\n" + judgment + md[pos:]
        else:
            md = judgment + "\n\n" + md
    return md + note


def register_merged_into(
    task_id: str | int,
    *,
    target_entry: dict[str, Any],
    gap: dict[str, Any] | None = None,
    dedup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Запись текущего task как merged_into чужого in_review черновика."""
    index = load_index()
    entries: list[dict[str, Any]] = list(index.get("entries") or [])
    tid = str(task_id).strip()
    row = {
        "task_id": tid,
        "code": target_entry.get("code"),
        "service_key": target_entry.get("service_key"),
        "target_page_id": target_entry.get("target_page_id"),
        "draft_path": target_entry.get("draft_path"),
        "status": "merged_into",
        "created_at": _now_iso(),
        "gap_reason": (gap or {}).get("reason"),
        "helpdesk_url": (dedup or {}).get("helpdesk_url"),
        "mode": "update_in_place",
        "merged_into_task_id": str(target_entry.get("task_id") or ""),
        "merged_into_code": str(target_entry.get("code") or ""),
        "match_score": (dedup or {}).get("score"),
        "match_source": (dedup or {}).get("source"),
        "match_kind": (dedup or {}).get("match_kind"),
        "dedup_reason": (dedup or {}).get("reason"),
        "confluence_draft_page_id": target_entry.get("confluence_draft_page_id"),
        "confluence_draft_url": target_entry.get("confluence_draft_url"),
    }
    entries = [e for e in entries if str(e.get("task_id")) != tid]
    entries.append(row)
    index["entries"] = entries
    save_index(index)
    return row


def reject_draft(
    task_id: str | int,
    *,
    reason: str = "",
    archive_confluence: bool = True,
) -> dict[str, Any]:
    """Отклонить черновик AI-KB (не Promote)."""
    tid = str(task_id).strip()
    index = load_index()
    entry: dict[str, Any] | None = None
    for row in index.get("entries") or []:
        if str(row.get("task_id")) == tid:
            entry = row
            break
    if not entry:
        return {"ok": False, "error": f"черновик для #{tid} не найден в index"}

    st = str(entry.get("status") or "").lower()
    if st == "published":
        return {"ok": False, "error": "уже опубликован — отклонение через новый review"}

    entry["status"] = "rejected"
    entry["rejected_at"] = _now_iso()
    entry["rejection_reason"] = (reason or "отклонено на ревью")[:500]
    save_index(index)

    archive: dict[str, Any] | None = None
    if archive_confluence:
        rid = str(entry.get("confluence_draft_page_id") or "").strip()
        if rid:
            try:
                import confluence_client as cf

                s = cf.session()
                page = cf.get_page(s, rid, expand="version,title,body.storage")
                old_title = str(page.get("title") or "")
                new_title = old_title
                if not old_title.upper().startswith("[ОТКЛОНЕНО]"):
                    new_title = f"[ОТКЛОНЕНО] {old_title}"[:255]
                body = ((page.get("body") or {}).get("storage") or {}).get("value") or ""
                note = (
                    '<ac:structured-macro ac:name="warning"><ac:rich-text-body>'
                    f"<p><strong>Отклонено</strong> на ревью AI-KB."
                    f"{(' Причина: ' + reason) if reason else ''}"
                    " Не будет опубликовано в «Быстрые ответы».</p>"
                    "</ac:rich-text-body></ac:structured-macro>\n"
                )
                cf.update_page(
                    s,
                    rid,
                    title=new_title,
                    storage=note + body,
                    message=f"AI-KB rejected {entry.get('code')}",
                )
                try:
                    cf.remove_label(s, rid, "ai-kb-draft")
                except Exception:
                    pass
                try:
                    cf.add_labels(s, rid, ["ai-kb-rejected"])
                except Exception:
                    pass
                archive = {"ok": True, "page_id": rid, "title": new_title}
            except Exception as exc:
                archive = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return {
        "ok": True,
        "task_id": tid,
        "code": entry.get("code"),
        "status": "rejected",
        "confluence": archive,
    }


def touch_index_entry(task_id: str | int, **fields: Any) -> dict[str, Any] | None:
    index = load_index()
    tid = str(task_id).strip()
    for row in index.get("entries") or []:
        if str(row.get("task_id")) == tid:
            row.update({k: v for k, v in fields.items() if v is not None})
            row["updated_at"] = _now_iso()
            save_index(index)
            return row
    return None


def find_index_entry(task_id: str = "", *, draft_path: str = "", code: str = "") -> dict[str, Any] | None:
    index = load_index()
    for row in index.get("entries") or []:
        if task_id and str(row.get("task_id")) == str(task_id):
            return row
        if draft_path and str(row.get("draft_path") or "").replace("\\", "/") == draft_path.replace("\\", "/"):
            return row
        if code and str(row.get("code") or "").upper() == code.upper() and not task_id:
            return row
    return None


def save_draft(
    task_id: str | int,
    content: str,
    meta: dict[str, Any],
) -> Path:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    code = meta.get("code") or "HD-00"
    mode = str(meta.get("mode") or "new")
    if mode == "supplement" and meta.get("supplement_of"):
        slug = f"sup_{_slug(str(meta.get('supplement_of')))}"
    else:
        slug = _slug(meta.get("category") or meta.get("service_key") or str(task_id))
    fname = f"{str(code).lower().replace('+', 'plus')}_{slug}_hd{task_id}.md"
    # безопасное имя файла
    fname = re.sub(r"[^\w.\-]+", "_", fname, flags=re.UNICODE)
    path = DRAFTS_DIR / fname
    path.write_text(content, encoding="utf-8")
    return path


def register_draft(
    task_id: str | int,
    draft_path: Path,
    meta: dict[str, Any],
    *,
    status: str = "draft",
    gap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    index = load_index()
    entries: list[dict[str, Any]] = list(index.get("entries") or [])
    tid = str(task_id).strip()
    row = {
        "task_id": tid,
        "code": meta.get("code"),
        "service_key": meta.get("service_key"),
        "target_page_id": meta.get("target_page_id"),
        "draft_path": str(draft_path.relative_to(PKG)).replace("\\", "/"),
        "status": status,
        "created_at": _now_iso(),
        "gap_reason": (gap or {}).get("reason"),
        "helpdesk_url": meta.get("helpdesk_url"),
        "mode": meta.get("mode") or "new",
        "supplement_of": meta.get("supplement_of") or "",
        "match_score": meta.get("match_score"),
        "match_source": meta.get("match_source"),
        "match_kind": meta.get("match_kind"),
        "dedup_reason": meta.get("dedup_reason"),
    }
    entries = [e for e in entries if str(e.get("task_id")) != tid]
    entries.append(row)
    index["entries"] = entries
    save_index(index)
    return row


def format_learn_note(
    *,
    code: str,
    task_id: str | int,
    draft_path: str = "",
    target_page_id: str | None = None,
    target_title: str = "",
    review_page_id: str | None = None,
    review_page_url: str = "",
    updated_in_place: bool = False,
) -> str:
    """Краткая скрытая запись: создан черновик обучающей статьи + ссылка."""
    if updated_in_place:
        lines = [
            f"AI-KB: заявка #{task_id} дополняет существующий черновик {code or '—'} (правка на месте, без нового -SUP-).",
        ]
    else:
        lines = [
            f"AI-KB: на основе заявки #{task_id} создан черновик обучающей статьи {code or '—'}.",
        ]
    review_url = (review_page_url or "").strip() or confluence_view_url(review_page_id)
    if review_url:
        lines.append(f"Confluence (черновик на ревью, править здесь): {review_url}")
    target_url = confluence_view_url(target_page_id)
    if target_url:
        title = f" ({target_title})" if target_title else ""
        lines.append(f"После ревью попадёт в «Быстрые ответы»{title}: {target_url}")
    elif not review_url:
        lines.append(
            "Confluence: страница ревью создаётся при auto_push_confluence_draft "
            "(см. docs/confluence/kb_assistant_pages.json → ai_kb_review)."
        )
    if draft_path:
        rel = draft_path
        try:
            rel = str(Path(draft_path).resolve().relative_to(PKG)).replace("\\", "/")
        except Exception:
            pass
        lines.append(f"Локальная копия: {rel}")
    lines.append("После ревью: python scripts/sync_kb_after_review.py --task-id " + str(task_id))
    return "\n".join(lines)


def post_learn_note(
    task_id: str | int,
    *,
    code: str,
    draft_path: str = "",
    target_page_id: str | None = None,
    target_title: str = "",
    review_page_id: str | None = None,
    review_page_url: str = "",
) -> dict[str, Any]:
    import intraservice

    text = format_learn_note(
        code=code,
        task_id=task_id,
        draft_path=draft_path,
        target_page_id=target_page_id,
        target_title=target_title,
        review_page_id=review_page_id,
        review_page_url=review_page_url,
    )
    result = intraservice.add_private_comment(str(task_id), text)
    result["note_preview"] = text
    return result


def push_draft_to_confluence_review(
    task_id: str | int,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Создать/обновить видимую страницу [ЧЕРНОВИК] в папке ревью Confluence."""
    cmd = [
        sys.executable,
        str(PKG / "scripts" / "push_kb_draft_confluence_review.py"),
        "--task-id",
        str(task_id),
    ]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(
        cmd,
        cwd=str(PKG),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )  # noqa: S603 — локальный скрипт пакета
    raw = (proc.stdout or "").strip()
    try:
        data = json.loads(raw) if raw.startswith("{") else {"raw": raw}
    except json.JSONDecodeError:
        data = {"raw": raw[-1500:]}
    data["returncode"] = proc.returncode
    data["ok"] = proc.returncode == 0 and bool(data.get("ok", True))
    if proc.stderr:
        data["stderr"] = proc.stderr[-500:]
    # достать url из pushed[0]
    pushed = data.get("pushed") or []
    if pushed and isinstance(pushed[0], dict):
        data["page_id"] = pushed[0].get("page_id")
        data["url"] = pushed[0].get("url")
    return data


def _run_gap_judgment(
    task: dict[str, Any],
    analysis: dict[str, Any] | None,
    *,
    resolution: str,
    dedup_info: dict[str, Any],
    service_key: str,
) -> dict[str, Any]:
    import kb_gap_llm

    target = target_for_contour(service_key)
    page_id = str(target.get("page_id") or target.get("fallback_page_id") or "")
    page_url = confluence_view_url(page_id)
    parsed = (analysis or {}).get("parsed") or {}
    matched_excerpt = ""
    matched_title = str(dedup_info.get("title") or "")
    matched_code = str(dedup_info.get("code") or "")
    path = str(dedup_info.get("path") or "")
    if path:
        p = PKG / path
        if p.is_file():
            matched_excerpt = p.read_text(encoding="utf-8", errors="replace")[:3500]
    confluence_search: dict[str, Any] | None = None
    if not matched_excerpt or len(matched_excerpt) < 80:
        confluence_search = _confluence_excerpt_for_learning(
            task, analysis, resolution=resolution, service_key=service_key
        )
        if confluence_search.get("ok") and confluence_search.get("excerpt"):
            matched_excerpt = str(confluence_search.get("excerpt") or "")[:3500]
            if not matched_title:
                matched_title = str(confluence_search.get("title") or "")
            if not matched_code and confluence_search.get("title"):
                matched_code = str(confluence_search.get("title") or "")[:40]
    mode_hint = str(dedup_info.get("mode") or "new")
    if mode_hint == "update_in_place":
        mode_hint = "supplement"
    import kb_dedup
    import learn_llm

    parsed = (analysis or {}).get("parsed") or {}
    sk_key = str(parsed.get("service_key") or service_key or "other")
    q = kb_dedup.query_blob(task, analysis, resolution=resolution)
    rej_ctx = learn_llm.rejection_context(
        q,
        service_key=sk_key,
        task_id=str(task.get("Id") or ""),
    )
    verdict = kb_gap_llm.judge_kb_gap(
        task_id=str(task.get("Id") or ""),
        task_name=str(task.get("Name") or ""),
        summary_ru=str(parsed.get("summary_ru") or ""),
        resolution=resolution,
        facts=list(parsed.get("facts") or []),
        matched_title=matched_title,
        matched_code=matched_code,
        matched_excerpt=matched_excerpt,
        mode_hint=mode_hint,
        target_title=str(target.get("title") or ""),
        target_page_id=page_id,
        target_url=page_url,
        rejection_context=rej_ctx,
    )
    if confluence_search:
        verdict["confluence_search"] = {
            "query": confluence_search.get("query"),
            "hit_id": confluence_search.get("page_id"),
            "hit_title": confluence_search.get("title"),
            "hit_url": confluence_search.get("url"),
        }
    return verdict


def _confluence_excerpt_for_learning(
    task: dict[str, Any],
    analysis: dict[str, Any] | None,
    *,
    resolution: str = "",
    service_key: str = "",
) -> dict[str, Any]:
    """CQL WEBKB (+ LK для контуров ЛК) — фрагмент статьи для сравнения с заявкой."""
    import confluence_client as cf

    parsed = (analysis or {}).get("parsed") or {}
    bits = [
        str(task.get("Name") or ""),
        str(parsed.get("summary_ru") or ""),
        str(resolution or "")[:160],
    ]
    query = " ".join(b.strip() for b in bits if b and b.strip())[:140]
    if not query:
        return {"ok": False, "reason": "пустой запрос"}
    sk = str(service_key or parsed.get("service_key") or "").lower()
    spaces = ["WEBKB", "LK"] if sk == "lk" else ["WEBKB"]
    queries = [query]
    blob = f"{query} {resolution}".lower()
    if "трекинг" in blob or "tracking" in blob:
        queries.extend(["api/v2/tracking orders", "API каталога tracking"])
    seen: set[str] = set()
    for q in queries:
        q = q.strip()
        if not q or q in seen:
            continue
        seen.add(q)
        sr = cf.search_pages(q, spaces=spaces, limit=5)
        if not sr.get("ok") or not sr.get("hits"):
            continue
        for hit in sr["hits"]:
            title = str(hit.get("title") or "")
            if title.upper().startswith("[ОТКЛОНЕНО]") or "ЧЕРНОВИК" in title.upper():
                continue
            pid = str(hit.get("id") or "")
            excerpt = str(hit.get("excerpt") or "")
            if pid and len(excerpt) < 120:
                try:
                    s = cf.session()
                    page = cf.get_page(s, pid, expand="body.view")
                    body = ((page.get("body") or {}).get("view") or {}).get("value") or ""
                    if body:
                        excerpt = cf._plain_excerpt(body, max_len=1200)  # type: ignore[attr-defined]
                except Exception:
                    pass
            if excerpt:
                return {
                    "ok": True,
                    "query": q,
                    "page_id": pid,
                    "title": title,
                    "url": hit.get("url"),
                    "excerpt": excerpt,
                    "cql": sr.get("cql"),
                    "spaces": spaces,
                }
    return {
        "ok": False,
        "reason": "нет hits",
        "query": query,
        "spaces": spaces,
    }


def learn_from_task_data(
    task: dict[str, Any],
    analysis: dict[str, Any] | None,
    *,
    lifetime: dict[str, Any] | None = None,
    force: bool = False,
    require_closed: bool = False,
    resolution_override: str = "",
    trigger: str = "manual",
    post_note: bool | None = None,
) -> dict[str, Any]:
    tid = task.get("Id")

    def _finish(out: dict[str, Any]) -> dict[str, Any]:
        try:
            import learn_journal

            learn_journal.record_from_learn_result(tid or "", out)
        except Exception:
            pass
        return out

    from settings import load_settings

    settings = load_settings()
    tr = "watch_close" if require_closed else trigger
    decision = should_auto_learn(
        task, analysis, trigger=tr, force=force, settings=settings
    )
    if not decision.get("run"):
        return _finish({
            "ok": False,
            "skipped": True,
            "reason": decision.get("reason"),
            "auto_learn_decision": decision,
        })

    comments = extract_lifetime_comments(lifetime)
    resolution = resolution_override or pick_resolution_text(
        task, comments, analysis, lifetime=lifetime
    )

    # «Учить только закрытые (watch)»: помимо статуса 28/29 требуем, чтобы было
    # реальное решение исполнителя в публичном ответе, а не fallback на summary/название.
    if (
        require_closed
        and settings.get("require_closed_for_auto_learn", True)
        and not resolution_override
        and not performer_resolution_present(task, lifetime)
    ):
        return _finish({
            "ok": False,
            "skipped": True,
            "reason": "нет решения исполнителя в публичном ответе (require_closed_for_auto_learn)",
            "auto_learn_decision": decision,
        })

    import learn_compare

    cmp = learn_compare.learn_compare_block(task, analysis, lifetime)
    compare_md = learn_compare.format_compare_markdown(cmp)

    import kb_dedup

    dedup_match = kb_dedup.resolve_learn_mode(
        task, analysis, resolution=resolution, settings=settings, force=force
    )
    dedup_info = dedup_match.as_dict()

    if dedup_match.mode == "duplicate" or dedup_match.action == "skip":
        return _finish({
            "ok": False,
            "skipped": True,
            "reason": dedup_match.reason,
            "mode": "duplicate",
            "dedup": dedup_info,
            "auto_learn_decision": decision,
            "supplement_of": dedup_info.get("code"),
            "learn_compare": cmp,
        })

    sk = ((analysis or {}).get("parsed") or {}).get("service_key") or "other"
    gap_j = _run_gap_judgment(
        task, analysis, resolution=resolution, dedup_info=dedup_info, service_key=sk
    )
    if gap_j.get("mode") == "skip" and not force:
        return _finish({
            "ok": False,
            "skipped": True,
            "reason": gap_j.get("why_incomplete") or "LLM: skip — статья достаточна",
            "mode": "skip",
            "dedup": dedup_info,
            "gap_judgment": gap_j,
            "auto_learn_decision": decision,
            "learn_compare": cmp,
        })

    # --- in-place update существующего in_review/draft ---
    if dedup_match.action == "update_in_place" and dedup_match.unit:
        target_tid = str(dedup_match.unit.task_id or "")
        target_entry = find_index_entry(target_tid) if target_tid else None
        if not target_entry and dedup_info.get("path"):
            target_entry = find_index_entry(draft_path=str(dedup_info["path"]))
        draft_rel = str(
            (target_entry or {}).get("draft_path") or dedup_info.get("path") or ""
        )
        draft_path = PKG / draft_rel if draft_rel else None
        if not draft_path or not draft_path.is_file():
            # fallback: создать новый review (не ломаем пайплайн)
            pass
        else:
            old_md = draft_path.read_text(encoding="utf-8")
            # поправить target_page_id у существующей записи на contour
            # контур publish — из текущей заявки (lk/bp), не из старого «other» у HD-09
            contour_target = target_for_contour(str(sk or (target_entry or {}).get("service_key") or "other"))

            fixed_page = str(
                contour_target.get("page_id") or contour_target.get("fallback_page_id") or ""
            )
            new_md = merge_into_existing_draft(
                old_md, task=task, gap_judgment=gap_j, dedup=dedup_info
            )
            # optional note inside draft about unpublished base
            kind = str(dedup_info.get("match_kind") or "")
            if kind.endswith("_new") and "дополнение к неопубликованной" not in new_md.lower():
                code_base = str((target_entry or {}).get("code") or dedup_info.get("code") or "")
                new_md = (
                    new_md
                    + f"\n\n_Примечание LLM: дополнение к неопубликованной статье `{code_base}` "
                    f"(status=in_review) — правка того же черновика._\n"
                )
            draft_path.write_text(new_md, encoding="utf-8")
            if target_entry and fixed_page:
                touch_index_entry(
                    target_tid,
                    target_page_id=fixed_page,
                    target_title=contour_target.get("title"),
                )
                target_entry = find_index_entry(target_tid) or target_entry

            review_page_id: str | None = str(
                (target_entry or {}).get("confluence_draft_page_id") or ""
            ) or None
            review_page_url = str((target_entry or {}).get("confluence_draft_url") or "")
            confluence_push: dict[str, Any] | None = None
            push_tid = target_tid or tid
            if settings.get("auto_push_confluence_draft", True) and push_tid:
                try:
                    confluence_push = push_draft_to_confluence_review(push_tid)
                    if confluence_push.get("ok"):
                        review_page_id = str(confluence_push.get("page_id") or review_page_id or "") or None
                        review_page_url = str(confluence_push.get("url") or review_page_url)
                        refreshed = draft_exists_for_task(push_tid)
                        if refreshed:
                            target_entry = refreshed
                            review_page_id = (
                                str(refreshed.get("confluence_draft_page_id") or review_page_id or "")
                                or None
                            )
                            review_page_url = str(
                                refreshed.get("confluence_draft_url") or review_page_url
                            )
                except Exception as exc:
                    confluence_push = {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                    }

            merged_row = register_merged_into(
                tid or "",
                target_entry=target_entry or {"task_id": target_tid, "code": dedup_info.get("code"), "draft_path": draft_rel},
                gap=assess_kb_gap(analysis),
                dedup={**dedup_info, "helpdesk_url": task.get("url")},
            )
            code = str((target_entry or {}).get("code") or dedup_info.get("code") or "")
            note_preview = format_learn_note(
                code=code,
                task_id=tid or "",
                draft_path=str(draft_path),
                target_page_id=fixed_page or (target_entry or {}).get("target_page_id"),
                target_title=str(contour_target.get("title") or ""),
                review_page_id=review_page_id,
                review_page_url=review_page_url,
                updated_in_place=True,
            )
            result: dict[str, Any] = {
                "ok": True,
                "updated_in_place": True,
                "task_id": tid,
                "merged_into_task_id": target_tid,
                "draft_path": str(draft_path),
                "code": code,
                "mode": "update_in_place",
                "supplement_of": (target_entry or {}).get("supplement_of")
                or dedup_info.get("supplement_of")
                or "",
                "dedup": dedup_info,
                "gap_judgment": gap_j,
                "target_page_id": fixed_page or (target_entry or {}).get("target_page_id"),
                "target_title": contour_target.get("title"),
                "confluence_draft_page_id": review_page_id,
                "confluence_draft_url": review_page_url,
                "confluence_push": confluence_push,
                "index": merged_row,
                "auto_learn_decision": decision,
                "resolution_preview": (gap_j.get("words_to_add") or resolution)[:400],
                "note_preview": note_preview,
                "learn_compare": cmp,
            }
            do_post = settings.get("post_learn_note", True) if post_note is None else bool(post_note)
            if do_post:
                try:
                    import intraservice

                    posted = intraservice.add_private_comment(str(tid or ""), note_preview)
                    posted["note_preview"] = note_preview
                    result["learn_note_post"] = posted
                except Exception as exc:
                    result["learn_note_post"] = {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                    }
            else:
                result["learn_note_post"] = {"ok": False, "skipped": True, "reason": "post_note=false"}
            return _finish(result)

    # --- создать новый review-черновик (corpus/published/new) ---
    content, meta = build_draft_markdown(
        task,
        analysis,
        resolution_text=resolution,
        service_key=sk,
        dedup=dedup_info,
        learn_compare_md=compare_md,
        gap_judgment=gap_j,
    )
    meta["helpdesk_url"] = task.get("url")
    draft_path = save_draft(tid, content, meta)
    gap = assess_kb_gap(analysis)
    index_row = register_draft(tid, draft_path, meta, gap=gap)

    review_page_id = None
    review_page_url = ""
    confluence_push = None
    if settings.get("auto_push_confluence_draft", True):
        try:
            confluence_push = push_draft_to_confluence_review(tid or "")
            if confluence_push.get("ok"):
                review_page_id = str(confluence_push.get("page_id") or "") or None
                review_page_url = str(confluence_push.get("url") or "")
                refreshed = draft_exists_for_task(tid or "")
                if refreshed:
                    index_row = refreshed
                    review_page_id = str(refreshed.get("confluence_draft_page_id") or review_page_id or "") or None
                    review_page_url = str(refreshed.get("confluence_draft_url") or review_page_url)
        except Exception as exc:
            confluence_push = {
                "ok": False,
                "error": f"{type(exc).__name__}: {str(exc)[:240]}",
            }

    note_preview = format_learn_note(
        code=str(meta.get("code") or ""),
        task_id=tid or "",
        draft_path=str(draft_path),
        target_page_id=meta.get("target_page_id"),
        target_title=str(meta.get("target_title") or ""),
        review_page_id=review_page_id,
        review_page_url=review_page_url,
    )
    if meta.get("mode") == "supplement" and meta.get("supplement_of"):
        note_preview = (
            note_preview
            + f"\nРежим: дополнение к {meta.get('supplement_of')} "
            f"(score={meta.get('match_score')}) — не новый быстрый ответ."
        )

    result = {
        "ok": True,
        "task_id": tid,
        "draft_path": str(draft_path),
        "code": meta.get("code"),
        "mode": meta.get("mode") or "new",
        "supplement_of": meta.get("supplement_of") or "",
        "dedup": dedup_info,
        "gap_judgment": gap_j,
        "target_page_id": meta.get("target_page_id"),
        "target_title": meta.get("target_title"),
        "confluence_draft_page_id": review_page_id,
        "confluence_draft_url": review_page_url,
        "confluence_push": confluence_push,
        "index": index_row,
        "auto_learn_decision": decision,
        "resolution_preview": (gap_j.get("words_to_add") or resolution)[:400],
        "note_preview": note_preview,
        "learn_compare": cmp,
    }

    do_post = settings.get("post_learn_note", True) if post_note is None else bool(post_note)
    if do_post:
        try:
            import intraservice

            posted = intraservice.add_private_comment(str(tid or ""), note_preview)
            posted["note_preview"] = note_preview
            result["learn_note_post"] = posted
        except Exception as exc:
            result["learn_note_post"] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {str(exc)[:240]}",
            }
    else:
        result["learn_note_post"] = {"ok": False, "skipped": True, "reason": "post_note=false"}

    return _finish(result)


def dedup_from_index_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Восстановить dedup_info из строки index.json (без повторного kb_dedup)."""
    mode = str(entry.get("mode") or "new").strip().lower()
    if mode not in {"new", "supplement", "skip"}:
        mode = "new"
    base = str(entry.get("supplement_of") or "").strip().upper()
    code = str(entry.get("code") or "").strip().upper()
    dedup_code = base if mode == "supplement" and base else code
    return {
        "mode": mode,
        "reason": str(entry.get("dedup_reason") or entry.get("gap_reason") or ""),
        "code": dedup_code,
        "supplement_of": base,
        "title": str(entry.get("target_title") or entry.get("match_title") or ""),
        "path": str(entry.get("draft_path") or ""),
        "source": str(entry.get("match_source") or ""),
        "score": entry.get("match_score"),
        "match_kind": str(entry.get("match_kind") or ""),
        "action": "supplement" if mode == "supplement" else "new",
    }


def gap_judgment_from_entry(
    entry: dict[str, Any],
    *,
    service_key: str,
) -> dict[str, Any]:
    """Минимальный gap_judgment из index — compose_kb_article сгенерирует KB_INSERT."""
    mode = str(entry.get("mode") or "new")
    page_id = str(entry.get("target_page_id") or "").strip()
    if not page_id:
        target = target_for_contour(service_key)
        page_id = str(target.get("page_id") or target.get("fallback_page_id") or "")
    title = str(entry.get("target_title") or "").strip()
    if not title and page_id:
        target = target_for_contour(service_key)
        title = str(target.get("title") or "")
    return {
        "mode": mode,
        "incomplete": mode == "supplement",
        "why_incomplete": str(entry.get("gap_reason") or entry.get("dedup_reason") or ""),
        "target_page_id": page_id,
        "target_url": confluence_view_url(page_id),
        "target_title": title,
        "source_ticket_id": str(entry.get("task_id") or ""),
        "words_to_add": "",
    }


def rebuild_review_draft(
    entry: dict[str, Any],
    *,
    push_confluence: bool = False,
    dry_run: bool = False,
    use_gap_llm: bool = False,
) -> dict[str, Any]:
    """Пересобрать локальный черновик по index entry (новый compose + шаблон KB_INSERT)."""
    tid = str(entry.get("task_id") or "").strip()
    if not tid:
        return {"ok": False, "error": "no task_id"}
    status = str(entry.get("status") or "")
    if status not in {"in_review", "draft"}:
        return {"ok": False, "skipped": True, "reason": f"status={status}", "task_id": tid}

    draft_rel = str(entry.get("draft_path") or "").strip()
    if not draft_rel:
        return {"ok": False, "error": "no draft_path", "task_id": tid}
    draft_path = PKG / draft_rel.replace("\\", "/")

    analysis = load_analysis(tid)
    if not analysis:
        return {"ok": False, "skipped": True, "reason": "нет _analysis_*", "task_id": tid}

    task: dict[str, Any] = {}
    lifetime = None
    try:
        import intraservice

        if intraservice.has_credentials():
            task = intraservice.get_task(tid) or {}
            try:
                lifetime = intraservice.get_task_lifetime(tid)
            except Exception:
                lifetime = None
    except Exception:
        pass
    if not task:
        task = dict((analysis or {}).get("task") or {})
    task = dict(task)
    if not task.get("Id"):
        task["Id"] = tid
    if not task.get("url") and entry.get("helpdesk_url"):
        task["url"] = entry["helpdesk_url"]

    comments = extract_lifetime_comments(lifetime)
    resolution = pick_resolution_text(task, comments, analysis, lifetime=lifetime)

    compare_md = ""
    try:
        import learn_compare

        cmp = learn_compare.learn_compare_block(task, analysis, lifetime)
        compare_md = learn_compare.format_compare_markdown(cmp)
    except Exception:
        pass

    sk = str(
        entry.get("service_key")
        or ((analysis.get("parsed") or {}).get("service_key"))
        or "other"
    ).strip().lower()
    dedup_info = dedup_from_index_entry(entry)
    code = str(entry.get("code") or "").strip().upper()

    if use_gap_llm:
        gap_j = _run_gap_judgment(
            task, analysis, resolution=resolution, dedup_info=dedup_info, service_key=sk
        )
        if entry.get("mode"):
            gap_j["mode"] = entry.get("mode")
    else:
        gap_j = gap_judgment_from_entry(entry, service_key=sk)

    content, meta = build_draft_markdown(
        task,
        analysis,
        resolution_text=resolution,
        service_key=sk,
        code=code,
        dedup=dedup_info,
        learn_compare_md=compare_md,
        gap_judgment=gap_j,
    )

    result: dict[str, Any] = {
        "ok": True,
        "task_id": tid,
        "code": meta.get("code"),
        "draft_path": str(draft_path),
        "dry_run": dry_run,
        "compose_fallback": (gap_j or {}).get("compose_fallback"),
        "compose_model": (gap_j or {}).get("compose_model"),
        "kb_insert_preview": (gap_j.get("words_to_add") or "")[:240],
    }

    if dry_run:
        result["preview_chars"] = len(content)
        return result

    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(content, encoding="utf-8")

    touch_index_entry(
        tid,
        updated_at=_now_iso(),
        target_page_id=meta.get("target_page_id"),
        target_title=meta.get("target_title"),
    )

    if push_confluence:
        try:
            push_res = push_draft_to_confluence_review(tid)
            result["confluence_push"] = push_res
            if push_res.get("ok"):
                touch_index_entry(
                    tid,
                    confluence_draft_page_id=push_res.get("page_id"),
                    confluence_draft_url=push_res.get("url"),
                    pushed_to_confluence_at=_now_iso(),
                )
        except Exception as exc:
            result["confluence_push"] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {str(exc)[:240]}",
            }

    return result


def rebuild_all_review_drafts(
    *,
    push_confluence: bool = False,
    dry_run: bool = False,
    use_gap_llm: bool = False,
    limit: int = 0,
    task_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Пакетная пересборка всех in_review/draft черновиков."""
    index = load_index()
    entries = list(index.get("entries") or [])
    targets = [e for e in entries if str(e.get("status")) in {"in_review", "draft"}]
    if task_ids:
        want = {str(t).strip() for t in task_ids}
        targets = [e for e in targets if str(e.get("task_id")) in want]
    if limit and limit > 0:
        targets = targets[:limit]
    results: list[dict[str, Any]] = []
    ok = fail = skip = 0
    for entry in targets:
        r = rebuild_review_draft(
            entry,
            push_confluence=push_confluence,
            dry_run=dry_run,
            use_gap_llm=use_gap_llm,
        )
        results.append(r)
        if r.get("skipped"):
            skip += 1
        elif r.get("ok"):
            ok += 1
        else:
            fail += 1
    return {
        "ok": fail == 0,
        "total": len(targets),
        "ok_count": ok,
        "fail_count": fail,
        "skip_count": skip,
        "dry_run": dry_run,
        "results": results,
    }

