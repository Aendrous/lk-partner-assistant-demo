# -*- coding: utf-8 -*-
"""Роутер ассистентов для чатбота IntraService.

Open WebUI-имена (*-web-helper) в API llm.iek.local недоступны.
Эквивалент support-dep-lk-web-helper → профиль l1_web (confluence-agent + промпт L1).
Отдельный профиль bp_tickets — разбор заявок БП на корпусе WEBKB + закрытых заявок.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AssistantProfile:
    key: str
    title: str
    model: str
    fallback_model: str
    openwebui_hint: str
    system_extra: str
    corpus_path: str = ""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _pkg_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _system_extra(profile_key: str, default: str) -> str:
    try:
        import prompt_store

        return prompt_store.system_extra_for(profile_key, fallback=default) or default
    except Exception:
        return default


def profiles() -> dict[str, AssistantProfile]:
    support = _env("IEK_LLM_SUPPORT_MODEL", "iek/gpt-oss-120b")
    support_fb = _env("IEK_LLM_SUPPORT_FALLBACK_MODEL", "iek/gpt-oss-120b")
    crm = _env("IEK_LLM_CRM_MODEL", support)
    partner = _env("IEK_LLM_PARTNER_MODEL", "iek/qwen3.5-122b-vl-int4")
    bp_model = _env("IEK_LLM_BP_MODEL", support)
    bp_fb = _env("IEK_LLM_BP_FALLBACK_MODEL", support_fb)
    onec_model = _env("IEK_LLM_1C_MODEL", support)
    return {
        "l1_web": AssistantProfile(
            key="l1_web",
            title="1 линия WEB / HelpDesk (аналог support-dep-lk-web-helper)",
            model=support,
            fallback_model=support_fb,
            openwebui_hint="https://chatgpt.iek.local/?model=support-dep-lk-web-helper",
            system_extra=_system_extra(
                "l1_web",
                "Ты помогаешь исполнителю HelpDesk разобрать заявку (ЛК / WEB). "
                "Поиск Confluence — REST prefetch + локальный КОРПУС ЛК (приоритетнее prefetch). "
                "Не выдумывай URL. Нет статьи → has_kb_solution=false. "
                "Скрытый комментарий: факты + решение со ссылками только из KB.",
            ),
            corpus_path="knowledge/lk/corpus.md",
        ),
        "bp_tickets": AssistantProfile(
            key="bp_tickets",
            title="Разбор заявок БП (bp.iek.ru / ЦКГ)",
            model=bp_model,
            fallback_model=bp_fb,
            openwebui_hint="https://chatgpt.iek.local/?model=support-dep-bp-web-helper",
            corpus_path="knowledge/bp/corpus.md",
            system_extra=_system_extra(
                "bp_tickets",
                "Ты ассистент по bp.iek.ru (ЦКГ / DBP). "
                "Поиск Confluence — REST prefetch + локальный КОРПУС БП (приоритетнее prefetch). "
                "adm: https://adm.bp.iek.ru/main?search=<email>&page=1&pageSize=16 "
                "ServiceId bp→833, lk→732. API-ключ: bp.iek.ru/profile#api-keys. "
                "Не путай с ЛК. Нет сценария → has_kb_solution=false.",
            ),
        ),
        "onec_tickets": AssistantProfile(
            key="onec_tickets",
            title="Разбор заявок 1С (заказ, резерв в пути, счета)",
            model=onec_model,
            fallback_model=support_fb,
            openwebui_hint="https://chatgpt.iek.local/?model=support-dep-1c-web-helper",
            corpus_path="knowledge/1c/corpus.md",
            system_extra=_system_extra(
                "onec_tickets",
                "Ты ассистент по 1С Солярис (заказы, резерв в пути, счета, НС, эл.заявки). "
                "Поиск Confluence — REST prefetch + КОРПУС 1С (приоритетнее prefetch). "
                "Confluence: пространства 1C, WEBKB (быстрые ответы 1С), при необходимости LK. "
                "Не путай с ЛК/bp.iek.ru. Нет сценария → has_kb_solution=false.",
            ),
        ),
        "onec_logistics_tn": AssistantProfile(
            key="onec_logistics_tn",
            title="1С: выгрузка ТН (портал перевозчиков → Солярис)",
            model=onec_model,
            fallback_model=support_fb,
            openwebui_hint="https://chatgpt.iek.local/?model=support-dep-1c-web-helper",
            corpus_path="knowledge/1c/corpus_logistics_tn.md",
            system_extra=_system_extra(
                "onec_logistics_tn",
                "Ты ассистент по выгрузке ТН с logistic.iek.ru в 1С (XMLImportTransport). "
                "Корпус ОП-2765 — приоритетнее RAG. Не путай с заказами/НС/резервом.",
            ),
        ),
        "l1_crm": AssistantProfile(
            key="l1_crm",
            title="1 линия CRM",
            model=crm,
            fallback_model=support_fb,
            openwebui_hint="",
            corpus_path="knowledge/crm/corpus.md",
            system_extra=_system_extra(
                "l1_crm",
                "Контур CRM. Поиск Confluence — REST prefetch (CRMRF/WEBKB). Не путай с ЛК и bp.iek.ru.",
            ),
        ),
        "partner_howto": AssistantProfile(
            key="partner_howto",
            title="How-to партнёра ЛК (не для разбора HD)",
            model=partner,
            fallback_model=support_fb,
            openwebui_hint="https://chatgpt.iek.local/?model=partner-lk-web-helper",
            system_extra="Только how-to ЛК 3.0 для партнёра. Не разбирай внутренние заявки HelpDesk.",
        ),
    }


_BP = re.compile(
    r"bp\.iek|бизнес[\s-]*платформ|цкг|dbp|"
    r"iek[\s\-]*id|oauth/login|profile#api|"
    r"api[\s-]*ключ|ticket\s*/\s*api|"
    r"неверн\w*\s+парол\w*\s+(?:iek\s*id|бп|bp)|"
    r"восстановлен\w*\s+парол\w*.{0,40}(?:bp\.iek|iek\s*id)|"
    r"сброс\w*\s+парол\w*.{0,40}(?:bp\.iek|iek\s*id)",
    re.I,
)
# API каталога ЛК / письмо mailer — это ЛК, не БП
_LK_API = re.compile(
    r"lk\.iek.*/(?:products/)?api|products/api/join|"
    r"внешн\w*\s+пользовател\w*\s+api|"
    r"api\s+каталог|каталог\w*\s+api|"
    r"mailer@iek\.ru.{0,80}api|api.{0,80}mailer@iek\.ru",
    re.I,
)
_LK = re.compile(
    r"lk\.iek|личн\w*\s+кабинет|партн[её]р|трекинг|неудовлетвор|"
    r"заказы\s*3\.0|упд|тендер",
    re.I,
)
_KP = re.compile(r"corp\.iek|корпоративн\w*\s+портал|\bкп\b|сквозн", re.I)
_CRM = re.compile(r"\bcrm\b|битрикс|сделк|лид\b|воронк", re.I)
_VPN = re.compile(r"\bvpn\b|ideсo|ideco|сетев\w*\s+диск", re.I)
_MAIL = re.compile(r"почт|exchange|outlook|\bmail\b", re.I)
_ONEC = re.compile(
    r"\b1[cс]\b|солярис|заказ\s+покупател|заказ\w*\s+хи|"
    r"резерв\w*\s+в\s+пути|эл\.?\s*заявк|"
    r"счет\s+хи|счёт\s+хи|"
    r"попал\w*\s+в\s+нс|\bнс\b",
    re.I,
)
_ONEC_LOGISTICS_TN = re.compile(
    r"(?i)"
    r"товарн\w*\s+накладн|транспортн\w*\s+накладн|(?:^|\s)тн(?:\s|$|-|938)|тн-?тп|"
    r"logistic\.iek\.ru|портал\w*\s+перевозчик|web[\s-]*логист|"
    r"xmlimporttransport|"
    r"не\s+выгружа\w+\s+(?:тн|товарн|транспортн)|выгружа\w*\s+(?:тн|товарн|транспортн)|"
    r"обновить\s+документы\s+1[cс]|создать\\обновить",
)

# IEK HelpDesk: ServiceId 833 — заявки контура БП; 731/732 — ветка ЛК; 69 — Солярис
_BP_SERVICE_IDS = {833, 827}
_LK_SERVICE_IDS = {731, 732, 713}
_SOLARIS_SERVICE_IDS = {14, 69}


def service_id_from_task(task: dict[str, Any]) -> int | None:
    """Нормализовать ServiceId из заявки (API иногда отдаёт строку)."""
    raw = task.get("ServiceId")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    svc = task.get("Service")
    if isinstance(svc, dict):
        sid = svc.get("Id")
        if isinstance(sid, int):
            return sid
        if isinstance(sid, str) and sid.strip().isdigit():
            return int(sid.strip())
    return None


def resolved_models(profile: AssistantProfile) -> tuple[str, str]:
    """Проверить /v1/models и не слать запросы на снятые агенты."""
    import sys

    repo = _pkg_root().parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    import llm_client

    primary = llm_client.resolve_model(profile.model, fallback=profile.fallback_model)
    fallback = llm_client.resolve_model(profile.fallback_model, fallback=primary)
    if fallback == primary:
        return primary, primary
    return primary, fallback


def prefetch_spaces_for_profile(profile_key: str) -> list[str]:
    """Confluence spaces для REST prefetch по профилю ассистента."""
    key = (profile_key or "").strip().lower()
    if key == "bp_tickets":
        return ["WEBKB"]
    if key == "onec_logistics_tn":
        return ["1C", "WEBKB"]
    if key == "onec_tickets":
        # 1C — техдок; WEBKB — быстрые ответы чатбота; LK — резерв в пути (смежные статьи)
        return ["1C", "WEBKB", "LK"]
    if key == "l1_crm":
        return ["CRMRF", "WEBKB"]
    return ["WEBKB"]


def load_corpus(profile: AssistantProfile, max_chars: int = 14000) -> str:
    if not profile.corpus_path:
        return ""
    path = _pkg_root() / profile.corpus_path
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[… корпус обрезан …]\n"
    return text


def is_logistics_tn_task(task: dict[str, Any]) -> bool:
    """Заявка про выгрузку ТН с портала перевозчиков в 1С (ОП-2765, *ТН-ТП*)."""
    blob = f"{task.get('Name') or ''}\n{task.get('Description') or ''}"
    if _ONEC_LOGISTICS_TN.search(blob):
        return True
    name = (task.get("Name") or "").lower()
    if "тн-тп" in name or "*тн" in name:
        return True
    return False


def onec_analyze_scope(settings: dict[str, Any] | None) -> str:
    """logistics_tn — только ТН с портала; all — весь контур Солярис."""
    raw = str((settings or {}).get("onec_analyze_scope") or "logistics_tn").strip().lower()
    return raw if raw in {"logistics_tn", "all"} else "logistics_tn"


_ONEC_CHANGE_REQUEST_TYPE_IDS = {1010}  # «запрос на изменение» — идёт на разработчика
_ONEC_IN_PROGRESS_STATUS_IDS = {27}     # «В процессе» — предразбор уже не нужен


def _task_int_field(task: dict[str, Any], key: str) -> int | None:
    raw = task.get(key)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


def skip_onec_task(task: dict[str, Any]) -> str | None:
    """Жёсткий пропуск предразбора/обучения для заявок 1С Солярис.

    Не разбираем: «запрос на изменение» (TypeId 1010, уходит на разработчика)
    и заявки, которые уже «в работе» (StatusId 27).
    """
    sid = service_id_from_task(task)
    if sid not in _SOLARIS_SERVICE_IDS:
        return None
    if _task_int_field(task, "TypeId") in _ONEC_CHANGE_REQUEST_TYPE_IDS:
        return "1С: запрос на изменение (TypeId 1010) — предразбор не выполняется"
    if _task_int_field(task, "StatusId") in _ONEC_IN_PROGRESS_STATUS_IDS:
        return "1С: заявка уже в работе (StatusId 27) — предразбор не выполняется"
    return None


def skip_onec_out_of_scope(
    task: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> str | None:
    """Пропуск заявок Солярис вне выбранного scope."""
    if onec_analyze_scope(settings) != "logistics_tn":
        return None
    sid = service_id_from_task(task)
    if sid not in _SOLARIS_SERVICE_IDS:
        return None
    if is_logistics_tn_task(task):
        return None
    return (
        "1С Солярис: разбор включён только для ТН (портал перевозчиков → 1С); "
        "см. onec_analyze_scope=logistics_tn"
    )


def choose_assistant(
    *,
    text: str = "",
    service_key: str = "",
    service_id: int | None = None,
    settings: dict[str, Any] | None = None,
) -> AssistantProfile:
    """Выбрать профиль ассистента по тексту заявки / ключу сервиса.

    Важно: ServiceId 731/732 (ветка ЛК) + API каталога → l1_web.
    Не путать «письмо для API» на 732 с bp.iek.ru (833).
    """
    blob = f"{service_key}\n{text}".lower()
    key = (service_key or "").strip().lower()
    sid = service_id if service_id is not None else None

    # явный ключ
    if key == "bp":
        return profiles()["bp_tickets"]
    if key in {"lk", "kp"}:
        return profiles()["l1_web"]
    if key in {"1c", "onec", "edi"}:
        if is_logistics_tn_task({"Name": text, "Description": text}):
            return profiles()["onec_logistics_tn"]
        if onec_analyze_scope(settings) != "logistics_tn":
            return profiles()["onec_tickets"]
    if key == "crm":
        return profiles()["l1_crm"]

    # API каталога ЛК / mailer — раньше общего BP
    if _LK_API.search(blob) or (sid in _LK_SERVICE_IDS and re.search(r"\bapi\b", blob)):
        # исключение: явно bp.iek / IEK ID
        if not (_BP.search(blob) and re.search(r"bp\.iek|iek[\s\-]*id|цкг|dbp", blob)):
            return profiles()["l1_web"]

    if is_logistics_tn_task({"Name": blob, "Description": blob}):
        return profiles()["onec_logistics_tn"]

    if sid in _SOLARIS_SERVICE_IDS:
        if onec_analyze_scope(settings) != "logistics_tn":
            return profiles()["onec_tickets"]
    if sid in _BP_SERVICE_IDS or (key == "bp"):
        return profiles()["bp_tickets"]
    if _BP.search(blob) and sid not in _LK_SERVICE_IDS:
        return profiles()["bp_tickets"]
    # на ветке ЛК «авторизация» без bp.iek → остаёмся на l1_web
    if sid in _LK_SERVICE_IDS:
        if _BP.search(blob) and re.search(r"bp\.iek|iek[\s\-]*id|цкг|бизнес[\s-]*платформ", blob):
            return profiles()["bp_tickets"]
        return profiles()["l1_web"]

    if _ONEC.search(blob) and onec_analyze_scope(settings) != "logistics_tn":
        return profiles()["onec_tickets"]
    if _LK.search(blob) or _KP.search(blob):
        return profiles()["l1_web"]
    if _CRM.search(blob):
        return profiles()["l1_crm"]
    if _VPN.search(blob) or _MAIL.search(blob):
        return profiles()["l1_web"]
    if _BP.search(blob):
        return profiles()["bp_tickets"]
    return profiles()["l1_web"]


def choose_for_task(
    task: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> AssistantProfile:
    sid = service_id_from_task(task)
    return choose_assistant(
        text=f"{task.get('Name') or ''}\n{task.get('Description') or ''}",
        service_id=sid,
        settings=settings,
    )


_FAKE_HOST = re.compile(
    r"confluence\.company\.com|webkb\.company\.com|example\.com|localhost/wiki",
    re.I,
)


def sanitize_article_links(links: list[Any] | None) -> list[str]:
    out: list[str] = []
    for item in links or []:
        url = str(item or "").strip()
        if not url.startswith("http"):
            continue
        if _FAKE_HOST.search(url):
            continue
        if "confluence.dev.iek.ru" in url or "corp.iek.ru" in url or "lk.iek.ru" in url:
            out.append(url)
        elif "iek." in url and "confluence" in url:
            out.append(url)
    seen: set[str] = set()
    uniq: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq
