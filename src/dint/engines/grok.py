"""Grok CLI: `grok -p --output-format streaming-json`.

Native NDJSON (not Claude stream-json):
  {"type":"text","data":"..."}
  {"type":"tool_call","toolName":"read_file",...}
  {"type":"end","sessionId":"..."}
  {"type":"error","message":"..."}
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from dint.engines.base import CliEngine
from dint.types import Event


class GrokEngine(CliEngine):
    name = "grok"

    def __init__(self, binary: str | None = None) -> None:
        super().__init__(binary or os.environ.get("DINT_GROK_BIN") or shutil.which("grok") or "grok")

    def argv(self, prompt: str, cwd: str, session_id: str | None) -> list[str]:
        cmd = [
            self.binary,
            "--no-auto-update",
            "--always-approve",
            "--cwd",
            cwd,
            "--output-format",
            "streaming-json",
            "-p",
            prompt,
        ]
        if session_id:
            cmd.extend(["--resume", session_id])
        return cmd

    def parse_line(self, line: str, session_id: str | None) -> list[Event]:
        return parse_grok_line(line, session_id=session_id)


def parse_grok_line(line: str, *, session_id: str | None = None) -> list[Event]:
    obj = _json(line)
    if not obj:
        return []
    sid = obj.get("sessionId") or obj.get("session_id") or session_id
    kind = str(obj.get("type") or "")
    if kind == "text":
        text = obj.get("data")
        if isinstance(text, str) and text:
            return [Event(type="text", text=text, session_id=sid)]
        return []
    if kind == "tool_call":
        name = str(obj.get("toolName") or obj.get("title") or "tool")
        return [Event(type="tool", text=name, tool=name, session_id=sid)]
    if kind == "end":
        return [Event(type="done", session_id=sid)]
    if kind == "error":
        return [Event(type="error", text=str(obj.get("message") or "grok error"), session_id=sid)]
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
