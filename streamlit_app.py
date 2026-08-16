# -*- coding: utf-8 -*-
"""Веб-чат помощника партнёра ЛК на GigaChat (Streamlit).

Локально и Streamlit Community Cloud: streamlit run streamlit_app.py
"""
from __future__ import annotations

import streamlit as st

from gigachat_client import GigaChatClient, has_credentials, load_runtime_secrets
from rag import system_prompt

load_runtime_secrets()

st.set_page_config(
    page_title="Помощник партнёра ЛК (демо)",
    page_icon="💬",
    layout="centered",
    initial_sidebar_state="collapsed",
)

EXAMPLES = (
    "Как создать заказ в ЛК?",
    "Где трекинг заказов?",
    "Куда писать, если кабинет не открывается?",
)

st.title("Помощник партнёра ЛК (демо)")
st.caption("Справка по личному кабинету партнёра · отдельно от lk.iek.ru")

st.info(
    "Пилот. Не официальный виджет ЛК. Не остатки и не цены из 1С — их смотрите в кабинете "
    "после выбора плательщика, адреса и склада. Сбои кабинета — **hd@iek.ru**. "
    "Ключ GigaChat — личный PERS (Freemium), не прод IEK.",
    icon="⚠️",
)

with st.expander("Ссылки и что это за чат"):
    st.markdown(
        "- Кабинет: [lk.iek.ru](https://lk.iek.ru)\n"
        "- Справка: [lk.iek.ru/lk/help](https://lk.iek.ru/lk/help/)\n"
        "- Ролики: [dzen.ru/lk_iek_ru](https://dzen.ru/lk_iek_ru)\n"
        "- Сбои: **hd@iek.ru** (номер заказа, скрин, время). Идеи: wishes-lk@iek.ru\n"
        "- Модель: **GigaChat**. Это не внутренний chatgpt.iek.local и не виджет внутри ЛК."
    )

if not has_credentials():
    st.error(
        "Нет ключа GigaChat. Локально: скопируйте `.env.example` → `.env`. "
        "На хостинге: Secrets → `GIGACHAT_AUTHORIZATION_KEY` (и scope PERS)."
    )
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "client" not in st.session_state:
    st.session_state.client = GigaChatClient()
if "pending_question" not in st.session_state:
    st.session_state.pending_question = ""


def _use_example(text: str) -> None:
    st.session_state.pending_question = text


cols = st.columns(len(EXAMPLES))
for col, sample in zip(cols, EXAMPLES):
    col.button(sample, on_click=_use_example, args=(sample,), use_container_width=True)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

typed = st.chat_input("Вопрос по личному кабинету…")
question = st.session_state.pending_question or typed
st.session_state.pending_question = ""

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("GigaChat…"):
            try:
                history = [{"role": "system", "content": system_prompt(question)}]
                for msg in st.session_state.messages[-8:]:
                    history.append({"role": msg["role"], "content": msg["content"]})
                answer = st.session_state.client.chat(history, temperature=0.15)
            except Exception as err:
                answer = (
                    "Не удалось получить ответ GigaChat. Если сбой в кабинете — напишите на hd@iek.ru. "
                    f"({err})"
                )
        st.markdown(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})
