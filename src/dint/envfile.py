"""Load KEY=VALUE from .env without overriding the real environment."""

from __future__ import annotations

import os
from pathlib import Path


def home_dir() -> Path:
    override = os.environ.get("DINT_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".dint"


def home_env_path() -> Path:
    return home_dir() / ".env"


def load_dotenv(start: str | None = None) -> Path | None:
    cwd_env = _find_env(start)
    home_env = home_env_path()
    applied: Path | None = None
    if cwd_env is not None:
        _apply(cwd_env)
        applied = cwd_env
    if home_env.is_file() and home_env != cwd_env:
        _apply(home_env)
        applied = applied or home_env
    return applied


def write_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _apply(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _find_env(start: str | None) -> Path | None:
    here = Path(start or os.getcwd()).resolve()
    for _ in range(6):
        candidate = here / ".env"
        if candidate.is_file():
            return candidate
        if here.parent == here:
            break
        here = here.parent
    return None
