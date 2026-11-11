from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActionLevel(str, Enum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    SENSITIVE = "sensitive"
    DESTRUCTIVE = "destructive"
    ELEVATED = "elevated"


@dataclass(slots=True)
class ToolResult:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    verified: bool = False

    @classmethod
    def success(
        cls, message: str, *, data: dict[str, Any] | None = None, verified: bool = True
    ) -> "ToolResult":
        return cls(True, message, data or {}, verified)

    @classmethod
    def failure(
        cls, message: str, *, data: dict[str, Any] | None = None
    ) -> "ToolResult":
        return cls(False, message, data or {}, False)


@dataclass(slots=True)
class ActionRequest:
    tool: str
    args: dict[str, Any]
    raw: str = ""
