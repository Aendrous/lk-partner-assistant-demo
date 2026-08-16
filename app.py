# -*- coding: utf-8 -*-
"""Простой веб-чат помощника партнёра ЛК (FastAPI). Без Gradio и ZeroGPU."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from gigachat_client import GigaChatClient, has_credentials, load_env
from rag import system_prompt

load_env()

try:
    import spaces
except ImportError:
    class spaces:
        @staticmethod
        def GPU(*_a, **_k):
            def deco(fn):
                return fn
            if _a and callable(_a[0]):
                return _a[0]
            return deco


@spaces.GPU(duration=10)
def _zerogpu_placeholder() -> str:
    """Нужна ZeroGPU-железу HF; чат идёт на CPU через GigaChat HTTP."""
    return "ok"


# ZeroGPU сканирует события Gradio, а не «голый» декоратор. UI — FastAPI на /.
import gradio as gr

with gr.Blocks(title="keepalive") as _zero:
    _out = gr.Textbox(visible=False)
    gr.Button(visible=False).click(_zerogpu_placeholder, outputs=_out)


app = FastAPI(title="Помощник партнёра ЛК (демо)", docs_url=None, redoc_url=None)
_giga: GigaChatClient | None = None

PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Помощник партнёра ЛК (демо)</title>
  <style>
    :root { color-scheme: light; }
    body { font-family: system-ui, Segoe UI, sans-serif; margin: 0; background: #f5f5f5; color: #1a1a1a; }
    main { max-width: 720px; margin: 0 auto; padding: 16px; }
    h1 { font-size: 1.35rem; color: #e30613; margin: 0 0 8px; }
    .note { background: #fff3cd; border: 1px solid #ffe08a; padding: 10px 12px; border-radius: 8px; font-size: .92rem; }
    .links { font-size: .9rem; margin: 10px 0 14px; }
    #log { background: #fff; border: 1px solid #ddd; border-radius: 8px; min-height: 240px; max-height: 55vh; overflow: auto; padding: 12px; }
    .msg { margin: 0 0 12px; }
    .msg b { display: block; font-size: .8rem; color: #666; margin-bottom: 4px; }
    .row { display: flex; gap: 8px; margin-top: 10px; }
    textarea { flex: 1; min-height: 64px; padding: 10px; border-radius: 8px; border: 1px solid #ccc; font: inherit; }
    button { background: #e30613; color: #fff; border: 0; border-radius: 8px; padding: 10px 14px; font: inherit; cursor: pointer; }
    button:disabled { opacity: .6; }
    .ex { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
    .ex button { background: #fff; color: #1a1a1a; border: 1px solid #ccc; font-size: .85rem; padding: 6px 10px; }
  </style>
</head>
<body>
<main>
  <h1>Помощник партнёра ЛК (демо)</h1>
  <p class="note">Пилот. Не официальный виджет ЛК. Не остатки и не цены из 1С — смотрите их в кабинете после выбора плательщика, адреса и склада. Сбои кабинета — <b>hd@iek.ru</b>. Ключ GigaChat — личный PERS, не прод IEK.</p>
  <p class="links">Кабинет: <a href="https://lk.iek.ru">lk.iek.ru</a> · справка: <a href="https://lk.iek.ru/lk/help/">lk.iek.ru/lk/help</a> · ролики: <a href="https://dzen.ru/lk_iek_ru">dzen.ru/lk_iek_ru</a></p>
  <div class="ex">
    <button type="button" data-q="Как создать заказ в ЛК?">Как создать заказ в ЛК?</button>
    <button type="button" data-q="Где трекинг заказов?">Где трекинг заказов?</button>
    <button type="button" data-q="Куда писать, если кабинет не открывается?">Куда писать при сбое?</button>
  </div>
  <div id="log"></div>
  <form class="row" id="f">
    <textarea id="q" placeholder="Вопрос по личному кабинету…" required></textarea>
    <button type="submit" id="go">Спросить</button>
  </form>
</main>
<script>
const log = document.getElementById("log");
const q = document.getElementById("q");
const go = document.getElementById("go");
function add(who, text) {
  const d = document.createElement("div");
  d.className = "msg";
  d.innerHTML = "<b>" + who + "</b>";
  const p = document.createElement("div");
  p.textContent = text;
  d.appendChild(p);
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
}
async function ask(text) {
  add("Вы", text);
  go.disabled = true;
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message: text})
    });
    const data = await r.json();
    add("Помощник", data.answer || data.detail || "Нет ответа");
  } catch (e) {
    add("Помощник", "Не удалось связаться с сервером. Обновите страницу или напишите на hd@iek.ru, если сбой в кабинете.");
  }
  go.disabled = false;
}
document.getElementById("f").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const text = q.value.trim();
  if (!text) return;
  q.value = "";
  ask(text);
});
document.querySelectorAll(".ex button").forEach((b) => {
  b.addEventListener("click", () => ask(b.getAttribute("data-q")));
});
</script>
</body>
</html>
"""


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def get_client() -> GigaChatClient:
    global _giga
    if _giga is None:
        if not has_credentials():
            raise HTTPException(
                status_code=503,
                detail="Нет ключа GigaChat. В Space → Settings → Secrets задайте GIGACHAT_AUTHORIZATION_KEY.",
            )
        _giga = GigaChatClient()
    return _giga


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return PAGE


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
def api_chat(body: ChatIn) -> dict[str, Any]:
    question = body.message.strip()
    try:
        answer = get_client().chat(
            [
                {"role": "system", "content": system_prompt(question)},
                {"role": "user", "content": question},
            ],
            temperature=0.15,
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(
            status_code=502,
            detail=f"Не удалось получить ответ GigaChat. Если сбой в кабинете — hd@iek.ru. ({err})",
        ) from err
    return {"answer": answer}


try:
    app = gr.mount_gradio_app(app, _zero, path="/_zero")
except Exception:
    pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7860, log_level="info")
