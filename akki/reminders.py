from __future__ import annotations

import re

_TIME_PATTERN = re.compile(
    r"(?:\bin|\bafter|\bfor|\bbaad)\s+(\d+(?:\.\d+)?)\s*"
    r"(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b"
    r"|(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)"
    r"\s+(?:baad|ke\s+baad)\b",
    re.IGNORECASE,
)
_REMINDER_HINT = re.compile(
    r"\b(?:remind|yaad\s+dilana|yaad\s+dila\s+do|yaad\s+dilao|timer)\b",
    re.IGNORECASE,
)
_PREFIX_PATTERN = re.compile(
    r"^\s*(?:hey\s+akki[,\s]+)?"
    r"(?:(?:remind\s+me|mujhe|yaad\s+dilana|yaad\s+dila\s+do|yaad\s+dilao|"
    r"set\s+(?:a\s+)?timer|timer)\b[\s,:-]*)+",
    re.IGNORECASE,
)
_LEAD_PATTERN = re.compile(
    r"^\s*(?:to|that|ki|ke\s+liye|for)\b[\s,:-]*",
    re.IGNORECASE,
)
_UNIT_SECONDS = {
    "second": 1,
    "sec": 1,
    "minute": 60,
    "min": 60,
    "hour": 3600,
    "hr": 3600,
}


def parse_reminder(text: str) -> tuple[int, str] | None:
    if _REMINDER_HINT.search(text) is None:
        return None
    match = _TIME_PATTERN.search(text)
    if match is None:
        return None
    amount_text = match.group(1) or match.group(3)
    unit_text = match.group(2) or match.group(4)
    try:
        amount = float(amount_text)
    except (TypeError, ValueError):
        return None
    unit = unit_text.lower().rstrip("s")
    factor = _UNIT_SECONDS.get(unit)
    if factor is None or amount <= 0:
        return None
    seconds = int(round(amount * factor))
    if seconds <= 0:
        return None
    body = (text[: match.start()] + " " + text[match.end() :]).strip()
    body = _PREFIX_PATTERN.sub("", body).strip()
    body = _LEAD_PATTERN.sub("", body).strip()
    body = re.sub(r"^[\s,:-]+", "", body).strip(" .?!")
    if not body:
        return None
    return seconds, body


def format_duration(seconds: int) -> str:
    if seconds >= 3600 and seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    if seconds >= 60 and seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    return f"{seconds} second" if seconds == 1 else f"{seconds} seconds"
