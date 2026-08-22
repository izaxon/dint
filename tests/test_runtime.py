from __future__ import annotations

import os
from pathlib import Path

import pytest

from dint.runtime import (
    ensure_defaults,
    ensure_logbook,
    ensure_serve,
    pick_engine,
)


def test_ensure_defaults_writes_home_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DINT_HOME", str(tmp_path))
    monkeypatch.delenv("LOGBOOK_API_KEY", raising=False)
    monkeypatch.delenv("LOGBOOK_PROJECT", raising=False)
    monkeypatch.delenv("LOGBOOK_URL", raising=False)
    ensure_defaults()
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "LOGBOOK_PROJECT=dint" in text
    assert "LOGBOOK_URL=http://127.0.0.1:5100" in text
    assert os.environ["LOGBOOK_API_KEY"]
    assert os.environ["LOGBOOK_PROJECT"] == "dint"


def test_ensure_logbook_skips_when_healthy(monkeypatch) -> None:
    monkeypatch.setattr("dint.runtime.probe", lambda url, timeout=1.5: True)

    def boom(*_a, **_k):
        raise AssertionError("should not spawn")

    monkeypatch.setattr("dint.runtime.spawn_detached", boom)
    ensure_logbook()


def test_ensure_logbook_spawns(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DINT_HOME", str(tmp_path))
    monkeypatch.setattr("dint.runtime.probe", lambda url, timeout=1.5: False)
    monkeypatch.setattr("dint.runtime.wait_for", lambda url, timeout=12: True)
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


def test_ensure_logbook_missing_binary(monkeypatch) -> None:
    monkeypatch.setattr("dint.runtime.probe", lambda url, timeout=1.5: False)
    monkeypatch.setattr("dint.runtime.shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="logbook-server"):
        ensure_logbook()


def test_ensure_serve_spawns(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DINT_HOME", str(tmp_path))
    monkeypatch.delenv("DINT_ROLE", raising=False)
    monkeypatch.setattr("dint.runtime.probe", lambda url, timeout=1.5: False)
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


def test_pick_engine_env_override(monkeypatch) -> None:
    monkeypatch.setenv("DINT_ENGINE", "codex")
    monkeypatch.setattr(
        "dint.runtime.shutil.which",
        lambda name: str(Path("/bin") / name) if name in {"grok", "codex"} else None,
    )
    assert pick_engine() == "codex"