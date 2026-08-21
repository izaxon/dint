---
name: dint-jobs
description: >
  Enqueue and read dint coding-agent jobs through Codicent Logbook
  (post_message #job, poll #job-run, read #chat-<id>). Use when the user
  wants Claude, Codex, Grok, or Copilot to work on a folder via Logbook,
  dint serve, webhook jobs, or Logbook MCP — not a dint MCP. Use when
  asked to /dint-jobs, post a #job, or dispatch an engine CLI through
  the ledger.
---

# dint jobs via Logbook MCP

dint has no MCP server. Jobs are ordinary Logbook messages. `dint serve` must be running against **the same** Logbook you post to (local `logbook-server` MCP at `$LOGBOOK_URL/mcp`, not Codicent.com unless serve points there).

Engines: `claude` | `codex` | `grok` | `copilot`.
`cwd` is a filesystem path on the machine running `dint serve`.

## Enqueue

Call Logbook `post_message` (no `parentId`) with:

```
@<LOGBOOK_PROJECT> #job #<engine> {"engine":"<engine>","cwd":"<absolute-cwd>","prompt":"<task>"}
```

Example:

```
@test #job #grok {"engine":"grok","cwd":"C:\\Users\\JohanIsaksson\\src\\dint","prompt":"Reply with only: pong"}
```

Plain text after the tags is also valid: `@test #job #claude Summarize this repo`.

Do not post `#job-run`. That is the serve ack. Do not tag `#job` on chat turns.

## Wait for the chat

Poll `get_messages` with search `#job-run` (or `#job-run` plus `#chat-` if available). Find the row whose JSON has `"jobId":"<id from post_message>"` or whose `parentId` is that id. Read `chatId`.

If nothing appears, serve is not running or the webhook is registered on a different Logbook.

## Read the answer

`get_messages` search `#chat-<chatId>` (raise `length` on long chats). Prefer tagged search over `get_message_history`: history can truncate bodies past 1000 chars and break JSON.

Parse JSON after the first `{`. Keep `role` in `header` / `session` / `user` / `bot` / `tool` / `error`. The answer is the latest `role=bot` `text`. `#tool` rows are noisy; skip them unless debugging.

## Limits (v0)

One `#job` is one new chat and one turn. There is no `chatId` resume on a job yet. Bot text is written when the engine finishes, not streamed into Logbook.
