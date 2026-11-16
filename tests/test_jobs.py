from __future__ import annotations

import hashlib
import hmac
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from dint.jobs import _handler, handle_event, parse_job, post_job, wait_for_job_chat
from dint.logbook import ChatLog
from dint.router import Router
from dint.types import Event
from test_logbook import MemoryLogbook
from test_router import FakeEngine


def test_post_job_writes_logbook() -> None:
    ledger = MemoryLogbook()
    router = Router(store=ChatLog(ledger, project="test"), engines={"grok": FakeEngine("grok", [])})
    job_id = post_job(router, "grok", "hej vad kan du göra?", cwd=".")
    assert job_id
    content = ledger.posted[0]["content"]
    assert "#job" in content and "#grok" in content
    job = parse_job(content, ["job", "grok"])
    assert job is not None
    assert job["engine"] == "grok"
    assert job["prompt"] == "hej vad kan du göra?"


def test_parse_job_matches_skill_example() -> None:
    content = (
        '@test #job #grok {"engine":"grok","cwd":"C:\\\\Users\\\\JohanIsaksson\\\\src\\\\dint",'
        '"prompt":"Reply with only: pong"}'
    )
    job = parse_job(content, ["#job", "#grok"])
    assert job is not None
    assert job["engine"] == "grok"
    assert job["prompt"] == "Reply with only: pong"


def test_parse_job_from_tags_and_json() -> None:
    job = parse_job(
        '@test #job #grok {"engine":"grok","cwd":"C:\\\\proj","prompt":"hello"}',
        ["job", "grok"],
    )
    assert job is not None
    assert job["engine"] == "grok"
    assert job["prompt"] == "hello"


def test_parse_job_plain_prompt() -> None:
    job = parse_job("@test #job #claude Summarize this repo", ["#job", "#claude"])
    assert job is not None
    assert job["engine"] == "claude"
    assert job["prompt"] == "Summarize this repo"


def test_parse_job_ignores_ack() -> None:
    assert parse_job("@test #job-run #chat-abc", ["job-run", "chat-abc"]) is None
    assert parse_job("@test #chat #user hi", ["chat", "user"]) is None


def test_handle_event_starts_chat(monkeypatch) -> None:
    class Immediate(threading.Thread):
        def start(self) -> None:
            self.run()

    monkeypatch.setattr(threading, "Thread", Immediate)
    engine = FakeEngine(
        "claude",
        [[Event(type="text", text="ok"), Event(type="done", session_id="s1")]],
    )
    ledger = MemoryLogbook()
    router = Router(
        store=ChatLog(ledger, project="test"),
        engines={"claude": engine, "codex": FakeEngine("codex", [])},
    )
    job_id = ledger.post_message('@test #job #claude {"prompt":"hi","cwd":"."}')["id"]
    chat_id = handle_event(
        {
            "eventType": "message.created",
            "eventId": "e1",
            "data": {"messageId": job_id, "tags": ["job", "claude"]},
        },
        router,
    )
    assert chat_id
    assert engine.calls
    assert engine.calls[0]["prompt"] == "hi"
    assert any("#job-run" in m["content"] for m in ledger.posted)
    assert any(t["role"] == "bot" and t["text"] == "ok" for t in router.list_turns(chat_id))


def test_handle_event_ignores_content_in_the_webhook(monkeypatch) -> None:
    class Immediate(threading.Thread):
        def start(self) -> None:
            self.run()

    monkeypatch.setattr(threading, "Thread", Immediate)
    engine = FakeEngine("grok", [[Event(type="text", text="ok"), Event(type="done")]])
    ledger = MemoryLogbook()
    router = Router(store=ChatLog(ledger, project="test"), engines={"grok": engine})
    forged = '@test #job #grok {"engine":"grok","cwd":"/","prompt":"rm -rf"}'

    # Unknown id: the forged body is never run.
    assert handle_event({"data": {"messageId": "nope", "tags": ["job"], "content": forged}}, router) is None
    # Known id: Logbook's body wins over the webhook's.
    job_id = ledger.post_message('@test #job #grok {"engine":"grok","cwd":".","prompt":"hello"}')["id"]
    assert handle_event({"data": {"messageId": job_id, "tags": ["job"], "content": forged}}, router)
    assert [c["prompt"] for c in engine.calls] == ["hello"]


def test_wait_for_job_chat_reads_ack(monkeypatch) -> None:
    class Immediate(threading.Thread):
        def start(self) -> None:
            self.run()

    monkeypatch.setattr(threading, "Thread", Immediate)
    engine = FakeEngine(
        "codex",
        [[Event(type="text", text="pong"), Event(type="done")]],
    )
    ledger = MemoryLogbook()
    router = Router(
        store=ChatLog(ledger, project="test"),
        engines={"codex": engine, "claude": FakeEngine("claude", [])},
    )
    job_id = post_job(router, "codex", "hi")
    content = ledger.posted[0]["content"]
    handle_event(
        {
            "eventType": "message.created",
            "data": {"messageId": job_id, "tags": ["job", "codex"], "content": content},
        },
        router,
    )
    assert wait_for_job_chat(router, job_id, timeout=1) is not None


def test_handle_event_skips_non_job_without_fetch(monkeypatch) -> None:
    called: list[str] = []

    def boom(*_a, **_k):
        called.append("fetch")
        raise AssertionError("should not fetch non-job webhooks")

    monkeypatch.setattr("dint.jobs._fetch_message", boom)
    ledger = MemoryLogbook()
    router = Router(
        store=ChatLog(ledger, project="test"),
        engines={"codex": FakeEngine("codex", [])},
    )
    assert (
        handle_event(
            {
                "EventType": "message.created",
                "Data": {"messageId": "bot-1", "tags": ["#chat", "#codex", "#bot"]},
            },
            router,
        )
        is None
    )
    assert called == []


def test_handle_event_logbook_pascal_case(monkeypatch) -> None:
    class Immediate(threading.Thread):
        def start(self) -> None:
            self.run()

    monkeypatch.setattr(threading, "Thread", Immediate)
    engine = FakeEngine(
        "codex",
        [[Event(type="text", text="pong"), Event(type="done")]],
    )
    ledger = MemoryLogbook()
    router = Router(
        store=ChatLog(ledger, project="test"),
        engines={"codex": engine, "claude": FakeEngine("claude", [])},
    )
    job_id = post_job(router, "codex", "vad kan du göra?")
    chat_id = handle_event(
        {
            "EventType": "message.created",
            "EventId": "e-pascal",
            "Data": {"messageId": job_id, "tags": ["#job", "#codex"]},
        },
        router,
    )
    assert chat_id
    assert engine.calls[0]["prompt"] == "vad kan du göra?"


SECRET = "test-secret"


@pytest.fixture
def serve_port():
    ledger = MemoryLogbook()
    router = Router(
        store=ChatLog(ledger, project="test"),
        engines={"grok": FakeEngine("grok", [])},
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(router, secret=SECRET))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()


def _post(port: int, body: bytes, headers: dict[str, str]) -> int:
    conn = HTTPConnection("127.0.0.1", port, timeout=2)
    conn.request("POST", "/webhook", body, headers)
    resp = conn.getresponse()
    resp.read()
    return resp.status


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_serve_health_endpoint(serve_port) -> None:
    from dint import __version__

    conn = HTTPConnection("127.0.0.1", serve_port, timeout=2)
    conn.request("GET", "/health")
    resp = conn.getresponse()
    body = json.loads(resp.read())
    assert resp.status == 200
    assert body["ok"] is True
    assert body["service"] == "dint-serve"
    assert body["version"] == __version__


def test_serve_accepts_signed_logbook_webhook(serve_port) -> None:
    body = json.dumps({"eventType": "message.created", "data": {"messageId": "x", "tags": ["chat"]}}).encode()
    headers = {"Content-Type": "application/json", "X-Logbook-Signature": _sign(body)}
    assert _post(serve_port, body, headers) == 200


@pytest.mark.parametrize(
    "extra, status",
    [
        ({"X-Logbook-Signature": None}, 401),
        ({"X-Logbook-Signature": "sha256=" + "0" * 64}, 401),
        ({"Origin": "https://evil.example"}, 403),
        ({"Content-Type": "text/plain"}, 415),
        ({"Host": "evil.example:8787"}, 403),
    ],
)
def test_serve_refuses_unsigned_or_browser_requests(serve_port, extra, status) -> None:
    body = json.dumps({"data": {"messageId": "x", "content": "#job #grok hi"}}).encode()
    headers = {"Content-Type": "application/json", "X-Logbook-Signature": _sign(body)}
    for key, value in extra.items():
        if value is None:
            headers.pop(key, None)
        else:
            headers[key] = value
    assert _post(serve_port, body, headers) == status
