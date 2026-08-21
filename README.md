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

1. Start [logbook-server](https://logbook.codicent.ai):

```powershell
$env:LOGBOOK_PROJECT = "test"
$env:LOGBOOK_API_KEY = "123123"
logbook-server
```

2. Copy `.env.example` to `.env` in this folder and set the **same** project and API key (cmd `set` does not apply to PowerShell).

3. Have at least one engine CLI on PATH and logged in: `claude`, `codex`, `grok`, or `copilot`.

```powershell
cd C:\Users\JohanIsaksson\src\dint
.\.venv\Scripts\Activate.ps1
pip install -e .
dint status
dint start grok .
dint send <chat_id> "Summarize this repo"
dint chats
dint list <chat_id>
dint show <chat_id>
```

`dint status` checks Logbook health/auth and whether the four CLIs are on PATH.

## Jobs

Enqueue a job from the CLI (Logbook `#job`; `dint serve` runs it):

```powershell
dint serve                          # keep this running
dint job grok "hej vad kan du göra?"
# job    <logbook-id>
# chat   <chat_id>
dint list <chat_id>
dint chats
```

A `#job` message also works from Logbook itself:

```
@test #job #claude
{"engine":"claude","cwd":"C:\\src\\myproj","prompt":"Summarize this repo"}
```

or `@test #job #grok Summarize this repo`.

```powershell
dint serve
# POST http://127.0.0.1:8787/webhook
```

If register fails, start logbook with `LOGBOOK_WEBHOOK_URL=http://127.0.0.1:8787/webhook`. Completed turns are stored on `#chat-<id>` like a normal `send`. Ack is `#job-run` (not `#job`, so it does not loop).

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
| `LOGBOOK_TRANSPORT` | `rest` |
| `DINT_JOBS_PORT` | `8787` |
| `LOGBOOK_WEBHOOK_SECRET` | _(optional HMAC)_ |

Each chat is a Codicent-style thread: the header is the root; every later message sets `parentId` to the previous one. User turns are tagged `#user`, engine replies `#bot`. `dint list` reads `#chat-<id>` (full body) and merges `GetMessageHistory` for the parent chain — history alone can truncate long bot JSON.
