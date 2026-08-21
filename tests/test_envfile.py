from __future__ import annotations

import os

from dint.envfile import load_dotenv


def test_load_dotenv_does_not_override(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text("LOGBOOK_PROJECT=fromfile\nLOGBOOK_API_KEY=filekey\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOGBOOK_API_KEY", "already")
    monkeypatch.delenv("LOGBOOK_PROJECT", raising=False)
    path = load_dotenv(str(tmp_path))
    assert path == env
    assert os.environ["LOGBOOK_API_KEY"] == "already"
    assert os.environ["LOGBOOK_PROJECT"] == "fromfile"
