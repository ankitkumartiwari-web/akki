from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .models import ActionLevel, ActionRequest, ToolResult
from .permissions import requires_confirmation

ToolFunc = Callable[..., ToolResult]
ConfirmFunc = Callable[[str], bool]
logger = logging.getLogger("akki.registry")
logger.addHandler(logging.NullHandler())


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    level: ActionLevel
    func: ToolFunc
    parameters: dict[str, str] = field(default_factory=dict)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        name: str,
        description: str,
        level: ActionLevel,
        func: ToolFunc,
        parameters: dict[str, str] | None = None,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        self._tools[name] = ToolSpec(name, description, level, func, parameters or {})

    def unregister(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return sorted(self._tools.values(), key=lambda spec: spec.name)

    def execute(
        self,
        request: ActionRequest,
        *,
        profile: str = "sovereign",
        confirm: ConfirmFunc | None = None,
    ) -> ToolResult:
        spec = self._tools.get(request.tool)
        if spec is None:
            logger.warning("unknown tool=%s", request.tool)
            return ToolResult.failure(f"unknown tool: {request.tool}")

        if requires_confirmation(spec.level, profile):
            if confirm is None:
                return ToolResult.failure(
                    f"{request.tool} is a {spec.level.value} action and requires confirmation"
                )
            prompt = f"Run {request.tool} with {request.args}?"
            if not confirm(prompt):
                logger.info("tool=%s cancelled", request.tool)
                return ToolResult.failure("cancelled by user")

        started = time.perf_counter()
        try:
            result = spec.func(**request.args)
        except TypeError as exc:
            logger.warning("tool=%s invalid arguments", request.tool)
            return ToolResult.failure(f"invalid arguments for {request.tool}: {exc}")
        except Exception as exc:
            logger.exception("tool=%s crashed", request.tool)
            return ToolResult.failure(f"{request.tool} failed: {exc}")

        elapsed = time.perf_counter() - started
        if not isinstance(result, ToolResult):
            logger.error("tool=%s returned an invalid result", request.tool)
            return ToolResult.failure(f"{request.tool} returned an invalid result")
        logger.info(
            "tool=%s ok=%s verified=%s elapsed=%.3fs",
            request.tool,
            result.ok,
            result.verified,
            elapsed,
        )
        return result
