from __future__ import annotations

from collections.abc import Iterator

from dint.types import Engine, Event


class StubEngine(Engine):
    def __init__(self, name: str) -> None:
        self.name = name

    def send(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None,
    ) -> Iterator[Event]:
        raise NotImplementedError(f"{self.name} adapter is a stub in v0")

    def cancel(self) -> None:
        return
