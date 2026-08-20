# -*- coding: utf-8 -*-
"""Веб-чат помощника партнёра ЛК (Streamlit).

Локально: шлюз IEK LLM + карточка из каталога ЛК.
Streamlit Cloud: GigaChat (секреты Cloud), без внутренних *.iek.local.
"""
from __future__ import annotations

import re

import streamlit as st

from gigachat_client import (
    GigaChatClient,
    has_credentials,
    load_runtime_secrets,
    secrets_load_error,
)
from rag import system_prompt

st.set_page_config(
    page_title="Помощник партнёра ЛК",
    page_icon="💬",
    layout="centered",
    initial_sidebar_state="collapsed",
)

load_runtime_secrets()

QUICK = [
    "Как создать заказ в ЛК?",
    "Где трекинг заказов?",
    "Как оформить заказ из корзины?",
    "Склады и кратность — как выбрать?",
    "Добавил товар, а корзина пустая",
    "Что такое неудовлетворённый спрос?",
    "Как подтвердить отгрузку и счета?",
    "Как сделать возврат?",
    "Как импортировать артикулы из Excel?",
    "Как найти товар из буфера обмена?",
    "Спеццены через Excel — как загрузить?",
    "Как оформить заказ на Контактор?",
    "Где в каталоге Честный знак?",
    "Как считаются зональные цены?",
    "Когда платная доставка?",
    "Где новинки СПК?",
    "Профиль и сотрудники — кого добавить?",
    "Не могу войти: логин и пароль",
    "Куда писать, если кабинет не открывается?",
    "Где Школа партнёра и PDF?",
    "Что такое резервы в пути?",
    "Как отказаться от товара до отгрузки?",
    "Добавил из тендера — корзина пустая",
    "Куда писать идеи по кабинету?",
]
QUICK_SET = {item.lower() for item in QUICK}
SAMPLE_ART = "MKM14-N-18-31-Z"
ART_RE = re.compile(r"\b[A-Z0-9]{2,}(?:-[A-Z0-9]{1,}){2,}\b", re.I)

st.markdown(
    """
    <style>
      div[data-testid="stCaptionContainer"] { letter-spacing: .04em; }
      div[data-testid="stButton"] button {
        border: 1px solid #ccc; background: #fff; color: #1a1a1a;
        font-weight: 500; text-align: left; white-space: normal; height: auto;
        padding: .35rem .65rem; border-radius: 8px;
      }
      div[data-testid="stButton"] button:hover { border-color: #e30613; color: #e30613; }
      .art-tile { border: 1px solid #e30613; background: #fff8f8; border-radius: 8px;
                  padding: 8px 10px; margin-bottom: 8px; }
      .art-tile .k { font-size: .68rem; letter-spacing: .05em; text-transform: uppercase;
                     color: #e30613; font-weight: 700; }
      .art-tile .v { font-family: ui-monospace, Consolas, monospace; font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Помощник партнёра ЛК")
st.caption("How-to по кабинету и карточка товара из каталога ЛК по артикулу")

st.info(
    "Нажмите артикул ниже или вставьте свой — покажу карточку из каталога lk.iek.ru. "
    "How-to — по инструкциям ЛК 3.0. Живых заказов в Open API нет: трекинг в кабинете. "
    "Сбои — **hd@iek.ru**.",
    icon="ℹ️",
)

with st.expander("Ссылки и бэкенд"):
    st.markdown(
        "- Кабинет: [lk.iek.ru](https://lk.iek.ru)\n"
        "- Справка: [lk.iek.ru/lk/help](https://lk.iek.ru/lk/help/)\n"
        "- Ролики: [dzen.ru/lk_iek_ru](https://dzen.ru/lk_iek_ru)\n"
        "- Сбои: **hd@iek.ru**. Идеи: wishes-lk@iek.ru"
    )
    try:
        from agent import status_line

        st.caption(f"Шлюз: `{status_line()}`")
    except Exception:
        st.caption("Облако: GigaChat. Живой каталог ЛК — на офисном шлюзе.")


def _gateway_ask():
    try:
        from agent import ask as gateway_ask

        return gateway_ask
    except ImportError:
        return None


def _lookup_product(art: str) -> dict:
    try:
        from catalog import fetch_product

        return fetch_product(art)
    except Exception:
        return {
            "ok": False,
            "art": art,
            "name": "",
            "pills": [],
            "empty": (
                "Живая карточка из ЛК доступна на офисном шлюзе. "
                "Здесь отвечу по инструкциям: Заказы → + Новый заказ, поиск по артикулу."
            ),
            "source": "Каталог lk.iek.ru",
        }


def _chat_answer(question: str, history: list[dict[str, str]]) -> str:
    gateway = _gateway_ask()
    if gateway is not None:
        return gateway(question, history=history, temperature=0.15)
    client = st.session_state.setdefault("giga", GigaChatClient())
    messages = [{"role": "system", "content": system_prompt(question)}]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": question})
    return client.chat(messages, temperature=0.15)


def _extract_art(text: str) -> str:
    match = ART_RE.search(text or "")
    return match.group(0).upper() if match else ""


def _use_example(text: str) -> None:
    st.session_state.pending_question = text
    st.session_state.pending_art = _extract_art(text)


def _remember(text: str) -> None:
    item = (text or "").strip()
    if not item:
        return
    prev = [x for x in st.session_state.recent if x.lower() != item.lower()]
    st.session_state.recent = [item, *prev][:12]


def _chip_select(label: str, options: list[str], key: str):
    if not options:
        return None
    if hasattr(st, "pills"):
        return st.pills(label, options, label_visibility="collapsed", key=key)
    cols = st.columns(min(2, len(options)))
    for index, item in enumerate(options):
        if cols[index % len(cols)].button(item, key=f"{key}_{index}"):
            return item
    return None
    with st.container(border=True):
        st.markdown("**Карточка из ЛК**")
        st.markdown(f"`{card.get('art') or '—'}`")
        if card.get("name"):
            st.write(card["name"])
        pills = card.get("pills") or []
        if pills:
            st.caption(" · ".join(pills))
        if card.get("empty"):
            st.caption(card["empty"])
        st.caption(card.get("source") or "Каталог lk.iek.ru")


gateway = _gateway_ask()
if gateway is None and not has_credentials():
    st.error(
        "Нет ключа LLM. Локально задайте `IEK_LLM_TOKEN` или GigaChat в `.env`. "
        "На Streamlit Cloud: **⋮ → Settings → Secrets**."
    )
    st.code(
        'GIGACHAT_AUTHORIZATION_KEY = "ваш_ключ"\n'
        'GIGACHAT_SCOPE = "GIGACHAT_API_PERS"\n'
        'GIGACHAT_MODEL = "GigaChat-3-Ultra"',
        language="toml",
    )
    hint = secrets_load_error()
    if hint:
        st.warning(f"Secrets не прочитались ({hint}). Нужен TOML, не формат `.env`.")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = ""
if "pending_art" not in st.session_state:
    st.session_state.pending_art = ""
if "recent" not in st.session_state:
    st.session_state.recent = []
if "pill_prev" not in st.session_state:
    st.session_state.pill_prev = None
if "art_prev" not in st.session_state:
    st.session_state.art_prev = None
if "recent_prev" not in st.session_state:
    st.session_state.recent_prev = None

st.caption("БЫСТРЫЕ ВОПРОСЫ")
picked = _chip_select("Быстрые вопросы", QUICK, "quick_pills")
if picked and picked != st.session_state.pill_prev:
    st.session_state.pill_prev = picked
    _use_example(picked)

recent_extra = [q for q in st.session_state.recent if q.lower() not in QUICK_SET]
if recent_extra:
    st.caption("НЕДАВНИЕ")
    recent_pick = _chip_select("Недавние", recent_extra, "recent_pills")
    if recent_pick and recent_pick != st.session_state.recent_prev:
        st.session_state.recent_prev = recent_pick
        _use_example(recent_pick)

st.caption("КАРТОЧКА ИЗ ЛК")
st.markdown(
    '<div class="art-tile"><div class="k">Артикул из каталога кабинета</div>'
    f'<div class="v">{SAMPLE_ART}</div>'
    "<div>Наименование, цена, НДС — как плашка, только карточка товара</div></div>",
    unsafe_allow_html=True,
)
art_pick = _chip_select("Примеры артикулов", [SAMPLE_ART], "art_pills")
if art_pick and art_pick != st.session_state.art_prev:
    st.session_state.art_prev = art_pick
    st.session_state.pending_art = art_pick
    st.session_state.pending_question = f"Что за артикул {art_pick}? Покажи карточку из каталога ЛК."

art_cols = st.columns([3, 1])
with art_cols[0]:
    art_typed = st.text_input(
        "Артикул",
        placeholder="Вставьте артикул, например MKM14-N-18-31-Z",
        label_visibility="collapsed",
        key="art_input",
    )
with art_cols[1]:
    find_art = st.button("Найти в ЛК", use_container_width=True)
if find_art:
    code = (art_typed or "").strip().upper()
    if code:
        st.session_state.pending_art = code
        st.session_state.pending_question = f"Что за артикул {code}? Покажи карточку из каталога ЛК."
    else:
        st.warning("Вставьте артикул.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("card"):
            _render_card(msg["card"])
        if msg.get("content"):
            st.markdown(msg["content"])

typed = st.chat_input("Вопрос по кабинету или артикул из ЛК…")
question = st.session_state.pending_question or typed or ""
art = st.session_state.pending_art or _extract_art(question)
st.session_state.pending_question = ""
st.session_state.pending_art = ""

if question:
    _remember(question)
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[-12:]
        if m["role"] in {"user", "assistant"} and m.get("content")
    ]
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    card = _lookup_product(art) if art else None
    answer = ""
    with st.chat_message("assistant"):
        if card:
            _render_card(card)
        with st.spinner("Думаю…"):
            try:
                answer = _chat_answer(question, history)
            except Exception as err:
                answer = (
                    "Не удалось получить ответ. Если сбой в кабинете — напишите на hd@iek.ru. "
                    f"({err})"
                )
        st.markdown(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer, "card": card})
