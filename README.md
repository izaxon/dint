# dint

One local interface to enqueue multi-turn agent jobs. Official CLIs do the work.
[Codicent Logbook](https://logbook.codicent.ai) is the append-only store.

```
Your app / CLI
  ├─ Claude Code CLI   → claude -p --resume <id>
  └─ Codex CLI         → codex exec resume <id>
         │
         ▼
  Logbook (REST /api/messages or MCP /mcp)
```

v0 Python API:

```python
from dint import Router

router = Router()
chat_id = router.start_chat("claude", cwd=r"C:\src\myproj")
for event in router.send(chat_id, "Summarize this repo"):
    print(event.type, event.text)
router.cancel(chat_id)
```

Follow-ups reuse the same engine session id. Crash or cancel does not drop it:
the id is posted to Logbook as soon as the engine emits it.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Requires:

- `claude` on PATH (Claude Code CLI)
- `codex` on PATH (Codex CLI)
- [logbook-server](https://logbook.codicent.ai) running locally

Default Logbook endpoint matches the usual local MCP config:

| Env | Default |
| --- | --- |
| `LOGBOOK_URL` | `http://127.0.0.1:5100` |
| `LOGBOOK_API_KEY` | _(empty; set to your bearer token, e.g. `test-local-key`)_ |
| `LOGBOOK_PROJECT` | `dint` |
| `LOGBOOK_TRANSPORT` | `rest` (`mcp` talks to `/mcp` `post_message` / `get_messages`) |

This package does **not** use `codicentpy` or hosted Codicent. Logbook is the ledger.

## CLI

```powershell
dint start claude .
# → <chat_id>

dint send <chat_id> "Review the auth module"
dint send <chat_id> "Now implement the first suggestion"
dint list <chat_id>
dint show <chat_id>
dint cancel <chat_id>
```

`Ctrl+C` during `send` cancels the in-process turn.

## Ledger

Each chat is one header message plus one new message per turn. No updates.

Tags: `#chat` `#turn` `#claude`/`#codex` `#user`/`#assistant`/`#tool`/`#error` `#chat-<id>`

JSON on every message:

```json
{
  "chatId": "abc123def456",
  "engine": "claude",
  "role": "user",
  "cwd": "C:\\src\\myproj",
  "externalSessionId": "the-cli-session-id",
  "text": "…",
  "ts": "2026-08-20T16:42:00Z"
}
```

List a thread from Logbook MCP or REST:

```
GET /api/messages?search=%23chat-<id>
```

or MCP `get_messages({ search: "#chat-<id>" })`.

## Out of scope (v0)

CDP, Windows MCP, Claude Desktop / ChatGPT history sync, Copilot / Grok
(stubs only), reimplementing tools or permissions.

## Tests

```powershell
pytest
```
