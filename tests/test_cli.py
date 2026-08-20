from __future__ import annotations

from dint.cli import main
from dint.router import Router
from dint.store.logbook import LogbookStore
from test_logbook import MemoryClient
from test_router import FakeEngine
from dint.types import Event


def test_cli_start_and_list(monkeypatch, capsys) -> None:
    client = MemoryClient()
    engine = FakeEngine(
        "claude",
        [
            [
                Event(type="text", text="ok", session_id="ses-cli"),
                Event(type="done", session_id="ses-cli"),
            ]
        ],
    )
    store = LogbookStore(client=client, project="dint")
    router = Router(store=store, engines={"claude": engine, "codex": FakeEngine("codex", [])})

    monkeypatch.setattr("dint.cli.Router", lambda store=None: router)
    monkeypatch.setattr("dint.cli.LogbookStore", lambda: store)

    assert main(["start", "claude", "."]) == 0
    chat_id = capsys.readouterr().out.strip()
    assert len(chat_id) == 12
    assert main(["send", chat_id, "hello"]) == 0
    capsys.readouterr()
    assert main(["list", "--json", chat_id]) == 0
    out = capsys.readouterr().out
    assert "hello" in out
    assert "ok" in out
    assert main(["show", chat_id]) == 0
    show = capsys.readouterr().out
    assert "ses-cli" in show
