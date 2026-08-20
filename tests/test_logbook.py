from __future__ import annotations

import json

from dint.logbook import ChatLog, format_content
from dint.types import Chat


class MemoryLogbook:
    def __init__(self) -> None:
        self.posted: list[dict] = []

    def post_message(self, message: str, parent_id: str | None = None) -> dict:
        msg_id = f"m{len(self.posted) + 1}"
        self.posted.append({"id": msg_id, "content": message, "parentId": parent_id})
        return {"id": msg_id}

    def get_messages(self, search: str | None = None, *, start: int = 0, length: int = 100) -> list[dict]:
        items = list(self.posted)
        if search:
            items = [m for m in items if search in m["content"]]
        return items[start : start + length]

    def get_history(self, message_id: str) -> list[dict]:
        by_id = {m["id"]: m for m in self.posted}
        root = message_id
        seen: set[str] = set()
        while root in by_id and by_id[root].get("parentId") and root not in seen:
            seen.add(root)
            root = by_id[root]["parentId"]
        out: list[dict] = []
        for m in self.posted:
            cur = m["id"]
            hops = 0
            while cur and hops < 50:
                if cur == root:
                    out.append(m)
                    break
                cur = (by_id.get(cur) or {}).get("parentId")
                hops += 1
        return out


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


def test_parent_id_chains_user_and_bot() -> None:
    ledger = MemoryLogbook()
    store = ChatLog(ledger, project="dint")
    chat = Chat(chat_id="abc123abc123", engine="claude", cwd=r"C:\proj")
    header_id = store.post(chat, "header")
    chat.external_session_id = "ses-1"
    store.post(chat, "session")
    user_id = store.post(chat, "user", "hi")
    bot_id = store.post(chat, "bot", "hello")

    assert header_id == "m1"
    assert ledger.posted[0]["parentId"] is None
    assert ledger.posted[1]["parentId"] == header_id
    assert ledger.posted[2]["parentId"] == "m2"
    assert ledger.posted[3]["parentId"] == user_id
    assert "#user" in ledger.posted[2]["content"]
    assert "#bot" in ledger.posted[3]["content"]
    assert "#turn" not in ledger.posted[0]["content"]

    loaded = store.get_chat("abc123abc123")
    assert loaded is not None
    assert loaded.external_session_id == "ses-1"
    assert loaded.header_id == header_id
    assert loaded.tail_id == bot_id
    hist = store.list_messages("abc123abc123")
    assert [r["role"] for r in hist] == ["header", "session", "user", "bot"]
    assert [r.get("parentId") for r in hist] == [None, header_id, "m2", user_id]
    turns = store.list_turns("abc123abc123")
    assert [t["role"] for t in turns] == ["user", "bot"]
    assert turns[0]["text"] == "hi"
