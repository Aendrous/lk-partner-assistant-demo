# -*- coding: utf-8 -*-
"""HTTP API для n8n: запуск watch/analyze без Windows Task Scheduler.

  python scripts/n8n_http_server.py

.env:
  N8N_BOT_API_KEY=...
  N8N_BOT_HTTP_HOST=0.0.0.0
  N8N_BOT_HTTP_PORT=8765
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "src"))

from env_bootstrap import load_package_env  # noqa: E402

load_package_env()

import importlib.util


def _load_env() -> None:
    load_package_env()


def _api_key() -> str:
    return (
        os.environ.get("N8N_BOT_API_KEY")
        or os.environ.get("N8N_API_KEY")
        or os.environ.get("N8N_WEBHOOK_HELPDESK")
        or ""
    ).strip()


def _auth_ok(header: str | None) -> bool:
    key = _api_key()
    if not key:
        return True
    if not header:
        return False
    h = header.strip()
    if h.lower().startswith("bearer "):
        return h[7:].strip() == key
    return h == key


def _json_response(handler: BaseHTTPRequestHandler, code: int, body: dict[str, Any]) -> None:
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _n8n_run() -> Any:
    spec = importlib.util.spec_from_file_location("n8n_run", ROOT / "scripts" / "n8n_run.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("n8n_run.py not found")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_analyze(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
    from pipeline import run_ticket_pipeline

    post = body.get("post")
    learn = body.get("learn")
    take = body.get("take_in_work")
    trigger = str(body.get("trigger") or "n8n")
    return run_ticket_pipeline(
        task_id,
        post=post if post is not None else None,
        learn=learn if learn is not None else None,
        take_in_work=take if take is not None else None,
        trigger=trigger,  # type: ignore[arg-type]
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"[n8n-http] {self.address_string()} - {fmt % args}\n")

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def _handle(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/health":
            from settings import load_settings

            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "service": "chatbot-intraservice",
                    "watch_new": load_settings().get("watch_new_enabled"),
                },
            )
            return

        if not _auth_ok(self.headers.get("Authorization")):
            _json_response(self, 401, {"ok": False, "error": "unauthorized"})
            return

        body: dict[str, Any] = {}
        if self.command == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                try:
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                except json.JSONDecodeError:
                    _json_response(self, 400, {"ok": False, "error": "invalid JSON body"})
                    return

        try:
            if path.startswith("/analyze/"):
                task_id = path.split("/analyze/", 1)[1].strip("/")
                if not task_id.isdigit():
                    _json_response(self, 400, {"ok": False, "error": "task_id required"})
                    return
                result = _run_analyze(task_id, body)
                _json_response(self, 200, {"ok": True, "result": result})
                return

            action_map = {
                "/run/watch-new": "watch_new",
                "/run/watch-overdue": "watch_overdue",
                "/run/watch-user-reply": "watch_user_reply",
                "/run/pipeline-watch": "pipeline_watch",
            }
            action = action_map.get(path)
            if not action:
                _json_response(self, 404, {"ok": False, "error": f"unknown path: {path}"})
                return
            mod = _n8n_run()
            result = mod.run_script(action)
            _json_response(self, 200, result)
        except Exception as exc:
            _json_response(
                self,
                500,
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "trace": traceback.format_exc()[-800:],
                },
            )


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description="HTTP API for n8n")
    parser.add_argument("--host", default=os.environ.get("N8N_BOT_HTTP_HOST") or "0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("N8N_BOT_HTTP_PORT") or "8765"))
    args = parser.parse_args()

    if not _api_key():
        print("WARNING: N8N_BOT_API_KEY не задан — API без авторизации.", file=sys.stderr)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"n8n HTTP API: http://{args.host}:{args.port}/health", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
