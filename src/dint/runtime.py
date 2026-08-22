"""Start logbook-server and dint serve if they are not already up."""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from dint.envfile import home_dir, home_env_path, write_env

LOGBOOK_INSTALL = "https://logbook.codicent.ai"


def ensure_runtime(*, serve: bool = True) -> None:
    ensure_defaults()
    ensure_logbook()
    if serve:
        ensure_serve()


def ensure_defaults() -> None:
    home_dir().mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("LOGBOOK_URL", "http://127.0.0.1:5100")
    os.environ.setdefault("LOGBOOK_PROJECT", "dint")
    if not os.environ.get("LOGBOOK_API_KEY", "").strip():
        os.environ["LOGBOOK_API_KEY"] = secrets.token_urlsafe(16)
    path = home_env_path()
    if not path.is_file():
        write_env(
            path,
            {
                "LOGBOOK_URL": os.environ["LOGBOOK_URL"],
                "LOGBOOK_API_KEY": os.environ["LOGBOOK_API_KEY"],
                "LOGBOOK_PROJECT": os.environ["LOGBOOK_PROJECT"],
            },
        )
        os.environ.setdefault("DINT_ENV_FILE", str(path))


def ensure_logbook() -> None:
    if probe(logbook_url() + "/health"):
        return
    binary = shutil.which("logbook-server")
    if not binary:
        raise RuntimeError(
            "logbook-server is not on PATH and nothing is listening on "
            f"{logbook_url()}. Install it:\n  {logbook_install_cmd()}\n"
            f"then re-run dint — {LOGBOOK_INSTALL}"
        )
    env = os.environ.copy()
    parsed = urlparse(logbook_url())
    env["LOGBOOK_PROJECT"] = os.environ.get("LOGBOOK_PROJECT", "dint")
    env["LOGBOOK_API_KEY"] = os.environ.get("LOGBOOK_API_KEY", "")
    env["LOGBOOK_PORT"] = str(parsed.port or 5100)
    env["LOGBOOK_WEBHOOK_URL"] = jobs_url() + "/webhook"
    pid = spawn_detached(
        [binary],
        cwd=str(home_dir()),
        env=env,
        log_path=home_dir() / "logbook.log",
    )
    _note(f"started logbook-server pid={pid}")
    if not wait_for(logbook_url() + "/health"):
        raise RuntimeError(
            f"logbook-server did not become ready at {logbook_url()}. "
            f"See {home_dir() / 'logbook.log'}"
        )


def ensure_serve() -> None:
    if os.environ.get("DINT_ROLE") == "serve":
        return
    if probe(jobs_url() + "/health"):
        return
    env = os.environ.copy()
    env["DINT_ROLE"] = "serve"
    pid = spawn_detached(
        [
            sys.executable,
            "-m",
            "dint",
            "serve",
            "--host",
            jobs_host(),
            "--port",
            str(jobs_port()),
        ],
        cwd=str(home_dir()),
        env=env,
        log_path=home_dir() / "serve.log",
    )
    _note(f"started dint serve pid={pid}")
    if not wait_for(jobs_url() + "/health"):
        raise RuntimeError(
            f"dint serve did not become ready at {jobs_url()}. "
            f"See {home_dir() / 'serve.log'}"
        )


def serve_running() -> bool:
    return probe(jobs_url() + "/health")


def pick_engine() -> str | None:
    preferred = os.environ.get("DINT_ENGINE", "").strip().lower()
    order = ["grok", "claude", "copilot", "codex"]
    if preferred:
        order = [preferred] + [e for e in order if e != preferred]
    for name in order:
        if shutil.which(name):
            return name
    return None


def logbook_url() -> str:
    return os.environ.get("LOGBOOK_URL", "http://127.0.0.1:5100").rstrip("/")


def jobs_host() -> str:
    return os.environ.get("DINT_JOBS_HOST", "127.0.0.1")


def jobs_port() -> int:
    return int(os.environ.get("DINT_JOBS_PORT", "8787"))


def jobs_url() -> str:
    return f"http://{jobs_host()}:{jobs_port()}"


def logbook_install_cmd() -> str:
    if sys.platform == "win32":
        return "iwr https://logbook.codicent.ai/install.ps1 | iex"
    return "curl -fsSL https://logbook.codicent.ai/install.sh | bash"


def probe(url: str, timeout: float = 1.5) -> bool:
    try:
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False


def wait_for(url: str, *, timeout: float = 12) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if probe(url):
            return True
        time.sleep(0.2)
    return False


def spawn_detached(
    argv: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    log_path: Path,
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "a", encoding="utf-8")
    kwargs: dict = {
        "cwd": cwd,
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": log,
        "stderr": log,
        "close_fds": True,
    }
    if sys.platform == "win32":
        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        base = subprocess.CREATE_NEW_PROCESS_GROUP | no_window
        # 0x01000000 = CREATE_BREAKAWAY_FROM_JOB so serve outlives the parent shell
        kwargs["creationflags"] = base | 0x01000000
        try:
            proc = subprocess.Popen(argv, **kwargs)
        except OSError:
            kwargs["creationflags"] = base
            proc = subprocess.Popen(argv, **kwargs)
        return int(proc.pid)
    kwargs["start_new_session"] = True
    proc = subprocess.Popen(argv, **kwargs)
    log.close()
    return int(proc.pid)


def _note(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
