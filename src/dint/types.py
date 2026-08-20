from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal, Protocol

EventType = Literal["session", "text", "tool", "need_approval", "done", "error"]
Role = Literal["header", "session", "user", "bot", "tool", "error"]


@dataclass(frozen=True)
class Event:
    """Normalized stream from any engine CLI."""

    type: EventType
    text: str = ""
    session_id: str | None = None
    tool: str | None = None


@dataclass
class Chat:
    chat_id: str
    engine: str
    cwd: str
    external_session_id: str | None = None
    header_id: str | None = None
    tail_id: str | None = None


class Engine(Protocol):
    """One coding-agent CLI (Claude Code, Codex, Grok, …)."""

    name: str

    def send(self, prompt: str, *, cwd: str, session_id: str | None) -> Iterator[Event]:
        """Run one turn. Pass session_id to resume."""

    def cancel(self) -> None:
        """Stop the in-flight turn, if any."""


class Logbook(Protocol):
    """Codicent Logbook wire: PostMessage / GetMessages / GetMessageHistory."""

    def post_message(self, message: str, parent_id: str | None = None) -> dict:
        """Post a message. parent_id chains it onto the conversation (Codicent ParentId)."""

    def get_messages(
        self,
        search: str | None = None,
        *,
        start: int = 0,
        length: int = 100,
    ) -> list[dict]:
        """List messages, optionally filtered (e.g. #chat-<id>)."""

    def get_history(self, message_id: str) -> list[dict]:
        """Full conversation chain (GetMessageHistory / OriginalMessageId)."""
