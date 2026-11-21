from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

from .. import knowledge
from ..config import Config
from ..models import ToolResult

MAX_FILE_BYTES = 8_000_000
MAX_READ_CHARS = 20_000
ALL_TARGETS = {
    "all",
    "all files",
    "everything",
    "files",
    "folders",
    "my files",
    "sab",
    "sab kuch",
}
ROOT_ALIASES = {
    "desktop": ("Desktop",),
    "documents": ("Documents",),
    "downloads": ("Downloads",),
    "projects": ("Projects",),
    "code": ("Code",),
    "dev": ("Dev",),
}
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


def _clean_target(value: str) -> str:
    cleaned = " ".join(value.strip().strip("\"'").split())
    lowered = cleaned.lower()
    for prefix in ("my ", "the ", "mera ", "meri ", "mere ", "apna "):
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
            lowered = cleaned.lower()
    for suffix in (" folder", " directory", " files"):
        if lowered.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
            lowered = cleaned.lower()
    return cleaned


def _root_aliases(value: str, config: Config) -> list[Path]:
    key = _clean_target(value).lower()
    wanted = ROOT_ALIASES.get(key)
    if wanted is None:
        return []
    names = {name.lower() for name in wanted}
    roots = [root for root in config.search_roots if root.name.lower() in names]
    if not roots:
        home = Path.home()
        for base in (home, home / "OneDrive"):
            for name in wanted:
                candidate = base / name
                if candidate.exists():
                    roots.append(candidate)
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        marker = str(root.resolve()).lower()
        if marker not in seen:
            seen.add(marker)
            unique.append(root)
    return unique


def _root_alias(value: str, config: Config) -> Path | None:
    roots = _root_aliases(value, config)
    return roots[0] if roots else None


def resolve_target(
    target: str, config: Config, *, prefer_file: bool = False
) -> Path | None:
    raw = _clean_target(target)
    if not raw:
        return None
    alias = _root_alias(raw, config)
    if alias is not None:
        return alias.resolve()
    direct = Path(os.path.expandvars(raw)).expanduser()
    if direct.exists():
        return direct.resolve()
    if direct.is_absolute() or "/" in raw or "\\" in raw:
        return None
    matches = search_paths(raw, config)
    if not matches:
        return None
    files = [path for path in matches if path.is_file()]
    if prefer_file and files:
        matches = files
    wanted_name = Path(raw).name.lower()
    wanted_stem = Path(raw).stem.lower()

    def rank(path: Path) -> tuple[int, int, str]:
        exact = 0 if path.name.lower() in {wanted_name, wanted_stem} else 1
        return exact, len(path.name), str(path).lower()

    return sorted(matches, key=rank)[0].resolve()


def resolve_targets(target: str, config: Config) -> list[Path]:
    wanted = _clean_target(target)
    if not wanted or wanted.lower() in ALL_TARGETS:
        return [root for root in config.search_roots if root.exists()] or [Path.home()]
    aliases = _root_aliases(wanted, config)
    if aliases:
        return aliases
    single = resolve_target(wanted, config)
    return [single] if single is not None else []


def _size_label(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _entry(path: Path) -> dict[str, object] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return {
        "name": path.name,
        "path": str(path),
        "type": "folder" if path.is_dir() else "file",
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="minutes"),
    }


def _collect_entries(
    root: Path, *, recursive: bool, limit: int, config: Config
) -> list[dict[str, object]]:
    if limit <= 0:
        return []
    entries: list[dict[str, object]] = []
    if root.is_file():
        entry = _entry(root)
        return [entry] if entry else []
    if not recursive:
        try:
            children = sorted(
                root.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower())
            )
        except OSError:
            return []
        for child in children:
            entry = _entry(child)
            if entry:
                entries.append(entry)
            if len(entries) >= limit:
                break
        return entries
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack and len(entries) < limit:
        current, depth = stack.pop()
        try:
            children = sorted(
                current.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower())
            )
        except OSError:
            continue
        descend: list[tuple[Path, int]] = []
        for child in children:
            entry = _entry(child)
            if entry:
                entries.append(entry)
            if len(entries) >= limit:
                break
            if (
                child.is_dir()
                and not child.is_symlink()
                and child.name.lower() not in SKIP_DIRS
                and not child.name.startswith(".")
                and depth < config.max_depth
            ):
                descend.append((child, depth + 1))
        stack.extend(reversed(descend))
    return entries


def _format_entries(label: str, entries: list[dict[str, object]], limit: int) -> str:
    lines = [f"{label}: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}"]
    for entry in entries[:80]:
        lines.append(
            f"  {entry['type']}: {entry['name']} "
            f"({_size_label(int(entry['size']))}, {entry['modified']})"
        )
    if len(entries) > 80:
        lines.append(f"  ... {len(entries) - 80} more")
    if len(entries) >= limit:
        lines.append(f"  (limited to {limit} entries)")
    return "\n".join(lines)


def list_folder(
    target: str, *, config: Config, recursive: bool = False, limit: int = 200
) -> ToolResult:
    wanted = _clean_target(target)
    if not wanted or wanted.lower() in ALL_TARGETS:
        roots = [root for root in config.search_roots if root.exists()] or [Path.home()]
        entries: list[dict[str, object]] = []
        for root in roots:
            remaining = limit - len(entries)
            if remaining <= 0:
                break
            entries.extend(
                _collect_entries(
                    root, recursive=recursive, limit=remaining, config=config
                )
            )
        label = "Configured folders"
    else:
        alias_roots = _root_aliases(wanted, config)
        if alias_roots:
            entries = []
            for root in alias_roots:
                remaining = limit - len(entries)
                if remaining <= 0:
                    break
                entries.extend(
                    _collect_entries(
                        root, recursive=recursive, limit=remaining, config=config
                    )
                )
            label = " + ".join(str(root) for root in alias_roots)
        else:
            root = resolve_target(wanted, config)
            if root is None:
                roots = ", ".join(str(path) for path in config.search_roots)
                return ToolResult.failure(
                    f"could not find a file or folder matching '{target}' in {roots}"
                )
            entries = _collect_entries(
                root, recursive=recursive, limit=limit, config=config
            )
            label = str(root)
    return ToolResult.success(
        _format_entries(label, entries, limit),
        data={"root": label, "entries": entries, "truncated": len(entries) >= limit},
        verified=True,
    )


def read_file(target: str, *, config: Config, max_chars: int = MAX_READ_CHARS) -> ToolResult:
    path = resolve_target(target, config, prefer_file=True)
    if path is None:
        roots = ", ".join(str(root) for root in config.search_roots)
        return ToolResult.failure(
            f"could not find a file matching '{target}' in {roots}"
        )
    if path.is_dir():
        return list_folder(str(path), config=config)
    try:
        stat = path.stat()
    except OSError as exc:
        return ToolResult.failure(f"could not read {path}: {exc}")
    details = {
        "path": str(path),
        "name": path.name,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="minutes"),
    }
    if stat.st_size > MAX_FILE_BYTES:
        return ToolResult.failure(
            f"{path.name} is too large to read ({_size_label(stat.st_size)})",
            data=details,
        )
    if path.suffix.lower() not in knowledge.SUPPORTED_SUFFIXES:
        return ToolResult.success(
            f"{path.name}: {_size_label(stat.st_size)}, modified {details['modified']} "
            f"(text extraction is not supported for {path.suffix or 'this file type'})",
            data=details,
            verified=True,
        )
    try:
        text = knowledge.extract_text(path)
    except (knowledge.KnowledgeError, OSError, ValueError) as exc:
        return ToolResult.failure(f"could not read {path.name}: {exc}", data=details)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = text.count("\n") + 1 if text else 0
    truncated = len(text) > max_chars
    preview = text[:1200]
    message = (
        f"{path}: {_size_label(stat.st_size)}, {lines} lines, "
        f"modified {details['modified']}"
    )
    if preview:
        message += f"\n{preview}"
    if truncated:
        message += "\n..."
    return ToolResult.success(
        message,
        data={**details, "text": text[:max_chars], "chars": len(text),
              "lines": lines, "truncated": truncated},
        verified=True,
    )


def inspect_path(
    target: str, *, config: Config, recursive: bool = False, limit: int = 200
) -> ToolResult:
    wanted = _clean_target(target)
    if not wanted or wanted.lower() in ALL_TARGETS:
        return list_folder(wanted, config=config, recursive=recursive, limit=limit)
    path = resolve_target(wanted, config)
    if path is None:
        roots = ", ".join(str(root) for root in config.search_roots)
        return ToolResult.failure(
            f"could not find a file or folder matching '{target}' in {roots}"
        )
    if path.is_dir():
        return list_folder(str(path), config=config, recursive=recursive, limit=limit)
    return read_file(str(path), config=config)
