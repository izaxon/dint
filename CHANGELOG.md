# Changelog

## 0.2.0

- **Security:** `dint serve` only runs `#job` webhooks signed with `LOGBOOK_WEBHOOK_SECRET`, which dint now generates on first run and hands to the logbook-server it starts and to `register_webhook`. The job is always read back from Logbook by message id; a body in the request is ignored. Requests with an `Origin` header, a non-JSON content type, or a non-loopback `Host` are refused, so a web page or another local process can no longer start an engine with `--always-approve`. Stop a running 0.1.x `dint serve` after upgrading; `dint` warns while it is up.
- `dint last [chat]` prints the latest reply in full; `dint list --full` and `--json` show whole turns; `dint chats --json`.
- `dint job --wait [--timeout S]` follows the job, prints tool calls to stderr and the reply to stdout.
- Chat ids accept a unique prefix or `last` (default for `last`, `list`, `show`).
- REPL: a pasted multi-line block is one prompt instead of one turn per line; a typed line ending in `\` continues.
- Every turn ends in a `bot` or `error` row (`no reply` / `interrupted`), so readers can tell it is over.
- `~/.dint/.env` updates keep other keys and comments.
- Output piped to a file on Windows is UTF-8.
