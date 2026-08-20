from __future__ import annotations

from collections.abc import Iterator

from dint.router import Router
from dint.store.logbook import LogbookStore
from dint.types import Engine, Event
from test_logbook import MemoryClient


class FakeEngine(Engine):
    def __init__(self, name: str, batches: list[list[Event]]) -> None:
        self.name = name
        self.batches = list(batches)
        self.calls: list[dict] = []
        self.cancelled = False

    def send(self, prompt: str, *, cwd: str, session_id: str | None) -> Iterator[Event]:
        self.calls.append({"prompt": prompt, "cwd": cwd, "session_id": session_id})
        events = self.batches.pop(0) if self.batches else []
        yield from events

    def cancel(self) -> None:
        self.cancelled = True


def _router(engine: FakeEngine) -> tuple[Router, MemoryClient]:
    client = MemoryClient()
    store = LogbookStore(client=client, project="dint")
    engines = {
        "claude": FakeEngine("claude", []),
        "codex": FakeEngine("codex", []),
    }
    engines[engine.name] = engine
    router = Router(store=store, engines=engines)
    return router, client


def test_new_chat_and_followup_keeps_session() -> None:
    engine = FakeEngine(
        "claude",
        [
            [
                Event(type="text", text="", session_id="ses-1"),
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
    events = list(router.send(chat_id, "hello"))
    assert any(e.session_id == "ses-1" for e in events)
    list(router.send(chat_id, "again"))
    assert engine.calls[0]["session_id"] is None
    assert engine.calls[1]["session_id"] == "ses-1"
    turns = router.list_turns(chat_id)
    roles = [t["role"] for t in turns]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert all(t["externalSessionId"] == "ses-1" or t["role"] == "user" for t in turns[1:])


def test_crash_reload_does_not_lose_session_id() -> None:
    engine = FakeEngine(
        "codex",
        [
            [
                Event(type="text", text="hi", session_id="thr_1"),
                Event(type="error", text="boom", session_id="thr_1"),
            ]
        ],
    )
    router, client = _router(engine)
    chat_id = router.start_chat("codex", cwd=r"D:\work")
    list(router.send(chat_id, "run"))
    # New process: same ledger, empty memory.
    engine2 = FakeEngine("codex", [[Event(type="text", text="recovered", session_id="thr_1"), Event(type="done", session_id="thr_1")]])
    router2 = Router(
        store=LogbookStore(client=client, project="dint"),
        engines={"codex": engine2, "claude": FakeEngine("claude", [])},
    )
    assert router2.get_chat(chat_id).external_session_id == "thr_1"
    list(router2.send(chat_id, "continue"))
    assert engine2.calls[0]["session_id"] == "thr_1"


def test_cancel_without_live_turn_keeps_session() -> None:
    engine = FakeEngine(
        "claude",
        [[Event(type="text", text="x", session_id="ses-keep"), Event(type="done", session_id="ses-keep")]],
    )
    router, _ = _router(engine)
    chat_id = router.start_chat("claude", cwd=".")
    list(router.send(chat_id, "go"))
    router.cancel(chat_id)
    assert router.get_chat(chat_id).external_session_id == "ses-keep"
    assert engine.cancelled is False


def test_copilot_stub() -> None:
    router, _ = _router(FakeEngine("claude", []))
    router.engines["copilot"] = FakeEngine("copilot", [])
    chat_id = router.start_chat("copilot", cwd=".")
    try:
        list(router.send(chat_id, "hi"))
        raise AssertionError("stub should raise")
    except NotImplementedError:
        pass
