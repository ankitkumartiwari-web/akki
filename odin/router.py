from __future__ import annotations

import re
from pathlib import Path

from .config import Config
from .models import ActionRequest
from .tools.web import KNOWN_SITES

DOMAIN_PATTERN = re.compile(
    r"^[\w.-]+\.(?:com|org|net|io|dev|ai|co|in|edu|gov|app)(?:/.*)?$", re.IGNORECASE
)
URL_PATTERN = re.compile(r"^(?:https?://|www\.)", re.IGNORECASE)


def _squash(text: str) -> str:
    return " ".join(text.strip().split())


def _looks_like_path(value: str) -> bool:
    return bool(re.search(r"[\\/]", value)) or ":" in value or value.startswith(("~", "."))


def _site(value: str) -> str | None:
    key = value.strip().lower()
    if key in KNOWN_SITES:
        return KNOWN_SITES[key]
    if URL_PATTERN.match(value) or DOMAIN_PATTERN.match(value):
        return value
    return None


def _strip_article(value: str) -> str:
    return re.sub(r"^the\s+", "", value.strip(), flags=re.IGNORECASE)


def route(text: str, config: Config | None = None) -> ActionRequest | None:
    raw = text
    cleaned = _squash(text)
    if not cleaned:
        return None
    lowered = cleaned.lower().rstrip(".?!")

    if re.fullmatch(r"(?:take |grab )?(?:a )?screenshot(?: of (?:the )?screen)?", lowered) or re.fullmatch(
        r"(?:capture|grab) (?:the )?screen", lowered
    ):
        return ActionRequest("screenshot", {}, raw)

    match = re.fullmatch(
        r"(?:increase|raise|turn up)(?: the)? volume(?: by (\d+))?", lowered
    )
    if match:
        return ActionRequest("volume", {"direction": "up", "steps": int(match.group(1) or 2)}, raw)
    match = re.fullmatch(
        r"(?:decrease|lower|turn down|reduce)(?: the)? volume(?: by (\d+))?", lowered
    )
    if match:
        return ActionRequest(
            "volume", {"direction": "down", "steps": int(match.group(1) or 2)}, raw
        )
    if re.fullmatch(
        r"(?:mute|toggle mute)(?:\s+(?:the\s+)?(?:volume|sound|audio))?", lowered
    ):
        return ActionRequest("volume", {"direction": "mute", "steps": 1}, raw)
    if re.fullmatch(
        r"unmute(?:\s+(?:the\s+)?(?:volume|sound|audio))?", lowered
    ):
        return ActionRequest("volume", {"direction": "mute", "steps": 1}, raw)

    match = re.fullmatch(
        r"(?:open|launch|start) (?:my )?(.+?) (?:in|with|using) (.+)", cleaned, re.IGNORECASE
    )
    if match:
        return ActionRequest(
            "open_in_app",
            {"target": match.group(1).strip(), "alias": _strip_article(match.group(2))},
            raw,
        )

    match = re.fullmatch(
        r"(?:search|google|look up|web search)(?: for)? (.+)", cleaned, re.IGNORECASE
    )
    if match:
        return ActionRequest("web_search", {"query": match.group(1).strip()}, raw)

    match = re.fullmatch(r"(?:find|locate)(?: my| the)? (.+)", cleaned, re.IGNORECASE)
    if match:
        query = re.sub(r"^(?:my|the)\s+", "", match.group(1).strip(), flags=re.IGNORECASE)
        query = re.sub(
            r"\s+(?:files?|folder|directory|project)$", "", query, flags=re.IGNORECASE
        )
        return ActionRequest("find_files", {"query": query.strip()}, raw)

    match = re.fullmatch(r"(?:go to|visit) (.+)", cleaned, re.IGNORECASE)
    if match:
        target = _site(_strip_article(match.group(1)))
        if target:
            return ActionRequest("open_url", {"url": target}, raw)

    match = re.fullmatch(r"(?:open|launch|start|run) (.+)", cleaned, re.IGNORECASE)
    if match:
        target = _strip_article(match.group(1))
        site = _site(target)
        if site:
            return ActionRequest("open_url", {"url": site}, raw)
        if _looks_like_path(target):
            return ActionRequest("open_path", {"path": target}, raw)
        stripped = re.sub(r"^my\s+", "", target, flags=re.IGNORECASE)
        stripped = re.sub(
            r"\s+(?:project|folder|directory)$", "", stripped, flags=re.IGNORECASE
        )
        if config is not None and not config.find_app(stripped):
            from .tools.files import search_paths

            matches = search_paths(stripped, config)
            if matches:
                return ActionRequest("open_path", {"path": str(matches[0])}, raw)
        return ActionRequest("launch_app", {"alias": stripped}, raw)

    return None


def is_url(value: str) -> bool:
    return bool(URL_PATTERN.match(value) or DOMAIN_PATTERN.match(value))


def as_path(value: str) -> Path:
    return Path(value).expanduser()
