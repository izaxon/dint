from __future__ import annotations

from dint.cli import EventPrinter, main
from dint.logbook import ChatLog
from dint.router import Router
from dint.types import Event
from test_logbook import MemoryLogbook
from test_router import FakeEngine


def test_cli_start_and_list(monkeypatch, capsys) -> None:
    engine = FakeEngine(
        "claude",
        [[Event(type="session", session_id="ses-cli"), Event(type="text", text="ok"), Event(type="done")]],
    )
    router = Router(
        store=ChatLog(MemoryLogbook(), project="dint"),
        engines={"claude": engine, "codex": FakeEngine("codex", []), "grok": FakeEngine("grok", [])},
    )
    monkeypatch.setattr("dint.cli.Router", lambda: router)

    assert main(["start", "claude", "."]) == 0
    chat_id = capsys.readouterr().out.strip()
    assert len(chat_id) == 12
    assert main(["send", chat_id, "hello"]) == 0
    capsys.readouterr()
    assert main(["list", chat_id]) == 0
    out = capsys.readouterr().out
    assert "hello" in out and "ok" in out
    assert main(["show", chat_id]) == 0
    assert "ses-cli" in capsys.readouterr().out
    assert main(["chats"]) == 0
    chats_out = capsys.readouterr().out
    assert chat_id in chats_out


def test_cli_streams_tokens_inline(capsys) -> None:
    printer = EventPrinter()
    printer.emit(Event(type="text", text="He"))
    printer.emit(Event(type="text", text="j"))
    printer.emit(Event(type="done", session_id="g1"))
    out = capsys.readouterr().out
    assert out.startswith("Hej\n")
    assert "[done] session=g1" in out
