# -*- coding: utf-8 -*-
"""Tools чатбота 1 линии HelpDesk (только IntraService)."""
from __future__ import annotations

import inspect
import json
from typing import Any, Callable

from intraservice import (
    create_task,
    get_task,
    has_credentials,
    list_services_for_create,
    set_task_awaiting_reply,
    take_task_in_work,
    update_task_status,
)

OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_helpdesk_task",
            "description": "Прочитать заявку IntraService по номеру (helpdesk.iek.local).",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Номер заявки, например 693437"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_helpdesk_services",
            "description": "Список сервисов IntraService, в которые можно создать заявку.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_helpdesk_ticket",
            "description": (
                "Создать заявку в IntraService после уточнений. "
                "service_key: kp | lk | bp | vpn | mail | other."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Название ≤ 120 символов"},
                    "description": {"type": "string", "description": "Суть, URL, симптомы, время МСК"},
                    "service_key": {
                        "type": "string",
                        "enum": ["kp", "lk", "bp", "vpn", "mail", "other"],
                    },
                    "user_email": {"type": "string", "description": "Email заявителя"},
                },
                "required": ["name", "description", "service_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_helpdesk_task",
            "description": (
                "Взять заявку в работу: статус «В процессе» (в IEK нет отдельного «В работе») "
                "и назначить текущего API-пользователя исполнителем."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Номер заявки"},
                    "comment": {
                        "type": "string",
                        "description": "Комментарий в историю (необязательно)",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_helpdesk_task_status",
            "description": (
                "Сменить статус заявки. status: in_progress | awaiting_reply | open | done | "
                "closed | transferred | l1 | или Id/имя из HelpDesk. "
                "Для awaiting_reply комментарий обязателен."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "status": {"type": "string"},
                    "comment": {"type": "string"},
                    "assign_self": {
                        "type": "boolean",
                        "description": "Добавить себя в исполнители",
                    },
                },
                "required": ["task_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "await_helpdesk_user_reply",
            "description": (
                "Перевести заявку в «Ожидание ответа пользователя». "
                "Нужен текст вопроса/уточнения для заявителя."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "comment": {"type": "string", "description": "Что спросить у заявителя"},
                },
                "required": ["task_id", "comment"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_helpdesk_ticket",
            "description": (
                "Разобрать заявку ассистентом (для БП — bp_tickets + корпус WEBKB/закрытые заявки). "
                "Вернёт короткий скрытый комментарий: факты + adm + ссылки KB. "
                "post=true — записать комментарий в заявку (IsPrivateComment)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Номер заявки"},
                    "post": {
                        "type": "boolean",
                        "description": "Записать скрытый комментарий (по умолчанию false)",
                    },
                    "learn": {
                        "type": "boolean",
                        "description": "Создать черновик AI-KB если не было ответа в базе",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_helpdesk_chatbot_settings",
            "description": "Текущие настройки чатбота IntraService (автообучение AI-KB, автопост и т.д.).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_helpdesk_ticket_pipeline",
            "description": (
                "Полный пайплайн заявки: разбор + опционально комментарий + AI-KB по настройкам. "
                "Артефакты в pipeline/runs/."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "post": {"type": "boolean"},
                    "learn": {"type": "boolean", "description": "Принудительно создать черновик"},
                },
                "required": ["task_id"],
            },
        },
    },
]


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)[:8000]


def get_helpdesk_task(task_id: str) -> str:
    if not has_credentials():
        return _dumps({"ok": False, "error": "Нет INTRASERVICE_USER / INTRASERVICE_PASSWORD"})
    try:
        return _dumps({"ok": True, **get_task(str(task_id).strip())})
    except Exception as err:
        return _dumps({"ok": False, "error": str(err)[:800]})


def list_helpdesk_services() -> str:
    if not has_credentials():
        return _dumps({"ok": False, "error": "Нет учётки IntraService"})
    try:
        return _dumps({"ok": True, "services": list_services_for_create()})
    except Exception as err:
        return _dumps({"ok": False, "error": str(err)[:800]})


def create_helpdesk_ticket(
    name: str,
    description: str,
    service_key: str = "lk",
    user_email: str = "",
) -> str:
    if not has_credentials():
        return _dumps({"ok": False, "error": "Нет учётки IntraService"})
    try:
        return _dumps(
            create_task(
                name=name,
                description=description,
                service_key=service_key or "lk",
                user_email=user_email or "",
            )
        )
    except Exception as err:
        return _dumps({"ok": False, "error": str(err)[:800]})


def take_helpdesk_task(task_id: str, comment: str = "") -> str:
    if not has_credentials():
        return _dumps({"ok": False, "error": "Нет учётки IntraService"})
    try:
        return _dumps(take_task_in_work(str(task_id).strip(), comment=comment or ""))
    except Exception as err:
        return _dumps({"ok": False, "error": str(err)[:800]})


def set_helpdesk_task_status(
    task_id: str,
    status: str,
    comment: str = "",
    assign_self: bool = False,
) -> str:
    if not has_credentials():
        return _dumps({"ok": False, "error": "Нет учётки IntraService"})
    try:
        return _dumps(
            update_task_status(
                str(task_id).strip(),
                status,
                comment=comment or "",
                assign_self=bool(assign_self),
            )
        )
    except Exception as err:
        return _dumps({"ok": False, "error": str(err)[:800]})


def await_helpdesk_user_reply(task_id: str, comment: str) -> str:
    if not has_credentials():
        return _dumps({"ok": False, "error": "Нет учётки IntraService"})
    try:
        return _dumps(set_task_awaiting_reply(str(task_id).strip(), comment or ""))
    except Exception as err:
        return _dumps({"ok": False, "error": str(err)[:800]})


def analyze_helpdesk_ticket(task_id: str, post: bool = False, learn: bool = False) -> str:
    """Подключить разбор bp_tickets / l1 к чатботу через tool."""
    if not has_credentials():
        return _dumps({"ok": False, "error": "Нет учётки IntraService"})
    try:
        # Импорт ленивый: скрипт тянет llm_client из корня репо
        import importlib.util
        from pathlib import Path

        script = Path(__file__).resolve().parents[1] / "scripts" / "analyze_and_comment.py"
        spec = importlib.util.spec_from_file_location("analyze_and_comment", script)
        if not spec or not spec.loader:
            return _dumps({"ok": False, "error": "analyze_and_comment.py не найден"})
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod.run_pipeline(str(task_id).strip(), post=bool(post), learn=bool(learn))
        return _dumps(
            {
                "ok": True,
                "profile": result.get("profile"),
                "adm": result.get("adm"),
                "comment": result.get("comment_preview"),
                "parsed": result.get("parsed"),
                "kb_gap": result.get("kb_gap"),
                "kb_learning": result.get("kb_learning"),
                "post": result.get("post"),
            }
        )
    except Exception as err:
        return _dumps({"ok": False, "error": str(err)[:800]})


def learn_helpdesk_ticket(task_id: str, analyze_first: bool = False, force: bool = False) -> str:
    if not has_credentials():
        return _dumps({"ok": False, "error": "Нет учётки IntraService"})
    try:
        import importlib.util
        from pathlib import Path

        script = Path(__file__).resolve().parents[1] / "scripts" / "learn_from_ticket.py"
        spec = importlib.util.spec_from_file_location("learn_from_ticket", script)
        if not spec or not spec.loader:
            return _dumps({"ok": False, "error": "learn_from_ticket.py не найден"})
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod.process_one(
            str(task_id).strip(),
            analyze_first=bool(analyze_first),
            force=bool(force),
            trigger="cli",
        )
        return _dumps(result)
    except Exception as err:
        return _dumps({"ok": False, "error": str(err)[:800]})


def get_helpdesk_chatbot_settings() -> str:
    try:
        import sys
        from pathlib import Path

        src = Path(__file__).resolve().parents[1] / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from settings import settings_summary

        return _dumps({"ok": True, **settings_summary()})
    except Exception as err:
        return _dumps({"ok": False, "error": str(err)[:800]})


def run_helpdesk_ticket_pipeline(task_id: str, post: bool = False, learn: bool = False) -> str:
    if not has_credentials():
        return _dumps({"ok": False, "error": "Нет учётки IntraService"})
    try:
        import sys
        from pathlib import Path

        src = Path(__file__).resolve().parents[1] / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from pipeline import run_ticket_pipeline

        result = run_ticket_pipeline(
            str(task_id).strip(),
            post=bool(post),
            learn=True if learn else None,
            trigger="cli",
        )
        return _dumps(
            {
                "ok": True,
                "pipeline_run_id": result.get("pipeline_run_id"),
                "comment": result.get("comment_preview"),
                "kb_gap": result.get("kb_gap"),
                "auto_learn_decision": result.get("auto_learn_decision"),
                "kb_learning": result.get("kb_learning"),
            }
        )
    except Exception as err:
        return _dumps({"ok": False, "error": str(err)[:800]})


DISPATCH: dict[str, Callable[..., str]] = {
    "get_helpdesk_task": get_helpdesk_task,
    "list_helpdesk_services": list_helpdesk_services,
    "create_helpdesk_ticket": create_helpdesk_ticket,
    "take_helpdesk_task": take_helpdesk_task,
    "set_helpdesk_task_status": set_helpdesk_task_status,
    "await_helpdesk_user_reply": await_helpdesk_user_reply,
    "analyze_helpdesk_ticket": analyze_helpdesk_ticket,
    "learn_helpdesk_ticket": learn_helpdesk_ticket,
    "get_helpdesk_chatbot_settings": get_helpdesk_chatbot_settings,
    "run_helpdesk_ticket_pipeline": run_helpdesk_ticket_pipeline,
}


def enabled_tools() -> list[dict[str, Any]]:
    if not has_credentials():
        return []
    return list(OPENAI_TOOLS)


def run_tool(name: str, arguments: dict[str, Any]) -> str:
    fn = DISPATCH.get(name)
    if not fn:
        return _dumps({"ok": False, "error": f"Неизвестный tool {name}"})
    allowed = set(inspect.signature(fn).parameters)
    kwargs = {k: v for k, v in (arguments or {}).items() if k in allowed}
    return fn(**kwargs)
