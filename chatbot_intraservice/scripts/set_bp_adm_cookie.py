# -*- coding: utf-8 -*-
"""Записать BP_ADM_COOKIE из аргумента, файла или буфера обмена (Windows)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _normalize(raw: str) -> str:
    s = (raw or "").strip().strip('"').strip("'")
    if not s:
        return ""
    if s.lower().startswith("cookie:"):
        s = s.split(":", 1)[1].strip()
    if "kc-access=" not in s and s.startswith("eyJ"):
        s = f"kc-access={s}"
    return s


def _read_clipboard() -> str:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _write_env(cookie_str: str) -> None:
    env = ROOT / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.is_file() else []
    out, rep = [], False
    for line in lines:
        if line.startswith("BP_ADM_COOKIE="):
            out.append(f"BP_ADM_COOKIE={cookie_str}")
            rep = True
        else:
            out.append(line)
    if not rep:
        out.append(f"BP_ADM_COOKIE={cookie_str}")
    env.write_text("\n".join(out) + "\n", encoding="utf-8")
    import bp_adm  # noqa: WPS433

    cookies = bp_adm._parse_cookie_string(cookie_str)
    if not cookies.get("kc-access") and cookie_str.startswith("eyJ"):
        cookies = {"kc-access": cookie_str}
    bp_adm._sync_env(cookies)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cookie", nargs="?", help="Строка kc-access=...; kc-state=...")
    parser.add_argument("--paste", action="store_true", help="Из буфера обмена")
    parser.add_argument("--file", type=Path, help="Файл с cookie")
    args = parser.parse_args()

    raw = args.cookie or ""
    if args.file:
        raw = args.file.read_text(encoding="utf-8")
    if args.paste or not raw:
        clip = _read_clipboard()
        if clip.strip():
            raw = clip
    cookie_str = _normalize(raw)
    if not cookie_str or "kc-access=" not in cookie_str:
        print("Need Cookie header with kc-access=... (only kc-access; kc-state; kc-refresh)")
        return 1
    # оставить только kc-* перед записью
    import bp_adm  # noqa: WPS433

    cookies = bp_adm._parse_cookie_string(cookie_str)
    if not cookies.get("kc-access"):
        print("kc-access not found after parse")
        return 1
    cookie_str = bp_adm._cookie_string(cookies)
    names = [p.split("=", 1)[0].strip() for p in cookie_str.split(";") if "=" in p]
    print("names:", names)
    _write_env(cookie_str)
    print("updated", ROOT / ".env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
