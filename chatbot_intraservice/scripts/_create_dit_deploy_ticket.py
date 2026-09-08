# -*- coding: utf-8 -*-
"""Одноразово: заявка в IntraService — деплой чатбота на n8n."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(PKG / "src"))

from env_bootstrap import load_package_env  # noqa: E402

load_package_env()
import intraservice  # noqa: E402

NAME = (
    "Развёртывание IEK IntraService Chatbot на n8n.iek.local "
    "(co-located: API :8765, Streamlit UI :8502)"
)

DESCRIPTION = """Контекст
Внедряем «IEK: Помощник сотрудника» — ассистент 1 линии HelpDesk. Оркестрация на n8n.iek.local (workflow «IntraService HelpDesk Bot», id paYsXt1HK1ZSAHXt).

Проблема: API бота на ноутбуке разработчика — при VPN/выключении ПК n8n получает connection refused. UI Streamlit с ноутбука недоступен коллегам в сети ИЭК.

Нужно: развернуть Python-приложение на сервере рядом с n8n (co-located), работа 24/7.

Что сделать
1) Хост: сервер/VM worker n8n.iek.local (или VM в той же сети, доступная n8n).
2) Каталог /opt/iek-chatbot-intraservice, пользователь iekbot, Python 3.11+ venv, git.
3) systemd: n8n_http_server на порту 8765 (unit: chatbot_intraservice/scripts/deploy/iek-intraservice-n8n-api.service).
4) Желательно: Streamlit UI :8502 за HTTPS (nginx), доступ только из корпсети ИЭК.
5) Исходящий доступ VM: helpdesk.iek.local, llm.iek.local, confluence.dev.iek.ru.
6) Firewall: TCP 8765 — только n8n worker; 8502/443 — офис и VPN.

Секреты (.env: IntraService, LLM, Confluence) передадим отдельно после доступа к серверу.

Приёмка
- curl http://127.0.0.1:8765/health -> ok:true
- executions workflow n8n — success (не connection refused)
- UI открывается из корпсети

Документация: Confluence pageId 124641720.
Маршрутизация: администраторы n8n.iek.local / ДИТ."""

# Active Directory (учетные записи, права, настройки) — ServiceId 34
# Тип: Запрос на изменение — TypeId 1010
BODY = {
    "Name": NAME[:120],
    "Description": DESCRIPTION,
    "ServiceId": 34,
    "TypeId": 1010,
    "StatusId": 31,
    "PriorityId": 11,
}


def main() -> int:
    data = intraservice._request("POST", "/task", BODY)
    task = data.get("Task") or data
    tid = task.get("Id")
    out = {
        "ok": bool(tid),
        "Id": tid,
        "url": intraservice.task_url(tid) if tid else None,
        "Name": task.get("Name"),
        "ServiceId": 34,
        "TypeId": 1010,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if tid else 1


if __name__ == "__main__":
    raise SystemExit(main())
