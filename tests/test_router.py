from __future__ import annotations

from collections.abc import Iterator

from dint.logbook import ChatLog
from dint.router import Router
from dint.types import Engine, Event
from test_logbook import MemoryLogbook


class FakeEngine:
    def __init__(self, name: str, batches: list[list[Event]]) -> None:
        self.name = name
        self.batches = list(batches)
        self.calls: list[dict] = []
        self.cancelled = False

    def send(self, prompt: str, *, cwd: str, session_id: str | None) -> Iterator[Event]:
        self.calls.append({"prompt": prompt, "cwd": cwd, "session_id": session_id})
        yield from (self.batches.pop(0) if self.batches else [])

    def cancel(self) -> None:
        self.cancelled = True


def _router(engine: FakeEngine) -> tuple[Router, MemoryLogbook]:
    ledger = MemoryLogbook()
    engines: dict[str, Engine] = {
        "claude": FakeEngine("claude", []),
        "codex": FakeEngine("codex", []),
    }
    engines[engine.name] = engine
    return Router(store=ChatLog(ledger, project="dint"), engines=engines), ledger


def test_new_chat_and_followup_keeps_session() -> None:
    engine = FakeEngine(
        "claude",
        [
            [
                Event(type="session", session_id="ses-1"),
                Event(type="text", text="first answer", session_id="ses-1"),
                Event(type="done", session_id="ses-1"),
            ],
            [
                Event(type="text", text="follow-up answer", session_id="ses-1"),
                Event(type="done", session_id="ses-1"),
            ],
        ],
    )
    router, _ = _router(engine)
    chat_id = router.start_chat("claude", cwd=r"C:\proj")
    list(router.send(chat_id, "hello"))
    list(router.send(chat_id, "again"))
    assert engine.calls[0]["session_id"] is None
    assert engine.calls[1]["session_id"] == "ses-1"
    assert [t["role"] for t in router.list_turns(chat_id)] == ["user", "bot", "user", "bot"]
    hist = router.store.list_messages(chat_id)
    ids = [h.get("id") for h in hist]
    parents = [h.get("parentId") for h in hist]
    assert parents[0] is None
    assert parents[1] == ids[0]


def test_crash_reload_does_not_lose_session_id() -> None:
    engine = FakeEngine(
        "codex",
        [[Event(type="session", session_id="thr_1"), Event(type="error", text="boom", session_id="thr_1")]],
    )
    router, ledger = _router(engine)
    chat_id = router.start_chat("codex", cwd=r"D:\work")
    list(router.send(chat_id, "run"))
    engine2 = FakeEngine(
        "codex",
        [[Event(type="text", text="recovered", session_id="thr_1"), Event(type="done", session_id="thr_1")]],
    )
    router2 = Router(
        store=ChatLog(ledger, project="dint"),
        engines={"codex": engine2, "claude": FakeEngine("claude", [])},
    )
    assert router2.get_chat(chat_id).external_session_id == "thr_1"
    list(router2.send(chat_id, "continue"))
    assert engine2.calls[0]["session_id"] == "thr_1"


def test_cancel_without_live_turn_keeps_session() -> None:
    engine = FakeEngine(
        "claude",
        [[Event(type="session", session_id="ses-keep"), Event(type="text", text="x"), Event(type="done")]],
    )
    router, _ = _router(engine)
    chat_id = router.start_chat("claude", cwd=".")
    list(router.send(chat_id, "go"))
    router.cancel(chat_id)
    assert router.get_chat(chat_id).external_session_id == "ses-keep"


def test_copilot_followup_uses_session() -> None:
    engine = FakeEngine(
        "copilot",
        [
            [Event(type="session", session_id="cp-1"), Event(type="text", text="ok"), Event(type="done")],
            [Event(type="text", text="again"), Event(type="done", session_id="cp-1")],
        ],
    )
    router, _ = _router(engine)
    chat_id = router.start_chat("copilot", cwd=".")
    list(router.send(chat_id, "hi"))
    list(router.send(chat_id, "more"))
    assert engine.calls[0]["session_id"] is None
    assert engine.calls[1]["session_id"] == "cp-1"
