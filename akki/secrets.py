from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from .config import config_path


class SecretError(RuntimeError):
    pass


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise SecretError("Windows DPAPI is required to store secrets")
    buffer = ctypes.create_string_buffer(data, len(data))
    input_blob = DATA_BLOB(
        len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
    )
    output_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise SecretError("CryptProtectData failed")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def _unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise SecretError("Windows DPAPI is required to store secrets")
    buffer = ctypes.create_string_buffer(data, len(data))
    input_blob = DATA_BLOB(
        len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
    )
    output_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise SecretError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def secrets_path() -> Path:
    override = os.environ.get("AKKI_SECRETS")
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else config_path().parent
    return root / "AKKI" / "secrets.json"


class SecretsStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        protect: Callable[[bytes], bytes] | None = None,
        unprotect: Callable[[bytes], bytes] | None = None,
    ) -> None:
        self.path = path or secrets_path()
        self._protect = protect or _protect
        self._unprotect = unprotect or _unprotect
        self._secrets: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        secrets = payload.get("secrets", {})
        if isinstance(secrets, dict):
            self._secrets = {
                str(name): str(value)
                for name, value in secrets.items()
                if isinstance(value, str)
            }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "secrets": self._secrets}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        os.replace(temporary, self.path)

    def names(self) -> list[str]:
        return sorted(self._secrets)

    def has_secret(self, name: str) -> bool:
        return self.get_secret(name) is not None

    def get_secret(self, name: str) -> str | None:
        encoded = self._secrets.get(name)
        if not encoded:
            return None
        try:
            raw = base64.b64decode(encoded)
            return self._unprotect(raw).decode("utf-8")
        except (SecretError, ValueError, UnicodeDecodeError):
            return None

    def set_secret(self, name: str, value: str) -> None:
        name = name.strip()
        if not name:
            raise SecretError("secret name is required")
        if not value:
            self.delete_secret(name)
            return
        encoded = base64.b64encode(self._protect(value.encode("utf-8"))).decode(
            "ascii"
        )
        self._secrets[name] = encoded
        self._save()
        os.environ[name] = value

    def delete_secret(self, name: str) -> None:
        if name not in self._secrets:
            return
        del self._secrets[name]
        self._save()
        os.environ.pop(name, None)

    def load_into_env(self, *, override: bool = False) -> None:
        for name in self._secrets:
            value = self.get_secret(name)
            if value is None:
                continue
            if override or not os.environ.get(name):
                os.environ[name] = value
