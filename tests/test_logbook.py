from __future__ import annotations

import json

from dint.logbook import ChatLog, format_content
from dint.types import Chat


class MemoryLogbook:
    def __init__(self) -> None:
        self.posted: list[dict] = []

    def post_message(self, message: str) -> dict:
        msg_id = f"m{len(self.posted) + 1}"
        self.posted.append({"id": msg_id, "content": message})
        return {"id": msg_id}

    def get_messages(self, search: str | None = None, *, start: int = 0, length: int = 100) -> list[dict]:
        items = list(self.posted)
        if search:
            items = [m for m in items if search in m["content"]]
        return items[start : start + length]


def test_format_content_uses_flat_tags_and_json() -> None:
    content = format_content(
        "dint",
        ["chat", "turn", "claude", "user", "chat-abc"],
        {
            "chatId": "abc",
            "engine": "claude",
            "role": "user",
            "cwd": r"C:\proj",
            "externalSessionId": "ses-1",
            "text": "hello",
            "ts": "2026-08-20T16:42:00Z",
        },
    )
    assert content.startswith("@dint #chat #turn #claude #user #chat-abc ")
    payload = json.loads(content[content.index("{") :])
    assert payload["externalSessionId"] == "ses-1"


def test_header_and_turns_are_new_messages() -> None:
    ledger = MemoryLogbook()
    store = ChatLog(ledger, project="dint")
    chat = Chat(chat_id="abc123abc123", engine="claude", cwd=r"C:\proj")
    store.post(chat, "header")
    chat.external_session_id = "ses-1"
    store.post(chat, "session")
    store.post(chat, "user", "hi")
    store.post(chat, "assistant", "hello")

    assert len(ledger.posted) == 4
    assert all("parentId" not in m for m in ledger.posted)
    assert "#turn" not in ledger.posted[0]["content"]
    assert "#turn" in ledger.posted[2]["content"] and "#user" in ledger.posted[2]["content"]

    loaded = store.get_chat("abc123abc123")
    assert loaded is not None
    assert loaded.external_session_id == "ses-1"
    turns = store.list_turns("abc123abc123")
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[0]["text"] == "hi"
