from __future__ import annotations

import uuid
from collections.abc import Iterator

from dint.engines import default_engines
from dint.store.logbook import LogbookStore
from dint.types import Chat, Engine, Event

LIVE_ENGINES = {"claude", "codex"}
STUB_ENGINES = {"copilot", "grok"}
KNOWN_ENGINES = LIVE_ENGINES | STUB_ENGINES


class Router:
    def __init__(
        self,
        store: LogbookStore | None = None,
        engines: dict[str, Engine] | None = None,
    ) -> None:
        self.store = store or LogbookStore()
        self.engines = engines or default_engines()
        self._chats: dict[str, Chat] = {}
        self._active: dict[str, Engine] = {}

    def start_chat(self, engine: str, cwd: str) -> str:
        engine = engine.strip().lower()
        if engine not in KNOWN_ENGINES:
            raise ValueError(f"unknown engine: {engine}")
        if engine not in self.engines:
            raise ValueError(f"engine not registered: {engine}")
        chat_id = uuid.uuid4().hex[:12]
        chat = Chat(chat_id=chat_id, engine=engine, cwd=cwd, external_session_id=None)
        self.store.post_header(chat)
        self._chats[chat_id] = chat
        return chat_id

    def send(self, chat_id: str, prompt: str) -> Iterator[Event]:
        if chat_id in self._active:
            raise RuntimeError(f"chat {chat_id} already has a running turn")
        chat = self._load(chat_id)
        engine = self.engines[chat.engine]
        if chat.engine in STUB_ENGINES:
            raise NotImplementedError(f"{chat.engine} adapter is a stub in v0")

        self.store.post_turn(chat, role="user", text=prompt)
        self._active[chat_id] = engine
        assistant_parts: list[str] = []
        posted_session = bool(chat.external_session_id)
        error_text: str | None = None
        try:
            for event in engine.send(
                prompt,
                cwd=chat.cwd,
                session_id=chat.external_session_id,
            ):
                if event.session_id and event.session_id != chat.external_session_id:
                    chat.external_session_id = event.session_id
                    self._chats[chat_id] = chat
                    if not posted_session:
                        self.store.post_session(chat)
                        posted_session = True
                if event.type == "text" and event.text:
                    assistant_parts.append(event.text)
                elif event.type == "tool":
                    self.store.post_turn(chat, role="tool", text=event.text or event.tool or "tool")
                elif event.type == "error":
                    error_text = event.text or "error"
                yield event
        finally:
            self._active.pop(chat_id, None)
            # Session id is already in the ledger if the engine emitted it.
            assistant = "\n".join(part for part in assistant_parts if part).strip()
            if assistant:
                self.store.post_turn(chat, role="assistant", text=assistant)
            if error_text:
                self.store.post_turn(chat, role="error", text=error_text)

    def cancel(self, chat_id: str) -> None:
        engine = self._active.get(chat_id)
        if engine is not None:
            engine.cancel()
            return
        # No live process: session id still lives in Logbook from prior turns.
        self._load(chat_id)

    def list_turns(self, chat_id: str) -> list[dict[str, str | None]]:
        records = self.store.list_turns(chat_id)
        return [
            {
                "chatId": r.chat_id,
                "engine": r.engine,
                "role": r.role,
                "cwd": r.cwd,
                "externalSessionId": r.external_session_id,
                "text": r.text,
                "ts": r.ts,
            }
            for r in records
        ]

    def get_chat(self, chat_id: str) -> Chat:
        return self._load(chat_id)

    def _load(self, chat_id: str) -> Chat:
        chat = self.store.get_chat(chat_id)
        if chat is None:
            cached = self._chats.get(chat_id)
            if cached is None:
                raise KeyError(f"unknown chat: {chat_id}")
            return cached
        self._chats[chat_id] = chat
        return chat
