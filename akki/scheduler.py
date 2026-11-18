from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from .models import ActionRequest
from .router import route
from .storage import Storage


def schedule_every(storage: Storage, command: str, seconds: float) -> int:
    if seconds <= 0:
        raise ValueError("interval must be positive")
    return storage.add_job(
        command=command,
        kind="interval",
        interval_seconds=float(seconds),
        daily_time=None,
        next_run=time.time() + float(seconds),
    )


def schedule_daily(storage: Storage, command: str, hhmm: str) -> int:
    parts = hhmm.split(":")
    if len(parts) != 2:
        raise ValueError("daily schedule uses HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("daily schedule time is invalid")
    now = datetime.now()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate = candidate.replace(day=candidate.day + 1)
    return storage.add_job(
        command=command,
        kind="daily",
        interval_seconds=None,
        daily_time=hhmm,
        next_run=candidate.timestamp(),
    )


def list_jobs(storage: Storage) -> list[dict[str, object]]:
    return [dict(job) for job in storage.list_jobs()]


def cancel_job(storage: Storage, job_id: int) -> bool:
    return storage.delete_job(job_id)


def due_jobs(storage: Storage, now: float) -> list[dict[str, object]]:
    return [dict(job) for job in storage.pop_due_jobs(now)]


def execute_due(
    storage: Storage,
    registry: object,
    config: object,
    now: float,
) -> list[tuple[dict[str, object], object]]:
    jobs = due_jobs(storage, now)
    results: list[tuple[dict[str, object], object]] = []
    for job in jobs:
        command = str(job.get("command") or "")
        request = route(command, config)  # type: ignore[arg-type]
        if request is None:
            continue
        result = registry.execute(
            request,  # type: ignore[arg-type]
            profile=str(getattr(config, "profile", "sovereign")),  # type: ignore[arg-type]
            confirm=lambda _: False,
        )  # type: ignore[arg-type]
        results.append((dict(job), result))
    return results
