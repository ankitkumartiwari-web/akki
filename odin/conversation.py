from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .models import ActionRequest, ToolResult

AGAIN_PHRASES = {"again", "do that again", "repeat that", "repeat", "one more time"}


@dataclass(slots=True)
class Turn:
    role: str
    content: str


class Conversation:
    def __init__(
        self,
        max_turns: int = 40,
        cloud_turns: int = 20,
        max_chars: int = 500,
        max_history_chars: int = 4000,
        on_turn: Callable[[str, str], None] | None = None,
    ) -> None:
        self.max_turns = max_turns
        self.cloud_turns = cloud_turns
        self.max_chars = max_chars
        self.max_history_chars = max_history_chars
        self.on_turn = on_turn
        self._turns: list[Turn] = []
        self.last_request: ActionRequest | None = None
        self.last_target: str | None = None

    def add(self, role: str, content: str) -> None:
        text = " ".join(content.split())
        if not text:
            return
        self._turns.append(Turn(role, text))
        if len(self._turns) > self.max_turns:
            del self._turns[: len(self._turns) - self.max_turns]
        if self.on_turn is not None:
            self.on_turn(role, text)

    def record(self, request: ActionRequest, result: ToolResult) -> None:
        if not result.ok:
            return
        self.last_request = request
        data = result.data
        matches = data.get("matches")
        if matches:
            self.last_target = str(matches[0])
        if data.get("path"):
            self.last_target = str(data["path"])
        if data.get("target"):
            self.last_target = str(data["target"])
        if self.last_target is None:
            target = request.args.get("target") or request.args.get("path")
            if target:
                self.last_target = str(target)

    def last_exchange(self) -> tuple[str, str]:
        prompt = ""
        response = ""
        for turn in reversed(self._turns):
            if turn.role == "assistant" and not response:
                response = turn.content
            elif turn.role == "user" and not prompt:
                prompt = turn.content
            if prompt and response:
                break
        return prompt, response

    def cloud_messages(self) -> list[dict[str, str]]:
        selected: list[dict[str, str]] = []
        total = 0
        for turn in reversed(self._turns):
            if turn.role not in {"user", "assistant"}:
                continue
            content = turn.content[: self.max_chars]
            if selected and total + len(content) > self.max_history_chars:
                break
            selected.append({"role": turn.role, "content": content})
            total += len(content)
            if len(selected) >= self.cloud_turns:
                break
        selected.reverse()
        return selected

    def clear(self) -> None:
        self._turns.clear()
        self.last_request = None
        self.last_target = None


def _squash(text: str) -> str:
    return " ".join(text.strip().split()).lower().rstrip("?!.")


def resolve_followup(text: str, conversation: Conversation) -> ActionRequest | None:
    low = _squash(text)
    if not low:
        return None

    if low in AGAIN_PHRASES and conversation.last_request is not None:
        return conversation.last_request

    match = re.fullmatch(r"open (?:it|that|that folder|the folder)(?: in (.+))?", low)
    if match and conversation.last_target:
        alias = match.group(1)
        if alias:
            alias = re.sub(r"^the\s+", "", alias.strip())
            return ActionRequest(
                "open_in_app",
                {"target": conversation.last_target, "alias": alias},
                text,
            )
        return ActionRequest("open_path", {"path": conversation.last_target}, text)

    if re.fullmatch(
        r"open (?:the )?(?:first|top) (?:one|result|match)", low
    ) and conversation.last_target:
        return ActionRequest("open_path", {"path": conversation.last_target}, text)

    match = re.fullmatch(r"(?:search|google|look up|find)(?: for)? (?:it|that)", low)
    if match and conversation.last_request is not None:
        previous = conversation.last_request
        if previous.tool in {"web_search", "find_files"}:
            return previous

    return None
