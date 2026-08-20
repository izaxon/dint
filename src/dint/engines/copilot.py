"""GitHub Copilot CLI: `copilot -p --resume=<id> --output-format json`."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from dint.engines.base import CliEngine
from dint.types import Event


class CopilotEngine(CliEngine):
    name = "copilot"

    def __init__(self, binary: str | None = None) -> None:
        super().__init__(
            binary or os.environ.get("DINT_COPILOT_BIN") or shutil.which("copilot") or "copilot"
        )

    def argv(self, prompt: str, cwd: str, session_id: str | None) -> list[str]:
        cmd = [
            self.binary,
            "-C",
            cwd,
            "--output-format",
            "json",
            "--allow-all",
            "-p",
            prompt,
        ]
        if session_id:
            cmd.append(f"--resume={session_id}")
        return cmd

    def parse_line(self, line: str, session_id: str | None) -> list[Event]:
        return parse_copilot_line(line, session_id=session_id)


def parse_copilot_line(line: str, *, session_id: str | None = None) -> list[Event]:
    obj = _json(line)
    if not obj:
        return []
    sid = obj.get("sessionId") or obj.get("session_id") or session_id
    kind = str(obj.get("type") or "")
    data = obj.get("data") if isinstance(obj.get("data"), dict) else {}

    if kind == "result":
        if obj.get("exitCode") not in {None, 0}:
            return [Event(type="error", text=f"copilot exit {obj.get('exitCode')}", session_id=sid)]
        return [Event(type="done", session_id=sid)]
    if kind == "assistant.message":
        events: list[Event] = []
        for req in data.get("toolRequests") or []:
            if isinstance(req, dict):
                name = str(req.get("name") or "tool")
                events.append(Event(type="tool", text=name, tool=name, session_id=sid))
        text = data.get("content")
        if isinstance(text, str) and text.strip():
            events.append(Event(type="text", text=text, session_id=sid))
        return events
    if kind == "tool.execution_start":
        name = str(data.get("toolName") or "tool")
        return [Event(type="tool", text=name, tool=name, session_id=sid)]
    if kind in {"session.start", "user.message"} and sid:
        return [Event(type="session", session_id=sid)]
    return []


def _json(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None
