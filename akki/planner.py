from __future__ import annotations

import re
from collections.abc import Callable

from .config import Config
from .models import ActionRequest, ToolResult
from .registry import ToolRegistry
from .router import route

STEP_SPLIT = re.compile(
    r"\s+(?:(?:and\s+)?then|after that)\s+",
    re.IGNORECASE,
)


def split_steps(text: str) -> list[str]:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return []
    parts = [
        part.strip(" ,.")
        for part in STEP_SPLIT.split(cleaned)
        if part.strip(" ,.")
    ]
    return parts if len(parts) > 1 else [cleaned]


def plan_steps(text: str, config: Config | None = None) -> list[ActionRequest]:
    steps = split_steps(text)
    if len(steps) <= 1:
        return []
    requests: list[ActionRequest] = []
    for step in steps:
        request = route(step, config)
        if request is None:
            return []
        requests.append(request)
    return requests


def combine_results(results: list[ToolResult]) -> ToolResult:
    if not results:
        return ToolResult.failure("no steps to execute")
    lines = [
        f"{index}. {'OK' if result.ok else 'FAILED'}: {result.message}"
        for index, result in enumerate(results, 1)
    ]
    return ToolResult(
        all(result.ok for result in results),
        "\n".join(lines),
        {
            "steps": [
                {
                    "ok": result.ok,
                    "verified": result.verified,
                    "message": result.message,
                    "data": result.data,
                }
                for result in results
            ]
        },
        all(result.verified for result in results),
    )


def execute_steps(
    requests: list[ActionRequest],
    registry: ToolRegistry,
    *,
    profile: str = "sovereign",
    confirm: Callable[[str], bool] | None = None,
    on_result: Callable[[ActionRequest, ToolResult], None] | None = None,
) -> ToolResult:
    results: list[ToolResult] = []
    for request in requests:
        result = registry.execute(
            request,
            profile=profile,
            confirm=confirm,
        )
        results.append(result)
        if on_result is not None:
            on_result(request, result)
        if not result.ok:
            break
    return combine_results(results)
