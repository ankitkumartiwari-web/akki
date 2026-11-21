from __future__ import annotations

from ..models import ToolResult
from ..storage import Storage


def remember_fact(fact: str, *, storage: Storage | None) -> ToolResult:
    if storage is None:
        return ToolResult.failure("database unavailable")
    text = " ".join(fact.strip().split())
    if not text:
        return ToolResult.failure("memory fact cannot be empty")
    try:
        memory_id = storage.remember(text)
    except ValueError as exc:
        return ToolResult.failure(str(exc))
    return ToolResult.success(
        f"Remembered #{memory_id}: {text}",
        data={"memory_id": memory_id, "fact": text},
    )
