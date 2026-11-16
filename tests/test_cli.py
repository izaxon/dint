from __future__ import annotations

import json
import os
import sys

import pytest

from dint.cli import EventPrinter, _job_cwd_prompt, follow_chat, main, read_prompt, resolve_chat
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


def test_repl_help_engine_quit(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("dint.cli.ensure_runtime", lambda **k: None)
    monkeypatch.setattr("dint.cli.pick_engine", lambda: "grok")
    monkeypatch.setattr("dint.cli.shutil.which", lambda name: f"/bin/{name}" if name != "codex" else None)
    monkeypatch.setattr("dint.cli.logbook_url", lambda: "http://127.0.0.1:5101")
    monkeypatch.setattr("dint.cli.jobs_url", lambda: "http://127.0.0.1:8787")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    router = Router(
        store=ChatLog(MemoryLogbook(), project="dint"),
        engines={"grok": FakeEngine("grok", []), "claude": FakeEngine("claude", [])},
    )
    monkeypatch.setattr("dint.cli.Router", lambda: router)
    lines = iter(["/help", "/engine", "/quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    assert main([]) == 0
    err = capsys.readouterr().err
    assert "/job" in err and "dint job" in err
    assert "* grok" in err
    assert "NOT ON PATH" in err
    assert "no chats here yet" in err
    assert "grok    " in err or "chat " in err


def test_repl_engine_switch(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("dint.cli.ensure_runtime", lambda **k: None)
    monkeypatch.setattr("dint.cli.pick_engine", lambda: "grok")
    monkeypatch.setattr("dint.cli.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("dint.cli.logbook_url", lambda: "http://127.0.0.1:5100")
    monkeypatch.setattr("dint.cli.jobs_url", lambda: "http://127.0.0.1:8787")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    router = Router(
        store=ChatLog(MemoryLogbook(), project="dint"),
        engines={"grok": FakeEngine("grok", []), "claude": FakeEngine("claude", [])},
    )
    monkeypatch.setattr("dint.cli.Router", lambda: router)
    lines = iter(["/engine claude", "/quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    assert main([]) == 0
    engines = {c["engine"] for c in router.list_chats()}
    assert "claude" in engines


def test_repl_job(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("dint.cli.ensure_runtime", lambda **k: None)
    monkeypatch.setattr("dint.cli.pick_engine", lambda: "grok")
    monkeypatch.setattr("dint.cli.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("dint.cli.logbook_url", lambda: "http://127.0.0.1:5100")
    monkeypatch.setattr("dint.cli.jobs_url", lambda: "http://127.0.0.1:8787")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    router = Router(
        store=ChatLog(MemoryLogbook(), project="dint"),
        engines={"grok": FakeEngine("grok", [])},
    )
    monkeypatch.setattr("dint.cli.Router", lambda: router)
    monkeypatch.setattr("dint.jobs.post_job", lambda router, engine, prompt, cwd: "job-1")
    monkeypatch.setattr("dint.jobs.wait_for_job_chat", lambda router, job_id, timeout=20: "chatjob")
    lines = iter(["/job Summarize this repo", "/quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    assert main([]) == 0
    err = capsys.readouterr().err
    assert "job-1" in err and "chatjob" in err


def test_repl_unknown_slash_goes_to_engine(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("dint.cli.ensure_runtime", lambda **k: None)
    monkeypatch.setattr("dint.cli.pick_engine", lambda: "claude")
    monkeypatch.setattr("dint.cli.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("dint.cli.logbook_url", lambda: "http://127.0.0.1:5100")
    monkeypatch.setattr("dint.cli.jobs_url", lambda: "http://127.0.0.1:8787")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    claude = FakeEngine(
        "claude",
        [
            [Event(type="text", text="login please"), Event(type="done")],
            [Event(type="text", text="engine help"), Event(type="done")],
        ],
    )
    router = Router(
        store=ChatLog(MemoryLogbook(), project="dint"),
        engines={"claude": claude},
    )
    monkeypatch.setattr("dint.cli.Router", lambda: router)
    lines = iter(["/login", "//help", "/quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    assert main([]) == 0
    assert [c["prompt"] for c in claude.calls] == ["/login", "/help"]
    out = capsys.readouterr().out
    assert "login please" in out and "engine help" in out


def test_cli_streams_tokens_inline(capsys) -> None:
    printer = EventPrinter()
    printer.emit(Event(type="text", text="He"))
    printer.emit(Event(type="text", text="j"))
    printer.emit(Event(type="done", session_id="g1"))
    out = capsys.readouterr().out
    assert out.startswith("Hej\n")
    assert "[done] session=g1" in out


def _cli_router(monkeypatch, engine: FakeEngine) -> Router:
    router = Router(store=ChatLog(MemoryLogbook(), project="dint"), engines={engine.name: engine})
    monkeypatch.setattr("dint.cli.ensure_runtime", lambda **k: None)
    monkeypatch.setattr("dint.cli.Router", lambda: router)
    return router


def test_last_prints_the_whole_reply(monkeypatch, capsys) -> None:
    reply = "line one\nline two " + "x" * 300
    router = _cli_router(monkeypatch, FakeEngine("claude", [[Event(type="text", text=reply), Event(type="done")]]))
    chat_id = router.start_chat("claude", ".")
    list(router.send(chat_id, "hi"))
    assert main(["last"]) == 0
    assert capsys.readouterr().out == reply + "\n"
    assert main(["last", chat_id[:4], "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["bot"]["text"] == reply


def test_last_reports_error_and_running_turns(monkeypatch, capsys) -> None:
    router = _cli_router(monkeypatch, FakeEngine("grok", [[Event(type="error", text="not logged in")]]))
    chat_id = router.start_chat("grok", ".")
    assert main(["last", chat_id]) == 2
    assert "no reply yet" in capsys.readouterr().err
    list(router.send(chat_id, "hi"))
    assert main(["last", chat_id]) == 1
    assert "[error] not logged in" in capsys.readouterr().err


def test_list_full_and_json(monkeypatch, capsys) -> None:
    reply = "a\n" + "b" * 200
    router = _cli_router(monkeypatch, FakeEngine("claude", [[Event(type="text", text=reply), Event(type="done")]]))
    chat_id = router.start_chat("claude", ".")
    list(router.send(chat_id, "hi"))
    assert main(["list", chat_id, "--full"]) == 0
    out = capsys.readouterr().out
    assert "--- user" in out and "--- bot" in out and reply in out
    assert main(["list", chat_id, "--json"]) == 0
    assert [t["role"] for t in json.loads(capsys.readouterr().out)] == ["user", "bot"]
    assert main(["chats", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["chatId"] == chat_id


def test_resolve_chat_prefix_and_ambiguity() -> None:
    router = Router(store=ChatLog(MemoryLogbook(), project="dint"), engines={"grok": FakeEngine("grok", [])})
    a = router.start_chat("grok", ".")
    b = router.start_chat("grok", ".")
    assert resolve_chat(router, a[:12]) == a
    assert resolve_chat(router, b) == b
    assert resolve_chat(router, "last") in {a, b}
    unique = next(n for n in range(1, 13) if a[:n] != b[:n])
    assert resolve_chat(router, a[:unique]) == a
    if unique > 1:
        with pytest.raises(ValueError):
            resolve_chat(router, a[: unique - 1])
    with pytest.raises(RuntimeError):
        resolve_chat(Router(store=ChatLog(MemoryLogbook()), engines={}), "last")


def test_follow_chat_waits_for_the_reply(capsys) -> None:
    states = [
        [{"id": "1", "role": "user", "text": "hi"}],
        [{"id": "1", "role": "user", "text": "hi"}, {"id": "2", "role": "tool", "text": "read_file"}],
        [
            {"id": "1", "role": "user", "text": "hi"},
            {"id": "2", "role": "tool", "text": "read_file"},
            {"id": "3", "role": "bot", "text": "done!"},
        ],
    ]

    class Polled:
        def list_turns(self, chat_id: str) -> list[dict]:
            return states.pop(0) if len(states) > 1 else states[0]

    assert follow_chat(Polled(), "c1", sleep=lambda _s: None) == 0
    out = capsys.readouterr()
    assert out.out == "done!\n"
    assert out.err.count("[tool] read_file") == 1


def test_follow_chat_times_out(capsys) -> None:
    class Running:
        def list_turns(self, chat_id: str) -> list[dict]:
            return [{"id": "1", "role": "user", "text": "hi"}]

    assert follow_chat(Running(), "c1", timeout=0.01, interval=0.02) == 2
    assert "dint last c1" in capsys.readouterr().err


def test_job_wait_follows_the_chat(monkeypatch, capsys) -> None:
    _cli_router(monkeypatch, FakeEngine("grok", []))
    monkeypatch.setattr("dint.jobs.post_job", lambda router, engine, prompt, cwd: "job-1")
    monkeypatch.setattr("dint.jobs.wait_for_job_chat", lambda router, job_id, timeout=20: "chatjob")
    followed: list[tuple[str, float]] = []

    def fake_follow(router, chat_id, *, timeout=0):
        followed.append((chat_id, timeout))
        print("the answer")
        return 0

    monkeypatch.setattr("dint.cli.follow_chat", fake_follow)
    assert main(["job", "grok", "--wait", "--timeout", "5", "do", "it"]) == 0
    out = capsys.readouterr()
    assert out.out == "the answer\n"
    assert followed == [("chatjob", 5.0)]


def test_read_prompt_joins_pasted_lines() -> None:
    lines = iter(["first", "second", "third"])
    waiting = iter([True, True, False])
    text = read_prompt("> ", read=lambda _p: next(lines), pending=lambda: next(waiting))
    assert text == "first\nsecond\nthird"


def test_read_prompt_backslash_continues_typed_lines_only() -> None:
    lines = iter(["typed \\", "more"])
    assert read_prompt("> ", read=lambda _p: next(lines), pending=lambda: False) == "typed \nmore"
    pasted = iter(["echo a \\", "  b"])
    waiting = iter([True, False])
    assert (
        read_prompt("> ", read=lambda _p: next(pasted), pending=lambda: next(waiting))
        == "echo a \\\n  b"
    )


def test_repl_sends_a_pasted_block_as_one_turn(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("dint.cli.pick_engine", lambda: "claude")
    monkeypatch.setattr("dint.cli.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("dint.cli.logbook_url", lambda: "http://127.0.0.1:5100")
    monkeypatch.setattr("dint.cli.jobs_url", lambda: "http://127.0.0.1:8787")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    claude = FakeEngine("claude", [[Event(type="text", text="ok"), Event(type="done")]])
    _cli_router(monkeypatch, claude)
    lines = iter(["/review this:", "def f():", "    return 1", "/quit"])
    waiting = iter([True, True, False, False])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    monkeypatch.setattr("dint.cli._input_pending", lambda: next(waiting))
    assert main([]) == 0
    assert [c["prompt"] for c in claude.calls] == ["/review this:\ndef f():\n    return 1"]
