from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import Config
from ..models import ToolResult

VK_CODES = {"up": 0xAF, "down": 0xAE, "mute": 0xAD}

SCREENSHOT_SCRIPT = """
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Windows.Forms.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bitmap.Size)
$bitmap.Save('{path}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output 'ok'
"""

VOLUME_SCRIPT = """
$signature = '[DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);'
Add-Type -MemberDefinition $signature -Name Keyboard -Namespace AKKI
[AKKI.Keyboard]::keybd_event({code}, 0, 0, [UIntPtr]::Zero)
[AKKI.Keyboard]::keybd_event({code}, 0, 2, [UIntPtr]::Zero)
"""


def _run_powershell(script: str, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def take_screenshot(*, config: Config) -> ToolResult:
    folder = config.screenshot_dir.expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    target = folder / f"screenshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    escaped = str(target).replace("'", "''")
    try:
        completed = _run_powershell(SCREENSHOT_SCRIPT.format(path=escaped))
    except subprocess.TimeoutExpired:
        return ToolResult.failure("screenshot timed out")
    if completed.returncode != 0 or not target.exists():
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        return ToolResult.failure(f"screenshot failed: {detail}")
    return ToolResult.success(
        f"Screenshot saved to {target}",
        data={"path": str(target), "bytes": target.stat().st_size},
    )


def change_volume(direction: str, steps: int = 2) -> ToolResult:
    key = direction.strip().lower()
    if key not in VK_CODES:
        return ToolResult.failure(f"unknown volume direction: {direction}")
    count = 1 if key == "mute" else max(1, int(steps))
    script = "\n".join(VOLUME_SCRIPT.format(code=code) for code in range(1, count + 1))
    try:
        completed = _run_powershell(script, timeout=15.0)
    except subprocess.TimeoutExpired:
        return ToolResult.failure("volume change timed out")
    if completed.returncode != 0:
        return ToolResult.failure(f"volume change failed: {completed.stderr.strip()}")
    return ToolResult.success(f"Volume {key} requested (unverified)", verified=False)


def lock_screen() -> ToolResult:
    try:
        completed = subprocess.run(
            ["rundll32.exe", "user32.dll,LockWorkStation"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult.failure(f"could not lock screen: {exc}")
    if completed.returncode != 0:
        return ToolResult.failure("could not lock screen")
    return ToolResult.success("Locked the Windows screen", verified=True)


def clipboard_read() -> ToolResult:
    script = "[System.Windows.Forms.Clipboard]::GetText()"
    try:
        completed = _run_powershell(script, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult.failure(f"could not read clipboard: {exc}")
    if completed.returncode != 0:
        return ToolResult.failure(f"could not read clipboard: {completed.stderr.strip()}")
    text = (completed.stdout or "").strip()
    if not text:
        return ToolResult.failure("clipboard is empty")
    return ToolResult.success(
        f"Read clipboard ({len(text)} chars)",
        data={"text": text, "chars": len(text)},
    )


def clipboard_write(text: str) -> ToolResult:
    cleaned = text.strip()
    if not cleaned:
        return ToolResult.failure("clipboard text cannot be empty")
    escaped = cleaned.replace("'", "''")
    script = f"[System.Windows.Forms.Clipboard]::SetText('{escaped}')"
    try:
        completed = _run_powershell(script, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult.failure(f"could not write clipboard: {exc}")
    if completed.returncode != 0:
        return ToolResult.failure(f"could not write clipboard: {completed.stderr.strip()}")
    return ToolResult.success(f"Wrote {len(cleaned)} chars to the clipboard", verified=True)
