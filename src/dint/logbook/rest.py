"""Logbook over REST `/api/messages` — same data as MCP PostMessage / GetMessages."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class LogbookError(RuntimeError):
    pass


class RestLogbook:
    def __init__(self, url: str, api_key: str = "") -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key

    def post_message(self, message: str) -> dict:
        data = self._request("POST", "/api/messages", {"content": message, "userId": "dint"})
        if not isinstance(data, dict):
            raise LogbookError(f"unexpected post response: {data!r}")
        return data

    def get_messages(
        self,
        search: str | None = None,
        *,
        start: int = 0,
        length: int = 100,
    ) -> list[dict]:
        q = {"start": str(start), "length": str(length)}
        if search:
            q["search"] = search
        data = self._request("GET", "/api/messages?" + urllib.parse.urlencode(q))
        if isinstance(data, list):
            return [m for m in data if isinstance(m, dict)]
        if isinstance(data, dict):
            return list(data.get("messages") or data.get("items") or [])
        return []

    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        raw_body = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.url + path, data=raw_body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8")
                return json.loads(text) if text else None
        except urllib.error.HTTPError as e:
            raise LogbookError(f"HTTP {e.code} {method} {path}: {e.read().decode('utf-8', 'replace')}") from e
        except urllib.error.URLError as e:
            raise LogbookError(
                f"Cannot reach logbook at {self.url} ({e.reason}). "
                "Start logbook-server — https://logbook.codicent.ai"
            ) from e
