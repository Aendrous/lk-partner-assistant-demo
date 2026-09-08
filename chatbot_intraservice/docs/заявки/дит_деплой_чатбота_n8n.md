# Заявка в IntraService: развёртывание чатбота L1 на сервере n8n

**Куда подавать:** сервис **ДИТ / инфраструктура / серверы** (или владелец `n8n.iek.local`).  
Если в справочнике нет отдельного сервиса — **«Прочее IT / WEB»** с пометкой «маршрутизировать на администраторов n8n.iek.local».

**Инициатор:** Фетисов А. (разработка «IEK: Помощник сотрудника» / чатбот 1 линии HelpDesk).

---

## Тема заявки (копировать в поле «Название»)

```
Развёртывание IEK IntraService Chatbot на хосте n8n.iek.local (co-located): HTTP API :8765 и Streamlit UI :8502
```

---

## Описание (копировать в поле «Описание»)

### Контекст

Внедряем **«IEK: Помощник сотрудника»** — ассистент 1 линии HelpDesk: автоматический разбор заявок (скрытый комментарий исполнителю), опрос закрытых заявок для AI-KB.

**Оркестрация** уже переведена на **n8n.iek.local** (workflow **«IntraService HelpDesk Bot»**, id `paYsXt1HK1ZSAHXt`): по расписанию каждые 15/30 мин n8n вызывает HTTP API бота.

**Проблема сейчас:** API бота крутится на **ноутбуке разработчика**. При VPN/выключении ПК n8n получает `connection refused`. Ссылку на Streamlit с ноутбука коллеги из сети ИЭК открыть **нельзя** (VPN point-to-point, firewall).

**Нужно:** развернуть Python-приложение **на сервере рядом с n8n** (co-located), чтобы работа была **24/7** без привязки к ноутбуку.

Документация в репозитории (после выдачи доступа к git):

- `chatbot_intraservice/scripts/deploy/README.md`
- `chatbot_intraservice/scripts/deploy/iek-intraservice-n8n-api.service`
- `chatbot_intraservice/docs/интеграции/n8n.md`
- Confluence: страница «Переход на n8n (оркестрация)», pageId **124641720**

---

### Что просим сделать

#### 1. Размещение приложения

| Параметр | Значение |
|----------|----------|
| Хост | **Тот же сервер/VM, где worker n8n** (`n8n.iek.local`), либо отдельная VM в той же сети с маршрутом для n8n |
| Каталог | `/opt/iek-chatbot-intraservice` (или согласованный путь) |
| Пользователь ОС | `iekbot` (service account, без интерактивного входа) |
| Источник кода | Git (репозиторий `iek-chatbot-intraservice` / монорепо AI Assistant IEK — выдадим URL и ветку) |
| Python | 3.11+ venv, `pip install -r requirements.txt` |

#### 2. Служба HTTP API для n8n (обязательно)

| Параметр | Значение |
|----------|----------|
| Процесс | `python scripts/n8n_http_server.py --host 0.0.0.0 --port 8765` |
| systemd | unit из `scripts/deploy/iek-intraservice-n8n-api.service` |
| Автозапуск | `enable` + `Restart=on-failure` |
| Проверка | `curl -s http://127.0.0.1:8765/health` → `{"ok":true,...}` |

**Связь с n8n:** workflow уже настроен на `http://127.0.0.1:8765/run/watch-new` (и аналоги), если worker на **том же хосте**.  
Если n8n в **Docker** — нужен доступ worker-контейнера к API хоста (`host.docker.internal:8765` или IP хоста; проверить `curl` **из контейнера**).

Эндпоинты (POST, Bearer `N8N_API_KEY`):

- `/run/watch-new`, `/run/watch-overdue`, `/run/watch-user-reply`, `/run/pipeline-watch`

#### 3. Streamlit UI — панель оператора (желательно)

| Параметр | Значение |
|----------|----------|
| Процесс | `streamlit run app.py --server.address 0.0.0.0 --server.port 8502 --server.headless true` |
| Назначение | Настройки бота, ревью черновиков AI-KB, ручной разбор заявки |
| Доступ | **Только корпоративная сеть ИЭК** (офис + VPN), **не в публичный интернет** |
| Рекомендация | HTTPS через **nginx/IIS** reverse proxy, например `https://iek-chatbot-intraservice.iek.local` |

Пример systemd — в `chatbot_intraservice/README.md`, раздел «Установка на сервер».

#### 4. Секреты и конфигурация

Секреты **не в git**. Инициатор передаёт исполнителю **отдельно** (KeePass / защищённый канал):

- `INTRASERVICE_*` (API HelpDesk)
- `IEK_LLM_*` / токен `llm.iek.local`
- `CONFLUENCE_*` (при публикации в AI-KB)
- `N8N_API_KEY` (тот же, что для REST n8n)

Файл: `/opt/iek-chatbot-intraservice/.env` (права `600`, владелец `iekbot`).

Настройки L1 (без секретов): `config/settings.local.json` — при необходимости обновляет инициатор.

#### 5. Сеть и firewall

| Откуда | Куда | Порт | Зачем |
|--------|------|------|-------|
| n8n worker | localhost / host Docker | **8765** | cron workflow |
| Подсети офиса / VPN ИЭК | VM бота | **8502** (или 443 через proxy) | Streamlit UI |
| VM бота | `helpdesk.iek.local` | 443 | IntraService API |
| VM бота | `llm.iek.local` | 443 | LLM API |
| VM бота | `confluence.dev.iek.ru` | 443 | Confluence (AI-KB) |
| VM бота | `adm.bp.iek.ru`, lk-admin | 443 | проверки БП/ЛК (по сценарию) |

**Исходящий** доступ с VM — обязателен. **Входящий** 8765 — только с n8n, не из интернета.

#### 6. Ресурсы VM (если отдельная машина)

| Ресурс | Минимум |
|--------|---------|
| CPU | 2 vCPU |
| RAM | 4–8 GB |
| Диск | 20 GB (+ логи, `pipeline/runs/`) |
| ОС | Linux (предпочтительно), допустим Windows Server |

---

### Что сделает инициатор после развёртывания

1. Проверка: `python scripts/n8n_diag_bot_url.py` — health OK, workflow URLs совпадают.
2. Тестовый прогон workflow в n8n (executions — success).
3. Отключение дублей на ноутбуке (`disable_iek_scheduler_for_n8n.ps1`).
4. Краткая инструкция операторам: URL панели Streamlit.

---

### Критерии приёмки

- [ ] `curl http://127.0.0.1:8765/health` на хосте бота → `ok: true`
- [ ] Executions workflow **IntraService HelpDesk Bot** в n8n — **success** (не `connection refused`)
- [ ] В HelpDesk появляются скрытые комментарии бота по расписанию (при включённом `auto_post_comment`)
- [ ] Streamlit UI открывается из корпсети ИЭК по согласованному URL
- [ ] Службы в autostart, перезагрузка сервера не ломает работу

---

### Альтернатива (если co-located на хост n8n невозможен)

Отдельная **Linux VM** в сети ИЭК + в workflow n8n URL `http://<IP-VM>:8765` (обновим скриптом `n8n_setup_helpdesk_watch.py --bot-url ...`).

---

### Контакты и ссылки

- Workflow n8n: https://n8n.iek.local/workflow/paYsXt1HK1ZSAHXt
- HelpDesk (пример): https://helpdesk.iek.local
- Confluence (пайплайн): pageId **124640056**
- Confluence (n8n миграция): pageId **124641720**

**Приоритет:** средний (блокирует стабильную эксплуатацию без ноутбука разработчика).

---

## Короткая версия (если лимит символов)

```
Нужно развернуть Python-приложение «IEK IntraService Chatbot» на сервере рядом с n8n.iek.local:
1) systemd: n8n_http_server на порту 8765 (для workflow IntraService HelpDesk Bot, id paYsXt1HK1ZSAHXt);
2) желательно: Streamlit UI на 8502 за HTTPS для операторов из сети ИЭК;
3) исходящий доступ к helpdesk.iek.local, llm.iek.local, confluence.dev.iek.ru;
4) секреты (.env) передадим отдельно.
Сейчас бот на ноутбуке — n8n падает с connection refused при отключении VPN/ПК.
Инструкция: chatbot_intraservice/scripts/deploy/README.md в git.
```
