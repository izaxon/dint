from __future__ import annotations

import json

from dint.store.logbook import LogbookStore, _format_content
from dint.types import Chat


class MemoryClient:
    def __init__(self) -> None:
        self.posted: list[dict] = []

    def post_message(self, content: str, user_id: str) -> dict:
        msg_id = f"m{len(self.posted) + 1}"
        self.posted.append({"id": msg_id, "content": content, "userId": user_id})
        return {"id": msg_id, "success": True}

    def get_messages(self, *, search: str | None, start: int, length: int) -> list[dict]:
        items = list(self.posted)
        if search:
            items = [m for m in items if search in m["content"]]
        return items[start : start + length]


def test_format_content_uses_flat_tags_and_json() -> None:
    content = _format_content(
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
    assert payload["chatId"] == "abc"
    assert payload["externalSessionId"] == "ses-1"


def test_header_and_turns_are_new_messages() -> None:
    client = MemoryClient()
    store = LogbookStore(client=client, project="dint")
    chat = Chat(chat_id="abc123abc123", engine="claude", cwd=r"C:\proj")
    store.post_header(chat)
    chat.external_session_id = "ses-1"
    store.post_session(chat)
    store.post_turn(chat, role="user", text="hi")
    store.post_turn(chat, role="assistant", text="hello")

    assert len(client.posted) == 4
    assert all("parentId" not in m for m in client.posted)
    header = client.posted[0]["content"]
    assert "#chat-abc123abc123" in header
    assert "#turn" not in header
    user = client.posted[2]["content"]
    assert "#turn" in user and "#user" in user and "#claude" in user

    loaded = store.get_chat("abc123abc123")
    assert loaded is not None
    assert loaded.external_session_id == "ses-1"
    turns = store.list_turns("abc123abc123")
    assert [t.role for t in turns] == ["user", "assistant"]
    assert turns[0].text == "hi"
