from __future__ import annotations

import os
import shutil

from dint.logbook import LogbookError, default_logbook
from dint.logbook.rest import RestLogbook
from dint.router import ENGINES


def run_status() -> int:
    url = os.environ.get("LOGBOOK_URL", "http://127.0.0.1:5100")
    project = os.environ.get("LOGBOOK_PROJECT", "dint")
    key = os.environ.get("LOGBOOK_API_KEY", "")
    env_path = os.environ.get("DINT_ENV_FILE") or ""
    print(f"env file:  {env_path or '(none)'}")
    print(f"logbook:   {url}")
    print(f"project:   {project}")
    print(f"api key:   {'set' if key else 'MISSING'}")
    failed = 0

    logbook = default_logbook()
    rest = logbook if isinstance(logbook, RestLogbook) else RestLogbook(url, key)
    try:
        health = rest.health()
        print(f"health:    OK  {health.get('status')} project={health.get('project')}")
    except LogbookError as e:
        print(f"health:    FAIL  {e}")
        failed += 1

    try:
        rest.get_messages(length=1)
        print("auth:      OK")
    except LogbookError as e:
        print(f"auth:      FAIL  {e}")
        failed += 1

    missing: list[str] = []
    for name in sorted(ENGINES):
        path = shutil.which(name)
        print(f"{name:10} {path or 'NOT ON PATH'}")
        if path is None:
            missing.append(name)
    if missing:
        print(f"note: missing CLIs (ok if unused): {', '.join(missing)}")
    return 1 if failed else 0
