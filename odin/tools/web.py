from __future__ import annotations

import os
from urllib.parse import quote_plus, urlparse

from ..config import Config
from ..models import ToolResult

KNOWN_SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "chatgpt": "https://chatgpt.com",
    "reddit": "https://www.reddit.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com",
    "maps": "https://maps.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "wikipedia": "https://www.wikipedia.org",
}

SEARCH_ENGINES = {
    "duckduckgo": "https://duckduckgo.com/?q=",
    "google": "https://www.google.com/search?q=",
    "bing": "https://www.bing.com/search?q=",
}


def _start(url: str, label: str) -> ToolResult:
    try:
        os.startfile(url)  # type: ignore[attr-defined]
    except OSError as exc:
        return ToolResult.failure(f"could not open browser: {exc}")
    return ToolResult.success(f"Opened {label} (unverified)", verified=False)


def open_url(url: str, *, config: Config) -> ToolResult:
    target = url.strip()
    site = KNOWN_SITES.get(target.lower())
    if site:
        target = site
    if not target.lower().startswith(("http://", "https://")):
        target = "https://" + target
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ToolResult.failure(f"invalid URL: {url}")
    return _start(target, parsed.netloc)


def web_search(query: str, *, config: Config) -> ToolResult:
    cleaned = query.strip().strip(".?!")
    if not cleaned:
        return ToolResult.failure("no search query given")
    base = SEARCH_ENGINES.get(config.search_engine.lower(), SEARCH_ENGINES["duckduckgo"])
    return _start(base + quote_plus(cleaned), f"search for '{cleaned}'")
