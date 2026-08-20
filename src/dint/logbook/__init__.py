"""Chat ledger on Codicent Logbook.

Logbook is the wire (post_message / get_messages). ChatLog maps a chat onto
append-only tagged JSON messages. No updates, no parentId.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from dint.logbook.mcp import McpLogbook
from dint.logbook.rest import LogbookError, RestLogbook
from dint.types import Chat, Logbook, Role

DEFAULT_URL = os.environ.get("LOGBOOK_URL", "http://127.0.0.1:5100")
DEFAULT_KEY = os.environ.get("LOGBOOK_API_KEY", "test-local-key")
DEFAULT_PROJECT = os.environ.get("LOGBOOK_PROJECT", "dint")
DEFAULT_TRANSPORT = os.environ.get("LOGBOOK_TRANSPORT", "rest")


def default_logbook() -> Logbook:
    url, key = DEFAULT_URL, DEFAULT_KEY
    if DEFAULT_TRANSPORT == "mcp":
        return McpLogbook(url, key)
    return RestLogbook(url, key)


class ChatLog:
    """One header per chat; each turn is a new Logbook message."""

    def __init__(self, logbook: Logbook | None = None, *, project: str | None = None) -> None:
        self.logbook = logbook or default_logbook()
        self.project = project or DEFAULT_PROJECT

    def post(self, chat: Chat, role: Role, text: str = "") -> str:
        tags = ["chat", chat.engine, f"chat-{chat.chat_id}"]
        if role == "session":
            text = text or (chat.external_session_id or "")
        elif role != "header":
            tags.extend(["turn", role])
        payload = {
            "chatId": chat.chat_id,
            "engine": chat.engine,
            "role": role,
            "cwd": chat.cwd,
            "externalSessionId": chat.external_session_id,
            "text": text,
            "ts": _now(),
        }
        result = self.logbook.post_message(format_content(self.project, tags, payload))
        return str(result.get("id") or result.get("Id") or "")

    def get_chat(self, chat_id: str) -> Chat | None:
        rows = self.list_messages(chat_id)
        if not rows:
            return None
        header = next((r for r in rows if r.get("role") == "header"), rows[0])
        session = None
        for r in rows:
            if r.get("externalSessionId"):
                session = r["externalSessionId"]
        return Chat(header["chatId"], header["engine"], header["cwd"], session)

    def list_messages(self, chat_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in self.logbook.get_messages(f"#chat-{chat_id}"):
            content = item.get("content") or item.get("Content") or ""
            payload = extract_json(str(content))
            if payload and payload.get("chatId") == chat_id:
                out.append(payload)
        out.sort(key=lambda r: r.get("ts") or "")
        return out

    def list_turns(self, chat_id: str) -> list[dict[str, Any]]:
        return [r for r in self.list_messages(chat_id) if r.get("role") in {"user", "assistant", "tool", "error"}]


def format_content(project: str, tags: list[str], payload: dict[str, Any]) -> str:
    parts: list[str] = []
    if project:
        parts.append("@" + project.lstrip("@"))
    seen: set[str] = set()
    for tag in tags:
        t = tag.strip().lstrip("#")
        if t and t not in seen:
            seen.add(t)
            parts.append("#" + t)
    parts.append(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return " ".join(parts)


def extract_json(content: str) -> dict[str, Any] | None:
    i = content.find("{")
    if i < 0:
        return None
    try:
        data = json.loads(content[i:])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "ChatLog",
    "LogbookError",
    "McpLogbook",
    "RestLogbook",
    "default_logbook",
    "extract_json",
    "format_content",
]
