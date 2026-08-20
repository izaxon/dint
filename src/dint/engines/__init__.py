from dint.engines.base import CliEngine, StubEngine
from dint.engines.claude import ClaudeEngine, parse_claude_line
from dint.engines.codex import CodexEngine, parse_codex_line
from dint.engines.grok import GrokEngine
from dint.types import Engine


def default_engines() -> dict[str, Engine]:
    return {
        "claude": ClaudeEngine(),
        "codex": CodexEngine(),
        "grok": GrokEngine(),
        "copilot": StubEngine("copilot"),
    }


__all__ = [
    "ClaudeEngine",
    "CliEngine",
    "CodexEngine",
    "GrokEngine",
    "StubEngine",
    "default_engines",
    "parse_claude_line",
    "parse_codex_line",
]
