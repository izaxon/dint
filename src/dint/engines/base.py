"""JSONL CLI runner. Adapters only supply argv + line parser."""

from __future__ import annotations

from collections.abc import Iterator

from dint.proc import CancelledError, RunningProcess, spawn
from dint.types import Event


class CliEngine:
    """Spawn a CLI, stream JSONL stdout into Event, cancel the process tree."""

    name: str

    def __init__(self, binary: str) -> None:
        self.binary = binary
        self._running: RunningProcess | None = None

    def argv(self, prompt: str, cwd: str, session_id: str | None) -> list[str]:
        raise NotImplementedError

    def parse_line(self, line: str, session_id: str | None) -> list[Event]:
        raise NotImplementedError

    def send(self, prompt: str, *, cwd: str, session_id: str | None) -> Iterator[Event]:
        self._running = spawn(self.argv(prompt, cwd, session_id), cwd=cwd)
        sid = session_id
        done = False
        try:
            for line in self._running.lines():
                for event in self.parse_line(line, sid):
                    if event.session_id:
                        sid = event.session_id
                    if event.type == "done":
                        done = True
                    yield event
            if not done:
                yield Event(type="done", session_id=sid)
        except CancelledError:
            yield Event(type="error", text="cancelled", session_id=sid)
        finally:
            self._running = None

    def cancel(self) -> None:
        if self._running is not None:
            self._running.cancel()


class StubEngine:
    def __init__(self, name: str) -> None:
        self.name = name

    def send(self, prompt: str, *, cwd: str, session_id: str | None) -> Iterator[Event]:
        raise NotImplementedError(f"{self.name} adapter is a stub")

    def cancel(self) -> None:
        return
