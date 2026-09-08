#!/usr/bin/env python3
"""Читение заявки IntraService по API (Basic Auth из .env).

Usage:
  python scripts/intraservice_get_task.py 693437
  python scripts/intraservice_get_task.py 693437 --comments
  python scripts/intraservice_get_task.py 693437 --raw
"""
from __future__ import annotations

import argparse
import base64
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        raise SystemExit(f"Не найден {path}. Скопируйте .env.example → .env")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        env[key.strip()] = val.strip()
    return env


def basic_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def api_base_from_env(raw: str) -> tuple[str, str]:
    """Вернуть (api_base, host_base). api_base = https://host/api"""
    raw = (raw or "https://helpdesk.iek.local").strip().rstrip("/")
    parts = urlsplit(raw if "://" in raw else f"https://{raw}")
    host_base = urlunsplit((parts.scheme or "https", parts.netloc, "", "", ""))
    return f"{host_base}/api", host_base


def api_get(url: str, user: str, password: str, insecure_ssl: bool = True) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Authorization", basic_header(user, password))
    req.add_header("Accept", "application/json")
    ctx = ssl._create_unverified_context() if insecure_ssl else None
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"HTTP {e.code} {e.reason} for {url}\n{body}") from e
    except urllib.error.URLError as e:
        raise SystemExit(f"URL error: {e}") from e


def resolve_user(env: dict[str, str]) -> str:
    """IntraService Basic Auth: обычно логин без домена (fetisovaa)."""
    user = env.get("INTRASERVICE_USER", "").strip()
    if not user:
        raise SystemExit("В .env нет INTRASERVICE_USER")
    if env.get("INTRASERVICE_USER_AS_IS", "").strip().lower() in {"1", "true", "yes"}:
        return user
    if "@" in user:
        return user.split("@", 1)[0]
    return user


def uname(ref, users: dict) -> str:
    if isinstance(ref, dict):
        return ref.get("Name") or ref.get("Login") or str(ref.get("Id"))
    if isinstance(ref, int) and ref in users:
        u = users[ref]
        return u.get("Name") or u.get("Login") or str(ref)
    return str(ref)


def as_list(value) -> list:
    """API иногда отдаёт Executors/Observers/Files строкой через запятую."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",")]
        return [p for p in parts if p]
    return [value]


def main() -> int:
    parser = argparse.ArgumentParser(description="GET IntraService task by id")
    parser.add_argument("task_id", help="Id заявки, например 693437")
    parser.add_argument(
        "--fields",
        default="Id,Name,StatusId,PriorityId,Description,Created,Changed,ServiceId,TypeId",
        help="Список fields для API",
    )
    parser.add_argument(
        "--include",
        default="status,priority,executors,observers,creator,files",
        help="include=... для связанных сущностей",
    )
    parser.add_argument("--comments", action="store_true", help="Показать Lifetime/Comments если есть")
    parser.add_argument("--raw", action="store_true", help="Печатать полный JSON")
    parser.add_argument("--env", default=str(ROOT / ".env"), help="Путь к .env")
    args = parser.parse_args()

    env = load_env(Path(args.env))
    api_base, host_base = api_base_from_env(env.get("INTRASERVICE_BASE_URL", ""))
    password = env.get("INTRASERVICE_PASSWORD", "")
    if not password:
        raise SystemExit("В .env нет INTRASERVICE_PASSWORD")
    user = resolve_user(env)

    url = f"{api_base}/task/{args.task_id}?fields={args.fields}&include={args.include}"
    data = api_get(url, user, password)
    task = data.get("Task") or data

    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    card = f"{host_base}/Task/View/{task.get('Id', args.task_id)}"
    statuses = {s.get("Id"): s.get("Name") for s in (data.get("Statuses") or []) if isinstance(s, dict)}
    priorities = {p.get("Id"): p.get("Name") for p in (data.get("Priorities") or []) if isinstance(p, dict)}
    users = {u.get("Id"): u for u in (data.get("Users") or []) if isinstance(u, dict)}

    print(f"URL: {card}")
    print(f"Auth user: {user}")
    print(f"Id: {task.get('Id')}")
    print(f"Name: {task.get('Name')}")
    sid = task.get("StatusId")
    print(f"StatusId: {sid} ({statuses.get(sid, '?')})")
    pid = task.get("PriorityId")
    print(f"PriorityId: {pid} ({priorities.get(pid, '?')})")
    print(f"Created: {task.get('Created')}")
    print(f"Changed: {task.get('Changed')}")
    print("--- Description ---")
    print((task.get("Description") or "").strip())

    executors = as_list(task.get("Executors") or data.get("Executors"))
    observers = as_list(task.get("Observers") or data.get("Observers"))
    if executors:
        print("--- Executors ---")
        for e in executors:
            print(f"- {uname(e, users)}")
    if observers:
        print("--- Observers ---")
        for o in observers:
            print(f"- {uname(o, users)}")

    files = as_list(task.get("Files") or data.get("Files"))
    if files:
        print("--- Files ---")
        for f in files:
            if isinstance(f, dict):
                print(f"- {f.get('Name') or f.get('FileName')} (Id={f.get('Id')})")
            else:
                print(f"- {f}")

    if args.comments:
        for key in ("Lifetime", "Comments", "TaskComments"):
            block = data.get(key) or task.get(key)
            if block:
                print(f"--- {key} ---")
                print(json.dumps(block, ensure_ascii=False, indent=2)[:8000])
                break
        else:
            print("--- Comments ---")
            print("(в ответе API нет Lifetime/Comments; смотрите карточку в UI)")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
