# -*- coding: utf-8 -*-
"""Import adm.bp cookies from Cursor browser (Windows, DPAPI + AES-GCM)."""
from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PART = Path(os.environ.get("APPDATA", "")) / "Cursor" / "Partitions" / "cursor-browser"
COOKIES = PART / "Network" / "Cookies"
LOCAL_STATE = Path(os.environ.get("APPDATA", "")) / "Cursor" / "Local State"
KC_ORDER = ("kc-access", "kc-state", "kc-refresh", "id_token")


def _copy_locked(src: Path, dst: Path) -> bool:
    try:
        import win32file
        import pywintypes

        handle = win32file.CreateFile(
            str(src),
            win32file.GENERIC_READ,
            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE | win32file.FILE_SHARE_DELETE,
            None,
            win32file.OPEN_EXISTING,
            win32file.FILE_ATTRIBUTE_NORMAL,
            None,
        )
        try:
            size = win32file.GetFileSize(handle)
            _, data = win32file.ReadFile(handle, size)
            dst.write_bytes(data)
            return True
        finally:
            win32file.CloseHandle(handle)
    except ImportError:
        pass
    except Exception as err:
        print("win32 copy:", err)
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        GENERIC_READ = 0x80000000
        FILE_SHARE_READ = 0x1
        FILE_SHARE_WRITE = 0x2
        FILE_SHARE_DELETE = 0x4
        OPEN_EXISTING = 3
        handle = kernel32.CreateFileW(
            str(src),
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle == wintypes.HANDLE(-1).value:
            print("CreateFileW failed", ctypes.get_last_error())
            return False
        try:
            size = kernel32.GetFileSize(handle, None)
            buf = ctypes.create_string_buffer(size)
            read = wintypes.DWORD()
            if not kernel32.ReadFile(handle, buf, size, ctypes.byref(read), None):
                print("ReadFile failed", ctypes.get_last_error())
                return False
            dst.write_bytes(buf.raw[: read.value])
            return True
        finally:
            kernel32.CloseHandle(handle)
    except Exception as err:
        print("ctypes copy:", err)
    try:
        shutil.copy2(src, dst)
        return True
    except Exception as err:
        print("shutil copy:", err)
        return False


def _master_key() -> bytes | None:
    if not LOCAL_STATE.is_file():
        return None
    try:
        data = json.loads(LOCAL_STATE.read_text(encoding="utf-8"))
        enc_key = base64.b64decode(data["os_crypt"]["encrypted_key"])
        if enc_key.startswith(b"DPAPI"):
            enc_key = enc_key[5:]
        import win32crypt

        return win32crypt.CryptUnprotectData(enc_key, None, None, None, 0)[1]
    except ImportError:
        print("pip install pywin32 for cookie decrypt")
        return None
    except Exception as err:
        print("master key:", err)
        return None


def _decrypt_value(raw: bytes, key: bytes | None) -> str:
    if not raw:
        return ""
    if raw[:3] in (b"v10", b"v11") and key:
        try:
            from Cryptodome.Cipher import AES

            nonce = raw[3:15]
            payload = raw[15:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            return cipher.decrypt(payload).decode("utf-8")
        except Exception as err:
            print("aes decrypt:", err)
            return ""
    try:
        return raw.decode("utf-8")
    except Exception:
        if key:
            try:
                import win32crypt

                return win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1].decode("utf-8")
            except Exception:
                return ""
        return ""


def read_cookies() -> dict[str, str]:
    if not COOKIES.is_file():
        print("no cookies db", COOKIES)
        return {}
    tmp = Path(tempfile.gettempdir()) / "cursor_adm_cookies.db"
    if not _copy_locked(COOKIES, tmp):
        return {}
    key = _master_key()
    con = sqlite3.connect(str(tmp))
    cur = con.cursor()
    cur.execute(
        "SELECT name, value, encrypted_value, host_key FROM cookies "
        "WHERE host_key LIKE '%bp.iek%'"
    )
    out: dict[str, str] = {}
    for name, value, enc, host in cur.fetchall():
        if not str(name).startswith("kc-") and name != "id_token":
            continue
        plain = value or _decrypt_value(enc or b"", key)
        if plain:
            out[str(name)] = plain
            print(host, name, "ok len", len(plain))
    con.close()
    return out


def write_env(cookies: dict[str, str]) -> None:
    cookie_str = "; ".join(f"{k}={cookies[k]}" for k in KC_ORDER if cookies.get(k))
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


def main() -> int:
    if not COOKIES.is_file():
        print("no cookies db", COOKIES)
        return 1
    print("If import fails: close adm.bp tab in Cursor browser, then rerun.")
    cookies = read_cookies()
    print("names", sorted(cookies.keys()))
    if not cookies.get("kc-access"):
        return 1
    write_env(cookies)
    print("updated", ROOT / ".env")
    # init session cache
    sys.path.insert(0, str(ROOT / "src"))
    import bp_adm  # noqa: WPS433

    bp_adm._sync_env(cookies)
    print("session synced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
