"""Codex CLI: `codex exec` / `codex exec resume <id>`."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from dint.engines.base import CliEngine
from dint.types import Event


class CodexEngine(CliEngine):
    name = "codex"

    def __init__(self, binary: str | None = None) -> None:
        super().__init__(binary or os.environ.get("DINT_CODEX_BIN") or shutil.which("codex") or "codex")

    def argv(self, prompt: str, cwd: str, session_id: str | None) -> list[str]:
        cmd = [self.binary, "exec"]
        if session_id:
            cmd.extend(["resume", session_id])
        cmd.extend(
            [
                "--json",
                "--skip-git-repo-check",
                "-C",
                cwd,
                "-s",
                os.environ.get("DINT_CODEX_SANDBOX", "workspace-write"),
            ]
        )
        cmd.append(prompt)
        return cmd

    def parse_line(self, line: str, session_id: str | None) -> list[Event]:
        return parse_codex_line(line, session_id=session_id)


def parse_codex_line(line: str, *, session_id: str | None = None) -> list[Event]:
    obj = _json(line)
    if not obj:
        return []
    msg = obj["msg"] if isinstance(obj.get("msg"), dict) else obj
    sid = (
        obj.get("thread_id")
        or msg.get("thread_id")
        or obj.get("session_id")
        or msg.get("session_id")
        or session_id
    )
    kind = str(msg.get("type") or obj.get("type") or "")
    if kind in {"thread.started", "thread_started", "session_created"} and sid:
        return [Event(type="session", session_id=sid)]
    if kind in {"item.completed", "item_completed", "item.started", "agent_message"}:
        return _item(msg.get("item") or msg, sid)
    if kind in {"turn.completed", "turn_complete", "task_complete"}:
        return [Event(type="done", session_id=sid)]
    if kind in {"turn.failed", "error", "turn_failed"}:
        return [Event(type="error", text=str(msg.get("message") or msg.get("error") or "error"), session_id=sid)]
    if "approval" in kind:
        return [Event(type="need_approval", text=str(msg.get("command") or kind), session_id=sid)]
    return []


def _item(item: Any, sid: str | None) -> list[Event]:
    if not isinstance(item, dict):
        return []
    itype = str(item.get("type") or "")
    if itype in {"command_execution", "command", "mcp_tool_call", "file_change", "patch", "tool"}:
        name = str(item.get("command") or item.get("name") or itype)
        return [Event(type="tool", text=name, tool=itype, session_id=sid)]
    text = item.get("text") or item.get("content") or item.get("message")
    if isinstance(text, str) and text:
        return [Event(type="text", text=text, session_id=sid)]
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
