# -*- coding: utf-8 -*-
"""UI настроек и пайплайна чатбота IntraService (Streamlit).

  cd chatbot_intraservice
  streamlit run app.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
REPO = ROOT.parent
# src первым — не подхватывать чужой call_history с PYTHONPATH / cwd
sys.path = [str(SRC), str(REPO)] + [
    p for p in sys.path if Path(p).resolve() not in {SRC.resolve(), REPO.resolve()}
]


def _load_src_module(name: str) -> ModuleType:
    """Жёстко грузить модуль из chatbot_intraservice/src (не из кэша/коллизии)."""
    path = SRC / f"{name}.py"
    if not path.is_file():
        raise ImportError(f"Нет {path}")
    # сбросить кэш Streamlit/старый модуль без list_overdue_taken
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Не удалось загрузить {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _draft_file_path(draft_path: str) -> Path | None:
    if not draft_path:
        return None
    p = Path(draft_path)
    if p.is_file():
        return p
    fp = ROOT / draft_path
    return fp if fp.is_file() else None


def _render_draft_body(kb_learning_mod: ModuleType, entry: dict) -> None:
    fp = _draft_file_path(str(entry.get("draft_path") or ""))
    tid = str(entry.get("task_id") or "")
    if not fp:
        st.warning("Локальный файл черновика не найден.")
        return
    full = fp.read_text(encoding="utf-8")
    insert = kb_learning_mod.extract_insert_sections(full)
    insert_key = f"kb_insert_edit_{tid}"
    box_h = min(400, 120 + max(insert.count("\n"), 8) * 22)

    st.markdown("#### Текст для Promote")
    st.caption(
        "Слева — markdown для правки; справа — как увидит исполнитель в Confluence. "
        "В «Быстрые ответы» уйдёт только этот блок (сохранение при **Promote**)."
    )

    col_edit, col_preview = st.columns(2, gap="medium")
    with col_edit:
        st.caption("Редактирование")
        edited = st.text_area(
            "KB_INSERT",
            value=insert.strip(),
            height=box_h,
            key=insert_key,
            label_visibility="collapsed",
            placeholder="## LK-NN. …\n**Сценарий:** …\n**Ключевые слова:** …",
        )
        if insert.strip() and (st.session_state.get(insert_key) or "").strip() != insert.strip():
            if st.button(f"Сбросить правки (#{tid})", key=f"reset_kb_insert_{tid}"):
                st.rerun()

    preview_md = (st.session_state.get(insert_key) or edited or "").strip()
    with col_preview:
        st.caption("Превью")
        with st.container(height=box_h, border=True):
            if preview_md:
                st.markdown(preview_md)
            else:
                st.caption("Пусто — допишите текст слева.")

    if not insert.strip() and "KB_INSERT_START" in full:
        st.warning("Маркеры KB_INSERT пусты — допишите текст перед Promote.")

    with st.expander("Контекст заявки и полный черновик (не в KB)", expanded=False):
        st.markdown(full)


def _parse_subprocess_json(stdout: str) -> dict | None:
    import json as _json

    text = (stdout or "").strip()
    if not text:
        return None
    # цельный JSON (sync_kb_after_review печатает многострочный)
    if text.startswith("{"):
        try:
            return _json.loads(text)
        except Exception:
            pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return _json.loads(line)
            except Exception:
                continue
    return None


def _index_published_entry(task_id: str, kb_learning_mod: ModuleType | None = None) -> dict | None:
    if not task_id:
        return None
    mod = kb_learning_mod
    if mod is None:
        try:
            mod = _load_src_module("kb_learning")
        except Exception:
            return None
    for entry in mod.load_index().get("entries") or []:
        if str(entry.get("task_id")) == str(task_id) and str(entry.get("status")) == "published":
            return entry
    return None


def _format_promote_error(data: dict | None, stdout: str) -> str:
    if not data:
        return (stdout or "ошибка sync")[-800:]
    for step in data.get("steps") or []:
        if step.get("ok") or step.get("skipped"):
            continue
        name = step.get("name") or "step"
        err = (step.get("stderr") or step.get("stdout") or "fail").strip()
        if "Confluence PUT HTTP" in err:
            m = re.search(r'"message":"([^"]+)"', err)
            if m:
                return f"{name}: Confluence — {m.group(1)[:400]}"
        return f"{name}: {err[-500:]}"
    return (stdout or "")[-800:]


def _sync_promote_result_message(
    stdout: str,
    returncode: int,
    *,
    stderr: str = "",
    task_id: str = "",
    kb_learning_mod: ModuleType | None = None,
) -> tuple[bool, str, str]:
    """(успех для UI, сообщение, уровень: success|warning|error)"""
    blob = f"{stdout or ''}\n{stderr or ''}"
    data = _parse_subprocess_json(blob)
    if not data:
        sync_file = ROOT / "_sync_kb_after_review.json"
        if sync_file.is_file():
            try:
                data = json.loads(sync_file.read_text(encoding="utf-8"))
            except Exception:
                data = None

    pub_entry = _index_published_entry(task_id, kb_learning_mod)
    confluence_url = ""
    if pub_entry:
        pid = str(pub_entry.get("published_page_id") or pub_entry.get("target_page_id") or "")
        if pid:
            confluence_url = f"https://confluence.dev.iek.ru/pages/viewpage.action?pageId={pid}"

    if not data:
        if returncode == 0 or pub_entry:
            msg = "Опубликовано в «Быстрые ответы»."
            if confluence_url:
                msg += f" [Открыть]({confluence_url})"
            return True, msg, "success"
        return False, "Ошибка Promote — см. лог `_sync_kb_after_review.json`.", "error"

    steps = list(data.get("steps") or [])
    publish_ok = any(s.get("name") == "publish" and s.get("ok") for s in steps)
    if not publish_ok and pub_entry:
        publish_ok = True
    msg = str(data.get("success_message") or "").strip()
    failed = [s.get("name") for s in steps if not s.get("ok") and not s.get("skipped")]

    if publish_ok:
        tail = ""
        if failed:
            tail = f" (фон: не выполнено: {', '.join(failed)})"
        url = confluence_url
        for s in steps:
            pr = s.get("publish_result") or {}
            if pr.get("url"):
                url = str(pr["url"])
                break
        code = str((pub_entry or {}).get("code") or "")
        base = msg or (
            f"**{code}** опубликовано в «Быстрые ответы»." if code else "Опубликовано в «Быстрые ответы»."
        )
        if url and url not in base:
            base += f" [Открыть в Confluence]({url})"
        return True, base + tail, ("warning" if failed else "success")
    if data.get("ok"):
        return True, msg or "Готово.", "success"
    return False, _format_promote_error(data, blob), "error"


def _render_draft_review_card(
    entry: dict,
    *,
    kb_learning_mod: ModuleType,
    kb_promote_preview_mod: ModuleType,
    prefix: str = "",
) -> None:
    """Карточка черновика: превью, Promote, отклонить, push в Confluence."""
    import subprocess

    tid = str(entry.get("task_id") or "")
    key_prefix = f"{prefix}_{tid}" if prefix else tid
    links = [f"[HelpDesk]({entry.get('helpdesk_url')})"]
    if entry.get("confluence_url"):
        links.append(f"[Confluence ревью]({entry.get('confluence_url')})")
    st.markdown(" · ".join(links))
    gap = kb_learning_mod.humanize_gap_reason(str(entry.get("gap_reason") or ""))
    if gap:
        st.caption(gap)
    _render_draft_body(kb_learning_mod, entry)

    plan = kb_promote_preview_mod.build_promote_plan(entry)
    st.markdown("#### Promote")
    st.markdown(kb_promote_preview_mod.format_plan_markdown(plan))
    for w in plan.get("warnings") or []:
        st.warning(w)

    rej_reason = st.text_input(
        "Причина отклонения",
        value="",
        key=f"rej_reason_{key_prefix}",
        placeholder="например: дубль HD-09, не про ЛК, мусор из OCR",
    )
    c_rej, c_prom, c_push = st.columns(3)
    with c_rej:
        if st.button(f"Отклонить (#{tid})", key=f"reject_{key_prefix}"):
            res = kb_learning_mod.reject_draft(tid, reason=rej_reason)
            if res.get("ok"):
                st.success(f"Отклонено: {res.get('code')}")
                st.rerun()
            else:
                st.error(res.get("error") or "ошибка")
    with c_prom:
        do_promote = st.button(
            f"Promote → Быстрые ответы (#{tid})",
            key=f"promote_{key_prefix}",
            type="primary",
        )
    with c_push:
        if not entry.get("confluence_draft_page_id") and st.button(
            f"В Confluence (#{tid})",
            key=f"push_cf_{key_prefix}",
        ):
            with st.spinner(f"Push #{tid}…"):
                r = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "push_kb_draft_confluence_review.py"),
                        "--task-id",
                        tid,
                    ],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            if r.returncode == 0:
                st.success("Выгружено в Confluence.")
                st.rerun()
            else:
                st.error(((r.stderr or "") + "\n" + (r.stdout or ""))[-1000:])
    if do_promote:
        fp_prom = _draft_file_path(str(entry.get("draft_path") or ""))
        insert_key = f"kb_insert_edit_{tid}"
        if fp_prom and insert_key in st.session_state:
            try:
                kb_learning_mod.save_draft_kb_insert(
                    fp_prom, str(st.session_state[insert_key] or "")
                )
            except Exception as exc:
                st.error(f"Не удалось сохранить KB_INSERT: {exc}")
                st.stop()
        with st.spinner(f"Promote #{tid}…"):
            r = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "sync_kb_after_review.py"),
                    "--task-id",
                    tid,
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        ok_ui, msg, level = _sync_promote_result_message(
            r.stdout or "",
            r.returncode,
            stderr=r.stderr or "",
            task_id=tid,
            kb_learning_mod=kb_learning_mod,
        )
        if ok_ui:
            if level == "warning":
                st.warning(msg)
            else:
                st.success(msg)
            st.rerun()
        else:
            st.error(msg)


import streamlit as st

call_history = _load_src_module("call_history")
pipeline = _load_src_module("pipeline")
settings_mod = _load_src_module("settings")
PipelineRun = pipeline.PipelineRun
run_ticket_pipeline = pipeline.run_ticket_pipeline
load_settings = settings_mod.load_settings
save_local_settings = settings_mod.save_local_settings
settings_summary = settings_mod.settings_summary
service_filter = _load_src_module("service_filter")
task_linking = _load_src_module("task_linking")
env_bootstrap = _load_src_module("env_bootstrap")
env_bootstrap.load_package_env()
l0_chat = _load_src_module("l0_chat")

st.set_page_config(page_title="IntraService чатбот", page_icon="🎫", layout="wide")
st.title("Чатбот IntraService — настройки и пайплайн")

cfg = load_settings()

with st.sidebar:
    st.header("L1 Simple")
    st.caption("Профит: просрочка → взять в работу + скрытый разбор; открытый ответ — только если включён ниже.")

    auto_post_public_comment = st.toggle(
        "Открытые комментарии заявителю",
        value=bool(cfg.get("auto_post_public_comment", False)),
        help="Мастер-выключатель: любые видимые комментарии в заявке (сейчас — только сценарий «До просрочки»). "
        "По умолчанию выкл.: только скрытый разбор для исполнителя.",
    )
    watch_overdue_enabled = st.toggle(
        "Просрочка «До просрочки»",
        value=bool(cfg.get("watch_overdue_enabled", True)),
        help="Scheduler: take + скрытый; публичный — по флагу ниже",
    )
    auto_post_comment = st.toggle(
        "Автопост скрытого разбора",
        value=bool(cfg.get("auto_post_comment")),
        help="watch_new / reply / overdue пишут скрытый комментарий",
    )
    overdue_post_public = st.toggle(
        "Просрочка: открытый ответ заявителю",
        value=bool(cfg.get("overdue_post_public", False)),
        disabled=not watch_overdue_enabled or not auto_post_public_comment,
        help="При эскалации «До просрочки» — видимый ответ (только при KB / ответе исполнителя, не «спасибо» заявителя)",
    )
    public_reply_only_if_kb = st.toggle(
        "Открытый ответ только если есть KB",
        value=bool(cfg.get("public_reply_only_if_kb", True)),
        disabled=not auto_post_public_comment,
        help="Без has_kb_solution / ясного prior / факта 1С — только скрытый разбор",
    )
    auto_learn_kb = st.toggle(
        "AI-KB: учиться из закрытых (черновики)",
        value=bool(cfg.get("auto_learn_kb")),
    )

    with st.expander("Расширенные настройки", expanded=False):
        st.caption("Dedup, digests, related — не нужны для базового профита.")
        auto_take_in_work = st.toggle(
            "Авто «В процессе» на всех watch (не только overdue)",
            value=bool(cfg.get("auto_take_in_work")),
            help="По умолчанию false: take только из watch_overdue",
        )
        overdue_shift_deadline = st.toggle(
            "Просрочка: дедлайн +1 день",
            value=bool(cfg.get("overdue_shift_deadline", True)),
            disabled=not watch_overdue_enabled,
        )
        skip_if_in_progress_or_awaiting = st.toggle(
            "Skip если уже в работе / ожидание (кроме просрочки)",
            value=bool(cfg.get("skip_if_in_progress_or_awaiting", True)),
        )
        watch_new_enabled = st.toggle(
            "Новые/переданные (31/38/121)",
            value=bool(cfg.get("watch_new_enabled", True)),
        )
        watch_user_reply_enabled = st.toggle(
            "Ответ в «Ожидании» (46/120)",
            value=bool(cfg.get("watch_user_reply_enabled", True)),
        )
        watch_user_reply_crm_status_changes = st.toggle(
            "Ответ в «Ожидании»: менять статусы CRM",
            value=bool(cfg.get("watch_user_reply_crm_status_changes", False)),
            help="off — бот не переводит CRM-заявки в другие статусы (по умолчанию выключено)",
        )
        post_learn_note = st.toggle(
            "AI-KB: заметка в заявке + ссылка",
            value=bool(cfg.get("post_learn_note", True)),
        )
        auto_push_confluence_draft = st.toggle(
            "AI-KB: сразу страница в папке самообучения",
            value=bool(cfg.get("auto_push_confluence_draft", False)),
        )
        semantic_dedup_enabled = st.toggle(
            "Семантический дедуп",
            value=bool(cfg.get("semantic_dedup_enabled", True)),
        )
        auto_supplement_existing = st.toggle(
            "Дополнять похожую статью X",
            value=bool(cfg.get("auto_supplement_existing", True)),
            disabled=not semantic_dedup_enabled,
        )
        skip_semantic_duplicate = st.toggle(
            "Пропускать почти полные дубли",
            value=bool(cfg.get("skip_semantic_duplicate", True)),
            disabled=not semantic_dedup_enabled,
        )
        auto_learn_on_close = st.toggle(
            "Учить при закрытии",
            value=bool(cfg.get("auto_learn_on_close")),
            disabled=not auto_learn_kb,
        )
        auto_learn_on_analyze = st.toggle(
            "Учить сразу при разборе",
            value=bool(cfg.get("auto_learn_on_analyze")),
            disabled=not auto_learn_kb,
        )
        skip_if_kb_found = st.toggle(
            "Не учить если KB уже найдена",
            value=bool(cfg.get("skip_if_kb_found", True)),
        )
        skip_if_draft_exists = st.toggle(
            "Не дублировать черновик по task_id",
            value=bool(cfg.get("skip_if_draft_exists", True)),
        )
        link_related_on_post = st.toggle(
            "Связывать дубли при посте",
            value=bool(cfg.get("link_related_on_post", True)),
        )
        add_parent_creator_as_observer = st.toggle(
            "Инициатор ранней → наблюдатель",
            value=bool(cfg.get("add_parent_creator_as_observer", True)),
            disabled=not link_related_on_post,
        )
        gap_digest_enabled = st.toggle(
            "Weekly gap digest",
            value=bool(cfg.get("gap_digest_enabled", False)),
        )
        pipeline_save_runs = st.toggle(
            "Сохранять прогоны в pipeline/runs/",
            value=bool(cfg.get("pipeline_save_runs", True)),
        )
        require_closed = st.toggle(
            "Учить только закрытые (watch)",
            value=bool(cfg.get("require_closed_for_auto_learn", True)),
        )
        onec_analyze_all = st.toggle(
            "1С: разбирать все заявки (не только ТН)",
            value=bool((cfg.get("onec_analyze_scope") or "logistics_tn") == "all"),
            help="off — только ТН (ОП-2765); on — весь контур Солярис (кроме «запрос на изменение» и «уже в работе»)",
        )

        st.markdown("**Контуры — что обрабатывать**")
        st.caption("Опрос watch — ServiceId по «Опрос»; подчинение дублей — по «Подчинение» (тот же день, открытые).")
        link_by = cfg.get("link_related_by_contour") or {}
        contour_cfg: dict[str, dict[str, bool]] = {}
        link_cfg: dict[str, bool] = {}
        ce = cfg.get("contour_enabled") or {}
        for ckey, clabel in [
            ("lk", "ЛК"),
            ("bp", "БП"),
            ("crm", "CRM"),
            ("edi", "EDI / 1С"),
            ("other", "Прочее"),
        ]:
            row = ce.get(ckey) if isinstance(ce.get(ckey), dict) else {}
            link_row = link_by.get(ckey) if isinstance(link_by.get(ckey), bool) else link_by.get(ckey)
            st.markdown(f"**{clabel}**")
            c1, c2, c3, c4 = st.columns(4)
            contour_cfg[ckey] = {
                "comment": c1.checkbox(
                    "Разбор",
                    value=bool(row.get("comment", ckey != "crm")),
                    key=f"ce_{ckey}_comment",
                ),
                "kb_learn": c2.checkbox(
                    "AI-KB",
                    value=bool(row.get("kb_learn", ckey != "crm")),
                    key=f"ce_{ckey}_kb",
                ),
                "watch": c3.checkbox(
                    "Опрос",
                    value=bool(row.get("watch", ckey != "crm")),
                    key=f"ce_{ckey}_watch",
                ),
            }
            link_cfg[ckey] = c4.checkbox(
                "Подчинение",
                value=bool(link_row if isinstance(link_row, bool) else task_linking.DEFAULT_LINK_BY_CONTOUR.get(ckey, True)),
                key=f"lr_{ckey}_link",
                help="ParentId для дублей в тот же день (открытые заявки)",
            )

    if st.button("Сохранить Simple-пресет", type="primary"):
        draft_settings = {
            **cfg,
            "contour_enabled": contour_cfg,
        }
        watch_sync = service_filter.sync_watch_service_ids(draft_settings)
        path = save_local_settings(
            {
                "ui_mode": "simple",
                "auto_learn_kb": auto_learn_kb,
                "auto_learn_on_close": auto_learn_on_close,
                "auto_learn_on_analyze": auto_learn_on_analyze,
                "auto_post_comment": auto_post_comment,
                "auto_post_public_comment": auto_post_public_comment,
                "auto_take_in_work": auto_take_in_work,
                "public_reply_only_if_kb": public_reply_only_if_kb,
                "post_learn_note": post_learn_note,
                "auto_push_confluence_draft": auto_push_confluence_draft,
                "semantic_dedup_enabled": semantic_dedup_enabled,
                "auto_supplement_existing": auto_supplement_existing,
                "skip_semantic_duplicate": skip_semantic_duplicate,
                "semantic_duplicate_threshold": float(cfg.get("semantic_duplicate_threshold") or 0.55),
                "semantic_supplement_threshold": float(cfg.get("semantic_supplement_threshold") or 0.22),
                "skip_if_in_progress_or_awaiting": skip_if_in_progress_or_awaiting,
                "link_related_on_post": link_related_on_post,
                "add_parent_creator_as_observer": add_parent_creator_as_observer,
                "skip_if_kb_found": skip_if_kb_found,
                "skip_if_draft_exists": skip_if_draft_exists,
                "require_closed_for_auto_learn": require_closed,
                "onec_analyze_scope": "all" if onec_analyze_all else "logistics_tn",
                "pipeline_save_runs": pipeline_save_runs,
                "watch_overdue_enabled": watch_overdue_enabled,
                "overdue_shift_deadline": overdue_shift_deadline,
                "overdue_post_public": overdue_post_public,
                "overdue_shift_deadline_days": int(cfg.get("overdue_shift_deadline_days") or 1),
                "watch_new_enabled": watch_new_enabled,
                "watch_user_reply_enabled": watch_user_reply_enabled,
                "watch_user_reply_crm_status_changes": watch_user_reply_crm_status_changes,
                "gap_digest_enabled": gap_digest_enabled,
                "watch_closed_status_ids": cfg.get("watch_closed_status_ids") or [28, 29],
                "watch_new_status_ids": cfg.get("watch_new_status_ids") or [31, 38, 121],
                "watch_user_reply_status_ids": cfg.get("watch_user_reply_status_ids") or [46, 120],
                "watch_user_reply_max_age_hours": cfg.get("watch_user_reply_max_age_hours") or 72,
                "watch_overdue_status_ids": cfg.get("watch_overdue_status_ids") or [31, 38, 121, 27, 46, 120],
                "watch_overdue_marker": cfg.get("watch_overdue_marker") or "До просрочки",
                "watch_overdue_max_age_hours": cfg.get("watch_overdue_max_age_hours") or 6,
                "watch_new_max_age_hours": cfg.get("watch_new_max_age_hours") or 72,
                "drafts_review_digest_enabled": cfg.get("drafts_review_digest_enabled", True),
                "contour_enabled": contour_cfg,
                "link_related_by_contour": link_cfg,
                "disabled_service_ids": list(cfg.get("disabled_service_ids") or []),
                **watch_sync,
            }
        )
        st.success(f"Сохранено: {path.name}")
        st.rerun()

    st.divider()
    st.json(settings_summary())

tab_l0, tab_run, tab_hist, tab_overdue, tab_kb, tab_prompts, tab_runs, tab_docs = st.tabs(
    [
        "L0 чат (сотрудник)",
        "Запуск",
        "История LLM / partner-lk / KB",
        "Просрочки (робот)",
        "AI-KB черновики",
        "Промпты и корпуса",
        "Прогоны",
        "Правила",
    ]
)

with tab_l0:
    st.caption(
        "0 линия: ответ из KB / уточнения / черновик заявки. Можно **разобрать уже созданную** "
        "заявку HD (преданализ как на «Запуск», без поста) и задать уточняющие вопросы в чате. "
        "Пост скрытого комментария / take / learn — вкладка «Запуск». "
        "Спека: `docs/specs/L0_employee_chatbot.md`."
    )
    if "l0_messages" not in st.session_state:
        st.session_state.l0_messages = []
    if "l0_last_result" not in st.session_state:
        st.session_state.l0_last_result = None
    if "l0_ticket_context" not in st.session_state:
        st.session_state.l0_ticket_context = None
    if st.session_state.get("l0_email_pending"):
        st.session_state.l0_email = st.session_state.pop("l0_email_pending")

    l0_email = st.text_input(
        "Email заявителя (для создания заявки)",
        value=st.session_state.get("l0_email", ""),
        key="l0_email",
        placeholder="ivanov@iek.ru",
    )

    with st.expander("Разбор заявки HelpDesk (как «Запуск» + уточнения)", expanded=False):
        st.caption(
            "Загружает заявку, делает dry-run L1 (без скрытого поста) и открывает чат "
            "с уточняющими вопросами по матрице."
        )
        c_tid, c_btn = st.columns([2, 1])
        with c_tid:
            l0_task_id = st.text_input(
                "Номер заявки",
                value=st.session_state.get("l0_task_id_input", ""),
                key="l0_task_id_input",
                placeholder="699802",
            )
        with c_btn:
            st.write("")
            st.write("")
            do_review = st.button(
                "Разобрать + уточнить",
                type="primary",
                disabled=not str(l0_task_id or "").strip(),
                key="l0_review_btn",
            )
        if do_review:
            with st.spinner(f"Разбор #{l0_task_id.strip()}…"):
                try:
                    rev = l0_chat.review_ticket(
                        l0_task_id.strip(),
                        user_email=(l0_email or "").strip(),
                        run_l1_preview=True,
                    )
                except Exception as exc:
                    rev = {"ok": False, "error": str(exc)}
            if not rev.get("ok"):
                st.error(rev.get("error") or "ошибка разбора")
            else:
                st.session_state.l0_ticket_context = rev.get("ticket_context")
                st.session_state.l0_last_result = {
                    **rev,
                    "need_ticket": False,
                    "has_answer": True,
                }
                if (rev.get("task") or {}).get("CreatorEmail") and not (l0_email or "").strip():
                    st.session_state.l0_email_pending = rev["task"]["CreatorEmail"]
                st.session_state.l0_messages.append(
                    {
                        "role": "assistant",
                        "content": rev.get("answer_ru") or f"Загружена заявка #{rev.get('task_id')}",
                        "links": rev.get("article_links") or [],
                    }
                )
                l1p = rev.get("l1_preview") or {}
                if l1p.get("comment_preview"):
                    with st.expander("Преданализ L1 (preview)", expanded=False):
                        st.code(l1p["comment_preview"])
                        if l1p.get("service_check"):
                            st.json(l1p["service_check"])
                st.rerun()

    col_a, col_b = st.columns([1, 4])
    with col_a:
        if st.button("Очистить чат", key="l0_clear"):
            st.session_state.l0_messages = []
            st.session_state.l0_last_result = None
            st.session_state.l0_ticket_context = None
            st.rerun()
    with col_b:
        ctx = st.session_state.l0_ticket_context
        if ctx and ctx.get("task_id"):
            st.caption(
                f"Контекст заявки: [#{ctx['task_id']}]({ctx.get('url') or '#'}) — "
                f"{ctx.get('task_name') or ''}"
            )

    for msg in st.session_state.l0_messages:
        with st.chat_message(msg.get("role") or "user"):
            st.markdown(msg.get("content") or "")
            links = msg.get("links") or []
            if links:
                for u in links:
                    st.markdown(f"- {u}")

    prompt = st.chat_input("Вопрос сотрудника или ответ на уточнение…")
    if prompt:
        st.session_state.l0_messages.append({"role": "user", "content": prompt})
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.l0_messages[:-1]
            if m.get("role") in {"user", "assistant"}
        ]
        with st.spinner("Ищу в KB / уточняю…"):
            try:
                result = l0_chat.ask(
                    prompt,
                    history=history,
                    user_email=(l0_email or "").strip(),
                    create=False,
                    ticket_context=st.session_state.l0_ticket_context,
                )
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
        st.session_state.l0_last_result = result
        if result.get("ticket_context"):
            # сохранить контекст, если ask его вернул
            base = st.session_state.l0_ticket_context or {}
            st.session_state.l0_ticket_context = {**base, **(result.get("ticket_context") or {})}
        if not result.get("ok"):
            reply = f"Ошибка: {result.get('error') or 'неизвестно'}"
            st.session_state.l0_messages.append({"role": "assistant", "content": reply})
        elif result.get("has_answer") and result.get("answer_ru"):
            reply = result["answer_ru"]
            if result.get("need_ticket") and not (st.session_state.l0_ticket_context or {}).get("task_id"):
                reply += (
                    "\n\nЕсли не помогло — ниже можно создать заявку в HelpDesk "
                    f"(сервис: {((result.get('ticket_draft') or {}).get('ServiceName') or '—')})."
                )
            st.session_state.l0_messages.append(
                {
                    "role": "assistant",
                    "content": reply,
                    "links": result.get("article_links") or [],
                }
            )
        else:
            draft = result.get("ticket_draft") or {}
            reply = (
                "Готового ответа в KB не нашёл. Могу создать заявку:\n\n"
                f"**{draft.get('Name') or '—'}**\n\n"
                f"Сервис: {draft.get('ServiceName') or draft.get('ServiceKey')} "
                f"(Id={draft.get('ServiceId')})"
            )
            st.session_state.l0_messages.append({"role": "assistant", "content": reply})
        st.rerun()

    last = st.session_state.l0_last_result
    if last and last.get("ok") and last.get("need_ticket"):
        draft = last.get("ticket_draft") or {}
        with st.expander("Черновик заявки IntraService", expanded=True):
            st.write(
                {
                    "Name": draft.get("Name"),
                    "ServiceKey": draft.get("ServiceKey"),
                    "ServiceId": draft.get("ServiceId"),
                    "ServiceName": draft.get("ServiceName"),
                    "UserEmail": (l0_email or "").strip() or None,
                }
            )
            st.text_area(
                "Description",
                value=str(draft.get("Description") or ""),
                height=180,
                key="l0_draft_desc_view",
                disabled=True,
            )
            can_create = bool(draft.get("ServiceId") and (l0_email or "").strip())
            if st.button(
                "Создать заявку в HelpDesk",
                type="primary",
                disabled=not can_create,
                key="l0_create_ticket",
            ):
                with st.spinner("POST /api/task…"):
                    try:
                        intraservice_mod = _load_src_module("intraservice")
                        cre = intraservice_mod.create_task(
                            name=str(draft.get("Name") or "Обращение из L0-чата"),
                            description=str(draft.get("Description") or ""),
                            service_key=str(draft.get("ServiceKey") or "lk"),
                            user_email=(l0_email or "").strip(),
                            service_id=int(draft["ServiceId"]) if draft.get("ServiceId") else None,
                        )
                    except Exception as exc:
                        cre = {"ok": False, "error": str(exc)}
                if cre.get("ok") or cre.get("Id"):
                    tid = cre.get("Id") or cre.get("id")
                    url = cre.get("url") or f"https://helpdesk.iek.local/Task/View/{tid}"
                    st.session_state.l0_messages.append(
                        {
                            "role": "assistant",
                            "content": f"Заявка создана: **№{tid}**\n\nОткрыть: {url}",
                        }
                    )
                    st.session_state.l0_last_result = {
                        **(last or {}),
                        "need_ticket": False,
                        "created": cre,
                    }
                    st.success(f"Создано #{tid}")
                else:
                    st.error(str(cre.get("error") or "Не удалось создать заявку"))
                    st.json(cre)
                st.rerun()
            if not can_create:
                st.caption("Укажите email заявителя и дождитесь черновика с ServiceId.")
            st.caption(
                f"Модель: {last.get('model')} · prefetch hits: "
                f"{(last.get('prefetch') or {}).get('hits')}"
            )

with tab_run:
    st.caption(
        "L1 для исполнителя: полный пайплайн с опцией скрытого комментария / take / learn. "
        "Разбор + уточнения в чате без поста — вкладка «L0 чат»."
    )
    task_id = st.text_input("Номер заявки HelpDesk", placeholder="696955")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        do_post = st.checkbox("Скрытый комментарий", value=False)
    with col2:
        do_take = st.checkbox("Взять в работу", value=False)
    with col3:
        do_learn = st.checkbox("AI-KB (--learn)", value=False)
    with col4:
        no_learn = st.checkbox("Без обучения", value=False)

    if st.button("Запустить пайплайн", disabled=not task_id.strip()):
        with st.spinner("Разбор заявки…"):
            try:
                learn = False if no_learn else (True if do_learn else None)
                result = run_ticket_pipeline(
                    task_id.strip(),
                    post=do_post,
                    learn=learn,
                    take_in_work=do_take,
                    trigger="ui",
                )
                if result.get("skipped"):
                    st.warning(f"Пропуск: {result.get('reason')}")
                else:
                    st.success(f"Готово · run_id={result.get('pipeline_run_id')}")
                st.code(result.get("comment_preview") or "(пусто)")
                st.json(
                    {
                        "skipped": result.get("skipped"),
                        "reason": result.get("reason"),
                        "kb_learning": result.get("kb_learning"),
                        "take_in_work": result.get("take_in_work"),
                        "link_related": result.get("link_related"),
                    }
                )
            except Exception as exc:
                st.error(str(exc))

with tab_hist:
    summary = call_history.summarize()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("LLM вызовы", summary.get("llm_calls") or 0)
    c2.metric("partner-lk (UI hint)", summary.get("partner_lk_calls") or 0)
    c3.metric("Попытки AI-KB", summary.get("kb_learn_attempts") or 0)
    c4.metric("Статьи/черновики OK", summary.get("kb_articles_written") or 0)
    st.caption(
        f"Карточка UI: {summary.get('partner_lk_hint')} · "
        "Полный промпт/ответ — в `_analysis_<id>.json` (см. ниже)."
    )
    st.subheader("Разбор заявки (артефакт)")
    hist_task = st.text_input("Номер заявки", placeholder="699197", key="hist_task_id")
    if hist_task.strip():
        analysis_mod = _load_src_module("analysis_artifact")
        analysis = analysis_mod.load_analysis(hist_task.strip())
        if analysis:
            st.markdown(f"Найден анализ заявки #{hist_task.strip()}")
            lr = analysis.get("llm_request") or {}
            has_full = bool(
                (lr.get("user_message") or "").strip()
                or any(
                    m.get("role") == "user" and (m.get("content") or "").strip()
                    for m in (lr.get("messages") or [])
                )
            )
            st.caption(
                f"API: {lr.get('api_base') or '—'} · "
                f"запрошена: {lr.get('model_requested') or analysis.get('profile', {}).get('model')} · "
                f"использована: {lr.get('model_used') or analysis.get('profile', {}).get('model')} · "
                f"fallback: {lr.get('fallback_used', '—')}"
            )
            if not has_full:
                st.warning(
                    "В этом артефакте нет сохранённого промпта (разбор до обновления). "
                    "Ниже — восстановленные фрагменты. Для полного текста перезапустите разбор."
                )
            user_msg, user_src = analysis_mod.extract_user_prompt(analysis)
            system_msg, system_src = analysis_mod.extract_system_prompt(analysis)
            with st.expander("Промпт user (что ушло в LLM)", expanded=True):
                st.caption(f"Источник: {user_src}")
                st.text_area(
                    "user message",
                    user_msg,
                    height=360,
                    disabled=True,
                    label_visibility="collapsed",
                )
            with st.expander("Промпт system (правила + корпус + prefetch)", expanded=False):
                st.caption(f"Источник: {system_src}")
                if system_msg.strip():
                    st.text_area(
                        "system message",
                        system_msg,
                        height=280,
                        disabled=True,
                        label_visibility="collapsed",
                    )
                else:
                    st.caption("System-промпт не сохранён — переразберите заявку.")
            with st.expander("Ответ LLM (content)", expanded=False):
                content = analysis_mod.extract_assistant_content(analysis)
                st.text_area(
                    "assistant content",
                    content,
                    height=280,
                    disabled=True,
                    label_visibility="collapsed",
                )
            with st.expander("Вложения (ocr)", expanded=False):
                st.json(analysis.get("ocr") or {})
            with st.expander("Скрытый комментарий (preview)", expanded=False):
                st.code(analysis.get("comment_preview") or "")
        else:
            st.info(f"Нет артефакта анализа для заявки #{hist_task.strip()} — сначала разберите заявку (вкладка «Запуск»).")
    st.divider()
    st.subheader("Последние partner-lk / UI-hint")
    st.json(summary.get("recent_partner") or [])
    st.subheader("Последние LLM")
    st.json(summary.get("recent_llm") or [])
    st.subheader("AI-KB learn")
    st.json(summary.get("recent_learns") or [])
    st.caption(f"Файл: `{summary.get('history_file')}`")

with tab_overdue:
    st.markdown(
        "Заявки, которые локальный робот взял после эскалации "
        "**«До просрочки»** (`scripts/watch_overdue.py` / Task Scheduler)."
    )
    list_fn = getattr(call_history, "list_overdue_taken", None)
    if callable(list_fn):
        overdue_rows = list_fn(100)
    else:
        st.error(
            f"Модуль call_history без list_overdue_taken: `{getattr(call_history, '__file__', '?')}`. "
            "Перезапустите `streamlit run app.py` из `chatbot_intraservice/`."
        )
        overdue_rows = (call_history.summarize().get("overdue_taken") or []) if hasattr(call_history, "summarize") else []
    st.metric("Всего в отчёте", len(overdue_rows))
    if not overdue_rows:
        st.info("Пока пусто — появятся после срабатывания watch_overdue.")
    else:
        for row in overdue_rows:
            tid = row.get("task_id")
            title = f"#{tid}"
            if row.get("skipped"):
                title += " · skip"
            elif row.get("handled") or row.get("ok"):
                title += " · взята"
            with st.expander(f"{title} · {row.get('at') or row.get('last_event_ts') or ''}"):
                st.markdown(f"[Открыть в HelpDesk]({row.get('url')})")
                st.json(row)

with tab_kb:
    kb_learning_mod = _load_src_module("kb_learning")
    kb_promote_preview = _load_src_module("kb_promote_preview")
    drafts_ui = _load_src_module("kb_drafts_ui")
    st.markdown(
        """
**Самообучение AI-KB** — ревью по командам **ЛК · БП · 1С · CRM**.

1. Выберите команду и черновик.
2. Правьте **Текст для Promote** (сценарий + шаги, без переписки HD).
3. **Promote** — в «Быстрые ответы»; **Отклонить** — с причиной (учтётся при learn).
        """
    )
    learn_journal_mod = _load_src_module("learn_journal")
    events = learn_journal_mod.load_events(25)
    with st.expander(f"Журнал самообучения ({len(events)} последних)"):
        if not events:
            st.caption("Пока пусто — появится после `pipeline_watch` / `--learn`.")
        else:
            for ev in reversed(events):
                tid = ev.get("task_id") or "?"
                mode = ev.get("mode") or ev.get("gap_mode") or ""
                ok = "✓" if ev.get("ok") else ("skip" if ev.get("skipped") else "✗")
                st.markdown(
                    f"**#{tid}** · {ok} · `{mode}` · {ev.get('at', '')[:19]}"
                )
                reason = ev.get("reason") or ""
                if reason:
                    st.caption(reason[:200])
                lesson = ev.get("kb_lesson") or ""
                if lesson:
                    st.caption(f"Урок: {lesson[:180]}")

    refresh_col, _ = st.columns([1, 4])
    with refresh_col:
        if st.button("Обновить список", key="kb_refresh_list"):
            st.rerun()

    try:
        import subprocess

        pending, published, rejected, digest_mod = drafts_ui.load_all_lists()
        counts = drafts_ui.count_pending_by_team(pending)

        team_labels = {k: drafts_ui.team_radio_label(k, counts) for k in drafts_ui.TEAM_ORDER}
        team = st.radio(
            "Команда техподдержки",
            options=[k for k in drafts_ui.TEAM_ORDER],
            format_func=lambda k: team_labels[k],
            horizontal=True,
            key="kb_team_filter",
        )
        target_md = drafts_ui.team_target_markdown(team)
        if target_md:
            st.info(target_md)
        elif team == "other":
            st.caption("Прочие контуры: mail, vpn, kp — Promote в общий раздел или вручную.")

        q_col, view_col = st.columns([2, 1])
        with q_col:
            search_q = st.text_input(
                "Поиск",
                placeholder="код, #заявки, ключевое слово в тексте",
                key="kb_draft_search",
            )
        with view_col:
            view = st.selectbox(
                "Статус",
                ["На ревью", "Опубликованные", "Отклонённые"],
                key="kb_draft_view",
            )

        if view == "На ревью":
            rows = drafts_ui.filter_team(pending, team)
            rows = drafts_ui.search_filter(rows, search_q)
            local_n = sum(1 for p in rows if not p.get("confluence_draft_page_id"))
            cf_n = sum(1 for p in rows if p.get("confluence_draft_page_id"))
            m1, m2, m3 = st.columns(3)
            m1.metric("На ревью", len(rows))
            m2.metric("Только локально", local_n)
            m3.metric("В Confluence", cf_n)
            if not rows:
                st.info("Нет черновиков на ревью для выбранной команды.")
            else:
                for p in rows:
                    with st.expander(
                        drafts_ui.draft_card_title(p).replace("**", ""),
                        expanded=False,
                    ):
                        _render_draft_review_card(
                            p,
                            kb_learning_mod=kb_learning_mod,
                            kb_promote_preview_mod=kb_promote_preview,
                            prefix=team,
                        )

        elif view == "Опубликованные":
            rows = drafts_ui.filter_team(published, team)
            rows = drafts_ui.search_filter(rows, search_q)
            st.metric("Опубликовано", len(rows))
            if not rows:
                st.caption("После Promote статья появится здесь — ссылка на «Быстрые ответы».")
            else:
                for p in rows[:25]:
                    url = p.get("published_url") or ""
                    when = (p.get("published_at") or "")[:16].replace("T", " ")
                    line = f"**{p.get('code')}** · #{p.get('task_id')} · {when}"
                    preview = drafts_ui.draft_preview_line(p)
                    if preview:
                        line += f" — {preview}"
                    if url:
                        st.markdown(
                            f"{line} · [Быстрые ответы]({url}) · [HD]({p.get('helpdesk_url')})"
                        )
                    else:
                        st.markdown(f"{line} · [HD]({p.get('helpdesk_url')})")

        else:
            rows = drafts_ui.filter_team(rejected, team)
            rows = drafts_ui.search_filter(rows, search_q)
            st.metric("Отклонено", len(rows))
            if not rows:
                st.caption("Причины reject попадут в следующий learn.")
            else:
                for p in rows:
                    tid = str(p.get("task_id") or "")
                    with st.expander(
                        f"{p.get('code')} · #{tid} · {p.get('rejected_at', '')[:10]}",
                        expanded=False,
                    ):
                        st.caption(p.get("rejection_reason") or "без причины")
                        if p.get("confluence_url"):
                            st.markdown(f"[Confluence]({p.get('confluence_url')})")
                        _render_draft_body(kb_learning_mod, p)

        latest = ROOT / "pipeline" / "digests" / "drafts_review_latest.md"
        if latest.is_file():
            with st.expander("Служебный digest (markdown-файл)"):
                st.caption(f"`{latest.name}` — сводка для почты/Scheduler, не основной UI")
                st.markdown(latest.read_text(encoding="utf-8")[:8000])
        if st.button("Пересобрать digest-файл", key="kb_rebuild_digest"):
            r = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "drafts_review_digest.py")],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if r.returncode == 0:
                st.success("Digest обновлён")
                st.rerun()
            else:
                st.error((r.stderr or r.stdout or "error")[:800])
    except Exception as exc:
        st.error(str(exc))

with tab_prompts:
    prompt_store = _load_src_module("prompt_store")
    st.markdown(
        """
Как собирается запрос к IEK LLM при разборе заявки:

1. **System extra** профиля (ЛК / БП / 1С / CRM)
2. **Правила** разбора + (для не-БП) фрагмент правил 1 линии
3. **Корпус** выбранного контура (локальный markdown)
4. Черновики AI-KB / prefetch Confluence (если есть)
5. **Хвост «Важно»**
6. **User:** схема JSON + данные заявки (описание, вложения, adm/lk-admin/1С, prior)

Правки сохраняются в файлы на диске и сразу действуют на следующий разбор.
        """
    )
    kind_filter = st.radio(
        "Показать",
        ["Все", "Промпты", "Корпуса", "Правила"],
        horizontal=True,
        key="prompt_kind_filter",
    )
    kind_map = {"Все": None, "Промпты": "prompt", "Корпуса": "corpus", "Правила": "rules"}
    assets = prompt_store.list_assets(kind=kind_map[kind_filter])
    labels = {f"{a.title} · `{a.key}`": a.key for a in assets}
    if not labels:
        st.info("Нет файлов в этой группе.")
    else:
        pick = st.selectbox("Файл", list(labels.keys()), key="prompt_asset_pick")
        asset_key = labels[pick]
        asset = prompt_store.get_asset(asset_key)
        assert asset is not None
        rel = str(asset.path.relative_to(ROOT)).replace("\\", "/")
        st.caption(f"`{rel}` · {asset.path.stat().st_size if asset.path.is_file() else 0} байт")
        if asset.max_chars_hint:
            st.caption(
                f"В промпт уходит не больше ~{asset.max_chars_hint} символов "
                "(остальное обрезается при сборке)."
            )
        text0 = prompt_store.read_asset(asset_key)
        edited = st.text_area(
            "Содержимое",
            value=text0,
            height=420,
            key=f"prompt_editor_{asset_key}",
        )
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            if st.button("Сохранить", type="primary", key="prompt_save"):
                if edited.strip() == text0.strip() and edited == text0:
                    st.info("Без изменений.")
                else:
                    path = prompt_store.write_asset(asset_key, edited)
                    st.success(f"Сохранено: {path.name}")
                    st.rerun()
        with c2:
            if st.button("Перезагрузить с диска", key="prompt_reload"):
                st.rerun()
        with c3:
            st.caption("Не коммитьте секреты. Корпуса — обезличенные сценарии без email.")

    with st.expander("Схема сборки (кратко)", expanded=False):
        st.code(
            "system = system_extra + ПРАВИЛА + КОРПУС + footer + confluence_prefetch\n"
            "user   = user_schema + adm/lk/1С + заявка + вложения + prior + similar",
            language="text",
        )
    with st.expander("Все assets", expanded=False):
        st.json(prompt_store.asset_meta())

with tab_runs:
    runs = PipelineRun.list_runs(limit=25)
    if not runs:
        st.info("Прогонов пока нет.")
    else:
        for run in runs:
            with st.expander(
                f"#{run.get('task_id')} · {run.get('run_id')} · {run.get('status')} · {run.get('trigger')}"
            ):
                st.json(run)

with tab_docs:
    st.markdown(
        """
**Scheduler (автономное отслеживание)**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\\install_scheduler.ps1
python scripts\\watch_new.py --dry-run
python scripts\\watch_user_reply.py --dry-run
python scripts\\watch_overdue.py --dry-run
python scripts\\weekly_gap_digest.py --dry-run
```

| Watch | Когда | Действие |
|:--|:--|:--|
| `watch_new` | 31/38/121 | разбор; пост/take только если авто-флаги |
| `watch_user_reply` | 46/120 + ответ **заявителя** | «спасибо» → **120** + публичный; уточнение/«не помогло» → **38** |
| `watch_overdue` | эскалация робота | скрытый + дедлайн + открытый |
| `pipeline_watch` | 28/29 закрыта | черновик AI-KB (нужен master) |
| `weekly_gap_digest` | вс 09:00 | пробелы KB без черновика |

**После ревью:** Promote в Streamlit или `python scripts/sync_kb_after_review.py --task-id <id>`  
Папка самообучения: https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124640307  
Smoke L1 Simple: см. README § «L1 Simple».

**Open WebUI:** `docs/openwebui_bp_1c_helpers.md` · create: `scripts/create_owui_bp_1c_models.py`

**Skip «В работе»:** 27/46/120 без эскалации → skip (кроме watch_user_reply / overdue).
        """
    )
