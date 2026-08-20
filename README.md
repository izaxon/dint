# dint

One local chat API. Engine CLIs do the work. Codicent Logbook is the ledger.

```
Router.start_chat / send / cancel
        │
        ├─ Engine          Claude / Codex / Grok / Copilot CLI  (resume via session id)
        └─ Logbook         post_message / get_messages / get_history
              │
              └─ ChatLog   #user vs #bot, parentId chain, GetMessageHistory
```

```python
from dint import Router

r = Router()
chat_id = r.start_chat("claude", cwd=r"C:\src\myproj")
for ev in r.send(chat_id, "Summarize this repo"):
    print(ev.type, ev.text)
list(r.send(chat_id, "List the risks"))  # same CLI session
```

```powershell
pip install -e .
dint start claude .
dint send <chat_id> "Summarize this repo"
dint list <chat_id>
```

Needs `claude`, `codex`, `grok`, and/or `copilot` on PATH, and [logbook-server](https://logbook.codicent.ai) at `http://127.0.0.1:5100`.

| Env | Default |
| --- | --- |
| `LOGBOOK_URL` | `http://127.0.0.1:5100` |
| `LOGBOOK_API_KEY` | `test-local-key` |
| `LOGBOOK_PROJECT` | `dint` |
| `LOGBOOK_TRANSPORT` | `rest` (`mcp` uses `/mcp` `post_message` / `get_messages`) |

Each chat is a Codicent-style thread: the header is the root; every later message sets `parentId` to the previous one. User turns are tagged `#user`, engine replies `#bot`. Engine tag is `#claude` / `#codex` / `#grok` / `#copilot`. Load a conversation with Logbook `GetMessageHistory` (header id) or `GET /api/messages?search=#chat-<id>`.
