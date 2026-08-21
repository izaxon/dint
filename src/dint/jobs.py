"""Webhook-driven jobs: Logbook #job -> start_chat + send."""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from dint.logbook import extract_json, format_content
from dint.logbook.mcp import McpLogbook
from dint.router import ENGINES, Router

JOB_TAG = "job"
ACK_TAG = "job-run"


def post_job(router: Router, engine: str, prompt: str, cwd: str = ".") -> str:
    engine = engine.strip().lower()
    if engine not in ENGINES:
        raise ValueError(f"unknown engine: {engine}")
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("prompt is required")
    job = {
        "engine": engine,
        "cwd": os.path.abspath(cwd),
        "prompt": prompt,
    }
    content = format_content(router.store.project, [JOB_TAG, engine], job)
    result = router.store.logbook.post_message(content)
    return str(result.get("id") or result.get("Id") or "")


def parse_job(content: str, tags: list[str] | None = None) -> dict[str, str] | None:
    names = {_norm_tag(t) for t in (tags or [])}
    if not names:
        names = {part[1:].lower() for part in content.split() if part.startswith("#")}
    if JOB_TAG not in names or ACK_TAG in names:
        return None
    payload = extract_json(content) or {}
    engine = str(payload.get("engine") or "").strip().lower()
    if not engine:
        engine = next((e for e in ENGINES if e in names), "")
    prompt = str(payload.get("prompt") or payload.get("text") or "").strip()
    if not prompt:
        prompt = _strip_meta(content).strip()
    cwd = str(payload.get("cwd") or os.getcwd())
    if engine not in ENGINES or not prompt:
        return None
    return {"engine": engine, "cwd": os.path.abspath(cwd), "prompt": prompt}


def handle_event(payload: dict[str, Any], router: Router) -> str | None:
    if payload.get("eventType") not in {None, "message.created"}:
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    tags = data.get("tags") or []
    names = {_norm_tag(t) for t in tags}
    if JOB_TAG not in names or ACK_TAG in names:
        return None
    message_id = str(data.get("messageId") or data.get("id") or "")
    content = str(data.get("content") or data.get("Content") or "")
    if not content and message_id:
        row = _fetch_message(router, message_id)
        if row:
            content = str(row.get("content") or row.get("Content") or "")
            tags = row.get("tags") or tags
    job = parse_job(content, tags)
    if job is None:
        return None
    chat_id = router.start_chat(job["engine"], job["cwd"])
    _ack(router, message_id, chat_id, job)
    threading.Thread(
        target=_run_send,
        args=(router, chat_id, job["prompt"]),
        daemon=True,
        name=f"dint-job-{chat_id}",
    ).start()
    return chat_id


def serve(host: str = "127.0.0.1", port: int = 8787, *, register: bool = True) -> None:
    router = Router()
    httpd = ThreadingHTTPServer((host, port), _handler(router))
    hook = f"http://{host}:{port}/webhook"
    print(f"dint jobs listening on {hook}", flush=True)
    if register:
        _try_register(hook)
    else:
        print(f"set LOGBOOK_WEBHOOK_URL={hook} on logbook-server", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stopped", flush=True)


def _handler(router: Router) -> type[BaseHTTPRequestHandler]:
    seen: set[str] = set()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path not in {"/", "/webhook", "/jobs"}:
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            if not _signature_ok(raw, dict(self.headers)):
                self.send_error(401, "bad signature")
                return
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                self.send_error(400, "invalid json")
                return
            event_id = str(payload.get("eventId") or payload.get("data", {}).get("messageId") or "")
            if event_id and event_id in seen:
                self._ok({"ok": True, "duplicate": True})
                return
            if event_id:
                seen.add(event_id)
                if len(seen) > 500:
                    seen.clear()
            try:
                chat_id = handle_event(payload, router)
            except Exception as e:
                print(f"job error: {e}", file=sys.stderr, flush=True)
                self.send_error(500, str(e)[:200])
                return
            self._ok({"ok": True, "chatId": chat_id})

        def _ok(self, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _run_send(router: Router, chat_id: str, prompt: str) -> None:
    try:
        print(f"job chat {chat_id} starting", flush=True)
        for _ in router.send(chat_id, prompt):
            pass
        print(f"job chat {chat_id} done", flush=True)
    except Exception as e:
        print(f"job chat {chat_id} failed: {e}", file=sys.stderr, flush=True)


def _ack(router: Router, job_id: str, chat_id: str, job: dict[str, str]) -> None:
    content = format_content(
        router.store.project,
        [ACK_TAG, job["engine"], f"chat-{chat_id}"],
        {"chatId": chat_id, "engine": job["engine"], "cwd": job["cwd"], "jobId": job_id},
    )
    try:
        router.store.logbook.post_message(content, parent_id=job_id or None)
    except Exception as e:
        print(f"job ack failed: {e}", file=sys.stderr, flush=True)


def _fetch_message(router: Router, message_id: str) -> dict[str, Any] | None:
    logbook = router.store.logbook
    getter = getattr(logbook, "get_message", None)
    if callable(getter):
        row = getter(message_id)
        if isinstance(row, dict):
            return row
    rows = logbook.get_messages(message_id, length=20)
    for row in rows:
        if str(row.get("id") or row.get("Id") or "") == message_id:
            return row
    return rows[0] if rows else None


def _try_register(hook: str) -> None:
    url = os.environ.get("LOGBOOK_URL", "http://127.0.0.1:5100")
    key = os.environ.get("LOGBOOK_API_KEY", "")
    secret = os.environ.get("LOGBOOK_WEBHOOK_SECRET") or os.environ.get("DINT_WEBHOOK_SECRET") or ""
    try:
        mcp = McpLogbook(url, key)
        mcp.register_webhook(hook, secret=secret, event_types="message.created")
        print(f"registered webhook at logbook: {hook}", flush=True)
    except Exception as e:
        print(
            f"could not register webhook ({e}). "
            f"Start logbook-server with LOGBOOK_WEBHOOK_URL={hook}",
            file=sys.stderr,
            flush=True,
        )


def _signature_ok(body: str, headers: dict[str, str]) -> bool:
    import hmac
    import hashlib

    secret = os.environ.get("LOGBOOK_WEBHOOK_SECRET") or os.environ.get("DINT_WEBHOOK_SECRET") or ""
    if not secret:
        return True
    got = ""
    for key, value in headers.items():
        if key.lower() == "x-logbook-signature":
            got = value
            break
    if not got:
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, got)


def _norm_tag(tag: str) -> str:
    return str(tag).strip().lstrip("#").lower()


def _strip_meta(content: str) -> str:
    parts: list[str] = []
    for token in content.split():
        if token.startswith("#") or token.startswith("@"):
            continue
        if token.startswith("{"):
            break
        parts.append(token)
    return " ".join(parts)
