# -*- coding: utf-8 -*-
"""Клиент GigaChat по образцу ClubOfSisters (OAuth Basic → chat/completions).

Эндпоинты и модель как в Assets/Scripts/StoryKeeper/StoryKeeperLlmClient.cs:
  OAuth  https://ngw.devices.sberbank.ru:9443/api/v2/oauth
  Chat   https://api.giga.chat/v1/chat/completions
  Model  GigaChat-3-Ultra
Сертификаты Сбера часто не в системном хранилище Windows — verify=False, как CA-handler в Unity.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HERE = Path(__file__).resolve().parent
OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://api.giga.chat/v1/chat/completions"
DEFAULT_MODEL = "GigaChat-3-Ultra"
DEFAULT_SCOPE = "GIGACHAT_API_PERS"
SECRET_KEYS = (
    "GIGACHAT_AUTHORIZATION_KEY",
    "GIGACHAT_AUTH_KEY",
    "GIGACHAT_API_KEY",
    "GIGACHAT_CLIENT_ID",
    "GIGACHAT_CLIENT_SECRET",
    "GIGACHAT_SCOPE",
    "GIGACHAT_MODEL",
)


def load_env(path: Path | None = None) -> None:
    env_path = path or (HERE / ".env")
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip("'").strip('"'))


def apply_streamlit_secrets() -> None:
    """Secrets Streamlit Cloud / secrets.toml. На HF Spaces ключи уже в env."""
    try:
        import streamlit as st
    except ImportError:
        return
    try:
        secrets = st.secrets
    except Exception:
        return
    for key in SECRET_KEYS:
        try:
            val = secrets.get(key)
        except Exception:
            continue
        if val is None:
            continue
        text = str(val).strip()
        if text:
            os.environ[key] = text


def load_runtime_secrets() -> None:
    load_env()
    apply_streamlit_secrets()


def authorization_basic() -> str:
    key = (
        os.environ.get("GIGACHAT_AUTHORIZATION_KEY")
        or os.environ.get("GIGACHAT_AUTH_KEY")
        or os.environ.get("GIGACHAT_API_KEY")
        or ""
    ).strip()
    if key:
        return key
    client_id = os.environ.get("GIGACHAT_CLIENT_ID", "").strip()
    secret = os.environ.get("GIGACHAT_CLIENT_SECRET", "").strip()
    if client_id and secret:
        import base64

        return base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("ascii")
    return ""


def has_credentials() -> bool:
    return bool(authorization_basic())


class GigaChatClient:
    def __init__(self) -> None:
        self._token = ""
        self._expires_at = 0.0
        self.model = os.environ.get("GIGACHAT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        self.scope = os.environ.get("GIGACHAT_SCOPE", DEFAULT_SCOPE).strip() or DEFAULT_SCOPE
        self._session = requests.Session()
        self._session.verify = False

    def _headers_oauth(self) -> dict[str, str]:
        return {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Authorization": "Basic " + authorization_basic(),
            "RqUID": str(uuid.uuid4()),
        }

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token
        basic = authorization_basic()
        if not basic:
            raise RuntimeError("Нет GIGACHAT_AUTHORIZATION_KEY (и нет пары CLIENT_ID/SECRET) в .env")
        resp = self._session.post(
            OAUTH_URL,
            data={"scope": self.scope},
            headers=self._headers_oauth(),
            timeout=60,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"GigaChat OAuth HTTP {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        token = data.get("access_token") or ""
        if not token:
            raise RuntimeError("GigaChat OAuth: нет access_token в ответе")
        expires = data.get("expires_at") or 0
        now = time.time()
        if expires > 10_000_000_000:
            self._expires_at = expires / 1000.0 - 120
        elif expires > now:
            self._expires_at = float(expires) - 120
        else:
            self._expires_at = now + 25 * 60
        self._token = token
        return token

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.15,
    ) -> str:
        token = self._ensure_token()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        resp = self._session.post(
            CHAT_URL,
            json=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            timeout=180,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"GigaChat HTTP {resp.status_code}: {resp.text[:800]}")
        choice = (resp.json().get("choices") or [{}])[0]
        return ((choice.get("message") or {}).get("content") or "").strip()
