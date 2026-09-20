# Чатбот IEK на `chatbot.iek.local`: эксплуатация и доработки

> **Production runbook.** Источник правды для кода — Git-репозиторий; эта страница описывает фактическую production-инфраструктуру на `chatbot.iek.local` (`10.0.0.145`). Не помещать сюда пароли, токены, содержимое `.env` или закрытые ключи.

## 1. Что и куда перенесено

Раньше L0/L1 и автоматические watch-сценарии были привязаны к ноутбуку разработчика. Теперь приложение работает на отдельной Ubuntu VM `chatbot.iek.local` круглосуточно.

| Компонент | Где работает | Назначение |
|---|---|---|
| L0 UI | `https://chatbot.iek.local/l0/` | Чат для сотрудника: поиск ответа, уточнения, черновик заявки |
| L1 UI | `https://chatbot.iek.local/l1/` | Панель исполнителя: разбор заявок, настройки, AI-KB, история |
| Python API для n8n | `http://10.0.0.145:8765` | Принимает команды запуска watch-сценариев |
| n8n | `https://n8n.iek.local` | Расписание и журнал запусков workflow `IntraService HelpDesk Bot` (`paYsXt1HK1ZSAHXt`) |

L0/L1 сами не доступны по сетевым портам `7860` и `8502`: они слушают только `127.0.0.1` на VM. Для пользователей их публикует Nginx по HTTPS. Это обязательно: у Streamlit нет корпоративной аутентификации и он не должен быть сетевой границей безопасности.

## 2. Фактическая архитектура

```text
Пользователь корпоративной сети
  └─ HTTPS :443 → nginx на chatbot.iek.local
       ├─ /l0/ → 127.0.0.1:7860 (Streamlit L0)
       └─ /l1/ → 127.0.0.1:8502 (Streamlit L1)

n8n.iek.local (workflow по расписанию)
  └─ HTTP POST + Bearer token → 10.0.0.145:8765
       └─ n8n_http_server.py → n8n_run.py → watch_*.py / pipeline_watch.py
            └─ HelpDesk API, IEK LLM, Confluence REST, локальная AI-KB
```

### Службы systemd

| Unit | Пользователь | Команда / порт | Что проверять |
|---|---|---|---|
| `iek-l0-ui` | `iekbot` | Streamlit L0, `127.0.0.1:7860`, base path `/l0` | L0 UI |
| `iek-l1-ui` | `iekbot` | Streamlit L1, `127.0.0.1:8502`, base path `/l1` | L1 UI |
| `iek-intraservice-n8n-api` | `iekbot` | `scripts/n8n_http_server.py`, `0.0.0.0:8765` | n8n invokes it |
| `nginx` | system | `0.0.0.0:80`, `0.0.0.0:443` | HTTPS proxy and redirect |

Все units включены (`enabled`) и должны автоматически стартовать после перезагрузки VM.

### Файлы и права

| Ресурс | Путь | Правило |
|---|---|---|
| Production checkout | `/opt/iek-assistant` | Не редактировать напрямую без аварийной причины и фиксации изменений в Git |
| Package | `/opt/iek-assistant/chatbot_intraservice` | Рабочий каталог L1/API |
| Python virtualenv | `/opt/iek-assistant/.venv` | Зависимости устанавливать в него, не в system Python |
| Runtime secrets | `/opt/iek-assistant/chatbot_intraservice/.env` | Владелец `iekbot`, права `600`; никогда не коммитить и не выводить в терминал |
| L0/L1 unit files | `/etc/systemd/system/iek-l0-ui.service`, `/etc/systemd/system/iek-l1-ui.service` | После изменения: `daemon-reload` + restart |
| TLS key/cert | `/etc/nginx/ssl/chatbot.iek.local/` | Приватный ключ не копировать в репозиторий; доступ только администраторам |
| Nginx site | `/etc/nginx/sites-available/chatbot-ui` | Перед reload всегда `nginx -t` |

## 3. Сеть, TLS и доступ

### Открытые порты

| Порт | Доступ | Назначение |
|---|---|---|
| 22 | администраторы | SSH администрирование |
| 80 | корпоративная сеть | Только redirect на HTTPS |
| 443 | корпоративная сеть | L0/L1 через Nginx |
| 8765 | только n8n / согласованная внутренняя сеть | API watch-сценариев; не публиковать в интернет |
| 7860, 8502 | только loopback VM | Внутренние Streamlit, не открывать в UFW |

Сертификат выдан корпоративным CA `iek-AMALTEYA-CA` для `chatbot.iek.local`, `chatbot` и `10.0.0.145`; срок действия нужно проверять до продления. Пользовательский URL — только доменное имя `https://chatbot.iek.local/...`, а не IP.

### Streamlit и reverse proxy

Пути `/l0/` и `/l1/` требуют параметров Streamlit `--server.baseUrlPath l0` и `--server.baseUrlPath l1`. Если после обновления UI отдаёт HTML, но не загружает интерфейс/WebSocket, сначала проверить совпадение этих параметров с Nginx `location`.

## 4. Ежедневные проверки и диагностика

На VM (через SSH с разрешённой административной учётной записью):

```bash
systemctl status nginx iek-l0-ui iek-l1-ui iek-intraservice-n8n-api --no-pager
curl -s http://127.0.0.1:8765/health
curl -kI https://127.0.0.1/l0/ -H 'Host: chatbot.iek.local'
curl -kI https://127.0.0.1/l1/ -H 'Host: chatbot.iek.local'
journalctl -u nginx -u iek-l0-ui -u iek-l1-ui -u iek-intraservice-n8n-api --since '30 minutes ago' --no-pager
```

Ожидается:

- все service units — `active (running)`;
- `/health` возвращает JSON с `"ok": true`;
- L0/L1 через Nginx возвращают HTTP `200`;
- в n8n у workflow **IntraService HelpDesk Bot** зелёные executions.

Проверка с рабочей станции:

```powershell
curl.exe -k -I https://chatbot.iek.local/l0/
curl.exe -k -I https://chatbot.iek.local/l1/
python scripts\n8n_diag_bot_url.py
```

Если UI не открывается, **не** меняйте Streamlit на `0.0.0.0`. Проверять Nginx, сертификат, firewall и service logs.

## 5. n8n: как работает автоматизация

Workflow: **IntraService HelpDesk Bot**, ID `paYsXt1HK1ZSAHXt`, URL `https://n8n.iek.local/workflow/paYsXt1HK1ZSAHXt`.

| Ветка n8n | URL VM | Частота |
|---|---|---|
| watch new | `POST http://10.0.0.145:8765/run/watch-new` | 15 минут |
| overdue | `POST http://10.0.0.145:8765/run/watch-overdue` | 15 минут |
| user reply | `POST http://10.0.0.145:8765/run/watch-user-reply` | 15 минут |
| pipeline watch | `POST http://10.0.0.145:8765/run/pipeline-watch` | 30 минут |

Авторизация endpoint-ов (кроме `/health`) — `Authorization: Bearer ...`; ключ хранится в `.env`, не в документации. После миграции VM-backed scheduled executions `watch-new`, `overdue` и `user-reply` успешно завершались в n8n.

При ошибке n8n:

1. Открыть execution и сохранить **только техническое сообщение**, без заголовка Authorization.
2. Проверить `curl http://127.0.0.1:8765/health` на VM.
3. Проверить `systemctl status iek-intraservice-n8n-api` и его journal.
4. Сверить HTTP URLs workflow с `10.0.0.145:8765` через `python scripts/n8n_diag_bot_url.py`.
5. При `401` сверить ключи по защищённому каналу; не вставлять их в чат, тикет или командную строку.

Не выключать/не включать старый ноутбучный Scheduler до подтверждённого успешного n8n execution. После миграции не должно быть двух параллельных источников запуска watch-сценариев.

## 6. Штатное обновление кода

### Рекомендуемый процесс

1. Работать в локальной clone-версии репозитория на рабочей станции.
2. Создать ветку, внести минимальную правку, выполнить узкие тесты/`py_compile`.
3. Сделать code review и commit/push в Git.
4. На VM выполнить контролируемое обновление checkout до согласованного commit (без `git reset --hard`, если на VM есть незакоммиченные emergency-правки).
5. При изменении зависимостей — обновить `/opt/iek-assistant/.venv` только из проверенного источника. На VM корпоративный TLS к PyPI ранее не проходил проверку; для зависимостей использовался проверенный offline wheelhouse. Не обходить TLS через `--trusted-host`/отключение проверки.
6. Если изменены unit/config/Nginx: проверить конфигурацию, затем `systemctl daemon-reload` и restart только затронутых служб.
7. Проверить `/health`, L0/L1 URL и следующий execution n8n.
8. Записать изменение в Git, в эту страницу при смене эксплуатации и в `docs/handoff.md` в конце сессии.

### Команды после обновления кода

```bash
# На VM; запускать только затронутые службы
sudo systemctl restart iek-l0-ui
sudo systemctl restart iek-l1-ui
sudo systemctl restart iek-intraservice-n8n-api

# Если менялся nginx-конфиг
sudo nginx -t && sudo systemctl reload nginx

# Проверка
systemctl is-active nginx iek-l0-ui iek-l1-ui iek-intraservice-n8n-api
curl -s http://127.0.0.1:8765/health
```

### Изменение настроек и секретов

- Поведение watch/контуров — `config/settings.local.json` и L1 UI; сначала оценить влияние на все watch-сценарии.
- Секреты — только `.env` с правами `600`; после изменения перезапустить затронутую службу.
- Нельзя включать `auto_learn_kb` в defaults без решения оператора.
- В AI-KB публикуется только `KB_INSERT` после человеческого ревью; PII/email не включать.

### Rollback

Rollback — возврат checkout к последнему известному хорошему commit, затем restart только затронутых units. Перед rollback сохранить `git status`, текущий commit, журнал ошибки и артефакты из `debug/` / `pipeline/`; не уничтожать их `reset --hard` или очисткой каталогов.

## 7. Работа через RDP, VS Code и Harvi Code

**RDP на этой VM сейчас не является штатным способом работы:** VM работает под Ubuntu, а RDP/desktop-среда не установлены и не нужны для production-служб. Установка RDP ради редактирования кода увеличит поверхность атаки и создаст риск неотслеживаемых production-правок.

Разрешённый и рекомендуемый путь:

1. **VS Code / Cursor Remote-SSH** с рабочей станции для просмотра логов и точечной диагностики VM. Подключаться по SSH к `chatbot.iek.local` разрешённой учётной записью, не под `iekbot`.
2. **Harvi Code** запускать в локальной рабочей копии репозитория. Он может читать/проверять VM через SSH и публиковать согласованные изменения, но source-of-truth остаётся Git.
3. Для изменения production-файла по аварии: создать backup, зафиксировать точное изменение в Git как можно скорее, перезапустить только необходимую службу и документировать причину.

То есть работать «с файлами проекта в VS Code» технически можно через Remote-SSH, но **не следует использовать VM как обычную единственную рабочую папку разработки**. RDP не требуется. Для полноценной remote-разработки предпочтительнее VS Code Remote-SSH / Dev Containers с Git-веткой и review, а не GUI-доступ к production-хосту.

## 8. Обязательные напоминания и риски

- Секреты, напечатанные ранее в терминале или переписке, считаются раскрытыми и подлежат ротации: в частности пароль административной учётной записи и API-токены, если они попадали в вывод.
- Следить за сроком сертификата и согласованно продлевать его до истечения.
- L0/L1 рассчитаны на корпоративную сеть. Для более широкого доступа сначала внедрить корпоративную аутентификацию перед Nginx; не публиковать Streamlit напрямую в интернет.
- `8765` должен быть ограничен источником n8n на уровне firewall/сетевой политики. Это отдельный API, не UI.
- Наблюдать `finish_reason: length` и LLM throttle; max_tokens в вызовах обязателен.
- Не использовать OWUI MCP напрямую в HD-пайплайне: Confluence prefetch выполняется через `confluence_tools.py` + LiteLLM.

## 9. Полезные ссылки

- L0: `https://chatbot.iek.local/l0/`
- L1: `https://chatbot.iek.local/l1/`
- n8n workflow: `https://n8n.iek.local/workflow/paYsXt1HK1ZSAHXt`
- Проект в Confluence: «Чатбот IntraService: пайплайн, AI-KB и настройки»
- Локальная архитектура: `docs/ARCHITECTURE.md`
- Правила watch: `docs/pipeline/watch_unified_rules.md`
- Deployment assets: `scripts/deploy/`

---

**Как обновить страницу:** `python scripts/publish_chatbot_vm_deployment_confluence.py`.
