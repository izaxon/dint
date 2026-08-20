from __future__ import annotations

import argparse
import json
import os
import sys

from dint.router import Router


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dint", description="Chat router over Claude Code / Codex. Logbook is the ledger.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start")
    s.add_argument("engine", choices=["claude", "codex", "grok"])
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

    args = p.parse_args(argv)
    router = Router()

    try:
        if args.cmd == "start":
            print(router.start_chat(args.engine, os.path.abspath(args.cwd)))
            return 0
        if args.cmd == "send":
            try:
                for event in router.send(args.chat_id, " ".join(args.prompt)):
                    _print(event)
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
    except (KeyError, NotImplementedError, RuntimeError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 1


def _print(event: object) -> None:
    kind = getattr(event, "type", None)
    text = getattr(event, "text", "") or ""
    if kind == "text" and text:
        print(text, flush=True)
    elif kind == "tool":
        print(f"[tool] {getattr(event, 'tool', None) or text}", flush=True)
    elif kind == "error":
        print(f"[error] {text}", file=sys.stderr, flush=True)
    elif kind == "done":
        sid = getattr(event, "session_id", None)
        print(f"[done]{f' session={sid}' if sid else ''}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
