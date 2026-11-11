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
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bitmap.Size)
$bitmap.Save('{path}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output 'ok'
"""

VOLUME_SCRIPT = """
$signature = '[DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);'
Add-Type -MemberDefinition $signature -Name Keyboard -Namespace ODIN
[ODIN.Keyboard]::keybd_event({code}, 0, 0, [UIntPtr]::Zero)
[ODIN.Keyboard]::keybd_event({code}, 0, 2, [UIntPtr]::Zero)
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
    code = VK_CODES[key]
    script = "\n".join(VOLUME_SCRIPT.format(code=code) for _ in range(count))
    try:
        completed = _run_powershell(script, timeout=15.0)
    except subprocess.TimeoutExpired:
        return ToolResult.failure("volume change timed out")
    if completed.returncode != 0:
        return ToolResult.failure(f"volume change failed: {completed.stderr.strip()}")
    return ToolResult.success(f"Volume {key} requested (unverified)", verified=False)
