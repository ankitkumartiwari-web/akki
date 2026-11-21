from __future__ import annotations

import logging

from .. import alerts
from ..config import Config
from ..models import ToolResult

logger = logging.getLogger("akki.tools.reminders")


def announce_reminder(text: str, *, config: Config) -> ToolResult:
    clean = " ".join(text.split()).strip()
    if not clean:
        return ToolResult.failure("reminder text is empty")
    message = f"Reminder: {clean}"
    try:
        from ..cli import speak_text

        speak_text(message, config)
    except Exception as exc:
        logger.warning("reminder voice failed: %s", exc)
        alert = alerts.send_mobile_alert("AKKI reminder", clean, config=config)
        if alert.ok:
            return ToolResult.success(
                message, data={"channel": "mobile"}, verified=False
            )
        return ToolResult.failure(
            message,
            data={"voice_error": str(exc), "mobile_error": alert.message},
        )
    return ToolResult.success(message, data={"channel": "voice"}, verified=False)
