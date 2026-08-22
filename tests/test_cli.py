from __future__ import annotations

import os

from dint.cli import EventPrinter, _job_cwd_prompt, main
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
    monkeypatch.setattr("dint.cli.ensure_runtime", lambda **k: None)
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


def test_job_cwd_prompt(tmp_path) -> None:
    cwd, prompt = _job_cwd_prompt(["hello", "world"])
    assert prompt == "hello world"
    cwd, prompt = _job_cwd_prompt([str(tmp_path), "do", "work"])
    assert cwd == os.path.abspath(str(tmp_path))
    assert prompt == "do work"


def test_dint_prompt_starts_chat(monkeypatch, capsys) -> None:
    engine = FakeEngine(
        "grok",
        [[Event(type="text", text="pong"), Event(type="done", session_id="s1")]],
    )
    router = Router(
        store=ChatLog(MemoryLogbook(), project="dint"),
        engines={"grok": engine, "claude": FakeEngine("claude", []), "codex": FakeEngine("codex", [])},
    )
    monkeypatch.setattr("dint.cli.ensure_runtime", lambda **k: None)
    monkeypatch.setattr("dint.cli.pick_engine", lambda: "grok")
    monkeypatch.setattr("dint.cli.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("dint.cli.Router", lambda: router)
    assert main(["hello there"]) == 0
    out = capsys.readouterr()
    assert "pong" in out.out
    chats = router.list_chats()
    assert len(chats) == 1
    assert chats[0]["engine"] == "grok"


def test_dint_engine_prompt(monkeypatch, capsys) -> None:
    engine = FakeEngine(
        "claude",
        [[Event(type="text", text="ok"), Event(type="done")]],
    )
    router = Router(
        store=ChatLog(MemoryLogbook(), project="dint"),
        engines={"claude": engine, "grok": FakeEngine("grok", [])},
    )
    monkeypatch.setattr("dint.cli.ensure_runtime", lambda **k: None)
    monkeypatch.setattr("dint.cli.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("dint.cli.Router", lambda: router)
    assert main(["claude", "hi"]) == 0
    assert "ok" in capsys.readouterr().out
    assert router.list_chats()[0]["engine"] == "claude"


def test_dint_resumes_same_cwd(monkeypatch, capsys, tmp_path) -> None:
    engine = FakeEngine(
        "grok",
        [
            [Event(type="text", text="one"), Event(type="done")],
            [Event(type="text", text="two"), Event(type="done")],
        ],
    )
    router = Router(
        store=ChatLog(MemoryLogbook(), project="dint"),
        engines={"grok": engine},
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("dint.cli.ensure_runtime", lambda **k: None)
    monkeypatch.setattr("dint.cli.pick_engine", lambda: "grok")
    monkeypatch.setattr("dint.cli.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("dint.cli.Router", lambda: router)
    assert main(["first"]) == 0
    chat_id = router.list_chats()[0]["chatId"]
    assert main(["second"]) == 0
    assert router.list_chats()[0]["chatId"] == chat_id
    turns = router.list_turns(chat_id)
    assert [t.get("text") for t in turns if t.get("role") == "user"] == ["first", "second"]


def test_cli_streams_tokens_inline(capsys) -> None:
    printer = EventPrinter()
    printer.emit(Event(type="text", text="He"))
    printer.emit(Event(type="text", text="j"))
    printer.emit(Event(type="done", session_id="g1"))
    out = capsys.readouterr().out
    assert out.startswith("Hej\n")
    assert "[done] session=g1" in out
