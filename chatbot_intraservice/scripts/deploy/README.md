# Деплой HTTP API для n8n (co-located)

Цель: на сервере `n8n.iek.local` поднять `n8n_http_server` на порту **8765**, чтобы workflow **IntraService HelpDesk Bot** вызывал `POST /run/watch-*` по `http://127.0.0.1:8765`.

## 1. Пакет

```bash
sudo useradd -r -m -d /opt/iek-chatbot-intraservice iekbot || true
sudo -u iekbot git clone <repo-url> /opt/iek-chatbot-intraservice
cd /opt/iek-chatbot-intraservice
sudo -u iekbot python3 -m venv .venv
sudo -u iekbot .venv/bin/pip install -r requirements.txt
sudo -u iekbot cp .env.example .env
# заполнить .env: INTRASERVICE_*, IEK_LLM_*, N8N_API_KEY (тот же что для n8n REST)
```

В **корневом** `.env` монорепо (или скопировать в пакетный):

```env
N8N_BOT_CALLBACK_URL=http://127.0.0.1:8765
```

## 2. systemd

```bash
sudo cp scripts/deploy/iek-intraservice-n8n-api.service /etc/systemd/system/
# при необходимости поправить User/WorkingDirectory
sudo systemctl daemon-reload
sudo systemctl enable --now iek-intraservice-n8n-api
curl -s http://127.0.0.1:8765/health
```

Ожидается JSON с `"ok": true`.

## 3. Workflow n8n

С рабочей станции (есть `N8N_API_KEY` в корневом `.env`):

```powershell
cd chatbot_intraservice
python scripts/n8n_setup_helpdesk_watch.py --co-located
python scripts/n8n_diag_bot_url.py
```

## 4. Отключить дубли на ноутбуке

```powershell
powershell -File scripts/disable_iek_scheduler_for_n8n.ps1
```

## n8n в Docker

Если worker в контейнере, `127.0.0.1` указывает на контейнер, не на хост. Проверьте из контейнера:

```bash
curl -s http://host.docker.internal:8765/health
```

И укажите этот URL в `--bot-url` при настройке workflow.

См. также [`docs/интеграции/n8n.md`](../интеграции/n8n.md).
