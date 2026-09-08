# n8n_http_server — HTTP API для workflow IntraService HelpDesk Bot

## Зачем

Workflow **«IntraService HelpDesk Bot»** на `n8n.iek.local` по расписанию шлёт **POST** на хост бота:

| Интервал | URL (пример) | Что запускается |
|:--|:--|:--|
| 15 мин | `POST …/run/watch-new` | новые/переданные заявки → разбор |
| 15 мин | `POST …/run/watch-overdue` | эскалация «До просрочки» |
| 15 мин | `POST …/run/watch-user-reply` | ответ заявителя (статусы 46/120) |
| 30 мин | `POST …/run/pipeline-watch` | закрытые → learn / pipeline |

На ноутбуке это обслуживает **`python scripts/n8n_http_server.py`** — лёгкий HTTP-сервер на порту **8765**.

Цепочка:

```
n8n (cron)  →  POST http://<IP-ноутбука>:8765/run/watch-overdue
            →  n8n_http_server.py
            →  n8n_run.py watch_overdue
            →  scripts/watch_overdue.py  (+ IntraService API, IEK LLM)
```

**Важно:** ошибка n8n *«The service refused the connection»* означает, что **до Python не дошли** — сервер на `:8765` не слушает или firewall. Это не ошибка LLM.

Текущий workflow (id `paYsXt1HK1ZSAHXt`) в нодах HTTP указывает URL вида `http://10.111.16.180:8765/run/…` — IP **ноутбука**, где должен быть запущен `n8n_http_server`.

---

## Что на порту 8765

| Метод | Путь | Назначение |
|:--|:--|:--|
| GET | `/health` | Проверка без авторизации → `{"ok":true,...}` |
| POST | `/run/watch-new` | `watch_new.py` |
| POST | `/run/watch-overdue` | `watch_overdue.py` |
| POST | `/run/watch-user-reply` | `watch_user_reply.py` |
| POST | `/run/pipeline-watch` | `pipeline_watch.py` |
| POST | `/analyze/{task_id}` | разбор одной заявки, body `{"post":true}` |

Авторизация (если задан ключ): заголовок `Authorization: Bearer <N8N_BOT_API_KEY>`.

Переменные `.env` (корень монорепо или `chatbot_intraservice/.env`):

```env
N8N_BOT_API_KEY=…          # тот же N8N_API_KEY, что для REST n8n
N8N_BOT_HTTP_HOST=0.0.0.0    # слушать все интерфейсы (нужно для n8n с сервера)
N8N_BOT_HTTP_PORT=8765
N8N_BOT_CALLBACK_URL=http://<ваш-LAN-IP>:8765
INTRASERVICE_*               # HelpDesk
IEK_LLM_TOKEN                # LLM
```

Настройки бота (`watch_new_enabled`, контуры, `auto_post_comment`) — `config/settings.local.json` на **том же** хосте, где крутится HTTP API.

---

## Запуск на ноутбуке (Windows)

### 1. Разово (для проверки)

```powershell
cd chatbot_intraservice
pip install -r requirements.txt
# .env в корне монорепо или chatbot_intraservice/.env — секреты HD + LLM + N8N_API_KEY

python scripts/n8n_http_server.py
# → n8n HTTP API: http://0.0.0.0:8765/health
```

Проверка локально:

```powershell
curl http://127.0.0.1:8765/health
```

### 2. Узнать IP для n8n

```powershell
ipconfig
# IPv4 в офисной/VPN сети, например 10.111.16.180
```

С **сервера n8n** (или с машины в той же сети) должно открываться:

```bash
curl -s http://10.111.16.180:8765/health
```

Если `connection refused` — сервер не запущен или firewall.

### 3. Firewall Windows

От администратора:

```powershell
netsh advfirewall firewall add rule name="IEK n8n_http_server 8765" dir=in action=allow protocol=TCP localport=8765
```

### 4. Автозапуск при входе

```powershell
cd chatbot_intraservice
powershell -ExecutionPolicy Bypass -File scripts\install_n8n_http_server.ps1
```

Создаёт задачу планировщика **IEK-IntraService-N8nHttp** (порт 8765, `0.0.0.0`).

### 5. Обновить URL в workflow n8n

Если IP ноутбука сменился (DHCP, другая сеть):

```powershell
cd chatbot_intraservice
python scripts\n8n_setup_helpdesk_watch.py --bot-url http://10.111.16.180:8765
```

Диагностика (сравнить URL в workflow с доступностью health):

```powershell
python scripts\n8n_diag_bot_url.py --workflow-id paYsXt1HK1ZSAHXt
```

### 6. Отключить дубли (Task Scheduler)

Если раньше watch крутился по Windows Scheduler — отключить, чтобы не было двойных разборов:

```powershell
powershell -File scripts\disable_iek_scheduler_for_n8n.ps1
```

---

## Схема ролей

| Где | Что |
|:--|:--|
| **Ноутбук** | `n8n_http_server :8765` + опционально Streamlit `app.py :8502` (ревью AI-KB) |
| **n8n.iek.local** | Только cron: workflow **IntraService HelpDesk Bot** |
| **HelpDesk / LLM** | Вызываются с ноутбука при срабатывании watch |

Streamlit и HTTP API могут быть на одном ноутбуке. Настройки из UI сохраняются в `config/settings.local.json` **локально** — watch на ноутбуке читает этот же файл.

---

## Troubleshooting

| Симптом | Причина | Действие |
|:--|:--|:--|
| `connection refused` на `POST watch-overdue` | `n8n_http_server` не запущен | `python scripts/n8n_http_server.py` или задача IEK-IntraService-N8nHttp |
| Health локально OK, с n8n — refused | Firewall / другая сеть | правило 8765; VPN; ping IP ноутбука с n8n |
| 401 unauthorized | Неверный Bearer | `N8N_BOT_API_KEY` в `.env` = ключ в ноде n8n |
| Workflow OK, заявки не разбираются | `watch_new_enabled: false` или контур выключен | Streamlit → Настройки / `settings.local.json` |
| Старый IP в нодах | DHCP | `n8n_diag_bot_url.py` → `n8n_setup_helpdesk_watch.py --bot-url …` |

---

## Альтернатива: бот на сервере n8n (co-located)

Если ноутбук не должен быть всегда онлайн — пакет на `n8n.iek.local`, systemd `iek-intraservice-n8n-api.service`, URL в workflow `http://127.0.0.1:8765`. См. `scripts/deploy/README.md`, заявка ДИТ: `docs/заявки/дит_деплой_чатбота_n8n.md`.

Ещё вариант без HTTP — нода **Execute Command** в n8n: `python scripts/n8n_run.py watch_overdue` на сервере (нужно разрешение админов n8n).

---

## Команды (шпаргалка)

```powershell
cd chatbot_intraservice
python scripts/n8n_http_server.py
python scripts/n8n_diag_bot_url.py
python scripts/n8n_setup_helpdesk_watch.py --bot-url http://<IP>:8765
python scripts/n8n_probe.py
curl http://127.0.0.1:8765/health
```

Исходники: `scripts/n8n_http_server.py`, `scripts/n8n_run.py`, workflow `workflows/n8n_chatbot_intraservice.json`.
