from __future__ import annotations

import os
import time
from pathlib import Path

from ..config import Config
from ..models import ToolResult

SKIP_DIRS = {
    "node_modules",
    ".git",
    "venv",
    "__pycache__",
    "appdata",
    "windows",
    "program files",
    "program files (x86)",
    "$recycle.bin",
    "system volume information",
}


def search_paths(query: str, config: Config) -> list[Path]:
    wanted = query.strip().lower()
    if not wanted:
        return []

    results: list[Path] = []
    deadline = time.monotonic() + config.timeout_seconds

    for root in config.search_roots:
        if not root.exists():
            continue
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack:
            if len(results) >= config.max_results or time.monotonic() > deadline:
                return results
            current, depth = stack.pop()
            try:
                entries = list(os.scandir(current))
            except OSError:
                continue
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        name = entry.name.lower()
                        if (
                            depth < config.max_depth
                            and name not in SKIP_DIRS
                            and not name.startswith(".")
                        ):
                            stack.append((Path(entry.path), depth + 1))
                    if wanted in entry.name.lower():
                        results.append(Path(entry.path))
                        if len(results) >= config.max_results:
                            return results
                except OSError:
                    continue

    return results


def find_files(query: str, *, config: Config) -> ToolResult:
    results = search_paths(query, config)
    if not results:
        roots = ", ".join(str(p) for p in config.search_roots)
        return ToolResult.failure(f"no matches for '{query}' in {roots}")

    results.sort(key=lambda p: (p.stem.lower() != query.lower(), len(p.name)))
    shown = [str(p) for p in results]
    limited = " (limited)" if len(results) >= config.max_results else ""
    return ToolResult.success(
        f"Found {len(results)} match(es) for '{query}'{limited}",
        data={"matches": shown},
    )


def open_path(path: str, *, config: Config) -> ToolResult:
    target = Path(path).expanduser()
    if not target.is_absolute():
        for root in config.search_roots:
            candidate = root / target
            if candidate.exists():
                target = candidate
                break
    if not target.exists():
        return ToolResult.failure(f"path does not exist: {target}")
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
    except OSError as exc:
        return ToolResult.failure(f"could not open {target}: {exc}")
    return ToolResult.success(f"Opened {target} (unverified)", verified=False)
