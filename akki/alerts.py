from __future__ import annotations

import imaplib
import json
import os
import re
from email import message_from_bytes
from email.header import decode_header, make_header
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import AlertSettings, Config
from .llm import ask_plain
from .models import ToolResult
from .storage import Storage

CLASSIFY_PROMPT = (
    "You are a notification triage classifier. Rate how important this item is "
    "for the user from 0 to 1. Reply with only the number. 0 means spam or "
    "low priority, 0.5 means normal, and 1 means urgent, security, finance, "
    "health, work deadline, or a message from a real person."
)

IMPORTANT_HINTS = {
    "urgent": 0.9,
    "asap": 0.85,
    "immediately": 0.85,
    "deadline": 0.8,
    "invoice": 0.75,
    "payment": 0.8,
    "paid": 0.7,
    "failed": 0.75,
    "failure": 0.75,
    "security": 0.85,
    "password": 0.85,
    "otp": 0.9,
    "verification": 0.8,
    "bank": 0.8,
    "transaction": 0.75,
    "medical": 0.85,
    "appointment": 0.75,
    "interview": 0.8,
    "offer": 0.75,
    "important": 0.75,
    "alert": 0.7,
}


class AlertError(RuntimeError):
    pass


def _snippet(text: str, limit: int = 800) -> str:
    return " ".join(str(text).split())[:limit]


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeDecodeError):
        return str(value)


def _body_snippet(message: Any, limit: int = 800) -> str:
    for part in message.walk():
        if part.get_content_type() != "text/plain":
            continue
        disposition = str(part.get("Content-Disposition") or "")
        if "attachment" in disposition.lower():
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        return _snippet(payload.decode(charset, errors="replace"), limit)
    return ""


def fetch_unseen_mail(
    settings: AlertSettings, *, limit: int | None = None
) -> list[dict[str, str]]:
    if not settings.imap_host:
        raise AlertError("IMAP host is not configured")
    if not settings.imap_user:
        raise AlertError("IMAP user is not configured")
    password = os.environ.get(settings.imap_password_env)
    if not password:
        raise AlertError(
            f"IMAP password is not configured: set {settings.imap_password_env}"
        )
    maximum = max(1, limit or settings.max_messages)
    mail: imaplib.IMAP4_SSL | None = None
    try:
        mail = imaplib.IMAP4_SSL(
            settings.imap_host,
            settings.imap_port,
            timeout=settings.timeout_seconds,
        )
        mail.login(settings.imap_user, password)
        status, _ = mail.select(settings.imap_folder)
        if status != "OK":
            raise AlertError(f"could not select IMAP folder {settings.imap_folder}")
        status, data = mail.uid("search", None, "UNSEEN")
        if status != "OK":
            raise AlertError("IMAP search for unseen mail failed")
        raw_uids = data[0].split() if data and data[0] else []
        messages: list[dict[str, str]] = []
        for raw_uid in raw_uids[-maximum:]:
            uid = raw_uid.decode("ascii", errors="ignore") if isinstance(raw_uid, bytes) else str(raw_uid)
            status, parts = mail.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK":
                continue
            payload = b""
            for part in parts:
                if isinstance(part, tuple) and len(part) > 1:
                    payload = part[1]
                    break
            if not payload:
                continue
            message = message_from_bytes(payload)
            messages.append(
                {
                    "uid": uid,
                    "from": _decode_header(message.get("From")),
                    "subject": _decode_header(message.get("Subject")),
                    "date": _decode_header(message.get("Date")),
                    "snippet": _body_snippet(message),
                }
            )
        return messages
    except imaplib.IMAP4.error as exc:
        raise AlertError(f"IMAP error: {exc}") from exc
    finally:
        if mail is not None:
            try:
                mail.logout()
            except (imaplib.IMAP4.error, OSError):
                pass


def send_ntfy(
    settings: AlertSettings,
    title: str,
    message: str,
    *,
    priority: str = "default",
    tags: list[str] | None = None,
) -> ToolResult:
    topic = settings.ntfy_topic.strip()
    if not topic:
        return ToolResult.failure("ntfy topic is not configured")
    base = (settings.ntfy_server or "https://ntfy.sh").strip().rstrip("/")
    payload: dict[str, Any] = {
        "topic": topic,
        "title": title.strip()[:120] or "AKKI alert",
        "message": message,
        "priority": priority,
    }
    if tags:
        payload["tags"] = tags
    headers = {"Content-Type": "application/json"}
    token_env = settings.ntfy_token_env.strip()
    if token_env:
        token = os.environ.get(token_env)
        if token:
            headers["Authorization"] = f"Bearer {token}"
    request = Request(
        base,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.timeout_seconds) as response:
            response.read()
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
        except OSError:
            pass
        return ToolResult.failure(
            f"ntfy returned HTTP {exc.code}: {detail or exc.reason}"
        )
    except (URLError, TimeoutError, OSError) as exc:
        return ToolResult.failure(f"ntfy request failed: {exc}")
    return ToolResult.success(f"Sent mobile alert: {title}", verified=False)


def _keyword_score(item: dict[str, str]) -> float:
    text = " ".join(
        [item.get("subject", ""), item.get("from", ""), item.get("snippet", "")]
    ).lower()
    scores = [score for word, score in IMPORTANT_HINTS.items() if word in text]
    return max(scores, default=0.2)


def score_importance(item: dict[str, str], config: Config) -> float:
    prompt = (
        f"From: {item.get('from', '')}\n"
        f"Subject: {item.get('subject', '')}\n"
        f"Preview: {item.get('snippet', '')[:700]}"
    )
    outcome = ask_plain(
        prompt,
        config.llm,
        system_prompt=CLASSIFY_PROMPT,
        prefer_local=True,
        max_tokens=8,
        temperature=0.0,
    )
    if outcome.text:
        match = re.search(r"\d+(?:\.\d+)?", outcome.text)
        if match:
            value = float(match.group(0))
            if 1.0 < value <= 10.0:
                value /= 10.0
            return max(0.0, min(1.0, value))
    return _keyword_score(item)


def _format_alert(item: dict[str, str]) -> tuple[str, str]:
    subject = item.get("subject") or "(no subject)"
    sender = item.get("from") or "(unknown sender)"
    title = f"Mail: {subject[:90]}"
    body = f"{sender}\n{item.get('snippet', '')}".strip()
    return title, body[:900]


def poll_once(storage: Storage, config: Config) -> list[dict[str, object]]:
    settings = config.alerts
    if not settings.enabled:
        raise AlertError("mobile alerts are disabled")
    if not settings.ntfy_topic.strip():
        raise AlertError("ntfy topic is not configured")
    sent: list[dict[str, object]] = []
    for item in fetch_unseen_mail(settings):
        key = f"{settings.imap_user}:{settings.imap_folder}:{item['uid']}"
        if storage.alert_seen("imap", key):
            continue
        score = score_importance(item, config)
        title, body = _format_alert(item)
        if score < settings.importance_threshold:
            storage.record_alert("imap", key, title, score, sent=False)
            continue
        priority = "high" if score >= 0.85 else "default"
        result = send_ntfy(settings, title, body, priority=priority, tags=["email"])
        if not result.ok:
            continue
        storage.record_alert("imap", key, title, score, sent=True)
        sent.append(
            {
                "uid": item["uid"],
                "title": title,
                "importance": score,
                "from": item.get("from", ""),
            }
        )
    return sent


def send_mobile_alert(title: str, message: str, *, config: Config) -> ToolResult:
    return send_ntfy(config.alerts, title, message)
