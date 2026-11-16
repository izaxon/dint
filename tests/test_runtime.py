from __future__ import annotations

import os
from pathlib import Path

import pytest

from dint.logbook.rest import LogbookError
from dint.runtime import (
    can_bind,
    ensure_defaults,
    ensure_logbook,
    ensure_serve,
    find_free_port,
    pick_engine,
)


class _OkRest:
    def __init__(self, *_a, **_k) -> None:
        pass

    def get_messages(self, length: int = 1) -> list:
        return []


class _UnauthorizedRest:
    def __init__(self, *_a, **_k) -> None:
        pass

    def get_messages(self, length: int = 1) -> list:
        raise LogbookError('HTTP 401 GET /api/messages: {"error":"Unauthorized"}')


def test_ensure_defaults_writes_home_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DINT_HOME", str(tmp_path))
    monkeypatch.delenv("LOGBOOK_API_KEY", raising=False)
    monkeypatch.delenv("LOGBOOK_PROJECT", raising=False)
    monkeypatch.delenv("LOGBOOK_URL", raising=False)
    ensure_defaults()
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "LOGBOOK_PROJECT=dint" in text
    assert "LOGBOOK_URL=http://127.0.0.1:5100" in text
    assert "LOGBOOK_API_KEY" not in text
    assert os.environ["LOGBOOK_PROJECT"] == "dint"


def test_ensure_logbook_skips_when_healthy(monkeypatch) -> None:
    monkeypatch.setattr(
        "dint.runtime.logbook_health",
        lambda **k: {"status": "healthy", "project": "test"},
    )
    monkeypatch.setattr("dint.runtime.RestLogbook", _OkRest)

    def boom(*_a, **_k):
        raise AssertionError("should not spawn")

    monkeypatch.setattr("dint.runtime.spawn_detached", boom)
    ensure_logbook()


def test_ensure_logbook_foreign_starts_on_new_port(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DINT_HOME", str(tmp_path))
    monkeypatch.setenv("LOGBOOK_URL", "http://127.0.0.1:5100")
    monkeypatch.setenv("LOGBOOK_API_KEY", "dint-key")
    monkeypatch.setenv("LOGBOOK_PROJECT", "dint")

    def health(**_k):
        if os.environ.get("LOGBOOK_URL", "").endswith(":5100"):
            return {"status": "healthy", "project": "test"}
        return None

    monkeypatch.setattr("dint.runtime.logbook_health", health)
    monkeypatch.setattr("dint.runtime.RestLogbook", _UnauthorizedRest)
    monkeypatch.setattr("dint.runtime.find_free_port", lambda host, start, count=30: 5101)
    monkeypatch.setattr("dint.runtime.ensure_logbook_auth", lambda health=None: None)
    monkeypatch.setattr("dint.runtime.wait_for", lambda url, timeout=12: True)
    monkeypatch.setattr(
        "dint.runtime.shutil.which",
        lambda name: "/bin/logbook-server" if name == "logbook-server" else None,
    )
    monkeypatch.setattr("dint.runtime.spawn_detached", lambda argv, **k: 9)
    ensure_logbook()
    assert os.environ["LOGBOOK_URL"] == "http://127.0.0.1:5101"
    assert "5101" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_ensure_logbook_spawns(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DINT_HOME", str(tmp_path))
    monkeypatch.delenv("LOGBOOK_API_KEY", raising=False)
    monkeypatch.setattr("dint.runtime.logbook_health", lambda **k: None)
    monkeypatch.setattr("dint.runtime.ensure_logbook_auth", lambda health=None: None)
    monkeypatch.setattr("dint.runtime.wait_for", lambda url, timeout=12: True)
    # Keep real ports out of it: a busy 5100 on the runner made this test flaky.
    monkeypatch.setattr("dint.runtime.can_bind", lambda host, port: True)
    monkeypatch.setattr("dint.runtime.probe", lambda url, timeout=1.5: False)
    monkeypatch.setattr(
        "dint.runtime.shutil.which",
        lambda name: "/bin/logbook-server" if name == "logbook-server" else None,
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "dint.runtime.spawn_detached",
        lambda argv, **k: calls.append(argv) or 42,
    )
    ensure_defaults()
    ensure_logbook()
    assert calls[0] == ["/bin/logbook-server"]
    assert os.environ["LOGBOOK_API_KEY"]


def test_ensure_logbook_missing_binary(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DINT_HOME", str(tmp_path))
    monkeypatch.delenv("LOGBOOK_API_KEY", raising=False)
    monkeypatch.setattr("dint.runtime.logbook_health", lambda **k: None)
    monkeypatch.setattr("dint.runtime.shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="logbook-server"):
        ensure_logbook()


def test_ensure_serve_spawns(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DINT_HOME", str(tmp_path))
    monkeypatch.delenv("DINT_ROLE", raising=False)
    monkeypatch.setattr("dint.runtime.probe", lambda url, timeout=1.5: False)
    monkeypatch.setattr("dint.runtime.serve_health", lambda: None)
    monkeypatch.setattr("dint.runtime.can_bind", lambda host, port: True)
    monkeypatch.setattr("dint.runtime.wait_for", lambda url, timeout=12: True)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "dint.runtime.spawn_detached",
        lambda argv, **k: calls.append(argv) or 7,
    )
    ensure_serve()
    assert "-m" in calls[0] and "dint" in calls[0] and "serve" in calls[0]


def test_ensure_serve_skips_when_already_server(monkeypatch) -> None:
    monkeypatch.setenv("DINT_ROLE", "serve")

    def boom(*_a, **_k):
        raise AssertionError("should not spawn")

    monkeypatch.setattr("dint.runtime.spawn_detached", boom)
    ensure_serve()


def test_pick_engine_prefers_grok(monkeypatch) -> None:
    monkeypatch.delenv("DINT_ENGINE", raising=False)
    monkeypatch.setattr(
        "dint.runtime.shutil.which",
        lambda name: str(Path("/bin") / name) if name in {"grok", "claude"} else None,
    )
    assert pick_engine() == "grok"


def test_find_free_port_skips_occupied(monkeypatch) -> None:
    busy = {5101}

    monkeypatch.setattr(
        "dint.runtime.probe",
        lambda url, timeout=1.5: ":5101" in url,
    )
    monkeypatch.setattr(
        "dint.runtime.can_bind",
        lambda host, port: port not in busy,
    )
    assert find_free_port("127.0.0.1", 5101) == 5102


def test_can_bind_occupied() -> None:
    sock = __import__("socket").socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        assert can_bind("127.0.0.1", port) is False
    finally:
        sock.close()


def test_pick_engine_env_override(monkeypatch) -> None:
    monkeypatch.setenv("DINT_ENGINE", "codex")
    monkeypatch.setattr(
        "dint.runtime.shutil.which",
        lambda name: str(Path("/bin") / name) if name in {"grok", "codex"} else None,
    )
    assert pick_engine() == "codex"