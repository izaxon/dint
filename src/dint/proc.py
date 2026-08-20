from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from typing import IO


class CancelledError(RuntimeError):
    """Raised when a running engine turn is cancelled."""


class RunningProcess:
    def __init__(self, proc: subprocess.Popen[str]) -> None:
        self.proc = proc
        self._lock = threading.Lock()
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
        _kill(self.proc)

    def lines(self) -> Iterator[str]:
        stdout = self.proc.stdout
        if stdout is None:
            return
        try:
            for line in stdout:
                if self.cancelled:
                    raise CancelledError("turn cancelled")
                yield line.rstrip("\r\n")
        finally:
            try:
                stdout.close()
            except OSError:
                pass
            code = self.proc.poll()
            if code is None:
                if self.cancelled:
                    _kill(self.proc)
                else:
                    try:
                        self.proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        _kill(self.proc)
            if self.cancelled:
                raise CancelledError("turn cancelled")


def spawn(
    argv: list[str],
    *,
    cwd: str,
    extra_env: dict[str, str] | None = None,
) -> RunningProcess:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["NO_COLOR"] = "1"
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        bufsize=1,
    )
    _drain_stderr(proc.stderr)
    return RunningProcess(proc)


def _drain_stderr(stream: IO[str] | None) -> None:
    if stream is None:
        return

    def _read() -> None:
        try:
            stream.read()
        except OSError:
            pass

    threading.Thread(target=_read, daemon=True).start()


def _kill(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
