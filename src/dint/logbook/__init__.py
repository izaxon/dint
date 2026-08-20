"""Chat ledger on Codicent Logbook.

Matches Codicent-core conversations:
  - header is the root (no parentId)
  - each turn posts with parentId = previous message
  - #user vs #bot tags
  - get_history (GetMessageHistory) walks the ParentId / OriginalMessageId chain
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

TURN_ROLES = {"user", "bot", "tool", "error"}


def default_logbook() -> Logbook:
    url, key = DEFAULT_URL, DEFAULT_KEY
    if DEFAULT_TRANSPORT == "mcp":
        return McpLogbook(url, key)
    return RestLogbook(url, key)


class ChatLog:
    """One header per chat; turns are children via parentId."""

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
        msg_id = _id(
            self.logbook.post_message(
                format_content(self.project, tags, payload),
                parent_id=chat.tail_id,
            )
        )
        chat.tail_id = msg_id or chat.tail_id
        if role == "header":
            chat.header_id = msg_id
        return msg_id

    def get_chat(self, chat_id: str) -> Chat | None:
        rows = self.list_messages(chat_id)
        if not rows:
            return None
        header = next((r for r in rows if r.get("role") == "header"), rows[0])
        session = None
        for r in rows:
            if r.get("externalSessionId"):
                session = r["externalSessionId"]
        return Chat(
            chat_id=header["chatId"],
            engine=header["engine"],
            cwd=header["cwd"],
            external_session_id=session,
            header_id=header.get("id"),
            tail_id=rows[-1].get("id"),
        )

    def list_messages(self, chat_id: str) -> list[dict[str, Any]]:
        tagged = [_record(item) for item in self.logbook.get_messages(f"#chat-{chat_id}")]
        tagged = [r for r in tagged if r and r.get("chatId") == chat_id]
        header_id = next((r.get("id") for r in tagged if r.get("role") == "header" and r.get("id")), None)
        if header_id:
            hist = [_record(item) for item in self.logbook.get_history(header_id)]
            hist = [r for r in hist if r]
            if hist:
                hist.sort(key=lambda r: r.get("ts") or "")
                return hist
        tagged.sort(key=lambda r: r.get("ts") or "")
        return tagged

    def list_turns(self, chat_id: str) -> list[dict[str, Any]]:
        return [r for r in self.list_messages(chat_id) if r.get("role") in TURN_ROLES]


def _record(item: dict[str, Any]) -> dict[str, Any] | None:
    content = item.get("content") or item.get("Content") or ""
    payload = extract_json(str(content))
    if not payload:
        return None
    payload["id"] = str(item.get("id") or item.get("Id") or payload.get("id") or "")
    parent = item.get("parentId") or item.get("ParentId")
    if parent:
        payload["parentId"] = str(parent)
    return payload


def _id(result: dict[str, Any]) -> str:
    return str(result.get("id") or result.get("Id") or "")


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
