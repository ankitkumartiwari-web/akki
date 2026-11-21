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
FOLDER_ALIASES = {
    "desktop",
    "documents",
    "downloads",
    "projects",
    "code",
    "dev",
    "all",
    "all files",
    "everything",
    "my files",
}


def _is_lock_request(text: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:(?:mera|meri|my|the|apna)\s+)?"
            r"(?:(?:screen|computer|pc|laptop|स्क्रीन|कंप्यूटर|लैपटॉप)\s+)?"
            r"(?:ko\s+)?(?:lock|लॉक)"
            r"(?:\s+(?:the\s+|my\s+|mera\s+|meri\s+|apna\s+)?"
            r"(?:screen|computer|pc|laptop|स्क्रीन|कंप्यूटर|लैपटॉप))?"
            r"(?:\s+(?:karo|kar\s*do|kardo|kar|करो|कर\s*दो))?",
            text,
        )
    )


def _fileish(value: str) -> bool:
    low = value.strip().lower()
    if low in FOLDER_ALIASES:
        return True
    if _looks_like_path(value):
        return True
    return bool(re.search(r"\.[a-z0-9]{1,6}$", low))


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

    if lowered.startswith("__reminder__:"):
        return ActionRequest(
            "reminder", {"text": cleaned.split(":", 1)[1].strip()}, raw
        )

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

    match = re.fullmatch(
        r"(?:read|fetch|summarize|inspect|tell me about|what(?:'s| is) on) (https?://\S+)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("read_url", {"url": match.group(1)}, raw)

    if _is_lock_request(lowered):
        return ActionRequest("lock_screen", {}, raw)

    match = re.fullmatch(
        r"(?:compose|dictate|copy|draft|write|type)\s+(?:a\s+|this\s+)?"
        r"(?:message|msg)\s*[:,-]?\s*(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("compose_message", {"text": match.group(1).strip()}, raw)

    match = re.fullmatch(
        r"(?:message|msg)\s*[:,-]\s*(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("compose_message", {"text": match.group(1).strip()}, raw)

    match = re.fullmatch(
        r"(?:message|msg)\s+(.+?)\s+(?:likho|likh do|banao|bana do)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("compose_message", {"text": match.group(1).strip()}, raw)

    match = re.fullmatch(
        r"(?:extract|pull|get|fetch)\s+(?:all\s+)?(?:the\s+)?"
        r"(?:info|information|details|summary)\s+(?:from|of|in)\s+"
        r"(?:the\s+)?(?:folder|directory)\s+(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("inspect_path", {"target": match.group(1).strip()}, raw)

    match = re.fullmatch(
        r"(?:remember|note)\s+(?:that\s+)?(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("remember_fact", {"fact": match.group(1).strip()}, raw)

    match = re.fullmatch(
        r"(?:yaad\s+rakho|yaad\s+rakhna)\s*[:,]?\s*(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("remember_fact", {"fact": match.group(1).strip()}, raw)

    match = re.fullmatch(
        r"(?:store|save|keep)\s+(?:this\s+|that\s+|the\s+)?"
        r"(?:important\s+)?(?:info(?:rmation)?|details?|fact|note|message)?"
        r"\s*(?:in|to)\s+(?:my\s+)?memory"
        r"(?:\s+for\s+(?:the\s+)?remainder)?\s*[:,-]?\s*(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("remember_fact", {"fact": match.group(1).strip()}, raw)

    match = re.fullmatch(
        r"(?:read|open|show|fetch|get|display|summari[sz]e)\s+"
        r"(?:the\s+)?(?:file|document)\s+(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("read_file", {"target": match.group(1).strip()}, raw)

    match = re.fullmatch(
        r"(?:read|open|show|fetch|get|display|give me)\s+(?:all\s+)?(?:the\s+)?"
        r"(?:contents?|details?)\s+(?:of|from|in)\s+(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("inspect_path", {"target": match.group(1).strip()}, raw)

    match = re.fullmatch(
        r"(?:list|show|scan|fetch|get)\s+(?:all\s+)?(?:the\s+)?"
        r"(?:files?|folders?|entries)\s+(?:in|on|of|from)\s+(?:my\s+)?(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        recursive = bool(re.search(r"\b(?:all|recursive|everything)\b", cleaned, re.IGNORECASE))
        return ActionRequest(
            "list_folder",
            {"target": match.group(1).strip(), "recursive": recursive},
            raw,
        )

    match = re.fullmatch(
        r"(?:what(?:'s| is)|list|show|scan)\s+(?:in|on|inside)\s+(?:my\s+)?(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match and _fileish(match.group(1).strip()):
        return ActionRequest("inspect_path", {"target": match.group(1).strip()}, raw)

    match = re.fullmatch(
        r"(?:list|show|scan)\s+(?:my\s+)?"
        r"(desktop|documents|downloads|projects|code|dev)(?:\s+(?:folder|files))?",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("list_folder", {"target": match.group(1)}, raw)

    match = re.fullmatch(
        r"(?:list|show|scan|fetch|get)\s+(?:all\s+)?(?:my\s+)?"
        r"(?:files|folders|everything)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        recursive = bool(re.search(r"\b(?:all|everything)\b", cleaned, re.IGNORECASE))
        return ActionRequest("list_folder", {"target": "all", "recursive": recursive}, raw)

    match = re.fullmatch(
        r"(desktop|documents|downloads|projects|code|dev)\s+(?:ki|ke)\s+"
        r"(?:files?|folders?)\s+(?:batao|dikhao|list karo)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("list_folder", {"target": match.group(1)}, raw)

    match = re.fullmatch(
        r"(.+?)\s+(?:file|फाइल|फ़ाइल)\s+(?:padho|padh do|read karo|kholo|dikhao)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("read_file", {"target": match.group(1).strip()}, raw)

    match = re.fullmatch(
        r"(?:file|फाइल|फ़ाइल)\s+(.+?)\s+(?:padho|padh do|read karo|kholo|dikhao|details batao)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return ActionRequest("read_file", {"target": match.group(1).strip()}, raw)
    if lowered == "clipboard" or lowered.startswith("clipboard get") or lowered.startswith("clipboard read"):
        return ActionRequest("clipboard_read", {}, raw)
    parts = cleaned.split(" ", 2)
    if (
        len(parts) >= 3
        and parts[0] == "clipboard"
        and parts[1].lower() in {"set", "write", "copy"}
    ):
        return ActionRequest("clipboard_write", {"text": parts[2].strip()}, raw)

    match = re.fullmatch(r"(?:go to|visit) (.+)", cleaned, re.IGNORECASE)
    if match:
        target = _site(_strip_article(match.group(1)))
        if target:
            return ActionRequest("open_url", {"url": target}, raw)

    match = re.fullmatch(
        r"(?:open|launch|start|show)\s+(?:the\s+)?folder\s+(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        target = _strip_article(match.group(1)).strip()
        if config is not None and target.lower() in FOLDER_ALIASES:
            from .tools.files import resolve_target

            resolved = resolve_target(target, config)
            if resolved is not None:
                target = str(resolved)
        return ActionRequest("open_path", {"path": target}, raw)

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
