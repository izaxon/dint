"""Codicent Logbook ledger (append-only).

Talks to a local logbook-server (https://logbook.codicent.ai) over REST
(`/api/messages`) or MCP (`/mcp` tools `post_message` / `get_messages`).
Does not use hosted Codicent or the `codicentpy` package.

This layer only posts new messages. It never supplies parentId / hide.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from dint.types import Chat, Role, TurnRecord

DEFAULT_URL = os.environ.get("LOGBOOK_URL", "http://127.0.0.1:5100")
DEFAULT_KEY = os.environ.get("LOGBOOK_API_KEY", "")
DEFAULT_PROJECT = os.environ.get("LOGBOOK_PROJECT", "dint")
DEFAULT_USER = os.environ.get("LOGBOOK_USER", "dint")
DEFAULT_TRANSPORT = os.environ.get("LOGBOOK_TRANSPORT", "rest")


class LogbookError(RuntimeError):
    pass


class LogbookStore:
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        *,
        project: str | None = None,
        user_id: str | None = None,
        transport: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.url = (url or DEFAULT_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else DEFAULT_KEY
        self.project = project or DEFAULT_PROJECT
        self.user_id = user_id or DEFAULT_USER
        self.transport = (transport or DEFAULT_TRANSPORT).lower()
        if self.transport not in {"rest", "mcp"}:
            raise ValueError(f"unknown logbook transport: {self.transport}")
        self._client = client or (
            _McpClient(self.url, self.api_key)
            if self.transport == "mcp"
            else _RestClient(self.url, self.api_key)
        )

    def post_header(self, chat: Chat) -> str:
        return self._post(
            chat,
            role="header",
            text="",
            extra_tags=[],
        )

    def post_session(self, chat: Chat) -> str:
        sid = chat.external_session_id or ""
        return self._post(
            chat,
            role="session",
            text=sid,
            extra_tags=[],
        )

    def post_turn(
        self,
        chat: Chat,
        *,
        role: Role,
        text: str,
    ) -> str:
        extra = ["turn", role]
        return self._post(chat, role=role, text=text, extra_tags=extra)

    def get_chat(self, chat_id: str) -> Chat | None:
        records = self.list_messages(chat_id)
        if not records:
            return None
        header = next((r for r in records if r.role == "header"), records[0])
        session_id = None
        for rec in records:
            if rec.external_session_id:
                session_id = rec.external_session_id
        return Chat(
            chat_id=header.chat_id,
            engine=header.engine,
            cwd=header.cwd,
            external_session_id=session_id,
        )

    def list_messages(self, chat_id: str, *, length: int = 100) -> list[TurnRecord]:
        raw = self._client.get_messages(search=f"#chat-{chat_id}", start=0, length=length)
        records: list[TurnRecord] = []
        for item in raw:
            rec = _record_from_message(item)
            if rec and rec.chat_id == chat_id:
                records.append(rec)
        records.sort(key=lambda r: r.ts)
        return records

    def list_turns(self, chat_id: str) -> list[TurnRecord]:
        return [r for r in self.list_messages(chat_id) if "turn" in r.tags]

    def _post(
        self,
        chat: Chat,
        *,
        role: Role,
        text: str,
        extra_tags: list[str],
    ) -> str:
        payload = {
            "chatId": chat.chat_id,
            "engine": chat.engine,
            "role": role,
            "cwd": chat.cwd,
            "externalSessionId": chat.external_session_id,
            "text": text,
            "ts": _now(),
        }
        tags = ["chat", chat.engine, f"chat-{chat.chat_id}", *extra_tags]
        content = _format_content(self.project, tags, payload)
        result = self._client.post_message(content, user_id=self.user_id)
        return _message_id(result)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _format_content(project: str, tags: list[str], payload: dict[str, Any]) -> str:
    parts: list[str] = []
    if project:
        parts.append("@" + project.lstrip("@"))
    seen: set[str] = set()
    for tag in tags:
        t = tag.strip().lstrip("#")
        if not t or t in seen:
            continue
        seen.add(t)
        parts.append("#" + t)
    parts.append(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return " ".join(parts)


def _record_from_message(item: dict[str, Any]) -> TurnRecord | None:
    content = item.get("content") or item.get("Content") or item.get("message") or ""
    if isinstance(content, dict):
        content = content.get("content") or content.get("text") or ""
    payload = _extract_json(str(content))
    if not payload or "chatId" not in payload:
        return None
    tags = _tags_from(item, str(content))
    return TurnRecord(
        chat_id=str(payload["chatId"]),
        engine=str(payload.get("engine") or ""),
        role=payload.get("role") or "assistant",  # type: ignore[arg-type]
        cwd=str(payload.get("cwd") or ""),
        external_session_id=payload.get("externalSessionId") or None,
        text=str(payload.get("text") or ""),
        ts=str(payload.get("ts") or ""),
        tags=tags,
        message_id=_message_id(item) or None,
    )


def _extract_json(content: str) -> dict[str, Any] | None:
    i = content.find("{")
    if i < 0:
        return None
    try:
        data = json.loads(content[i:])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _tags_from(item: dict[str, Any], content: str) -> list[str]:
    raw = item.get("tags") or item.get("Tags") or []
    tags: list[str] = []
    if isinstance(raw, list):
        for t in raw:
            if isinstance(t, str):
                tags.append(t.lstrip("#"))
            elif isinstance(t, dict) and t.get("name"):
                tags.append(str(t["name"]).lstrip("#"))
    if not tags:
        for part in content.split():
            if part.startswith("#"):
                tags.append(part[1:])
    return tags


def _message_id(result: Any) -> str:
    if isinstance(result, str):
        return result
    if not isinstance(result, dict):
        return ""
    for key in ("id", "Id", "messageId", "message_id"):
        value = result.get(key)
        if value:
            return str(value)
    inner = result.get("result")
    if isinstance(inner, dict):
        return _message_id(inner)
    return ""


class _RestClient:
    def __init__(self, url: str, api_key: str) -> None:
        self.url = url
        self.api_key = api_key

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        full = self.url + path
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(full, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise LogbookError(f"HTTP {e.code} {method} {path}: {detail}") from e
        except urllib.error.URLError as e:
            raise LogbookError(
                f"Cannot reach logbook at {self.url} ({e.reason}). "
                "Start logbook-server (https://logbook.codicent.ai) or set LOGBOOK_URL."
            ) from e

    def post_message(self, content: str, user_id: str) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/api/messages",
            {"content": content, "userId": user_id},
        )
        if not isinstance(result, dict):
            raise LogbookError(f"unexpected post response: {result!r}")
        return result

    def get_messages(self, *, search: str | None, start: int, length: int) -> list[dict[str, Any]]:
        q = {"start": str(start), "length": str(length)}
        if search:
            q["search"] = search
        result = self._request("GET", "/api/messages?" + urllib.parse.urlencode(q))
        if isinstance(result, list):
            return [m for m in result if isinstance(m, dict)]
        if not isinstance(result, dict):
            return []
        messages = result.get("messages") or result.get("items") or []
        return [m for m in messages if isinstance(m, dict)]


class _McpClient:
    """Streamable HTTP MCP client for logbook-server `/mcp`."""

    def __init__(self, url: str, api_key: str) -> None:
        parsed = urllib.parse.urlparse(url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.path = "/mcp"
        self.api_key = api_key
        self.session_id: str | None = None
        self._rid = 0
        self._ready = False

    def post_message(self, content: str, user_id: str) -> dict[str, Any]:
        result = self.tool("post_message", {"message": content, "userId": user_id})
        return result if isinstance(result, dict) else {"id": str(result)}

    def get_messages(self, *, search: str | None, start: int, length: int) -> list[dict[str, Any]]:
        args: dict[str, Any] = {"start": start, "length": length}
        if search:
            args["search"] = search
        result = self.tool("get_messages", args)
        if isinstance(result, list):
            return [m for m in result if isinstance(m, dict)]
        if not isinstance(result, dict):
            return []
        messages = result.get("messages") or result.get("items") or []
        return [m for m in messages if isinstance(m, dict)]

    def tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self._ensure()
        data = self._call("tools/call", {"name": name, "arguments": arguments})
        result = (data or {}).get("result") or {}
        content = result.get("content")
        if content and isinstance(content, list):
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            joined = "\n".join(texts)
            try:
                return json.loads(joined)
            except json.JSONDecodeError:
                return joined if len(texts) == 1 else texts
        return result

    def _ensure(self) -> None:
        if self._ready:
            return
        self._call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "dint", "version": "0.1.0"},
            },
        )
        try:
            self._call("notifications/initialized", {}, notify=True)
        except LogbookError:
            pass
        self._ready = True

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _call(self, method: str, params: dict[str, Any] | None = None, *, notify: bool = False) -> Any:
        import http.client

        self._rid += 1
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notify:
            body["id"] = self._rid
        if params is not None:
            body["params"] = params
        payload = json.dumps(body).encode("utf-8")
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
            conn.request("POST", self.path, payload, self._headers())
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8")
            sid = resp.getheader("Mcp-Session-Id")
            if sid:
                self.session_id = sid
        except OSError as e:
            raise LogbookError(
                f"Cannot reach logbook MCP at {self.host}:{self.port}{self.path} ({e}). "
                "Start logbook-server (https://logbook.codicent.ai) or set LOGBOOK_URL."
            ) from e
        if notify:
            return {"status": resp.status}
        if resp.status >= 400:
            raise LogbookError(f"MCP HTTP {resp.status}: {raw[:400]}")
        data = _parse_mcp(raw)
        if isinstance(data, dict) and data.get("error"):
            raise LogbookError(f"MCP error: {data['error']}")
        return data


def _parse_mcp(raw: str) -> Any:
    if "data:" in raw:
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
    return json.loads(raw) if raw.strip() else None
