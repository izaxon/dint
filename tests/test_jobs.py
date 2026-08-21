from __future__ import annotations

import threading

from dint.jobs import handle_event, parse_job
from dint.logbook import ChatLog
from dint.router import Router
from dint.types import Event
from test_logbook import MemoryLogbook
from test_router import FakeEngine


def test_parse_job_from_tags_and_json() -> None:
    job = parse_job(
        '@test #job #grok {"engine":"grok","cwd":"C:\\\\proj","prompt":"hello"}',
        ["job", "grok"],
    )
    assert job is not None
    assert job["engine"] == "grok"
    assert job["prompt"] == "hello"


def test_parse_job_plain_prompt() -> None:
    job = parse_job("@test #job #claude Summarize this repo", ["#job", "#claude"])
    assert job is not None
    assert job["engine"] == "claude"
    assert job["prompt"] == "Summarize this repo"


def test_parse_job_ignores_ack() -> None:
    assert parse_job("@test #job-run #chat-abc", ["job-run", "chat-abc"]) is None
    assert parse_job("@test #chat #user hi", ["chat", "user"]) is None


def test_handle_event_starts_chat(monkeypatch) -> None:
    class Immediate(threading.Thread):
        def start(self) -> None:
            self.run()

    monkeypatch.setattr(threading, "Thread", Immediate)
    engine = FakeEngine(
        "claude",
        [[Event(type="text", text="ok"), Event(type="done", session_id="s1")]],
    )
    ledger = MemoryLogbook()
    router = Router(
        store=ChatLog(ledger, project="test"),
        engines={"claude": engine, "codex": FakeEngine("codex", [])},
    )
    chat_id = handle_event(
        {
            "eventType": "message.created",
            "eventId": "e1",
            "data": {
                "messageId": "job1",
                "tags": ["job", "claude"],
                "content": '@test #job #claude {"prompt":"hi","cwd":"."}',
            },
        },
        router,
    )
    assert chat_id
    assert engine.calls
    assert engine.calls[0]["prompt"] == "hi"
    assert any("#job-run" in m["content"] for m in ledger.posted)
    assert any(t["role"] == "bot" and t["text"] == "ok" for t in router.list_turns(chat_id))
