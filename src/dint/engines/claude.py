from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from typing import Any

from dint.proc import CancelledError, RunningProcess, spawn
from dint.types import Engine, Event

# stream-json requires --verbose. acceptEdits lets the official CLI own tools
# without this layer reimplementing permissions.
_PERMISSION = os.environ.get("DINT_CLAUDE_PERMISSION_MODE", "acceptEdits")


class ClaudeEngine(Engine):
    name = "claude"

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or os.environ.get("DINT_CLAUDE_BIN") or shutil.which("claude") or "claude"
        self._running: RunningProcess | None = None

    def send(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None,
    ) -> Iterator[Event]:
        argv = [
            self.binary,
            "--print",
            "--verbose",
            "--output-format",
            "stream-json",
            "--permission-mode",
            _PERMISSION,
        ]
        if session_id:
            argv.extend(["--resume", session_id])
        argv.append(prompt)
        self._running = spawn(argv, cwd=cwd)
        try:
            yield from _parse_stream(self._running.lines())
        except CancelledError:
            yield Event(type="error", text="cancelled")
        finally:
            self._running = None

    def cancel(self) -> None:
        if self._running is not None:
            self._running.cancel()


def parse_claude_line(line: str, *, session_id: str | None = None) -> list[Event]:
    line = line.strip()
    if not line:
        return []
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return []
    if not isinstance(obj, dict):
        return []
    sid = _session_id(obj) or session_id
    kind = obj.get("type")
    events: list[Event] = []

    if kind == "assistant":
        events.extend(_assistant_events(obj.get("message") or {}, sid))
    elif kind == "result":
        if obj.get("is_error") or obj.get("subtype") not in {None, "success"}:
            text = str(obj.get("result") or obj.get("error") or "claude error")
            events.append(Event(type="error", text=text, session_id=sid, data=obj))
        else:
            events.append(Event(type="done", session_id=sid, data=obj))
    elif kind == "system" and sid:
        events.append(Event(type="text", text="", session_id=sid, data={"system": obj.get("subtype")}))
    elif kind == "user":
        events.extend(_user_tool_events(obj.get("message") or {}, sid))
    return events


def _parse_stream(lines: Iterator[str]) -> Iterator[Event]:
    session_id: str | None = None
    saw_done = False
    last_text = ""
    for line in lines:
        for event in parse_claude_line(line, session_id=session_id):
            if event.session_id:
                session_id = event.session_id
            if event.type == "text":
                if not event.text:
                    if session_id:
                        yield Event(type="text", text="", session_id=session_id)
                    continue
                last_text = event.text
            if event.type == "done":
                saw_done = True
            yield event
    if not saw_done:
        yield Event(type="done", text=last_text, session_id=session_id)


def _assistant_events(message: Any, session_id: str | None) -> list[Event]:
    events: list[Event] = []
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return events
    texts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text" and block.get("text"):
            texts.append(str(block["text"]))
        elif btype == "tool_use":
            name = str(block.get("name") or "tool")
            events.append(
                Event(
                    type="tool",
                    text=name,
                    tool=name,
                    session_id=session_id,
                    data=block.get("input") if isinstance(block.get("input"), dict) else {},
                )
            )
    if texts:
        events.append(Event(type="text", text="".join(texts), session_id=session_id))
    return events


def _user_tool_events(message: Any, session_id: str | None) -> list[Event]:
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    events: list[Event] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            events.append(
                Event(
                    type="tool",
                    text=str(block.get("content") or ""),
                    tool=str(block.get("tool_use_id") or "result"),
                    session_id=session_id,
                    data={"tool_result": True},
                )
            )
    return events


def _session_id(obj: dict[str, Any]) -> str | None:
    for key in ("session_id", "sessionId"):
        value = obj.get(key)
        if isinstance(value, str) and value:
            return value
    message = obj.get("message")
    if isinstance(message, dict):
        value = message.get("session_id") or message.get("sessionId")
        if isinstance(value, str) and value:
            return value
    return None
