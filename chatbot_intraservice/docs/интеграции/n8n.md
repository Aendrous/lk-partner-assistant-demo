# n8n — оркестрация чатбота IntraService

**Ключ n8n** — в **корневом** `.env` монорепо (`N8N_API_KEY`, `N8N_BASE_URL`), тот же что для LK Assistant webhook.  
Пакет `chatbot_intraservice` подхватывает его через `env_bootstrap` (корень → `chatbot_intraservice/.env`).

```powershell
# из chatbot_intraservice
python scripts/n8n_probe.py              # ping n8n.iek.local
python scripts/sync_n8n_env_from_root.py # скопировать N8N_* в пакетный .env (опционально)
```

## Рекомендуемая схема: Streamlit на ноутбуке + Execute на n8n

| Где | Роль |
|-----|------|
| **Ноутбук** | Streamlit (`app.py :8502`) — настройки, ревью AI-KB, ручной разбор |
| **Сервер n8n** | Python-пакет + `.env` с секретами; **n8n по расписанию** запускает `watch_*` |
| **n8n** | Только cron-оркестратор, **не** хранит логику бота |

**Execute Command** (без HTTP, без порта 8765) — лучший вариант для автономии:

```powershell
# после git clone пакета на n8n.iek.local в /opt/iek-chatbot-intraservice
python scripts/n8n_setup_helpdesk_watch.py --mode execute --bot-path /opt/iek-chatbot-intraservice
```

n8n каждые 15/30 мин выполняет на сервере:

```bash
cd /opt/iek-chatbot-intraservice && .venv/bin/python scripts/n8n_run.py watch_new
```

**Настройки:** Streamlit сохраняет `config/settings.local.json` **локально на ноутбуке**.  
Watch на сервере читает **свой** `config/settings.local.json` в каталоге пакета. После «Сохранить» в UI:

```powershell
$env:N8N_BOT_DEPLOY_HOST = "n8n.iek.local"
powershell -File scripts/push_deploy_settings.ps1
```

Секреты (`INTRASERVICE_*`, `IEK_LLM_*`) — только в `.env` **на сервере** (не в git).

> Нужна нода **Execute Command** в вашей инсталляции n8n. В **n8n v2** она **выключена по умолчанию** (`NODES_EXCLUDE`). Попросите админов на `n8n.iek.local` (main **и** worker):

```yaml
environment:
  - NODES_EXCLUDE="[n8n-nodes-base.localFileTrigger]"
```

После `docker compose down && docker compose up -d` — снова `python scripts/n8n_setup_helpdesk_watch.py --mode execute`.

Пока Execute недоступен — используйте HTTP (`--co-located` + `n8n_http_server` на сервере).

## Шаг 1. HTTP API бота (альтернатива Execute)

Подробная инструкция (ноутбук, firewall, troubleshooting):
[Confluence · n8n_http_server](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124642190)
· публикация: `python scripts/publish_n8n_http_confluence.py`

```powershell
cd chatbot_intraservice
python scripts/n8n_http_server.py
# → http://0.0.0.0:8765/health
```

Авторизация: `Authorization: Bearer <N8N_API_KEY>` (тот же ключ, что для REST n8n).

В **корневом** `.env` (или пакетном):

```env
N8N_BOT_CALLBACK_URL=http://10.1.25.17:8765
```

IP — тот, с которого n8n.iek.local достучится до хоста бота (не localhost с сервера n8n).

## Шаг 2. Workflow на n8n.iek.local

```powershell
python scripts/n8n_setup_helpdesk_watch.py --bot-url http://10.1.25.17:8765
```

Создаёт/обновляет workflow **«IntraService HelpDesk Bot»** с расписанием:

| Интервал | Endpoint бота |
|----------|----------------|
| 15 мин | `/run/watch-new` |
| 15 мин | `/run/watch-overdue` |
| 15 мин | `/run/watch-user-reply` |
| 30 мин | `/run/pipeline-watch` |

Активирует workflow. Проверка в UI: https://n8n.iek.local

## Шаг 3. Отключить Task Scheduler (после проверки)

```powershell
# из chatbot_intraservice — только Disable, без удаления
powershell -File scripts/disable_iek_scheduler_for_n8n.ps1
```

Или вручную: `Unregister-ScheduledTask -TaskName "IEK-IntraService-WatchNew" -Confirm:$false` и т.д.

## Бот на том же сервере, что n8n (co-located)

Если n8n worker и Python-пакет на **одном Linux-хосте** (типичный случай `n8n.iek.local`):

1. Развернуть пакет, например `/opt/iek-chatbot-intraservice`:
   ```bash
   git clone … /opt/iek-chatbot-intraservice
   cd /opt/iek-chatbot-intraservice
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   cp .env.example .env   # INTRASERVICE_*, IEK_LLM_*, N8N_API_KEY
   ```
2. Поднять HTTP API как службу — шаблон `scripts/deploy/iek-intraservice-n8n-api.service`:
   ```bash
   sudo cp scripts/deploy/iek-intraservice-n8n-api.service /etc/systemd/system/
   # поправить User и WorkingDirectory
   sudo systemctl enable --now iek-intraservice-n8n-api
   curl -s http://127.0.0.1:8765/health   # {"ok":true,...}
   ```
3. В **корневом** `.env`: `N8N_BOT_CALLBACK_URL=http://127.0.0.1:8765`
4. Обновить workflow:
   ```powershell
   python scripts/n8n_setup_helpdesk_watch.py --co-located
   ```
5. Диагностика с рабочей станции:
   ```powershell
   python scripts/n8n_diag_bot_url.py
   ```

**n8n в Docker** на том же хосте: worker не видит `127.0.0.1` контейнера — используйте `http://host.docker.internal:8765` или IP хоста в docker-сети (проверьте `curl` **из контейнера** n8n).

### Вариант B — без HTTP (Execute Command)

Если админы разрешили ноду **Execute Command** и не хотите открывать порт 8765:

```bash
cd /opt/iek-chatbot-intraservice && .venv/bin/python scripts/n8n_run.py watch_new
```

Аналогично: `watch_overdue`, `watch_user_reply`, `pipeline_watch`.

## Troubleshooting: connection refused

Симптом в n8n: **`The service refused the connection`** на ноде `POST watch-new` (или другой HTTP-ноде).

| Причина | Что сделать |
|---------|-------------|
| `n8n_http_server` не запущен | `systemctl status iek-intraservice-n8n-api` или `python scripts/n8n_http_server.py` |
| В workflow **старый IP** (ноутбук, DHCP) | `python scripts/n8n_diag_bot_url.py` → сравнить URL нод с `N8N_BOT_CALLBACK_URL` |
| Firewall блокирует 8765 | открыть только для n8n worker / localhost |
| URL `127.0.0.1`, а n8n в Docker | `host.docker.internal` или IP хоста |
| Дубли watch | отключить Task Scheduler: `disable_iek_scheduler_for_n8n.ps1` |

До Python-кода n8n **не доходит** — это не ошибка LLM/IntraService.

## Endpoints HTTP API

| POST | Назначение |
|------|------------|
| `/run/watch-new` | новые/переданные 31/38/121 |
| `/run/watch-overdue` | «До просрочки» |
| `/run/watch-user-reply` | ответ заявителя 46/120 |
| `/run/pipeline-watch` | закрытые → learn |
| `/analyze/{id}` | body `{"post":true}` |

## Альтернатива без HTTP

n8n **Execute Command** на хосте с Python:

```bash
python scripts/n8n_run.py watch_new
```

## Связь с LK webhook

| Переменная | Где |
|------------|-----|
| `N8N_API_KEY` | корневой `.env` — REST API n8n |
| `N8N_WEBHOOK_LK` | webhook LK Assistant (каталог) |
| `N8N_WEBHOOK_HELPDESK` | (опционально) входящий webhook для ручного запуска |
| `N8N_BOT_CALLBACK_URL` | URL `n8n_http_server` для исходящих вызовов **из** n8n |

Клиент: `n8n_client.py` в корне репо (используется `n8n_probe.py`).

## Настройки бота

Без изменений: `config/settings.local.json` / Streamlit — `auto_post_comment`, контуры lk/bp, `watch_new_status_ids`.

**Confluence:** [Переход на n8n (оркестрация)](https://confluence.dev.iek.ru/pages/viewpage.action?pageId=124641720) — `docs/интеграции/n8n_migration.md`, публикация: `python scripts/publish_n8n_migration_confluence.py`. Там же ответ: **не переносить** LLM/IntraService в n8n, только cron.

См. [intraservice_api.md](intraservice_api.md) — у HelpDesk нет outbound webhook.
