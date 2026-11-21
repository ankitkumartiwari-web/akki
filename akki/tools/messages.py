from __future__ import annotations

from datetime import datetime

from ..config import database_path
from ..models import ToolResult
from .system import clipboard_write


def compose_message(text: str) -> ToolResult:
    cleaned = text.strip()
    if not cleaned:
        return ToolResult.failure("message text cannot be empty")

    draft_dir = database_path().parent / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft = draft_dir / f"message-{datetime.now():%Y%m%d-%H%M%S}.txt"
    try:
        draft.write_text(cleaned + "\n", encoding="utf-8")
    except OSError as exc:
        return ToolResult.failure(f"could not save message draft: {exc}")

    copied = clipboard_write(cleaned)
    if not copied.ok:
        return ToolResult.failure(
            f"message saved to {draft}, but clipboard copy failed: {copied.message}",
            data={"text": cleaned, "chars": len(cleaned), "draft": str(draft)},
        )

    return ToolResult.success(
        f"Message ready ({len(cleaned)} chars) - copied to clipboard and saved to {draft}\n{cleaned}",
        data={"text": cleaned, "chars": len(cleaned), "draft": str(draft)},
    )
