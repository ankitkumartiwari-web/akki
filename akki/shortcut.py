from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .models import ToolResult

SHORTCUT_NAME = "AKKI Widget.lnk"


def _ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def install_desktop_widget_shortcut() -> ToolResult:
    target = Path(sys.executable).with_name("pythonw.exe")
    if not target.exists():
        target = Path(sys.executable)
    working_dir = Path(__file__).resolve().parent.parent
    script = (
        "$desktop = [Environment]::GetFolderPath('Desktop'); "
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$path = Join-Path $desktop {_ps(SHORTCUT_NAME)}; "
        "$link = $shell.CreateShortcut($path); "
        f"$link.TargetPath = {_ps(str(target))}; "
        "$link.Arguments = '-m akki.cli --widget-only'; "
        f"$link.WorkingDirectory = {_ps(str(working_dir))}; "
        "$link.Description = 'AKKI desktop access widget'; "
        f"$link.IconLocation = {_ps(str(target))} + ',0'; "
        "$link.Save(); Write-Output $path"
    )
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult.failure(f"could not create desktop shortcut: {exc}")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return ToolResult.failure(
            f"could not create desktop shortcut: {detail or 'PowerShell failed'}"
        )
    path = (completed.stdout or "").strip()
    return ToolResult.success(
        f"Desktop shortcut created: {path or SHORTCUT_NAME}",
        data={"path": path or SHORTCUT_NAME},
    )
