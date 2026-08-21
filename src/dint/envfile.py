"""Load KEY=VALUE from .env without overriding the real environment."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(start: str | None = None) -> Path | None:
    path = _find_env(start)
    if path is None:
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    return path


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
