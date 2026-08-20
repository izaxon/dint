from __future__ import annotations

import uuid
from collections.abc import Iterator

from dint.engines import default_engines
from dint.logbook import ChatLog
from dint.types import Chat, Engine, Event

ENGINES = {"claude", "codex", "copilot", "grok"}
STUBS = {"copilot", "grok"}


class Router:
    """Fan-out: Engine CLIs do the work, ChatLog is the ledger."""

    def __init__(
        self,
        store: ChatLog | None = None,
        engines: dict[str, Engine] | None = None,
    ) -> None:
        self.store = store or ChatLog()
        self.engines = engines or default_engines()
        self._chats: dict[str, Chat] = {}
        self._active: dict[str, Engine] = {}

    def start_chat(self, engine: str, cwd: str) -> str:
        engine = engine.strip().lower()
        if engine not in ENGINES:
            raise ValueError(f"unknown engine: {engine}")
        chat = Chat(uuid.uuid4().hex[:12], engine, cwd)
        self.store.post(chat, "header")
        self._chats[chat.chat_id] = chat
        return chat.chat_id

    def send(self, chat_id: str, prompt: str) -> Iterator[Event]:
        if chat_id in self._active:
            raise RuntimeError(f"chat {chat_id} already has a running turn")
        chat = self._load(chat_id)
        if chat.engine in STUBS:
            raise NotImplementedError(f"{chat.engine} adapter is a stub")
        engine = self.engines[chat.engine]
        self.store.post(chat, "user", prompt)
        self._active[chat_id] = engine
        assistant: list[str] = []
        error: str | None = None
        saw_session = bool(chat.external_session_id)
        try:
            for event in engine.send(prompt, cwd=chat.cwd, session_id=chat.external_session_id):
                if event.session_id and event.session_id != chat.external_session_id:
                    chat.external_session_id = event.session_id
                    self._chats[chat_id] = chat
                    if not saw_session:
                        self.store.post(chat, "session")
                        saw_session = True
                if event.type == "text" and event.text:
                    assistant.append(event.text)
                elif event.type == "tool":
                    self.store.post(chat, "tool", event.text or event.tool or "tool")
                elif event.type == "error":
                    error = event.text or "error"
                yield event
        finally:
            self._active.pop(chat_id, None)
            text = "\n".join(assistant).strip()
            if text:
                self.store.post(chat, "assistant", text)
            if error:
                self.store.post(chat, "error", error)

    def cancel(self, chat_id: str) -> None:
        engine = self._active.get(chat_id)
        if engine is not None:
            engine.cancel()
        else:
            self._load(chat_id)

    def list_turns(self, chat_id: str) -> list[dict]:
        return self.store.list_turns(chat_id)

    def get_chat(self, chat_id: str) -> Chat:
        return self._load(chat_id)

    def _load(self, chat_id: str) -> Chat:
        chat = self.store.get_chat(chat_id) or self._chats.get(chat_id)
        if chat is None:
            raise KeyError(f"unknown chat: {chat_id}")
        self._chats[chat_id] = chat
        return chat
