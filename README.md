# dint

One local chat API. Engine CLIs do the work. [Codicent Logbook](https://logbook.codicent.ai) is the ledger.

Site: [izaxon.github.io/dint](https://izaxon.github.io/dint/)

```
Router.start_chat / send / cancel
        │
        ├─ Engine          Claude / Codex / Grok / Copilot CLI  (resume via session id)
        └─ Logbook         post_message / get_messages / get_history
              │
              └─ ChatLog   #user vs #bot, parentId chain, GetMessageHistory
```

Coding agents already ship as official CLIs. Each one keeps its own sessions, transcripts, and resume ids. dint does not reimplement them. It starts a chat, streams a turn, and writes every message to Logbook as an append-only thread. A job is just a tagged Logbook message (`#job`); `dint serve` runs it.

v0: local, four engines, webhook jobs. Not a hosted product and not a desktop UI.

## Install

Python 3.11+, then at least one engine CLI on PATH and logged in: [`claude`](https://docs.anthropic.com/en/docs/claude-code), [`codex`](https://github.com/openai/codex), [`grok`](https://grok.com), or [`copilot`](https://docs.github.com/en/copilot/how-tos/use-copilot-agent-mode).

Run [logbook-server](https://logbook.codicent.ai) locally (or point at a remote Logbook). Copy `.env.example` to `.env` and set the same project and API key the server uses.

```bash
git clone https://github.com/izaxon/dint.git
cd dint
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
source .venv/bin/activate
pip install -e ".[dev]"
dint status
```

`dint status` checks Logbook health/auth and whether the four CLIs are on PATH.

## Chat

```bash
dint start grok .
dint send <chat_id> "Summarize this repo"
dint chats
dint list <chat_id>
dint show <chat_id>
```

Python:

```python
from dint import Router

r = Router()
chat_id = r.start_chat("claude", cwd=".")
for ev in r.send(chat_id, "Summarize this repo"):
    print(ev.type, ev.text)
```

## Jobs

Keep `dint serve` running. Enqueue from the CLI or by posting a `#job` in Logbook.

```bash
dint serve
dint job grok "What can you do?"
# job    <logbook-id>
# chat   <chat_id>
dint list <chat_id>
```

From Logbook:

```
@test #job #claude
{"engine":"claude","cwd":"/src/myproj","prompt":"Summarize this repo"}
```

or `@test #job #grok Summarize this repo`.

`dint serve` listens on `http://127.0.0.1:8787/webhook`. If register fails, start logbook-server with `LOGBOOK_WEBHOOK_URL=http://127.0.0.1:8787/webhook`. Completed turns are stored on `#chat-<id>` like a normal `send`. Ack is `#job-run` (not `#job`, so it does not loop).

Agents should use Logbook MCP (`post_message` / `get_messages`) rather than a dint MCP. The contract is in [`.grok/skills/dint-jobs/SKILL.md`](.grok/skills/dint-jobs/SKILL.md).

## Ledger

Each chat is a Codicent-style thread: the header is the root; every later message sets `parentId` to the previous one. User turns are tagged `#user`, engine replies `#bot`. `dint list` reads `#chat-<id>` (full body) and merges `GetMessageHistory` for the parent chain — history alone can truncate long bot JSON.

| Env | Default |
| --- | --- |
| `LOGBOOK_URL` | `http://127.0.0.1:5100` |
| `LOGBOOK_API_KEY` | `test-local-key` |
| `LOGBOOK_PROJECT` | `dint` |
| `LOGBOOK_TRANSPORT` | `rest` |
| `DINT_JOBS_PORT` | `8787` |
| `LOGBOOK_WEBHOOK_SECRET` | _(optional HMAC)_ |

## License

MIT. See [LICENSE](LICENSE).
