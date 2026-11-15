from __future__ import annotations

import os

from dint.envfile import load_dotenv, write_env
from dint.runtime import ensure_webhook_secret


def test_write_env_keeps_other_lines(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("# mine\nDINT_ENGINE=claude\nLOGBOOK_URL=http://old\n", encoding="utf-8")
    write_env(env, {"LOGBOOK_URL": "http://new", "LOGBOOK_WEBHOOK_SECRET": "s"})
    assert env.read_text(encoding="utf-8").splitlines() == [
        "# mine",
        "DINT_ENGINE=claude",
        "LOGBOOK_URL=http://new",
        "LOGBOOK_WEBHOOK_SECRET=s",
    ]


def test_webhook_secret_is_generated_once_and_persisted(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DINT_HOME", str(tmp_path))
    (tmp_path / ".env").write_text("DINT_ENGINE=grok\n", encoding="utf-8")
    secret = ensure_webhook_secret()
    assert len(secret) >= 32
    assert ensure_webhook_secret() == secret
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "DINT_ENGINE=grok" in text
    assert f"LOGBOOK_WEBHOOK_SECRET={secret}" in text


def test_load_dotenv_does_not_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DINT_HOME", str(tmp_path / "home"))
    env = tmp_path / ".env"
    env.write_text("LOGBOOK_PROJECT=fromfile\nLOGBOOK_API_KEY=filekey\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOGBOOK_API_KEY", "already")
    monkeypatch.delenv("LOGBOOK_PROJECT", raising=False)
    path = load_dotenv(str(tmp_path))
    assert path == env
    assert os.environ["LOGBOOK_API_KEY"] == "already"
    assert os.environ["LOGBOOK_PROJECT"] == "fromfile"


def test_cwd_env_wins_over_home(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".env").write_text(
        "LOGBOOK_PROJECT=homeproj\nLOGBOOK_URL=http://home:5100\n",
        encoding="utf-8",
    )
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".env").write_text("LOGBOOK_PROJECT=cwdproj\n", encoding="utf-8")
    monkeypatch.setenv("DINT_HOME", str(home))
    monkeypatch.chdir(proj)
    monkeypatch.delenv("LOGBOOK_PROJECT", raising=False)
    monkeypatch.delenv("LOGBOOK_URL", raising=False)
    path = load_dotenv(str(proj))
    assert path == proj / ".env"
    assert os.environ["LOGBOOK_PROJECT"] == "cwdproj"
    assert os.environ["LOGBOOK_URL"] == "http://home:5100"
