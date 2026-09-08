# -*- coding: utf-8 -*-
"""Семантический дедуп AI-KB: corpus + черновики → new | supplement | duplicate.

Без внешних эмбеддингов: нормализация RU-текста + Jaccard по токенам/биграммам.
Пороги настраиваются (settings.semantic_*_threshold).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PKG = HERE.parent

CORPUS_PATHS = {
    "bp": PKG / "knowledge" / "bp" / "corpus.md",
    "lk": PKG / "knowledge" / "lk" / "corpus.md",
    "onec": PKG / "knowledge" / "1c" / "corpus.md",
    "1c": PKG / "knowledge" / "1c" / "corpus.md",
    "edi": PKG / "knowledge" / "1c" / "corpus.md",
    "crm": PKG / "knowledge" / "crm" / "corpus.md",
}
DRAFTS_DIR = PKG / "docs" / "черновики_статей"

_STOP = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все",
    "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по",
    "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из",
    "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже", "или",
    "ни", "быть", "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам",
    "ведь", "там", "потом", "себя", "ничего", "ей", "может", "они", "тут", "где",
    "есть", "надо", "ней", "для", "мы", "тебя", "их", "чем", "была", "сам",
    "чтоб", "без", "будто", "чего", "раз", "тоже", "себе", "под", "будет", "ж",
    "тогда", "кто", "этот", "того", "потому", "этого", "какой", "совсем", "ним",
    "здесь", "этом", "один", "почти", "мой", "тем", "чтобы", "нее", "сейчас",
    "были", "куда", "зачем", "сказать", "всех", "никогда", "сегодня", "можно",
    "при", "наконец", "два", "об", "другой", "хоть", "после", "над", "больше",
    "тот", "через", "эти", "нас", "про", "всего", "них", "какая", "много",
    "разве", "три", "эту", "моя", "впрочем", "хорошо", "свою", "этой", "перед",
    "иногда", "лучше", "чуть", "том", "нельзя", "такой", "им", "более", "всегда",
    "конечно", "всю", "между", "the", "and", "for", "with", "from", "this",
    "заявка", "заявки", "добрый", "день", "коллеги", "пожалуйста", "прошу",
    "проблема", "контекст", "быстрый", "ответ", "скопировать", "источник",
    "helpdesk", "черновик", "статус", "draft",
}

_CODE_HEAD = re.compile(
    r"^##\s+((?:BP|LK|HD|1C)-\d{2,3})\.\s*(.+)$",
    re.M | re.I,
)
_CODE_INLINE = re.compile(
    r"\b((?:BP|LK|HD|1C)-\d{2,3})\.\s+([^\n]{8,160})",
    re.I,
)
_DRAFT_TITLE = re.compile(
    r"^#\s+(?:Черновик|Дополнение):\s*((?:BP|LK|HD|1C)-[\w+-]+)\s*[—\-–:]?\s*(.+)$",
    re.M | re.I,
)
_WS = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w\s\-]+", re.UNICODE)
_PAGE_ID = re.compile(r"pageId=(\d+)", re.I)


@dataclass
class KbUnit:
    code: str
    title: str
    text: str
    source: str  # corpus:bp | draft | index:*
    page_id: str = ""
    path: str = ""
    task_id: str = ""
    match_kind: str = ""  # corpus | published | in_review_* | draft_* | none
    status: str = ""
    mode: str = ""  # new | supplement (из index)
    supplement_of: str = ""
    confluence_draft_page_id: str = ""
    tokens: frozenset[str] = field(default_factory=frozenset)


@dataclass
class DedupMatch:
    mode: str  # new | supplement | duplicate | update_in_place
    score: float
    unit: KbUnit | None = None
    reason: str = ""
    action: str = "create"  # create | update_in_place | skip
    match_kind: str = ""

    def as_dict(self) -> dict[str, Any]:
        u = self.unit
        kind = self.match_kind or (u.match_kind if u else "") or ""
        # page_id из matched draft часто мусор (корень 124630073) — не отдаём как target
        raw_page = (u.page_id if u else "") or ""
        publishable = kind in {"corpus", "published"}
        return {
            "mode": self.mode,
            "action": self.action,
            "match_kind": kind,
            "score": round(self.score, 4),
            "reason": self.reason,
            "code": (u.code if u else ""),
            "title": (u.title if u else ""),
            "source": (u.source if u else ""),
            # только для corpus/published; иначе пусто — target берёт contour mapping
            "page_id": raw_page if publishable else "",
            "matched_page_id": raw_page,
            "path": (u.path if u else ""),
            "task_id": (u.task_id if u else ""),
            "status": (u.status if u else ""),
            "unit_mode": (u.mode if u else ""),
            "supplement_of": (u.supplement_of if u else ""),
            "confluence_draft_page_id": (u.confluence_draft_page_id if u else ""),
        }


def normalize(text: str) -> str:
    t = (text or "").lower().replace("ё", "е")
    t = _NON_WORD.sub(" ", t)
    return _WS.sub(" ", t).strip()


def overlap_coef(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / float(min(len(a), len(b)))


def stem_tok(w: str) -> str:
    """Грубая стемминг-обрезка для RU (без pymorphy)."""
    if len(w) <= 5:
        return w
    for suf in ("иями", "ями", "ами", "ией", "ость", "ение", "ания", "ить", "ать", "ять", "ого", "ему", "ыми", "ими", "ой", "ый", "ий", "ая", "ое", "ые", "ие", "ам", "ом", "ем", "ах", "ях", "ов", "ев"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w[: max(5, len(w) - 2)]


def tokenize(text: str) -> frozenset[str]:
    words = [w for w in normalize(text).split() if len(w) > 2 and w not in _STOP]
    stems = [stem_tok(w) for w in words]
    toks: set[str] = set(words) | set(stems)
    for i in range(len(stems) - 1):
        toks.add(f"{stems[i]}_{stems[i + 1]}")
    return frozenset(toks)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / float(len(a | b))


def similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """Смесь Jaccard + overlap — лучше для короткого запроса vs длинной статьи."""
    j = jaccard(a, b)
    o = overlap_coef(a, b)
    return 0.4 * j + 0.6 * o


def query_blob(
    task: dict[str, Any],
    analysis: dict[str, Any] | None,
    *,
    resolution: str = "",
) -> str:
    parsed = (analysis or {}).get("parsed") or {}
    parts = [
        str(task.get("Name") or ""),
        str(parsed.get("summary_ru") or ""),
        str(parsed.get("category") or ""),
        " ".join(str(x) for x in (parsed.get("facts") or [])[:6]),
        resolution,
        str(task.get("Description") or "")[:800],
    ]
    return "\n".join(p for p in parts if p and str(p).strip())


def _page_from_text(text: str) -> str:
    m = _PAGE_ID.search(text or "")
    return m.group(1) if m else ""


def _units_from_markdown(md: str, *, source: str, default_page: str = "", path: str = "") -> list[KbUnit]:
    units: list[KbUnit] = []
    # ## CODE. Title blocks (lk corpus style)
    matches = list(_CODE_HEAD.finditer(md))
    if matches:
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
            block = md[start:end].strip()
            code = m.group(1).upper()
            title = m.group(2).strip()[:160]
            units.append(
                KbUnit(
                    code=code,
                    title=title,
                    text=block[:4000],
                    source=source,
                    page_id=_page_from_text(block) or default_page,
                    path=path,
                    tokens=tokenize(f"{code} {title} {block[:1500]}"),
                )
            )
        return units

    # flat BP-01. Title … in long confluence dump
    for m in _CODE_INLINE.finditer(md):
        code = m.group(1).upper()
        title = m.group(2).strip()[:160]
        # take a window after match
        chunk = md[m.start() : m.start() + 900]
        units.append(
            KbUnit(
                code=code,
                title=title,
                text=chunk,
                source=source,
                page_id=default_page or _page_from_text(md[: m.start() + 200][-500:] + chunk),
                path=path,
                tokens=tokenize(f"{code} {title} {chunk}"),
            )
        )
    return units


def _infer_match_kind(
    *,
    source: str,
    status: str = "",
    mode: str = "",
    code: str = "",
    supplement_of: str = "",
) -> str:
    """Классификация единицы для lifecycle: in_review ≠ published."""
    is_sup = (
        str(mode).lower() == "supplement"
        or bool(str(supplement_of or "").strip())
        or "-SUP-" in str(code or "").upper()
    )
    st = (status or "").strip().lower()
    src = (source or "").strip().lower()
    if src.startswith("corpus:"):
        return "corpus"
    if st == "published" or src == "index:published":
        return "published"
    if st in {"in_review", "reviewed", "draft"} or src.startswith("index:") or src == "draft":
        if not st and src == "draft":
            st = "draft"
        if st in {"in_review", "reviewed"} or src.startswith("index:in_review"):
            return "in_review_supplement" if is_sup else "in_review_new"
        if st == "draft" or src == "draft" or src.startswith("index:draft"):
            return "draft_supplement" if is_sup else "draft_new"
    if is_sup:
        return "draft_supplement"
    return "draft_new"


def _index_by_task() -> dict[str, dict[str, Any]]:
    from kb_learning import load_index

    out: dict[str, dict[str, Any]] = {}
    for e in load_index().get("entries") or []:
        tid = str(e.get("task_id") or "")
        if tid:
            out[tid] = e
    return out


def load_draft_units(*, exclude_task_id: str = "") -> list[KbUnit]:
    """Локальные .md; статус/mode из index. page_id из текста не используем как target."""
    out: list[KbUnit] = []
    if not DRAFTS_DIR.is_dir():
        return out
    by_task = _index_by_task()
    try:
        import learn_llm

        rejected_paths = learn_llm.rejected_paths_set()
    except Exception:
        rejected_paths = set()
    for path in sorted(DRAFTS_DIR.glob("*.md")):
        rel = str(path.relative_to(PKG)).replace("\\", "/")
        if rel in rejected_paths:
            continue
        md = path.read_text(encoding="utf-8", errors="replace")
        m_tid = re.search(r"HelpDesk #(\d+)|_hd(\d+)\.md$", md + path.name, re.I)
        tid = ""
        if m_tid:
            tid = m_tid.group(1) or m_tid.group(2) or ""
        if exclude_task_id and tid == str(exclude_task_id):
            continue
        entry = by_task.get(tid) or {}
        if str(entry.get("status") or "").lower() == "rejected":
            continue
        # если путь уже в index — пропустим здесь, возьмём из load_index_units
        if entry and str(entry.get("draft_path") or "").replace("\\", "/") == rel:
            continue
        m = _DRAFT_TITLE.search(md)
        if m:
            code = m.group(1).upper()
            title = m.group(2).strip()[:160]
        else:
            code = path.stem.split("_")[0].upper()
            title = path.stem
        status = str(entry.get("status") or "draft")
        mode = str(entry.get("mode") or ("supplement" if md.lstrip().startswith("# Дополнение") else "new"))
        supplement_of = str(entry.get("supplement_of") or "")
        if not supplement_of and "-SUP-" in code:
            supplement_of = code.split("-SUP-")[0]
        kind = _infer_match_kind(
            source="draft", status=status, mode=mode, code=code, supplement_of=supplement_of
        )
        out.append(
            KbUnit(
                code=code,
                title=title,
                text=md[:4000],
                source="draft",
                page_id="",  # не наследуем pageId из markdown
                path=rel,
                task_id=tid,
                match_kind=kind,
                status=status,
                mode=mode,
                supplement_of=supplement_of,
                confluence_draft_page_id=str(entry.get("confluence_draft_page_id") or ""),
                tokens=tokenize(md[:2000]),
            )
        )
    return out


def load_index_units(*, exclude_task_id: str = "") -> list[KbUnit]:
    from kb_learning import load_index

    out: list[KbUnit] = []
    for e in load_index().get("entries") or []:
        tid = str(e.get("task_id") or "")
        if exclude_task_id and tid == str(exclude_task_id):
            continue
        status = str(e.get("status") or "")
        if status in {"rejected", "merged_into", "duplicate_of"}:
            continue
        code = str(e.get("code") or "")
        if not code:
            continue
        mode = str(e.get("mode") or "new")
        supplement_of = str(e.get("supplement_of") or "")
        title = f"{code} ({status})"
        blob = f"{code} {e.get('service_key') or ''} {e.get('gap_reason') or ''}"
        path = str(e.get("draft_path") or "")
        if path:
            p = PKG / path
            if p.is_file():
                blob = p.read_text(encoding="utf-8", errors="replace")[:2000]
                m = _DRAFT_TITLE.search(blob)
                if m:
                    title = m.group(2).strip()[:160] or title
        kind = _infer_match_kind(
            source=f"index:{status}",
            status=status,
            mode=mode,
            code=code,
            supplement_of=supplement_of,
        )
        # published → page боевой; in_review → только confluence_draft (не target_page_id)
        if status == "published":
            page_id = str(e.get("published_page_id") or e.get("target_page_id") or "")
        else:
            page_id = ""
        out.append(
            KbUnit(
                code=code,
                title=title,
                text=blob,
                source=f"index:{status}",
                page_id=page_id,
                path=path,
                task_id=tid,
                match_kind=kind,
                status=status,
                mode=mode,
                supplement_of=supplement_of,
                confluence_draft_page_id=str(e.get("confluence_draft_page_id") or ""),
                tokens=tokenize(blob),
            )
        )
    return out


def load_corpus_units(service_key: str = "") -> list[KbUnit]:
    keys = []
    sk = (service_key or "").lower()
    if sk in CORPUS_PATHS:
        keys = [sk]
    else:
        keys = ["bp", "lk", "onec"]
    out: list[KbUnit] = []
    seen: set[str] = set()
    for key in keys:
        path = CORPUS_PATHS.get(key)
        if not path or not path.is_file():
            continue
        md = path.read_text(encoding="utf-8", errors="replace")
        default_page = _page_from_text(md[:2000])
        for u in _units_from_markdown(md, source=f"corpus:{key}", default_page=default_page, path=str(path)):
            u.match_kind = "corpus"
            u.status = "published"
            u.mode = "new"
            prev = next((x for x in out if x.code == u.code), None)
            if prev:
                if len(u.text) > len(prev.text):
                    out.remove(prev)
                    out.append(u)
                continue
            if u.code in seen and not u.text:
                continue
            seen.add(u.code)
            out.append(u)
    return out


def collect_units(service_key: str = "", *, exclude_task_id: str = "") -> list[KbUnit]:
    # index (с статусами) + orphan drafts + corpus; index раньше drafts по path
    return (
        load_corpus_units(service_key)
        + load_index_units(exclude_task_id=exclude_task_id)
        + load_draft_units(exclude_task_id=exclude_task_id)
    )


def best_match(
    query: str,
    units: list[KbUnit],
    *,
    duplicate_threshold: float = 0.55,
    supplement_threshold: float = 0.22,
    service_key: str = "",
) -> DedupMatch:
    q = tokenize(query)
    if not q or not units:
        return DedupMatch(mode="new", score=0.0, reason="нет токенов/единиц KB")

    sk = (service_key or "").lower()
    prefix = {"bp": "BP", "lk": "LK", "onec": "1C", "1c": "1C"}.get(sk, "")

    scored: list[tuple[float, KbUnit]] = []
    for u in units:
        toks = u.tokens or tokenize(u.text)
        score = similarity(q, toks)
        title_toks = tokenize(u.title)
        if title_toks:
            t_score = similarity(q, title_toks)
            score = max(score, 0.35 * score + 0.65 * t_score)
            if len(q & title_toks) >= 2:
                score = min(1.0, score + 0.06)
        # приоритет того же контура и corpus
        if prefix and u.code.upper().startswith(prefix + "-"):
            score = min(1.0, score + 0.05)
        elif prefix and u.code.upper()[:2] in {"BP", "LK", "HD", "1C"} and not u.code.upper().startswith(prefix):
            score *= 0.72  # чужой контур — слабее
        if u.source.startswith("corpus:"):
            score = min(1.0, score + 0.03)
        elif u.source.startswith("draft") or u.source.startswith("index:"):
            score *= 0.95
        scored.append((score, u))
    scored.sort(key=lambda x: x[0], reverse=True)
    score, unit = scored[0]

    if score >= duplicate_threshold:
        return DedupMatch(
            mode="duplicate",
            score=score,
            unit=unit,
            reason=f"почти совпадает с {unit.code} ({unit.source}, score={score:.2f})",
            match_kind=unit.match_kind or "",
        )
    if score >= supplement_threshold:
        return DedupMatch(
            mode="supplement",
            score=score,
            unit=unit,
            reason=f"похож на {unit.code} — дополнить ({unit.source}, score={score:.2f})",
            match_kind=unit.match_kind or "",
        )
    return DedupMatch(
        mode="new",
        score=score,
        unit=unit if score > 0.10 else None,
        reason=f"новый сценарий (лучший score={score:.2f}"
        + (f" к {unit.code}" if score > 0.10 else "")
        + ")",
        action="create",
        match_kind=(unit.match_kind if score > 0.10 else "none"),
    )


def _apply_lifecycle(match: DedupMatch, *, force: bool = False) -> DedupMatch:
    """in_review/draft → update_in_place; corpus/published → create supplement review."""
    if not match.unit:
        return DedupMatch(
            mode=match.mode,
            score=match.score,
            unit=None,
            reason=match.reason,
            action="create" if match.mode == "new" else "skip",
            match_kind="none",
        )
    kind = match.unit.match_kind or _infer_match_kind(
        source=match.unit.source,
        status=match.unit.status,
        mode=match.unit.mode,
        code=match.unit.code,
        supplement_of=match.unit.supplement_of,
    )
    pre_promote = kind in {
        "in_review_supplement",
        "in_review_new",
        "draft_supplement",
        "draft_new",
    }
    if match.mode == "new":
        return DedupMatch(
            mode="new",
            score=match.score,
            unit=match.unit if match.score > 0.10 else None,
            reason=match.reason,
            action="create",
            match_kind=kind if match.unit else "none",
        )
    if pre_promote:
        if match.mode == "duplicate" and not force:
            return DedupMatch(
                mode="duplicate",
                score=match.score,
                unit=match.unit,
                reason=(
                    f"уже покрыто черновиком {match.unit.code} "
                    f"({kind}, score={match.score:.2f}) — не плодить -SUP-"
                ),
                action="skip",
                match_kind=kind,
            )
        # supplement или force-duplicate → правим тот же черновик
        label = "дополнение" if "supplement" in kind else "кандидат новой статьи"
        return DedupMatch(
            mode="update_in_place",
            score=match.score,
            unit=match.unit,
            reason=(
                f"in_review/draft ({label}): обновить {match.unit.code} на месте "
                f"(task={match.unit.task_id}, score={match.score:.2f})"
            ),
            action="update_in_place",
            match_kind=kind,
        )
    # corpus / published → новый review (supplement) или skip duplicate
    if match.mode == "duplicate":
        return DedupMatch(
            mode="duplicate",
            score=match.score,
            unit=match.unit,
            reason=match.reason,
            action="skip",
            match_kind=kind,
        )
    return DedupMatch(
        mode="supplement",
        score=match.score,
        unit=match.unit,
        reason=match.reason,
        action="create",
        match_kind=kind,
    )


def resolve_learn_mode(
    task: dict[str, Any],
    analysis: dict[str, Any] | None,
    *,
    resolution: str = "",
    settings: dict[str, Any] | None = None,
    force: bool = False,
) -> DedupMatch:
    if settings is None:
        from settings import load_settings

        settings = load_settings()

    if not settings.get("semantic_dedup_enabled", True):
        return DedupMatch(
            mode="new",
            score=0.0,
            reason="semantic_dedup выключен",
            action="create",
            match_kind="none",
        )

    parsed = (analysis or {}).get("parsed") or {}
    sk = str(parsed.get("service_key") or "other")
    q = query_blob(task, analysis, resolution=resolution)
    units = collect_units(sk, exclude_task_id=str(task.get("Id") or ""))
    match = best_match(
        q,
        units,
        duplicate_threshold=float(settings.get("semantic_duplicate_threshold") or 0.55),
        supplement_threshold=float(settings.get("semantic_supplement_threshold") or 0.22),
        service_key=sk,
    )

    # force: не молча пропускать duplicate — делаем supplement для ревью
    if force and match.mode == "duplicate" and match.unit:
        match = DedupMatch(
            mode="supplement",
            score=match.score,
            unit=match.unit,
            reason=f"force: вместо skip → дополнить {match.unit.code} ({match.score:.2f})",
        )

    if match.mode == "duplicate" and not settings.get("skip_semantic_duplicate", True):
        if match.unit:
            match = DedupMatch(
                mode="supplement",
                score=match.score,
                unit=match.unit,
                reason=f"duplicate→supplement (skip_semantic_duplicate=false): {match.unit.code}",
            )
        else:
            match = DedupMatch(mode="new", score=match.score, reason="duplicate без unit → new")

    if match.mode == "supplement" and not settings.get("auto_supplement_existing", True):
        match = DedupMatch(
            mode="new",
            score=match.score,
            unit=match.unit,
            reason="supplement отключён (auto_supplement_existing=false) → new",
        )

    match = _apply_lifecycle(match, force=force)
    return _avoid_rejected_match(match)


def _avoid_rejected_match(match: DedupMatch) -> DedupMatch:
    """Не дополнять отклонённый черновик — создать новый с учётом причины."""
    import learn_llm

    if not match.unit:
        return match
    code = str(match.unit.code or "")
    if not learn_llm.is_rejected_code(code):
        return match
    rej = learn_llm.rejection_for_code(code) or {}
    reason = str(rej.get("rejection_reason") or "отклонено на ревью")[:200]
    return DedupMatch(
        mode="new",
        score=match.score,
        unit=None,
        reason=f"черновик {code} отклонён: {reason}",
        action="create",
        match_kind="rejected_avoid",
    )
