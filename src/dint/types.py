from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Literal

EngineName = Literal["claude", "codex", "copilot", "grok"]
EventType = Literal["text", "tool", "need_approval", "done", "error"]
Role = Literal["header", "session", "user", "assistant", "tool", "error"]


@dataclass(frozen=True)
class Event:
    type: EventType
    text: str = ""
    session_id: str | None = None
    tool: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chat:
    chat_id: str
    engine: str
    cwd: str
    external_session_id: str | None = None


@dataclass
class TurnRecord:
    chat_id: str
    engine: str
    role: Role
    cwd: str
    external_session_id: str | None
    text: str
    ts: str
    tags: list[str] = field(default_factory=list)
    message_id: str | None = None


class Engine:
    name: str

    def send(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None,
    ) -> Iterator[Event]:
        raise NotImplementedError

    def cancel(self) -> None:
        raise NotImplementedError
