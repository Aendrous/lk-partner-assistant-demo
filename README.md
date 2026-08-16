---
title: Помощник партнёра ЛК (демо)
emoji: 💬
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Помощник партнёра ЛК (демо)

**С телефона:** после деплоя Streamlit Cloud. Репозиторий: [Aendrous/lk-partner-assistant-demo](https://github.com/Aendrous/lk-partner-assistant-demo)

Чат для **сотрудников компаний-партнёров IEK** по личному кабинету [lk.iek.ru](https://lk.iek.ru). Открывается в браузере, в том числе **с телефона**, отдельно от кабинета.

Это **пилот**, не официальный виджет ЛК и не внутренний `chatgpt.iek.local`. Ответы даёт **GigaChat** (Сбер) по корпусу инструкций P-00…P-17. Не остатки и не цены из 1С.

**Ключ API в этом пилоте — личный `GIGACHAT_API_PERS` (Freemium, источник ClubOfSisters), не корпоративный прод IEK.** Для продакшена IEK нужен отдельный ключ, scope CORP и согласование ИБ.

Сбои кабинета — **hd@iek.ru**. Справка: [lk.iek.ru/lk/help](https://lk.iek.ru/lk/help/). Ролики: [dzen.ru/lk_iek_ru](https://dzen.ru/lk_iek_ru).

Ключ **не класть** в git, GitHub Pages и репозитории IEK-GROUP.

## Локально (компьютер и телефон в той же Wi‑Fi)

```powershell
cd "C:\Users\fetisovaa\AI Assistant IEK"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\.venv\Scripts\python.exe chat.py "Как создать заказ в ЛК?"
.\.venv\Scripts\python.exe app.py
# чат: http://localhost:7860  (с телефона в Wi‑Fi: http://<IPv4>:7860)
```

CLI: `python chat.py --repl`

## Хостинг Hugging Face

Чат — **FastAPI** (`GET /` HTML, `POST /api/chat`), Docker: `uvicorn app:app --host 0.0.0.0 --port 7860`.

На бесплатном аккаунте **не живёт**:

- SDK Docker / CPU Basic → HTTP 402, нужен [HF PRO](https://huggingface.co/pro).
- Бесплатный ZeroGPU работает только с Gradio SDK и **убивает uvicorn** (`No @spaces.GPU function detected`), даже когда сервер уже слушал 7860.

Чтобы URL `https://aendrous-lk-partner-assistant-demo.hf.space/` открыл HTML-чат: PRO → Settings → Hardware **CPU Basic** → Restart (секреты `GIGACHAT_*` уже в Space).

Бесплатная альтернатива с телефона: Streamlit Community Cloud + `streamlit_app.py` (нужен публичный GitHub, не IEK-GROUP). Скажите «запушить?».

В CLI **нет** аккаунта Streamlit Cloud и **нет** `HF_TOKEN` (в ClubOfSisters поле пустое). Нужен один логин в браузере. Ключ только в Secrets хостинга.

GitHub CLI на этой машине уже вошёл как **Aendrous**. Репозиторий ещё не создавали, **коммит и push не делали** — скажите «запушить?», если нужно.

### Вариант A — Hugging Face Spaces (удобно с телефона)

1. Откройте [huggingface.co/new-space](https://huggingface.co/new-space) (бесплатный аккаунт).
2. Имя, например `lk-partner-assistant-demo`. **SDK: Streamlit**. Visibility: Public (иначе с телефона нужен логин HF).
3. В Space → **Files** загрузите из этой папки (без `.env` и `.venv`):
   - `app.py`, `chat.py`, `gigachat_client.py`, `rag.py`, `prompt.md`, `requirements.txt`
   - `knowledge/corpus.md`
   - `.streamlit/config.toml`
   - этот `README.md`
4. Space → **Settings → Variables and secrets → New secret**:
   - `GIGACHAT_AUTHORIZATION_KEY` — тот же Authorization Key, что в локальном `.env`
   - `GIGACHAT_SCOPE` = `GIGACHAT_API_PERS`
   - `GIGACHAT_MODEL` = `GigaChat-3-Ultra`
5. Дождитесь `Running`. Ссылка вида `https://huggingface.co/spaces/<логин>/lk-partner-assistant-demo` — её и открывать с телефона. Прямой app: `https://<логин>-lk-partner-assistant-demo.hf.space`.

Через git (после вашего «запушить?»):

```powershell
cd "C:\Users\fetisovaa\AI Assistant IEK"
git init
git add app.py chat.py gigachat_client.py rag.py prompt.md requirements.txt knowledge .streamlit/config.toml README.md Dockerfile Procfile runtime.txt .gitignore .dockerignore .env.example
git commit -m "Demo: partner LK assistant on GigaChat"
git remote add hf https://huggingface.co/spaces/<логин>/lk-partner-assistant-demo
git push hf main
```

### Streamlit Community Cloud (основной публичный деплой)

Репозиторий: https://github.com/Aendrous/lk-partner-assistant-demo

1. [share.streamlit.io](https://share.streamlit.io) → **New app**
2. Repository: `Aendrous/lk-partner-assistant-demo`, branch `main`
3. Main file: **`streamlit_app.py`**
4. **App settings → Secrets** (TOML, значения из локального `.env`, не в git):

```toml
GIGACHAT_AUTHORIZATION_KEY = "вставьте ключ"
GIGACHAT_SCOPE = "GIGACHAT_API_PERS"
GIGACHAT_MODEL = "GigaChat-3-Ultra"
```

5. Deploy. Ссылка будет вида `https://lk-partner-assistant-demo-aendrous.streamlit.app` (точное имя покажет Cloud).

Не класть ключ в GitHub Pages и не в IEK-GROUP.

## Docker (по желанию)

Ключ передавайте переменной окружения, не копируйте `.env` в образ.

```powershell
docker build -t lk-partner-demo .
docker run --rm -p 8501:7860 -e GIGACHAT_AUTHORIZATION_KEY -e GIGACHAT_SCOPE=GIGACHAT_API_PERS -e GIGACHAT_MODEL=GigaChat-3-Ultra lk-partner-demo
```

`Procfile` — для PaaS вроде Railway/Render: тот же `streamlit run app.py`.

## Как устроен чат

| Файл | Роль |
|:---|:---|
| `prompt.md` | Системный промпт (партнёр, ЛК 3.0, hd@iek.ru) |
| `knowledge/corpus.md` | Корпус how-to P-00…P-17 |
| `rag.py` | Отбор разделов корпуса |
| `gigachat_client.py` | OAuth + chat/completions |
| `chat.py` | CLI |
| `streamlit_app.py` | Streamlit (Cloud и локально) |
| `app.py` | FastAPI (`GET /`, `POST /api/chat`) |

OAuth: `https://ngw.devices.sberbank.ru:9443/api/v2/oauth` → `https://api.giga.chat/v1/chat/completions`, модель `GigaChat-3-Ultra`.

## Чего здесь нет

- Не публикуем Confluence.
- Не трогаем `support-dep-lk-web-helper`, chatgpt.iek.local и страницы Казенникова.
- Ключ не кладём на GitHub Pages (ClubOfSisters) и не в IEK-GROUP.
