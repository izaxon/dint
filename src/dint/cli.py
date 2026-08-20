from __future__ import annotations

import argparse
import json
import os
import sys

from dint.router import Router
from dint.store.logbook import LogbookStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dint",
        description="Enqueue multi-turn agent jobs. Claude Code / Codex do the work; Logbook is the ledger.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="start_chat(engine, cwd) -> chat_id")
    p_start.add_argument("engine", choices=["claude", "codex", "copilot", "grok"])
    p_start.add_argument("cwd", nargs="?", default=".")
    p_start.add_argument("--json", action="store_true")

    p_send = sub.add_parser("send", help="send(chat_id, prompt) -> stream events")
    p_send.add_argument("chat_id")
    p_send.add_argument("prompt", nargs="+")
    p_send.add_argument("--json", action="store_true")

    p_cancel = sub.add_parser("cancel", help="cancel(chat_id)")
    p_cancel.add_argument("chat_id")

    p_list = sub.add_parser("list", help="list turns for #chat-<id>")
    p_list.add_argument("chat_id")
    p_list.add_argument("--json", action="store_true")

    p_show = sub.add_parser("show", help="show chat header / session id")
    p_show.add_argument("chat_id")

    args = parser.parse_args(argv)
    router = Router(store=LogbookStore())

    if args.cmd == "start":
        cwd = os.path.abspath(args.cwd)
        chat_id = router.start_chat(args.engine, cwd)
        if args.json:
            print(json.dumps({"chatId": chat_id, "engine": args.engine, "cwd": cwd}))
        else:
            print(chat_id)
        return 0

    if args.cmd == "send":
        prompt = " ".join(args.prompt)
        try:
            for event in router.send(args.chat_id, prompt):
                _print_event(event, as_json=args.json)
        except KeyboardInterrupt:
            router.cancel(args.chat_id)
            print("cancelled", file=sys.stderr)
            return 130
        except (KeyError, NotImplementedError, RuntimeError, ValueError) as e:
            print(str(e), file=sys.stderr)
            return 1
        return 0

    if args.cmd == "cancel":
        try:
            router.cancel(args.chat_id)
        except KeyError as e:
            print(str(e), file=sys.stderr)
            return 1
        return 0

    if args.cmd == "list":
        try:
            turns = router.list_turns(args.chat_id)
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(turns, indent=2, ensure_ascii=False))
        else:
            if not turns:
                print(f"no turns for #chat-{args.chat_id}")
                return 0
            for t in turns:
                role = t.get("role") or "?"
                text = (t.get("text") or "").replace("\n", " ")
                if len(text) > 120:
                    text = text[:117] + "..."
                print(f"{t.get('ts')}\t{role}\t{text}")
        return 0

    if args.cmd == "show":
        try:
            chat = router.get_chat(args.chat_id)
        except KeyError as e:
            print(str(e), file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "chatId": chat.chat_id,
                    "engine": chat.engine,
                    "cwd": chat.cwd,
                    "externalSessionId": chat.external_session_id,
                },
                indent=2,
            )
        )
        return 0

    return 1


def _print_event(event: object, *, as_json: bool) -> None:
    payload = {
        "type": getattr(event, "type", None),
        "text": getattr(event, "text", ""),
        "session_id": getattr(event, "session_id", None),
        "tool": getattr(event, "tool", None),
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return
    kind = payload["type"]
    if kind == "text" and payload["text"]:
        print(payload["text"], end="", flush=True)
        if not str(payload["text"]).endswith("\n"):
            print(flush=True)
    elif kind == "tool":
        print(f"[tool] {payload['tool'] or payload['text']}", flush=True)
    elif kind == "need_approval":
        print(f"[need_approval] {payload['text']}", flush=True)
    elif kind == "error":
        print(f"[error] {payload['text']}", file=sys.stderr, flush=True)
    elif kind == "done":
        sid = payload["session_id"]
        extra = f" session={sid}" if sid else ""
        print(f"[done]{extra}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
