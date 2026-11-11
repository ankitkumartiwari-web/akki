from __future__ import annotations

import os
import shutil
import subprocess
import time
import winreg
from pathlib import Path

from ..config import AppEntry, Config
from ..models import ToolResult

START_MENU_DIRS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(os.environ.get("ProgramData", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
]

KNOWN_PATHS = {
    "code": [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe",
    ],
    "chrome": [
        Path(os.environ.get("ProgramFiles", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ],
    "msedge": [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ],
}


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _viable(path: Path) -> bool:
    return bool(str(path)) and path.exists()


def _start_menu_match(wanted: str) -> Path | None:
    key = _normalize(wanted)
    best: tuple[int, Path] | None = None
    for root in START_MENU_DIRS:
        if not root.exists():
            continue
        for shortcut in root.rglob("*.lnk"):
            stem = _normalize(shortcut.stem)
            if stem == key:
                score = 0
            elif stem.startswith(key):
                score = 1
            elif key in stem:
                score = 2
            else:
                continue
            if best is None or score < best[0]:
                best = (score, shortcut)
                if score == 0:
                    return shortcut
    return best[1] if best else None


def _registry_match(name: str) -> Path | None:
    candidates = [name]
    if not name.lower().endswith(".exe"):
        candidates.append(f"{name}.exe")
    for candidate in candidates:
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            subkey = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{candidate}"
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | view) as key:
                        value, _ = winreg.QueryValueEx(key, "")
                        path = Path(value)
                        if path.exists():
                            return path
                except OSError:
                    continue
    return None


def _known_path(command: str) -> Path | None:
    for path in KNOWN_PATHS.get(command.lower(), []):
        if _viable(path):
            return path
    return None


def _which(command: str) -> Path | None:
    resolved = shutil.which(command)
    return Path(resolved) if resolved else None


def _pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259
    finally:
        kernel32.CloseHandle(handle)


def _spawn(executable: Path, args: list[str] | None = None) -> ToolResult:
    argv = [str(executable), *(args or [])]
    if executable.suffix.lower() in {".cmd", ".bat"}:
        argv = ["cmd", "/c", *argv]
    try:
        process = subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        return ToolResult.failure(f"could not launch {executable.name}: {exc}")
    time.sleep(0.4)
    code = process.poll()
    if code is not None:
        return ToolResult.failure(f"{executable.name} exited immediately with code {code}")
    if not _pid_alive(process.pid):
        return ToolResult.failure(f"{executable.name} did not stay running")
    return ToolResult.success(
        f"Launched {executable.name} (pid {process.pid})",
        data={"pid": process.pid, "executable": str(executable)},
        verified=True,
    )


def _shell_open(target: Path) -> ToolResult:
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
    except OSError as exc:
        return ToolResult.failure(f"could not open {target}: {exc}")
    return ToolResult.success(f"Opened {target} (unverified)", verified=False)


def _launch_aumid(name: str, aumid: str) -> ToolResult:
    try:
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{aumid}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return ToolResult.failure(f"could not launch {name}: {exc}")
    return ToolResult.success(f"Launched {name} (unverified)", verified=False)


def _resolve_executable(entry: AppEntry | None, alias: str) -> Path | None:
    if entry and entry.path:
        path = Path(entry.path).expanduser()
        if path.exists():
            return path
    if entry and entry.command:
        found = _known_path(entry.command) or _which(entry.command)
        if found:
            return found
    for candidate in (alias, alias.replace(" ", "")):
        found = _known_path(candidate) or _which(candidate) or _registry_match(candidate)
        if found:
            return found
    return None


def launch_app(alias: str, *, config: Config) -> ToolResult:
    name = alias.strip().strip(".?!")
    if not name:
        return ToolResult.failure("no application name given")

    match = config.find_app(name)
    entry = match[1] if match else None
    display = match[0] if match else name

    if entry and entry.aumid:
        return _launch_aumid(display, entry.aumid)

    executable = _resolve_executable(entry, name)
    if executable:
        return _spawn(executable)

    shortcut = _start_menu_match(name)
    if shortcut:
        return _shell_open(shortcut)

    return ToolResult.failure(
        f"could not find an application named '{name}'. "
        "Add it to the apps section of the ODIN config."
    )


def _clean_target(target: str) -> str:
    cleaned = target.strip().strip("\"'").strip()
    if cleaned.lower().startswith("my "):
        cleaned = cleaned[3:].strip()
    for suffix in (" project", " folder", " directory"):
        if cleaned.lower().endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    return cleaned


def _resolve_target(target: str, config: Config) -> Path | None:
    cleaned = _clean_target(target)
    direct = Path(cleaned).expanduser()
    if direct.exists():
        return direct.resolve()

    from .files import search_paths

    matches = search_paths(cleaned, config)
    if not matches:
        return None
    ranked = sorted(
        matches,
        key=lambda p: (p.stem.lower() != cleaned.lower(), len(p.name)),
    )
    return ranked[0]


def open_in_app(alias: str, target: str, *, config: Config) -> ToolResult:
    resolved = _resolve_target(target, config)
    if resolved is None:
        return ToolResult.failure(f"could not find a file or folder matching '{target}'")

    match = config.find_app(alias)
    entry = match[1] if match else None
    executable = _resolve_executable(entry, alias)
    if executable is None:
        return ToolResult.failure(
            f"could not find an application named '{alias}'. "
            "Add it to the apps section of the ODIN config."
        )

    result = _spawn(executable, [str(resolved)])
    if result.ok:
        result.message = f"Opened {resolved.name} in {executable.stem} (pid {result.data.get('pid')})"
        result.data["target"] = str(resolved)
    return result
