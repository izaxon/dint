"""Logbook over MCP `/mcp` tools `post_message` and `get_messages`."""

from __future__ import annotations

import http.client
import json
import urllib.parse
from typing import Any

from dint.logbook.rest import LogbookError


class McpLogbook:
    def __init__(self, url: str, api_key: str = "") -> None:
        parsed = urllib.parse.urlparse(url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.path = "/mcp"
        self.api_key = api_key
        self.session_id: str | None = None
        self._rid = 0
        self._ready = False

    def post_message(self, message: str, parent_id: str | None = None) -> dict:
        args: dict[str, Any] = {"message": message, "userId": "dint"}
        if parent_id:
            args["parentId"] = parent_id
        result = self._tool("post_message", args)
        return result if isinstance(result, dict) else {"id": str(result)}

    def get_messages(
        self,
        search: str | None = None,
        *,
        start: int = 0,
        length: int = 100,
    ) -> list[dict]:
        args: dict[str, Any] = {"start": start, "length": length}
        if search:
            args["search"] = search
        result = self._tool("get_messages", args)
        if isinstance(result, list):
            return [m for m in result if isinstance(m, dict)]
        if isinstance(result, dict):
            return list(result.get("messages") or result.get("items") or [])
        return []

    def get_history(self, message_id: str) -> list[dict]:
        result = self._tool("get_message_history", {"messageId": message_id})
        if isinstance(result, list):
            return [m for m in result if isinstance(m, dict)]
        if isinstance(result, dict):
            return list(result.get("messages") or result.get("items") or [])
        return []

    def _tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self._ensure()
        data = self._call("tools/call", {"name": name, "arguments": arguments})
        result = (data or {}).get("result") or {}
        content = result.get("content")
        if isinstance(content, list):
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

    def _call(self, method: str, params: dict | None = None, *, notify: bool = False) -> Any:
        self._rid += 1
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notify:
            body["id"] = self._rid
        if params is not None:
            body["params"] = params
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
            conn.request("POST", self.path, json.dumps(body).encode("utf-8"), self._headers())
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8")
            sid = resp.getheader("Mcp-Session-Id")
            if sid:
                self.session_id = sid
        except OSError as e:
            raise LogbookError(
                f"Cannot reach logbook MCP at {self.host}:{self.port}{self.path} ({e}). "
                "Start logbook-server — https://logbook.codicent.ai"
            ) from e
        if notify:
            return {"status": resp.status}
        if resp.status >= 400:
            raise LogbookError(f"MCP HTTP {resp.status}: {raw[:400]}")
        data = _parse(raw)
        if isinstance(data, dict) and data.get("error"):
            raise LogbookError(f"MCP error: {data['error']}")
        return data


def _parse(raw: str) -> Any:
    if "data:" in raw:
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
    return json.loads(raw) if raw.strip() else None
