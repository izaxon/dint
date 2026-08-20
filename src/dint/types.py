from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal, Protocol

EventType = Literal["session", "text", "tool", "need_approval", "done", "error"]
Role = Literal["header", "session", "user", "assistant", "tool", "error"]


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


class Engine(Protocol):
    """One coding-agent CLI (Claude Code, Codex, …)."""

    name: str

    def send(self, prompt: str, *, cwd: str, session_id: str | None) -> Iterator[Event]:
        """Run one turn. Pass session_id to resume."""

    def cancel(self) -> None:
        """Stop the in-flight turn, if any."""


class Logbook(Protocol):
    """Codicent Logbook wire: MCP PostMessage / GetMessages (append-only)."""

    def post_message(self, message: str) -> dict:
        """Post a new message. Never pass parentId."""

    def get_messages(
        self,
        search: str | None = None,
        *,
        start: int = 0,
        length: int = 100,
    ) -> list[dict]:
        """List messages, optionally filtered (e.g. #chat-<id>)."""
