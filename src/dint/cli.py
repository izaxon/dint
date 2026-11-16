from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from collections.abc import Callable

from dint import __version__
from dint.envfile import load_dotenv
from dint.router import ENGINES, Router
from dint.runtime import ensure_runtime, jobs_url, logbook_url, pick_engine, serve_running

COMMANDS = {
    "start",
    "send",
    "cancel",
    "list",
    "last",
    "show",
    "chats",
    "status",
    "job",
    "serve",
}

CHAT_REF_HELP = "chat id, a unique prefix of one, or 'last' (default)"


def main(argv: list[str] | None = None) -> int:
    _utf8_when_redirected()
    env_path = load_dotenv()
    if env_path:
        os.environ.setdefault("DINT_ENV_FILE", str(env_path))

    argv = list(sys.argv[1:] if argv is None else argv)
    if _is_chat_argv(argv):
        return run_chat_argv(argv)

    p = argparse.ArgumentParser(
        prog="dint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Chat router over Claude, Codex, Grok, and Copilot. "
            "No command opens a chat in this folder (starts logbook + serve)."
        ),
        epilog=(
            "examples:\n"
            "  dint                              chat REPL  (/help inside)\n"
            "  dint grok \"Summarize this\"        one-shot\n"
            "  dint job grok \"Summarize this\"    enqueue a #job\n"
            "  dint job --wait grok \"...\"        enqueue and print the reply\n"
            "  dint last                         latest reply, in full"
        ),
    )
    p.add_argument("--version", action="version", version=f"dint {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="start a chat and print its id")
    s.add_argument("engine", choices=sorted(ENGINES))
    s.add_argument("cwd", nargs="?", default=".")

    s = sub.add_parser("send", help="send a prompt to a chat")
    s.add_argument("chat_id", help=CHAT_REF_HELP)
    s.add_argument("prompt", nargs="+")

    s = sub.add_parser("cancel", help="cancel a turn running in this process")
    s.add_argument("chat_id", help=CHAT_REF_HELP)

    s = sub.add_parser("list", help="turns in a chat (one line each unless --full)")
    s.add_argument("chat_id", nargs="?", default="last", help=CHAT_REF_HELP)
    s.add_argument("--full", action="store_true", help="print every turn in full")
    s.add_argument("--json", action="store_true", help="print turns as JSON")

    s = sub.add_parser("last", help="the latest reply in a chat, in full")
    s.add_argument("chat_id", nargs="?", default="last", help=CHAT_REF_HELP)
    s.add_argument("--json", action="store_true", help="print the reply turn as JSON")

    s = sub.add_parser("show", help="chat metadata as JSON")
    s.add_argument("chat_id", nargs="?", default="last", help=CHAT_REF_HELP)

    s = sub.add_parser("chats", help="list conversations in Logbook")
    s.add_argument("--json", action="store_true", help="print chats as JSON")
    sub.add_parser("status", help="check Logbook and engine CLIs")

    s = sub.add_parser("job", help="enqueue a #job in Logbook (dint serve runs it)")
    s.add_argument("engine", choices=sorted(ENGINES))
    s.add_argument("args", nargs="+", help="optional cwd, then prompt")
    s.add_argument("--wait", action="store_true", help="follow the job and print its reply")
    s.add_argument(
        "--timeout", type=float, default=0, metavar="SECONDS", help="with --wait: give up after this long"
    )

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
        if args.cmd == "chats":
            chats = router.list_chats()
            if args.json:
                _print_json(chats)
                return 0
            for c in chats:
                preview = (c.get("preview") or "").replace("\n", " ")[:60]
                print(
                    f"{c.get('ts')}\t{c.get('chatId')}\t{c.get('engine')}\t{preview}"
                )
            return 0
        if args.cmd == "job":
            from dint.jobs import post_job, wait_for_job_chat

            cwd, prompt = _job_cwd_prompt(args.args)
            job_id = post_job(router, args.engine, prompt, cwd)
            print(f"job\t{job_id}", file=sys.stderr if args.wait else sys.stdout)
            chat_id = wait_for_job_chat(router, job_id)
            if not chat_id:
                print("waiting for dint serve... try: dint chats", file=sys.stderr)
                return 2
            if args.wait:
                print(f"chat\t{chat_id}", file=sys.stderr)
                return follow_chat(router, chat_id, timeout=args.timeout)
            print(f"chat\t{chat_id}")
            print(f"dint last {chat_id}")
            return 0
        chat_id = resolve_chat(router, args.chat_id)
        if args.cmd == "send":
            return _send(router, chat_id, " ".join(args.prompt))
        if args.cmd == "cancel":
            router.cancel(chat_id)
            return 0
        if args.cmd == "list":
            _print_turns(router.list_turns(chat_id), full=args.full, as_json=args.json)
            return 0
        if args.cmd == "last":
            return print_last_reply(router.list_turns(chat_id), chat_id, as_json=args.json)
        if args.cmd == "show":
            chat = router.get_chat(chat_id)
            _print_json({
                "chatId": chat.chat_id,
                "engine": chat.engine,
                "cwd": chat.cwd,
                "externalSessionId": chat.external_session_id,
            })
            return 0
    except (KeyError, NotImplementedError, RuntimeError, ValueError) as e:
        print(_message(e), file=sys.stderr)
        return 1
    return 1


def resolve_chat(router: Router, ref: str | None) -> str:
    """Accept a full chat id, a unique prefix of one, or 'last' / '-' for the newest chat."""
    ref = (ref or "last").strip()
    chats = router.list_chats()
    if ref.lower() in {"last", "-"}:
        if not chats:
            raise RuntimeError("no chats yet")
        return str(chats[0]["chatId"])
    ids = [str(c.get("chatId")) for c in chats]
    if ref in ids:
        return ref
    matches = [i for i in ids if i.startswith(ref)]
    if len(matches) > 1:
        raise ValueError(f"{ref} matches several chats: {', '.join(matches[:5])}")
    if matches:
        return matches[0]
    return ref  # older than the recent window; the store looks it up by id


def _turn_result(turns: list[dict]) -> tuple[dict | None, dict | None, bool]:
    """(bot, error, done) for the latest user turn. done once a bot or error row exists."""
    bot = error = None
    for t in turns:
        role = t.get("role")
        if role == "user":
            bot = error = None
        elif role == "bot":
            bot = t
        elif role == "error":
            error = t
    return bot, error, bool(bot or error)


def print_last_reply(turns: list[dict], chat_id: str, *, as_json: bool = False) -> int:
    bot, error, done = _turn_result(turns)
    if not done:
        print(f"no reply yet in {chat_id}    dint list {chat_id}", file=sys.stderr)
        return 2
    if as_json:
        _print_json({"chatId": chat_id, "bot": bot, "error": error})
    else:
        if bot:
            print(bot.get("text") or "")
        if error:
            print(f"[error] {error.get('text') or 'error'}", file=sys.stderr)
    return 1 if error else 0


def follow_chat(
    router: Router,
    chat_id: str,
    *,
    timeout: float = 0,
    interval: float = 1.0,
    sleep=time.sleep,
) -> int:
    """Poll a chat someone else is running (dint serve) until its turn ends."""
    deadline = time.monotonic() + timeout if timeout else None
    seen: set[str] = set()
    try:
        while True:
            turns = router.list_turns(chat_id)
            for t in turns:
                key = str(t.get("id") or "")
                if t.get("role") == "tool" and key and key not in seen:
                    seen.add(key)
                    print(f"[tool] {t.get('text') or 'tool'}", file=sys.stderr, flush=True)
            if _turn_result(turns)[2]:
                return print_last_reply(turns, chat_id)
            if deadline is not None and time.monotonic() >= deadline:
                print(f"still running    dint last {chat_id}", file=sys.stderr)
                return 2
            sleep(interval)
    except KeyboardInterrupt:
        print(f"stopped waiting; the job keeps running    dint last {chat_id}", file=sys.stderr)
        return 130


def _print_turns(turns: list[dict], *, full: bool, as_json: bool) -> None:
    if as_json:
        _print_json(turns)
        return
    for i, t in enumerate(turns):
        text = t.get("text") or ""
        if full:
            if i:
                print()
            print(f"--- {t.get('role')}  {t.get('ts')}")
            print(text)
        else:
            print(f"{t.get('ts')}\t{t.get('role')}\t{text.replace(chr(10), ' ')[:120]}")


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _message(e: BaseException) -> str:
    if isinstance(e, KeyError) and e.args:
        return str(e.args[0])
    return str(e)


def _utf8_when_redirected() -> None:
    # Replies are UTF-8; a Windows pipe or file would otherwise get the ANSI code page.
    for stream in (sys.stdout, sys.stderr):
        try:
            encoding = (stream.encoding or "").lower().replace("-", "")
            if encoding != "utf8" and not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


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
    had = any(_cwd_key(str(c.get("cwd") or "")) == _cwd_key(cwd) for c in router.list_chats())
    engine, chat_id = _resume_or_start(router, engine, cwd)
    if prompt:
        print(f"{engine}  {cwd}  {chat_id}", file=sys.stderr)
        return _send(router, chat_id, prompt)
    return _repl(router, engine, cwd, chat_id, fresh=not had)


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


def _repl(router: Router, engine: str, cwd: str, chat_id: str, *, fresh: bool) -> int:
    _print_banner(engine, cwd, chat_id, fresh=fresh)
    while True:
        try:
            text = read_prompt(f"{engine}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return 0
        if not text:
            continue
        send_text = text
        if text.startswith("//"):
            send_text = text[1:]
        elif text.startswith("/") and "\n" not in text:
            action, engine, chat_id = _slash(router, engine, cwd, chat_id, text)
            if action == "quit":
                return 0
            if action != "send":
                continue
        code = _send(router, chat_id, send_text, quiet_done=True)
        if code != 0:
            return code


def read_prompt(
    prompt: str,
    *,
    read: Callable[[str], str] | None = None,
    pending: Callable[[], bool] | None = None,
) -> str:
    """One REPL prompt, which may span lines.

    A pasted block arrives as several lines at once; whatever is already waiting
    in the terminal joins this prompt instead of becoming its own turn. A typed
    line ending in a backslash continues on the next one (pasted text is kept
    as is, backslashes included).
    """
    read = read or input
    pending = pending or _input_pending
    lines = [read(prompt)]
    while True:
        if pending():
            lines.append(read(""))
        elif lines[-1].endswith("\\"):
            lines[-1] = lines[-1][:-1]
            lines.append(read("... "))
        else:
            return "\n".join(lines)


def _input_pending(timeout: float = 0.05) -> bool:
    """True when more typed or pasted input is already waiting on the terminal."""
    try:
        if not os.isatty(sys.stdin.fileno()):
            return False
        if sys.platform == "win32":
            import msvcrt

            deadline = time.monotonic() + timeout
            while True:
                if msvcrt.kbhit():
                    return True
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.005)
        import select

        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        return bool(ready)
    except (OSError, ValueError, ImportError):
        return False


def _print_banner(engine: str, cwd: str, chat_id: str, *, fresh: bool) -> None:
    print(f"{engine}    {cwd}    chat {chat_id}", file=sys.stderr)
    print(f"logbook {logbook_url()}    serve {jobs_url()}", file=sys.stderr)
    if fresh:
        print(
            f'no chats here yet — type a prompt, or:  dint job {engine} "Summarize this repo"',
            file=sys.stderr,
        )
    print("/engine  /job  /chats  /new  /help    quit: Ctrl-C or /quit", file=sys.stderr)


def _print_help(engine: str) -> None:
    print(
        "slash:\n"
        "  /engine              CLIs on PATH\n"
        "  /engine claude       switch engine (new or resume in this folder)\n"
        "  /job [engine] text   enqueue a #job (dint serve runs it)\n"
        "  /chats               chats in this folder\n"
        "  /status              logbook + engines\n"
        "  /new                 new chat, same engine\n"
        "  /help  /quit\n"
        "  /login  (and other unknown /lines) go to the engine\n"
        "  //help               send /help to the engine\n"
        "multi-line: paste it, or end a line with \\ to continue\n"
        "same from another shell:\n"
        f'  dint job --wait {engine} "Summarize this repo"\n'
        "  dint last            latest reply in full\n"
        "  dint chats\n"
        "  dint status",
        file=sys.stderr,
    )


def _slash(
    router: Router, engine: str, cwd: str, chat_id: str, text: str
) -> tuple[str, str, str]:
    parts = text.split()
    cmd = parts[0].lower()
    args = parts[1:]
    if cmd in {"/quit", "/exit", "/q"}:
        return "quit", engine, chat_id
    if cmd == "/help":
        _print_help(engine)
        return "ok", engine, chat_id
    if cmd == "/new":
        chat_id = router.start_chat(engine, cwd)
        print(f"{engine}    {cwd}    chat {chat_id}", file=sys.stderr)
        return "ok", engine, chat_id
    if cmd == "/engine":
        if not args:
            _print_engines(engine)
            return "ok", engine, chat_id
        name = args[0].lower()
        if name not in ENGINES:
            print(f"unknown engine: {name}  ({', '.join(sorted(ENGINES))})", file=sys.stderr)
            return "ok", engine, chat_id
        if shutil.which(name) is None:
            print(f"{name} is not on PATH", file=sys.stderr)
            return "ok", engine, chat_id
        engine, chat_id = _resume_or_start(router, name, cwd)
        print(f"{engine}    {cwd}    chat {chat_id}", file=sys.stderr)
        return "ok", engine, chat_id
    if cmd == "/chats":
        _print_chats(router, cwd, chat_id)
        return "ok", engine, chat_id
    if cmd == "/status":
        from dint.status import run_status

        run_status()
        return "ok", engine, chat_id
    if cmd == "/job":
        _slash_job(router, engine, cwd, args)
        return "ok", engine, chat_id
    return "send", engine, chat_id


def _slash_job(router: Router, engine: str, cwd: str, args: list[str]) -> None:
    from dint.jobs import post_job, wait_for_job_chat

    if not args:
        print(f'/job [engine] prompt    e.g.  /job {engine} Summarize this repo', file=sys.stderr)
        return
    job_engine = engine
    prompt_parts = args
    if args[0].lower() in ENGINES:
        job_engine = args[0].lower()
        prompt_parts = args[1:]
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        print("/job: prompt required", file=sys.stderr)
        return
    job_id = post_job(router, job_engine, prompt, cwd)
    print(f"job\t{job_id}", file=sys.stderr)
    new_chat = wait_for_job_chat(router, job_id)
    if new_chat:
        print(f"chat\t{new_chat}    dint last {new_chat}", file=sys.stderr)
    else:
        print("waiting for dint serve... try: /chats", file=sys.stderr)


def _print_engines(current: str) -> None:
    for name in sorted(ENGINES):
        path = shutil.which(name)
        mark = "*" if name == current else " "
        print(f"{mark} {name:8} {path or 'NOT ON PATH'}", file=sys.stderr)


def _print_chats(router: Router, cwd: str, current: str) -> None:
    key = _cwd_key(cwd)
    rows = [c for c in router.list_chats() if _cwd_key(str(c.get("cwd") or "")) == key]
    if not rows:
        print("no chats in this folder    dint chats", file=sys.stderr)
        return
    for c in rows:
        mark = "*" if c.get("chatId") == current else " "
        preview = (c.get("preview") or "").replace("\n", " ")[:50]
        print(
            f"{mark} {c.get('ts')}\t{c.get('chatId')}\t{c.get('engine')}\t{preview}",
            file=sys.stderr,
        )


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
