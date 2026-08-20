"""Claude Code CLI: `claude -p --resume <id>`."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from dint.engines.base import CliEngine
from dint.types import Event


class ClaudeEngine(CliEngine):
    name = "claude"

    def __init__(self, binary: str | None = None) -> None:
        super().__init__(binary or os.environ.get("DINT_CLAUDE_BIN") or shutil.which("claude") or "claude")

    def argv(self, prompt: str, cwd: str, session_id: str | None) -> list[str]:
        cmd = [
            self.binary,
            "--print",
            "--verbose",
            "--output-format",
            "stream-json",
            "--permission-mode",
            os.environ.get("DINT_CLAUDE_PERMISSION_MODE", "acceptEdits"),
        ]
        if session_id:
            cmd.extend(["--resume", session_id])
        cmd.append(prompt)
        return cmd

    def parse_line(self, line: str, session_id: str | None) -> list[Event]:
        return parse_claude_line(line, session_id=session_id)


def parse_claude_line(line: str, *, session_id: str | None = None) -> list[Event]:
    obj = _json(line)
    if not obj:
        return []
    sid = obj.get("session_id") or obj.get("sessionId") or session_id
    kind = obj.get("type")
    if kind == "system" and sid:
        return [Event(type="session", session_id=sid)]
    if kind == "assistant":
        return _assistant(obj.get("message") or {}, sid)
    if kind == "result":
        if obj.get("is_error") or obj.get("subtype") not in {None, "success"}:
            return [Event(type="error", text=str(obj.get("result") or obj.get("error") or "error"), session_id=sid)]
        return [Event(type="done", session_id=sid)]
    return []


def _assistant(message: Any, sid: str | None) -> list[Event]:
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    events: list[Event] = []
    texts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            texts.append(str(block["text"]))
        elif block.get("type") == "tool_use":
            name = str(block.get("name") or "tool")
            events.append(Event(type="tool", text=name, tool=name, session_id=sid))
    if texts:
        events.append(Event(type="text", text="".join(texts), session_id=sid))
    return events


def _json(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None
