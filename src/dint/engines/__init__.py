from __future__ import annotations

from dint.engines.base import StubEngine
from dint.engines.claude import ClaudeEngine
from dint.engines.codex import CodexEngine
from dint.types import Engine


def default_engines() -> dict[str, Engine]:
    return {
        "claude": ClaudeEngine(),
        "codex": CodexEngine(),
        "copilot": StubEngine("copilot"),
        "grok": StubEngine("grok"),
    }
