"""Grok CLI: `grok -p --resume <id> --output-format streaming-json`.

Headless stream is the same NDJSON shape as Claude Code (`system/init`,
`assistant`, `result` with `session_id`).
"""

from __future__ import annotations

import os
import shutil

from dint.engines.base import CliEngine
from dint.engines.claude import parse_claude_line
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
        return parse_claude_line(line, session_id=session_id)
