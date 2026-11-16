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

Python 3.11+ and [pipx](https://pipx.pypa.io/), at least one engine CLI on PATH (`grok`, `claude`, `codex`, or `copilot`), and [logbook-server](https://logbook.codicent.ai) on PATH.

```bash
# Windows
iwr https://logbook.codicent.ai/install.ps1 | iex
# Linux / macOS
curl -fsSL https://logbook.codicent.ai/install.sh | bash

pipx install dint-cli
```

The PyPI name is `dint-cli` (`dint` is taken). From a checkout: `pipx install .` or `pip install -e ".[dev]"`.

Then, in any folder:

```bash
dint
```

That starts logbook-server and a background `dint serve` if they are not running, then opens a chat in the current directory (same idea as running `grok` in a new folder). One logbook covers every folder on the machine — chats store `cwd`; you do not get a server per repo. Config lives in `~/.dint`. If port 5100 already has someone else's logbook, dint picks the next free port and writes it to `~/.dint/.env`. `dint grok "Summarize this repo"` is a one-shot; `dint status` checks Logbook, serve, and engine CLIs.

## Chat

```bash
dint
dint grok "Summarize this repo"
dint start grok .
dint send <chat> "Summarize this repo"
dint last                 # latest reply, in full
dint list <chat> --full   # every turn in full (--json for scripts)
dint chats
dint show <chat>
```

Bare `dint` opens a chat in this folder (starts logbook + serve). Inside: `/engine`, `/job`, `/chats`, `/new`, `/help`. Any other `/line` (say `/login`) goes to the engine; `//help` sends a literal `/help`. A pasted block is one prompt; end a typed line with `\` to continue it. `DINT_ENGINE` picks the default CLI. Logbook and `dint serve` keep running in the background.

`<chat>` is a chat id, a unique prefix of one, or `last` (the newest chat, and the default for `last`, `list`, and `show`).

Python:

```python
from dint import Router

r = Router()
chat_id = r.start_chat("claude", cwd=".")
for ev in r.send(chat_id, "Summarize this repo"):
    print(ev.type, ev.text)
```

## Jobs

`dint` and `dint job` start a background `dint serve` if it is not running. Enqueue from the CLI or by posting a `#job` in Logbook. Run `dint serve` in the foreground if you want the webhook logs.

```bash
dint serve
dint job grok "What can you do?"
# job    <logbook-id>
# chat   <chat_id>
dint last <chat_id>

dint job --wait grok "What can you do?"   # follow the job, print the reply
```

From Logbook:

```
@test #job #claude
{"engine":"claude","cwd":"/src/myproj","prompt":"Summarize this repo"}
```

or `@test #job #grok Summarize this repo`.

`dint serve` listens on `http://127.0.0.1:8787/webhook`. If register fails, start logbook-server with `LOGBOOK_WEBHOOK_URL=http://127.0.0.1:8787/webhook` and `LOGBOOK_WEBHOOK_SECRET` from `~/.dint/.env`. Completed turns are stored on `#chat-<id>` like a normal `send`. Ack is `#job-run` (not `#job`, so it does not loop).

Serve only runs webhooks signed with `LOGBOOK_WEBHOOK_SECRET` (generated on first run). It reads the job back from Logbook by message id and never trusts a body sent in the request, and it turns away browser requests (an `Origin` header, a non-JSON body, or a foreign `Host`). After upgrading from 0.1.x, stop the old `dint serve`; `dint` warns while it is still running.

Agents should use Logbook MCP (`post_message` / `get_messages`) rather than a dint MCP. The contract is in [`.grok/skills/dint-jobs/SKILL.md`](.grok/skills/dint-jobs/SKILL.md).

## Ledger

Each chat is a Codicent-style thread: the header is the root; every later message sets `parentId` to the previous one. User turns are tagged `#user`, engine replies `#bot`. `dint list` reads `#chat-<id>` (full body) and merges `GetMessageHistory` for the parent chain — history alone can truncate long bot JSON.

| Env | Default |
| --- | --- |
| `DINT_HOME` | `~/.dint` |
| `DINT_ENGINE` | first of grok, claude, copilot, codex on PATH |
| `LOGBOOK_URL` | `http://127.0.0.1:5100` |
| `LOGBOOK_API_KEY` | generated on first run |
| `LOGBOOK_PROJECT` | `dint` |
| `LOGBOOK_TRANSPORT` | `rest` |
| `DINT_JOBS_PORT` | `8787` |
| `LOGBOOK_WEBHOOK_SECRET` | generated on first run (HMAC for `#job` webhooks) |

## License

MIT. See [LICENSE](LICENSE).
