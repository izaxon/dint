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

## Run

1. Start [logbook-server](https://logbook.codicent.ai) (MCP/REST on port 5100):

```powershell
$env:LOGBOOK_PROJECT = "dint"
$env:LOGBOOK_API_KEY = "test-local-key"
logbook-server
# UI:  http://127.0.0.1:5100
# MCP: http://127.0.0.1:5100/mcp
```

2. Have at least one engine CLI on PATH and logged in: `claude`, `codex`, `grok`, or `copilot`.

3. Install and chat:

```powershell
cd C:\Users\JohanIsaksson\src\dint
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
dint start claude .
# → <chat_id>
dint send <chat_id> "Summarize this repo"
dint send <chat_id> "List the risks"   # same engine session
dint list <chat_id>
dint show <chat_id>
```

Same with `codex`, `grok`, or `copilot`. `Ctrl+C` during `send` cancels the in-process turn.

Python:

```python
from dint import Router

r = Router()
chat_id = r.start_chat("claude", cwd=r"C:\src\myproj")
for ev in r.send(chat_id, "Summarize this repo"):
    print(ev.type, ev.text)
```

| Env | Default |
| --- | --- |
| `LOGBOOK_URL` | `http://127.0.0.1:5100` |
| `LOGBOOK_API_KEY` | `test-local-key` |
| `LOGBOOK_PROJECT` | `dint` |
| `LOGBOOK_TRANSPORT` | `rest` (`mcp` uses `/mcp` `post_message` / `get_messages` / `get_message_history`) |

Each chat is a Codicent-style thread: the header is the root; every later message sets `parentId` to the previous one. User turns are tagged `#user`, engine replies `#bot`. Engine tag is `#claude` / `#codex` / `#grok` / `#copilot`. Load a conversation with Logbook `GetMessageHistory` (header id) or `GET /api/messages?search=#chat-<id>`.
