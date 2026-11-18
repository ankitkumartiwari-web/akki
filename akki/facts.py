from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable

USER_AGENT = "AKKI/0.4 desktop assistant"
WIKI_API = "https://en.wikipedia.org/w/api.php"

_OFFICE_PATTERN = re.compile(
    r"\bwho(?:'s| is| was)?\s+(?:the\s+)?(?:current\s+)?"
    r"(vice[\s-]+president|prime minister|chief minister|president|governor|"
    r"chief justice|pm|cm)"
    r"\s+of\s+(.+)",
    re.IGNORECASE,
)

_OFFICE_ALIASES = {
    "pm": "prime minister",
    "cm": "chief minister",
}

_TRAILING_WORDS = re.compile(
    r"\b(?:now|currently|today|right now|at present|as of now)\b.*$",
    re.IGNORECASE,
)


def parse_office_question(text: str) -> tuple[str, str] | None:
    match = _OFFICE_PATTERN.search(text)
    if match is None:
        return None
    office = " ".join(match.group(1).lower().replace("-", " ").split())
    office = _OFFICE_ALIASES.get(office, office)
    place = match.group(2).strip()
    place = _TRAILING_WORDS.sub("", place)
    place = place.strip(" ?.!,;:\"'")
    place = re.sub(r"^the\s+", "", place, flags=re.IGNORECASE)
    if not office or not place:
        return None
    return office, place


def extract_incumbent(wikitext: str) -> tuple[str, str | None] | None:
    name = None
    since = None
    for line in wikitext.splitlines():
        stripped = line.strip()
        if stripped.startswith("| incumbent_since"):
            value = stripped.split("=", 1)[-1].strip()
            value = re.sub(r"<ref.*?</ref>", "", value, flags=re.IGNORECASE | re.DOTALL)
            value = re.sub(r"\{\{.*?\}\}", "", value)
            since = value.strip(" |") or None
        elif stripped.startswith("| incumbent"):
            match = re.search(r"\[\[([^\]|]+)", stripped)
            if match is not None:
                name = match.group(1).strip()
    if not name:
        return None
    return name, since


def _fetch_wikitext(title: str, timeout: float = 8.0) -> str | None:
    params = urllib.parse.urlencode(
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
        }
    )
    request = urllib.request.Request(
        f"{WIKI_API}?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    parse = data.get("parse") if isinstance(data, dict) else None
    if not isinstance(parse, dict):
        return None
    wikitext = parse.get("wikitext")
    return wikitext if isinstance(wikitext, str) else None


def lookup_officeholder(
    text: str,
    fetch: Callable[[str], str | None] | None = None,
) -> str | None:
    parsed = parse_office_question(text)
    if parsed is None:
        return None
    office, place = parsed
    title = f"{office.title()} of {place.title()}"
    wikitext = (fetch or _fetch_wikitext)(title)
    if not wikitext:
        return None
    incumbent = extract_incumbent(wikitext)
    if incumbent is None:
        return None
    name, since = incumbent
    name = re.sub(r"\[\[|\]\]", "", name)
    if since:
        return f"{name} is the {office} of {place} (since {since})."
    return f"{name} is the {office} of {place}."
