from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from typing import Any

from dint.proc import CancelledError, RunningProcess, spawn
from dint.types import Engine, Event

_SANDBOX = os.environ.get("DINT_CODEX_SANDBOX", "workspace-write")
_FULL_AUTO = os.environ.get("DINT_CODEX_FULL_AUTO", "").lower() in {"1", "true", "yes"}


class CodexEngine(Engine):
    name = "codex"

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or os.environ.get("DINT_CODEX_BIN") or shutil.which("codex") or "codex"
        self._running: RunningProcess | None = None

    def send(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None,
    ) -> Iterator[Event]:
        argv = [self.binary, "exec"]
        if session_id:
            argv.extend(["resume", session_id])
        argv.extend(["--json", "--skip-git-repo-check", "-C", cwd, "-s", _SANDBOX])
        if _FULL_AUTO:
            argv.append("--dangerously-bypass-approvals-and-sandbox")
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


def parse_codex_line(line: str, *, session_id: str | None = None) -> list[Event]:
    line = line.strip()
    if not line:
        return []
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return []
    if not isinstance(obj, dict):
        return []
    msg = obj.get("msg") if isinstance(obj.get("msg"), dict) else obj
    sid = _session_id(obj) or _session_id(msg) or session_id
    kind = str(msg.get("type") or obj.get("type") or "")
    events: list[Event] = []

    if kind in {"thread.started", "session_created", "thread_started"}:
        if sid:
            events.append(Event(type="text", text="", session_id=sid, data={"event": kind}))
    elif kind in {"item.completed", "item_completed", "agent_message"}:
        events.extend(_item_events(msg.get("item") or msg, sid))
    elif kind in {"turn.completed", "turn_complete", "task_complete"}:
        events.append(Event(type="done", session_id=sid, data=msg))
    elif kind in {"turn.failed", "error", "turn_failed"}:
        text = str(msg.get("message") or msg.get("error") or obj.get("error") or "codex error")
        events.append(Event(type="error", text=text, session_id=sid, data=msg))
    elif kind in {"item.started", "command_execution"}:
        item = msg.get("item") or msg
        events.extend(_item_events(item, sid))
    elif "approval" in kind:
        events.append(
            Event(
                type="need_approval",
                text=str(msg.get("command") or msg.get("message") or kind),
                session_id=sid,
                data=msg,
            )
        )
    return events


def _parse_stream(lines: Iterator[str]) -> Iterator[Event]:
    session_id: str | None = None
    saw_done = False
    last_text = ""
    for line in lines:
        for event in parse_codex_line(line, session_id=session_id):
            if event.session_id:
                session_id = event.session_id
            if event.type == "text" and event.text:
                last_text = event.text
            if event.type == "done":
                saw_done = True
            yield event
    if not saw_done:
        yield Event(type="done", text=last_text, session_id=session_id)


def _item_events(item: Any, session_id: str | None) -> list[Event]:
    if not isinstance(item, dict):
        return []
    itype = str(item.get("type") or item.get("item_type") or "")
    if itype in {"agent_message", "assistant_message", "message", "agent_message_delta"}:
        text = _item_text(item)
        if text:
            return [Event(type="text", text=text, session_id=session_id)]
        return []
    if itype in {
        "command_execution",
        "command",
        "mcp_tool_call",
        "file_change",
        "patch",
        "tool",
    }:
        name = str(item.get("command") or item.get("name") or item.get("tool") or itype)
        return [
            Event(
                type="tool",
                text=name,
                tool=itype,
                session_id=session_id,
                data=item if isinstance(item, dict) else {},
            )
        ]
    text = _item_text(item)
    if text:
        return [Event(type="text", text=text, session_id=session_id)]
    return []


def _item_text(item: dict[str, Any]) -> str:
    for key in ("text", "content", "message", "final_response"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _session_id(obj: dict[str, Any]) -> str | None:
    for key in ("thread_id", "threadId", "session_id", "sessionId", "id"):
        value = obj.get(key)
        if isinstance(value, str) and value and key != "id":
            return value
        if key == "id" and isinstance(value, str) and (
            value.startswith("thr_") or obj.get("type") in {"thread.started", "thread_started"}
        ):
            return value
    thread = obj.get("thread")
    if isinstance(thread, dict):
        value = thread.get("id") or thread.get("thread_id")
        if isinstance(value, str) and value:
            return value
    return None
