from __future__ import annotations

import os

from dint.envfile import load_dotenv


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
