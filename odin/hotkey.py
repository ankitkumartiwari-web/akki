from __future__ import annotations

import ctypes
import logging
import sys
import threading
from ctypes import wintypes
from typing import Callable

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MODIFIERS = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
}

KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
}
KEYS.update({f"f{number}": 0x6F + number for number in range(1, 25)})
KEYS.update({letter: ord(letter.upper()) for letter in "abcdefghijklmnopqrstuvwxyz"})
KEYS.update({digit: ord(digit) for digit in "0123456789"})

logger = logging.getLogger("odin.hotkey")
logger.addHandler(logging.NullHandler())


class HotkeyError(RuntimeError):
    pass


def hotkey_supported() -> bool:
    return sys.platform == "win32"


def parse_hotkey(value: str) -> tuple[int, int]:
    parts = [part.strip().lower() for part in value.split("+") if part.strip()]
    if not parts:
        raise HotkeyError("hotkey is empty")
    modifiers = 0
    key: int | None = None
    for part in parts:
        if part in MODIFIERS:
            modifiers |= MODIFIERS[part]
            continue
        if part in KEYS and key is None:
            key = KEYS[part]
            continue
        raise HotkeyError(f"unknown hotkey part: {part}")
    if key is None:
        raise HotkeyError("hotkey needs a key, for example ctrl+space")
    if not modifiers:
        raise HotkeyError("hotkey needs at least one modifier")
    return modifiers, key


class HotkeyListener:
    def __init__(self, callback: Callable[[], None], hotkey: str = "ctrl+space") -> None:
        self.callback = callback
        self.hotkey = hotkey
        self._modifiers, self._key = parse_hotkey(hotkey)
        self._id = (id(self) >> 4) & 0xBFFF or 1
        self._thread = threading.Thread(
            target=self._run, name="odin-hotkey", daemon=True
        )
        self._ready = threading.Event()
        self._thread_id: int | None = None
        self.error: str | None = None
        self.active = False

    def start(self, timeout: float = 3.0) -> None:
        if not hotkey_supported():
            raise HotkeyError("global hotkeys are only available on Windows")
        self._thread.start()
        if not self._ready.wait(timeout):
            self.stop()
            raise HotkeyError("timed out while registering the hotkey")
        if self.error:
            raise HotkeyError(self.error)

    def stop(self) -> None:
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id, WM_QUIT, 0, 0
            )
        if self._thread.is_alive():
            self._thread.join(2.0)
        self.active = False

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = int(kernel32.GetCurrentThreadId())
        try:
            registered = user32.RegisterHotKey(
                None, self._id, self._modifiers | MOD_NOREPEAT, self._key
            )
            if not registered:
                self.error = (
                    f"could not register {self.hotkey}; another application may use it"
                )
                return
            self.active = True
            self._ready.set()
            message = wintypes.MSG()
            while True:
                outcome = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if outcome in (0, -1):
                    break
                if message.message == WM_HOTKEY and message.wParam == self._id:
                    try:
                        self.callback()
                    except Exception:
                        pass
        finally:
            if self.active:
                user32.UnregisterHotKey(None, self._id)
            self.active = False
            self._ready.set()
