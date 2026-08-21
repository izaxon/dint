"""dint — one local chat API over Claude, Codex, Grok, and Copilot."""

from dint.router import Router
from dint.types import Chat, Event

__all__ = ["Chat", "Event", "Router"]
__version__ = "0.1.0"
