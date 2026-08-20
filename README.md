# dint

One local chat API. Engine CLIs do the work. Codicent Logbook is the ledger.

```
Router.start_chat / send / cancel
        │
        ├─ Engine          Claude Code CLI, Codex CLI  (resume via session id)
        └─ Logbook         post_message / get_messages  (REST or MCP)
              │
              └─ ChatLog   tags + JSON, append-only
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

Needs `claude` and/or `codex` on PATH, and [logbook-server](https://logbook.codicent.ai) at `http://127.0.0.1:5100`.

| Env | Default |
| --- | --- |
| `LOGBOOK_URL` | `http://127.0.0.1:5100` |
| `LOGBOOK_API_KEY` | `test-local-key` |
| `LOGBOOK_PROJECT` | `dint` |
| `LOGBOOK_TRANSPORT` | `rest` (`mcp` uses `/mcp` `post_message` / `get_messages`) |

Each chat is one header message plus new messages for turns. No updates. Tags: `#chat #turn #claude|#codex #user|#assistant|#tool|#error #chat-<id>`.
