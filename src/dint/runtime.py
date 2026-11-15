"""Start logbook-server and dint serve if they are not already up."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from dint.envfile import home_dir, home_env_path, write_env
from dint.logbook.rest import LogbookError, RestLogbook

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
    path = home_env_path()
    if not path.is_file():
        _write_home_env()
        os.environ.setdefault("DINT_ENV_FILE", str(path))
    ensure_webhook_secret()


def webhook_secret() -> str:
    return (
        os.environ.get("LOGBOOK_WEBHOOK_SECRET") or os.environ.get("DINT_WEBHOOK_SECRET") or ""
    ).strip()


def ensure_webhook_secret() -> str:
    """dint serve only runs signed webhooks; make sure there is a secret to sign with."""
    secret = webhook_secret()
    if secret:
        return secret
    secret = secrets.token_urlsafe(32)
    os.environ["LOGBOOK_WEBHOOK_SECRET"] = secret
    write_env(home_env_path(), {"LOGBOOK_WEBHOOK_SECRET": secret})
    return secret


def ensure_logbook() -> None:
    """Reuse a reachable logbook we can auth to; otherwise start one for this machine.

    One logbook-server process is one project/database. dint does not start a
    server per repo: chats already store cwd. If :5100 is someone else's
    logbook (401), pick the next free port and persist it in ~/.dint/.env.
    """
    health = logbook_health()
    if health is not None and _auth_ok():
        running = str(health.get("project") or "")
        ours = os.environ.get("LOGBOOK_PROJECT", "dint")
        if running and running != ours:
            _note(f"using logbook project={running} at {logbook_url()}")
        return
    if health is not None:
        _note(f"{logbook_url()} is another logbook; starting dint's own")
        _relocate_logbook_port()
    elif not can_bind(logbook_host(), logbook_port()):
        _relocate_logbook_port()
    _spawn_logbook()
    ensure_logbook_auth(logbook_health())


def _spawn_logbook() -> None:
    _ensure_own_api_key()
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
    env["LOGBOOK_WEBHOOK_SECRET"] = ensure_webhook_secret()
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


def _auth_ok() -> bool:
    rest = RestLogbook(logbook_url(), os.environ.get("LOGBOOK_API_KEY", "").strip())
    try:
        rest.get_messages(length=1)
        return True
    except LogbookError as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            return False
        raise RuntimeError(str(e)) from e


def ensure_logbook_auth(health: dict | None = None) -> None:
    if _auth_ok():
        return
    env_file = os.environ.get("DINT_ENV_FILE") or str(home_env_path())
    running = ""
    if health and health.get("project"):
        running = f" Server project is {health['project']}."
    raise RuntimeError(
        f"logbook at {logbook_url()} rejected dint's API key.{running}\n"
        f"dint read LOGBOOK_API_KEY from {env_file}."
    )


def _relocate_logbook_port() -> None:
    host = logbook_host()
    start = logbook_port() + 1
    port = find_free_port(host, start)
    os.environ["LOGBOOK_URL"] = f"{logbook_scheme()}://{host}:{port}"
    _write_home_env()
    _note(f"logbook {os.environ['LOGBOOK_URL']}")


def find_free_port(host: str, start: int, *, count: int = 30) -> int:
    bind_host = "127.0.0.1" if host in {"localhost", "127.0.0.1", "::1"} else host
    for port in range(start, start + count):
        if probe(f"http://{bind_host}:{port}/health"):
            continue
        if can_bind(bind_host, port):
            return port
    raise RuntimeError(f"no free port in {start}-{start + count - 1} for logbook-server")


def can_bind(host: str, port: int) -> bool:
    bind_host = "127.0.0.1" if host in {"localhost", ""} else host
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((bind_host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _ensure_own_api_key() -> None:
    if os.environ.get("LOGBOOK_API_KEY", "").strip():
        return
    os.environ["LOGBOOK_API_KEY"] = secrets.token_urlsafe(16)
    _write_home_env()


def _write_home_env() -> None:
    values = {
        "LOGBOOK_URL": os.environ.get("LOGBOOK_URL", "http://127.0.0.1:5100"),
        "LOGBOOK_PROJECT": os.environ.get("LOGBOOK_PROJECT", "dint"),
    }
    key = os.environ.get("LOGBOOK_API_KEY", "").strip()
    if key:
        values["LOGBOOK_API_KEY"] = key
    values["DINT_JOBS_PORT"] = str(jobs_port())
    write_env(home_env_path(), values)


def ensure_serve() -> None:
    if os.environ.get("DINT_ROLE") == "serve":
        return
    health = serve_health()
    if health is not None:
        _warn_stale_serve(health)
        return
    if not can_bind(jobs_host(), jobs_port()):
        port = find_free_port(jobs_host(), jobs_port() + 1)
        os.environ["DINT_JOBS_PORT"] = str(port)
        _write_home_env()
        _note(f"dint serve {jobs_url()}")
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


def serve_health() -> dict | None:
    return _get_json(jobs_url() + "/health")


def _warn_stale_serve(health: dict) -> None:
    from dint import __version__

    running = str(health.get("version") or "")
    if running == __version__:
        return
    pid = health.get("pid")
    who = f"dint serve {running or '< 0.2.0'}" + (f" (pid {pid})" if pid else "")
    _note(f"{who} is still running; this is dint {__version__}. Stop it and re-run dint.")


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


def logbook_scheme() -> str:
    return urlparse(logbook_url()).scheme or "http"


def logbook_host() -> str:
    return urlparse(logbook_url()).hostname or "127.0.0.1"


def logbook_port() -> int:
    return urlparse(logbook_url()).port or 5100


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


def logbook_health(*, timeout: float = 1.5) -> dict | None:
    return _get_json(logbook_url() + "/health", timeout=timeout)


def _get_json(url: str, *, timeout: float = 1.5) -> dict | None:
    try:
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {"raw": data}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
        return None


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
