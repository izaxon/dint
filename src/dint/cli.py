from __future__ import annotations

import argparse
import json
import os
import sys

from dint.envfile import load_dotenv
from dint.router import Router


def main(argv: list[str] | None = None) -> int:
    env_path = load_dotenv()
    if env_path:
        os.environ.setdefault("DINT_ENV_FILE", str(env_path))

    p = argparse.ArgumentParser(
        prog="dint",
        description="Chat router over Claude Code, Codex, Grok, and Copilot. Logbook is the ledger.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start")
    s.add_argument("engine", choices=["claude", "codex", "grok", "copilot"])
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
    s.add_argument("engine", choices=["claude", "codex", "grok", "copilot"])
    s.add_argument("args", nargs="+", help="optional cwd, then prompt")

    s = sub.add_parser("serve", help="run #job webhooks from Logbook")
    s.add_argument("--host", default=os.environ.get("DINT_JOBS_HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("DINT_JOBS_PORT", "8787")))
    s.add_argument("--no-register", action="store_true", help="do not call Logbook register_webhook")

    args = p.parse_args(argv)

    if args.cmd == "status":
        from dint.status import run_status

        return run_status()

    router = Router()
    try:
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
        if args.cmd == "serve":
            from dint.jobs import serve

            serve(args.host, args.port, register=not args.no_register)
            return 0
    except (KeyError, NotImplementedError, RuntimeError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 1


def _job_cwd_prompt(args: list[str]) -> tuple[str, str]:
    if len(args) >= 2 and os.path.isdir(args[0]):
        return os.path.abspath(args[0]), " ".join(args[1:])
    return os.path.abspath("."), " ".join(args)


class EventPrinter:
    """Stream token chunks inline; only start a new line for tools/done/errors."""

    def __init__(self) -> None:
        self._mid_line = False

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
        elif kind == "done":
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
