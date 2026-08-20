from dint.engines.base import CliEngine, StubEngine
from dint.engines.claude import ClaudeEngine, parse_claude_line
from dint.engines.codex import CodexEngine, parse_codex_line
from dint.engines.copilot import CopilotEngine, parse_copilot_line
from dint.engines.grok import GrokEngine
from dint.types import Engine


def default_engines() -> dict[str, Engine]:
    return {
        "claude": ClaudeEngine(),
        "codex": CodexEngine(),
        "grok": GrokEngine(),
        "copilot": CopilotEngine(),
    }


__all__ = [
    "ClaudeEngine",
    "CliEngine",
    "CodexEngine",
    "CopilotEngine",
    "GrokEngine",
    "StubEngine",
    "default_engines",
    "parse_claude_line",
    "parse_codex_line",
    "parse_copilot_line",
]
