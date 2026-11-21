from __future__ import annotations

import logging
from collections.abc import Callable

from .models import ActionLevel

logger = logging.getLogger("akki.permissions")

CONFIRM_LEVELS = frozenset(
    {ActionLevel.SENSITIVE, ActionLevel.DESTRUCTIVE, ActionLevel.ELEVATED}
)


def requires_confirmation(level: ActionLevel, profile: str) -> bool:
    if profile == "guarded":
        return level in CONFIRM_LEVELS or level == ActionLevel.REVERSIBLE
    return level in CONFIRM_LEVELS


def ask_confirmation(prompt: str, input_fn: Callable[[str], str] = input) -> bool:
    try:
        answer = input_fn(f"{prompt} [y/N] ").strip().lower()
    except (EOFError, RuntimeError, OSError) as exc:
        logger.warning("confirmation unavailable: %s", exc)
        return False
    return answer in {"y", "yes"}
