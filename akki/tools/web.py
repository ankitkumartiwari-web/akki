from __future__ import annotations

import os
from html.parser import HTMLParser
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from .. import __version__
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


class _WebTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            cleaned = " ".join(data.split())
            if cleaned:
                self.parts.append(cleaned)


def extract_web_text(html: str) -> str:
    parser = _WebTextExtractor()
    parser.feed(html)
    parser.close()
    return " ".join(parser.parts)


def read_page(url: str, *, max_chars: int = 8000, timeout: float = 12.0) -> tuple[str, str]:
    target = url.strip()
    if not target.lower().startswith(("http://", "https://")):
        raise ValueError("url must use http or https")
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid url")
    request = Request(target, headers={"User-Agent": f"AKKI/{__version__}"})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        raw = response.read(2_000_000).decode(charset, errors="ignore")
    text = extract_web_text(raw)
    if len(text) > max_chars:
        text = text[:max_chars]
    return url, text


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


def read_url(url: str, *, config: Config, max_chars: int = 6000) -> ToolResult:
    target = url.strip()
    parsed = urlparse(target)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return ToolResult.failure(f"invalid URL scheme: {url}")
    if not target.lower().startswith(("http://", "https://")):
        target = "https://" + target
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ToolResult.failure(f"invalid URL: {url}")
    try:
        _url, text = read_page(target, max_chars=max_chars, timeout=config.timeout_seconds)
    except Exception as exc:
        return ToolResult.failure(f"could not read {url}: {exc}")
    snippet = text.strip()
    if len(snippet) > 4000:
        snippet = snippet[:4000] + "..."
    return ToolResult.success(
        f"Read {url}: {len(text)} chars extracted\n{snippet}",
        data={"url": target, "text": text, "chars": len(text)},
    )
