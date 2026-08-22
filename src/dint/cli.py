from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from dint import __version__
from dint.envfile import load_dotenv
from dint.router import ENGINES, Router
from dint.runtime import ensure_runtime, pick_engine, serve_running

COMMANDS = {
    "start",
    "send",
    "cancel",
    "list",
    "show",
    "chats",
    "status",
    "job",
    "serve",
}


def main(argv: list[str] | None = None) -> int:
    env_path = load_dotenv()
    if env_path:
        os.environ.setdefault("DINT_ENV_FILE", str(env_path))

    argv = list(sys.argv[1:] if argv is None else argv)
    if _is_chat_argv(argv):
        return run_chat_argv(argv)

    p = argparse.ArgumentParser(
        prog="dint",
        description=(
            "Chat router over Claude, Codex, Grok, and Copilot. "
            "Run `dint` or `dint grok` in a folder to start logbook + serve and chat."
        ),
    )
    p.add_argument("--version", action="version", version=f"dint {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start")
    s.add_argument("engine", choices=sorted(ENGINES))
    s.add_argument("cwd", nargs="?", default=".")

    s = sub.add_parser("send")
    s.add_argument("chat_id")
    s.add_argument("prompt", nargs="+")

    s = sub.add_parser("cancel")
    s.add_argument("chat_id")

    s = sub.add_parser("list")
    s.add_argument("chat_id")

    s = sub.add_parser("show")
    s.add_argument("chat_id")

    sub.add_parser("chats", help="list conversations in Logbook")
    sub.add_parser("status", help="check Logbook and engine CLIs")

    s = sub.add_parser("job", help="enqueue a #job in Logbook (dint serve runs it)")
    s.add_argument("engine", choices=sorted(ENGINES))
    s.add_argument("args", nargs="+", help="optional cwd, then prompt")

    s = sub.add_parser("serve", help="run #job webhooks from Logbook")
    s.add_argument("--host", default=os.environ.get("DINT_JOBS_HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("DINT_JOBS_PORT", "8787")))
    s.add_argument("--no-register", action="store_true", help="do not call Logbook register_webhook")

    args = p.parse_args(argv)

    if args.cmd == "status":
        from dint.status import run_status

        return run_status()

    try:
        if args.cmd == "serve":
            return _run_serve(args.host, args.port, register=not args.no_register)
        ensure_runtime(serve=args.cmd == "job")
        router = Router()
        if args.cmd == "start":
            print(router.start_chat(args.engine, os.path.abspath(args.cwd)))
            return 0
        if args.cmd == "send":
            try:
                printer = EventPrinter()
                for event in router.send(args.chat_id, " ".join(args.prompt)):
                    printer.emit(event)
                printer.finish()
            except KeyboardInterrupt:
                router.cancel(args.chat_id)
                print("cancelled", file=sys.stderr)
                return 130
            return 0
        if args.cmd == "cancel":
            router.cancel(args.chat_id)
            return 0
        if args.cmd == "list":
            for t in router.list_turns(args.chat_id):
                text = (t.get("text") or "").replace("\n", " ")
                print(f"{t.get('ts')}\t{t.get('role')}\t{text[:120]}")
            return 0
        if args.cmd == "show":
            chat = router.get_chat(args.chat_id)
            print(json.dumps({
                "chatId": chat.chat_id,
                "engine": chat.engine,
                "cwd": chat.cwd,
                "externalSessionId": chat.external_session_id,
            }, indent=2))
            return 0
        if args.cmd == "chats":
            for c in router.list_chats():
                preview = (c.get("preview") or "").replace("\n", " ")[:60]
                print(
                    f"{c.get('ts')}\t{c.get('chatId')}\t{c.get('engine')}\t{preview}"
                )
            return 0
        if args.cmd == "job":
            from dint.jobs import post_job, wait_for_job_chat

            cwd, prompt = _job_cwd_prompt(args.args)
            job_id = post_job(router, args.engine, prompt, cwd)
            print(f"job\t{job_id}")
            chat_id = wait_for_job_chat(router, job_id)
            if chat_id:
                print(f"chat\t{chat_id}")
                print(f"dint list {chat_id}")
            else:
                print("waiting for dint serve... try: dint chats", file=sys.stderr)
            return 0 if chat_id else 2
    except (KeyError, NotImplementedError, RuntimeError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 1


def _is_chat_argv(argv: list[str]) -> bool:
    if not argv:
        return True
    if argv[0].startswith("-"):
        return False
    return argv[0] not in COMMANDS


def run_chat_argv(argv: list[str]) -> int:
    engine = None
    rest = argv
    if argv and argv[0].lower() in ENGINES:
        engine = argv[0].lower()
        rest = argv[1:]
    prompt = " ".join(rest).strip() or None
    try:
        return run_chat(engine, prompt)
    except (KeyError, NotImplementedError, RuntimeError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1


def run_chat(engine: str | None, prompt: str | None) -> int:
    ensure_runtime(serve=True)
    cwd = os.path.abspath(".")
    if engine and shutil.which(engine) is None:
        raise RuntimeError(f"{engine} is not on PATH")
    if prompt is None and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip() or None
        if prompt is None:
            print("dint: pass a prompt, or run in a terminal", file=sys.stderr)
            return 2
    router = Router()
    engine, chat_id = _resume_or_start(router, engine, cwd)
    print(f"{engine}  {cwd}  {chat_id}", file=sys.stderr)
    if prompt:
        return _send(router, chat_id, prompt)
    return _repl(router, engine, cwd, chat_id)


def _resume_or_start(router: Router, engine: str | None, cwd: str) -> tuple[str, str]:
    key = _cwd_key(cwd)
    if engine is None:
        for row in router.list_chats():
            name = str(row.get("engine") or "").lower()
            if name not in ENGINES or shutil.which(name) is None:
                continue
            if _cwd_key(str(row.get("cwd") or "")) == key:
                return name, str(row["chatId"])
        engine = pick_engine()
        if not engine:
            raise RuntimeError(
                "no engine CLI on PATH. Install grok, claude, copilot, or codex."
            )
        return engine, router.start_chat(engine, cwd)
    for row in router.list_chats():
        if str(row.get("engine") or "").lower() != engine:
            continue
        if _cwd_key(str(row.get("cwd") or "")) == key:
            return engine, str(row["chatId"])
    return engine, router.start_chat(engine, cwd)


def _repl(router: Router, engine: str, cwd: str, chat_id: str) -> int:
    print("message, /new, /quit", file=sys.stderr)
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return 0
        text = line.strip()
        if not text:
            continue
        if text in {"/quit", "/exit", "/q"}:
            return 0
        if text == "/new":
            chat_id = router.start_chat(engine, cwd)
            print(f"{engine}  {cwd}  {chat_id}", file=sys.stderr)
            continue
        if text.startswith("/"):
            print("commands: /new /quit", file=sys.stderr)
            continue
        code = _send(router, chat_id, text, quiet_done=True)
        if code != 0:
            return code


def _send(router: Router, chat_id: str, prompt: str, *, quiet_done: bool = False) -> int:
    printer = EventPrinter(quiet_done=quiet_done)
    try:
        for event in router.send(chat_id, prompt):
            printer.emit(event)
        printer.finish()
    except KeyboardInterrupt:
        router.cancel(chat_id)
        print("cancelled", file=sys.stderr)
        return 130
    return 0


def _run_serve(host: str, port: int, *, register: bool) -> int:
    os.environ["DINT_JOBS_HOST"] = host
    os.environ["DINT_JOBS_PORT"] = str(port)
    ensure_runtime(serve=False)
    if serve_running():
        print(f"dint serve already running at http://{host}:{port}/webhook")
        return 0
    os.environ["DINT_ROLE"] = "serve"
    from dint.jobs import serve

    try:
        serve(host, port, register=register)
    except OSError as e:
        if serve_running():
            print(f"dint serve already running at http://{host}:{port}/webhook")
            return 0
        print(str(e), file=sys.stderr)
        return 1
    return 0


def _cwd_key(cwd: str) -> str:
    try:
        return os.path.normcase(os.path.abspath(cwd or "."))
    except (OSError, ValueError):
        return os.path.normcase(cwd or "")


def _job_cwd_prompt(args: list[str]) -> tuple[str, str]:
    if len(args) >= 2 and os.path.isdir(args[0]):
        return os.path.abspath(args[0]), " ".join(args[1:])
    return os.path.abspath("."), " ".join(args)


class EventPrinter:
    """Stream token chunks inline; only start a new line for tools/done/errors."""

    def __init__(self, *, quiet_done: bool = False) -> None:
        self._mid_line = False
        self.quiet_done = quiet_done

    def emit(self, event: object) -> None:
        kind = getattr(event, "type", None)
        text = getattr(event, "text", "") or ""
        if kind == "text" and text:
            sys.stdout.write(text)
            sys.stdout.flush()
            self._mid_line = not text.endswith("\n")
            return
        self._break()
        if kind == "tool":
            print(f"[tool] {getattr(event, 'tool', None) or text}", flush=True)
        elif kind == "error":
            print(f"[error] {text}", file=sys.stderr, flush=True)
        elif kind == "done" and not self.quiet_done:
            sid = getattr(event, "session_id", None)
            print(f"[done]{f' session={sid}' if sid else ''}", flush=True)

    def finish(self) -> None:
        self._break()

    def _break(self) -> None:
        if self._mid_line:
            print(flush=True)
            self._mid_line = False


if __name__ == "__main__":
    raise SystemExit(main())
