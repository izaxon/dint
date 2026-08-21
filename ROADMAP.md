# dint roadmap

Review of the open issues as of `cb45e44` (2026-08-21), and the plan for the next four
milestones.

## Context

dint is ~1,600 lines of stdlib-only Python. It routes prompts to official coding-agent CLIs
(`claude`, `codex`, `grok`, `copilot`) and writes every message to Codicent Logbook as an
append-only thread. A job is a Logbook message tagged `#job`; `dint serve` turns it into a chat
plus one engine turn.

Seven issues are open (#1–#7). They were filed within ~2 hours of each other on 2026-08-21 by
three different reviewers plus the author, so they overlap heavily and several of their findings
have already been fixed on `master`. The repo has no agreed next milestone.

This plan does two things: reconciles the backlog with the code as it actually stands, and
sequences the surviving work into four milestones.

## Issue triage

Verified against the working tree at `cb45e44`.

### Already fixed — the issues are stale

| Claim | Where | Reality |
| --- | --- | --- |
| `Authorization` header sends literal `******` | #2 §1 (called "🔴 high priority") | Fixed. `logbook/rest.py:73` and `logbook/mcp.py:109` both interpolate `f"Bearer {self.api_key}"` |
| No LICENSE file, no `license` in pyproject | #5 §6 | Both present — MIT, `license = { file = "LICENSE" }` |
| No CI | #2 §9, #5 §6 | `.github/workflows/ci.yml` runs pytest on 3.11/3.12 (ubuntu only — see M4) |
| `__init__.py` still says "Claude Code and Codex" | #3 §7 | Fixed, names all four engines |
| `dint job` can't report the chat id without waiting for the engine | #3 §2 | Fixed in `6ad8f5e`; `dint job` prints the chat id from the `#job-run` ack |

### Complete

**#1** (v0 scope) is done, including all four listed follow-ups: Copilot adapter, Grok adapter,
webhook-driven jobs. Only "small UI" remains, and that is already tracked in #3 §3. Close it.

### Deferred by the author

**#6** (dint-owned chat titles) — explicitly marked "not now", blocked behind job-loop and
`dint chats` noise. Leave open, untouched; M3/M4 reduce the noise it is waiting on.

### Live work, deduplicated

The remaining issues are three reviews of the same code plus one strategy thread. Their
substance collapses into four tracks:

| Track | Sources |
| --- | --- |
| Zero-install / positioning | #7 (all three reviewers), #5 §6, #3 §7 |
| Durable + safe job loop | #4 (entire), #5 §1–2, #2 §3/§7/§12/§14/§15 |
| HTTP API + multi-turn jobs | #3 §1–2/§4, #5 §3, #2 §4/§6 |
| Engine + hygiene polish | #3 §5–6, #5 §4–5/§7, #2 §5/§8/§10/§11/§13/§16 |

One point of genuine disagreement across reviewers: whether Codicent Logbook should remain a
hard requirement. **Decision: it stays required.** No SQLite backend, no pluggable `Ledger`
abstraction. Zero-install is solved by making Logbook itself trivial to obtain, not by
replacing it.

## Two blockers found while reviewing, not mentioned in any issue

Both hit M1 directly and change its shape:

1. **The MCP client cannot speak HTTPS.** `logbook/mcp.py:17` correctly resolves port 443 for an
   `https://` URL, but `_call` at `logbook/mcp.py:122` hardcodes `http.client.HTTPConnection`.
   Any hosted Logbook is therefore unreachable over MCP. `RestLogbook` is fine — it uses
   `urllib`, which handles TLS.
2. **A hosted Logbook cannot deliver a webhook to a laptop.** `jobs.serve` binds
   `127.0.0.1:8787` and calls `register_webhook` with that URL. A server at
   `logbook.codicent.ai` cannot POST to a loopback address behind NAT. Webhook delivery only
   ever works against a Logbook on the same machine or LAN.

So "hosted Codicent by default" is not just a config change — `dint serve` needs an outbound
**polling** path for jobs. That is M1 work, not a nice-to-have.

---

# M1 — Zero-install onboarding, and backlog cleanup

Goal: `pipx install dint`, answer two prompts, run a job. No repo clone, no manual `.env`.

### 1.1 Poll-based job intake (unblocks hosted Logbook)

Add a poller alongside the existing webhook server in `src/dint/jobs.py`. Reuse `handle_event`
unchanged — the poller synthesizes the same payload shape a webhook delivers, so one code path
runs jobs.

- New `poll_loop(router, *, interval)`: `get_messages("#job", length=N)`, skip ids already seen
  (durable check via the ack lookup that `handle_event` already does), call `handle_event`.
- `serve()` gains a mode: `webhook` (today), `poll`, or `auto`. `auto` picks `poll` when
  `LOGBOOK_URL` is not loopback. Flag: `dint serve --mode {auto,webhook,poll}`.
- Polling makes `_try_register` optional rather than a hard failure path.

Poll interval default 3s, `DINT_POLL_INTERVAL`. This is chattier than webhooks but it is the
only thing that works against a hosted ledger, and it removes the "register failed, go edit
logbook-server config" dead end from the first-run experience.

### 1.2 Fix the MCP HTTPS bug

`logbook/mcp.py:_call` — select `HTTPSConnection` when the parsed scheme is `https`. Store the
scheme on `__init__` alongside `host`/`port`. Small, self-contained, needs the first real test
for that module (see M4).

### 1.3 `dint init`

New `src/dint/init.py`, wired as a subcommand in `cli.py`.

Interactive flow:
1. Ask: hosted Codicent (default) or local logbook-server.
2. Hosted → prompt for API key, point `LOGBOOK_URL` at the hosted endpoint, prompt for project
   name (default `dint`).
3. Local → check `LOGBOOK_URL` health; if unreachable, run the local-server bootstrap (1.4).
4. Probe: `health()` + `get_messages(length=1)` — reuse the logic in `status.py` rather than
   duplicating it (factor those two probes out of `run_status` into functions both call).
5. Report which engine CLIs are on PATH; if none, say which to install and link them.
6. Write config.

Non-interactive: `dint init --api-key K --project P --url U --yes` so it can be scripted and
tested without a TTY.

**Config location.** Write `~/.dint/config` (same `KEY=VALUE` format as `.env`). Precedence,
highest first: real environment → project `.env` → `~/.dint/config`. This keeps the existing
"real env always wins" guarantee in `envfile.py:load_dotenv` and adds a user-level layer under
it, so a cloned repo with its own `.env` still behaves as it does today. Extend `load_dotenv`
to load the user file after the project file, using the same `if key not in os.environ` guard.

**Unconfigured state.** Add `dint.config.is_configured()` (API key present and URL reachable).
`cli.main` checks it before building a `Router` for any command that needs the ledger, and
exits with a single actionable line: `not configured — run: dint init`. `dint status` prints
the same hint rather than two `FAIL` probes.

### 1.4 Local logbook-server bootstrap

Decision: hosted is the default, but first run should be able to install and start a local
server seamlessly.

**Upstream prerequisite — flag before building.** There is no published local artifact today
(README only links to the product page). One of these has to exist first:
a container image, or a per-platform self-contained binary attached to a GitHub release.

Given that, build the dint side against a small, swappable interface in `src/dint/server.py`:
- `find_server()` — is a logbook-server already running at `LOGBOOK_URL`? (`health()`)
- `install_server()` — fetch the artifact into `~/.dint/logbook/`.
- `start_server()` / `stop_server()` — launch it, wait for `/health`, record the pid.
- `dint up` / `dint down` as the user-facing commands; `dint init` calls `start_server` for the
  local path.

Reuse `proc.spawn` for the child process rather than a second subprocess wrapper.

**Recommendation:** ship 1.1–1.3 first and treat 1.4 as a follow-on within M1. The hosted path
alone already delivers "install, paste key, run a job", and it does not block on an upstream
release. Do not let 1.4 hold M1.

### 1.5 Packaging

- Add a `release.yml` workflow: on tag, build sdist+wheel and publish to PyPI via trusted
  publishing. Runtime deps stay `[]`.
- Verify `pipx install dint` then `dint init` on a clean machine.

### 1.6 Positioning and doc fixes

- README line 3 and `docs/index.html:214` claim "one local chat API"; no HTTP chat API exists
  until M3. Change to "one local interface" (which is what the repo description already says).
  Restore the API wording when M3 lands.
- `.env.example` says `LOGBOOK_PROJECT=test`, README's table says `dint`. Make both `dint`.
- README install section: lead with `pipx install dint && dint init`; move the
  clone/venv/`pip install -e` block into a "develop" section.
- Add GitHub topics (`coding-agents`, `claude-code`, `codex`, `copilot`, `local-first`) — free,
  and all three reviewers in #7 raised discoverability.

### 1.7 Backlog cleanup

- Close **#1** as complete (all v0 scope plus all four follow-ups shipped; the leftover UI is
  tracked in #3 §3).
- Comment on **#2** and **#5** listing the stale items from the triage table above, so nobody
  re-fixes the `Authorization` bug or re-adds a LICENSE.
- Leave **#6** open and untouched.
- Optionally split **#4** into child issues matching M2's sections — it is written as a roadmap
  and will otherwise stay open indefinitely.

### M1 acceptance

- [ ] On a machine with no dint checkout: `pipx install dint`, `dint init` (hosted, paste key),
      `dint serve` in one shell, `dint job claude "…"` in another returns a chat id and the turn
      lands in Logbook.
- [ ] `dint serve --mode poll` runs jobs against an HTTPS Logbook with no webhook registration.
- [ ] `McpLogbook` reaches an `https://` endpoint.
- [ ] Every ledger-touching command prints `run: dint init` when unconfigured instead of a stack
      trace or a bare `FAIL`.
- [ ] README, `docs/index.html`, and `.env.example` agree with each other and with the code.

---

# M2 — Durable and safe job loop

Goal: `dint serve` is safe to leave running unattended. Covers #4 in full and #5 §1–2.

Depends on M1 only in that the poller and the webhook handler must share one acceptance path.

### 2.1 Job state in an append-only ledger

Logbook has no updates, so state is a reduction over messages. Represent each transition as its
own message:

```
@project #job-state #job-<jobId> #<engine> {"jobId":…,"chatId":…,"state":"running","ts":…,"error":null}
```

States: `accepted → running → completed | failed | cancelled`. (`queued` is implicit — the
`#job` message itself is the queued record.)

- **Exact tag `#job-<jobId>`** replaces the 50-message `#job-run` scan in `_chat_id_for_job`
  (`jobs.py:50-58`), which silently misses anything older. Lookup becomes one exact-tag search.
- `reduce_job_state(rows)` — sort by ts, last state wins. Used by restart recovery,
  `dint jobs`, and `dint job --wait`.
- Keep posting `#job-run` for backward compatibility with `.grok/skills/dint-jobs/SKILL.md`
  and anything already polling it; it becomes the `accepted` record.

### 2.2 Acceptance ordering and durable dedupe

Two ordering bugs to fix in `jobs.py`:

- `_handler` adds `event_id` to `seen` at line 173, *before* `handle_event` runs at line 177.
  A handler exception returns 500, Logbook retries, and the retry is answered as a duplicate —
  the job is lost. Move the `seen.add` to after a successful acceptance, and on exception
  discard the id so the retry is real. Also replace `seen.clear()` at line 175 (wholesale wipe
  past 500 entries) with a bounded FIFO that evicts oldest-first.
- `_ack` currently posts before the engine runs, so a crash after ack looks handled forever.
  Keep the `accepted` write there — it is what makes duplicate delivery converge on one run —
  but make it no longer imply completion. Completion is a separate terminal record.

Durable dedupe: acceptance checks the exact `#job-<id>` tag, not just the in-memory
`router._started_jobs`. That set becomes a fast path in front of the ledger, not the source of
truth. Also promote it from a `setattr` on a private name (`jobs.py:106-112`) to a real bounded
field on the handler.

### 2.3 Restart recovery

On `serve` startup: search `#job-state`, reduce, and for every job stuck in `accepted` or
`running` with no terminal record, write `failed` with `"reason":"interrupted"`. Do not
auto-retry — an engine turn has side effects on disk, and silently re-running one after a crash
is worse than reporting it. Say so in the README.

### 2.4 Terminal states are always written

`_run_send` (`jobs.py:195-209`) catches `Exception` and only prints. Wrap the whole turn so
every exit path — engine spawn failure, adapter parse error, Logbook write failure, timeout,
cancel, unexpected exception — writes a terminal `#job-state` with an error summary. This is
the single highest-value change in M2: today a failed job is invisible to everything except
whoever is watching stderr.

### 2.5 Bounded worker pool

Replace the unbounded daemon thread per job (`jobs.py:116-121`) with a fixed
`ThreadPoolExecutor`. `DINT_MAX_WORKERS` / `--max-workers`, default 2. On shutdown: stop
accepting, let in-flight turns finish or cancel them, and write their terminal state either way.
Keep the existing invariant that one chat cannot run two turns at once (`router.send` raises).

### 2.6 Per-turn timeout

`RunningProcess.lines()` can block forever. Add `DINT_TURN_TIMEOUT` (default 0 = off, but set a
real default for webhook/poll jobs — 30 min). On expiry, `RunningProcess.cancel()` kills the
process tree via the existing `_kill`, and the job goes terminal as `failed`
`"reason":"timeout"`.

### 2.7 Execution policy

Today a job payload names any `cwd` on the machine and runs with `acceptEdits` /
`workspace-write` / `--always-approve` / `--allow-all`. Anyone who can post to the Logbook
project gets arbitrary code execution.

- Normalized policy `read-only | workspace-write | full-access`, carried on the job payload and
  recorded on the `accepted` state. Map it per engine in each adapter's `argv` — this is the
  reason to route it through `argv` rather than env vars, since the four CLIs spell it
  differently.
- **Default for webhook/poll jobs: `workspace-write`**, not full access. Interactive
  `dint send` keeps today's behavior.
- `DINT_JOB_ROOTS` allowlist; reject a job whose `cwd` is outside it, *before* acceptance, with
  a `failed` state explaining why. Reject a missing or non-directory `cwd` rather than falling
  back to the serve process's `os.getcwd()` (`jobs.py:74`).
- Require a webhook secret when `--host` is not loopback: `_signature_ok` returning `True` on
  an unset secret (`jobs.py:255-261`) is fine on `127.0.0.1` and unacceptable on `0.0.0.0`.
  Refuse to start in that combination.

### 2.8 Thread safety

- `Router._active` / `Router._chats` are mutated from worker threads with no lock. Add one.
  `Router._engine_for` already re-instantiates the engine per send, so process state is
  isolated; the dicts are the exposed part.
- `McpLogbook._rid` / `session_id` are mutable and unsynchronized. Give each worker its own
  client instance — simpler than locking, and the transports are cheap.

### 2.9 `dint jobs`

List recent jobs with reduced state: `jobId`, `chatId`, engine, state, ts, error summary.
`--json` for scripting. `dint job --wait` blocks to a terminal state instead of the current
20-second ack poll.

### M2 acceptance

Mirrors #4's own list:
- [ ] Handler failure then redelivery runs or explicitly rejects — never silently deduped away.
- [ ] Crash after acceptance is visible after restart as `failed/interrupted`.
- [ ] Every accepted job reaches `completed`, `failed`, or `cancelled`.
- [ ] Duplicate concurrent deliveries produce exactly one engine run.
- [ ] A job with `cwd` outside `DINT_JOB_ROOTS` is rejected before any process spawns.
- [ ] `serve --host 0.0.0.0` without a secret refuses to start.
- [ ] A hung engine is killed at the timeout and the job goes terminal.
- [ ] Tests: failure-then-retry, crash-after-ack recovery, duplicate concurrent delivery,
      restart reduction, cwd rejection, timeout.

---

# M3 — HTTP chat API and multi-turn jobs

Goal: make the "local chat API" claim true, and let a job continue an existing chat.

Depends on M2: serve must own turn lifecycle durably before it also owns HTTP clients.

### 3.1 HTTP API

Add routes to the existing `ThreadingHTTPServer` in `jobs.py` — **stdlib only, no FastAPI**;
the empty runtime-dependency list is a deliberate property of this project worth keeping. Split
the growing `jobs.py` (302 lines and about to grow) into `jobs.py` (job semantics) and
`server.py` (HTTP routing), with the webhook as one more route.

| Route | Behavior |
| --- | --- |
| `POST /chats` | `{engine, cwd}` → `{chatId}` |
| `POST /chats/{id}/send` | streams events as **NDJSON** |
| `POST /chats/{id}/cancel` | cancels a turn owned by this process |
| `GET /chats` | `list_chats` |
| `GET /chats/{id}` | chat header |
| `GET /chats/{id}/turns` | `list_turns` |
| `GET /jobs`, `GET /jobs/{id}` | reduced job state from M2 |

NDJSON over SSE: one JSON object per line maps exactly onto the existing `Event` dataclass,
is trivial to consume with `curl`, and needs no client library. SSE buys reconnection semantics
this does not need.

Bind loopback by default; require a token for any non-loopback bind, same rule as the webhook
secret.

### 3.2 Cross-process cancel

`dint cancel` reads `Router._active` in its own process, so it can never stop a turn running
inside `serve` (#2 §6, #3 §4). Point the CLI at the HTTP API when a serve process is reachable,
and fall back to today's in-process behavior otherwise.

### 3.3 Multi-turn jobs

`#job` currently always starts a new chat. Accept `chatId` in the payload: if present, skip
`start_chat` and send into the existing chat with its stored engine session. Reject an engine
that disagrees with the chat header. Update `.grok/skills/dint-jobs/SKILL.md` — its "Limits
(v0)" section states the one-job-one-chat rule, and
`test_parse_job_matches_skill_example` pins the doc to the code, so both move together.

### 3.4 Small UI (the last of #1)

Once the routes exist: a single static page served by `serve`, listing chats and streaming a
turn. Explicitly the last thing in M3 — it is a demo artifact, and #7's reviewers wanted the
API before the UI.

### M3 acceptance

- [ ] One `dint serve` hosts webhook/poll jobs *and* the HTTP API.
- [ ] `curl -N -XPOST .../chats/{id}/send` streams NDJSON events in real time.
- [ ] `dint cancel` stops a turn running inside a different process.
- [ ] A `#job` carrying `chatId` continues that chat using its stored engine session id.
- [ ] README/docs restore the "chat API" wording, now accurate.

---

# M4 — Engine and hygiene polish

Independent of M1–M3; pull items forward whenever one blocks something else.

### Engines
- **Capture stderr.** `proc._drain_stderr` (`proc.py:85-95`) reads and discards. Keep a bounded
  tail (~50 lines) on `RunningProcess` and attach it to the synthesized error Event in
  `CliEngine.send` (`engines/base.py:41`), so `claude exited 1` becomes actionable. Highest
  value item in M4 — it is the difference between a debuggable failure and a mystery.
- **Dedupe `_json`.** Four identical copies (`claude.py:75`, `codex.py:87`, `grok.py:68`,
  `copilot.py:71`) → one in `engines/base.py`.
- **`need_approval`.** Declared in `types.py:7` and emitted by `codex.py:70`, handled nowhere.
  Either surface it through the M3 API as an approval flow, or drop it from `EventType` and
  have the Codex adapter emit `tool`. Decide when M3 lands; do not leave it dead.
- **Engine registry.** `ENGINES` in `router.py:10` is duplicated as `choices=[...]` in
  `cli.py:24,44`. Derive the CLI choices from the constant. A registry also makes adding Gemini
  CLI / Aider cheap later — but do not add engines before M2; more engines multiply the safety
  surface.
- **`dint status`**: engine CLI versions (`claude --version`) and `--json`.

### CLI
- `_job_cwd_prompt` (`cli.py:123-126`) treats argv[0] as cwd whenever it happens to name a real
  directory, so `dint job claude test the parser` silently changes cwd. Replace with an explicit
  `--cwd` flag; keep the positional form working for one release with a warning.
- `dint chats --limit N --json`; `dint version`.

### Types and transports
- Complete the `Logbook` Protocol (`types.py:43`): add `get_message` and `register_webhook`
  (the latter as optional), both of which callers already use.
- Paginate `ChatLog.list_messages` — `get_messages` defaults to `length=100`, so long chats
  silently truncate.
- `extract_json` (`logbook/__init__.py:177`) assumes JSON runs to end-of-string; trailing text
  fails the whole parse. Use `json.JSONDecoder().raw_decode`.
- Add `register_webhook` to `RestLogbook` so the REST transport is not forced through
  `McpLogbook` in `jobs._try_register`.

### Tests and tooling
Untested today: `proc.py` entirely, `CliEngine.send`'s loop, `status.py`, both Logbook
transports, and the `jobs.py` HTTP handler.

- `tests/conftest.py` for `MemoryLogbook` (currently `test_logbook.py:9-47`) and `FakeEngine`
  (`test_router.py:11-23`); tests import them across modules today, which only works by
  accident of rootdir insertion.
- `proc.py`: spawn a short Python script as the child, assert streaming, nonzero exit, and
  cancel-mid-stream.
- Transports: a `http.server`-based fake asserting URLs, Bearer header, `LogbookError` mapping,
  the MCP handshake, `Mcp-Session-Id`, and SSE `data:` parsing.
- HTTP handler: drive `_handler` for 401/400/404/500, the dedupe set, and `_signature_ok`
  including the unset-secret default.
- CI: add a **Windows runner** — `proc._kill`'s `taskkill /T /F` branch is the primary target
  platform (the author's paths are Windows) and is never exercised. Add ruff + mypy steps and
  the matching `[tool.ruff]` / `[tool.mypy]` config; the code is already fully annotated, so
  mypy is close to free.
- Replace `print` with `logging` in `jobs.py` / `status.py` so serve output can be levelled.

---

## Sequencing summary

| | Milestone | Why here |
| --- | --- | --- |
| M1 | Zero-install + cleanup | Get strangers able to try it. Also unblocks the hosted path, which is currently broken two ways. |
| M2 | Durable + safe job loop | Do this before anyone leaves `dint serve` running. M1 brings users; M2 makes it safe for them. |
| M3 | HTTP API + multi-turn | Needs M2's durable turn ownership. Makes the README claim true and unblocks the UI. |
| M4 | Polish | Independent; pull items forward on demand. |

**One caution.** M1 before M2 means shipping easy onboarding onto a job loop that still runs
arbitrary `cwd` with permissive engine flags and no timeout. That is a deliberate choice and it
is defensible — early users run this on their own machines against their own ledger. To reduce
the exposure, pull two cheap M2 items into M1: the `DINT_JOB_ROOTS` allowlist (§2.7) and the
refusal to bind non-loopback without a secret. Both are small and neither depends on the state
machine.

## Verification

Per-milestone acceptance lists are above. Baseline for any change:

```bash
pip install -e ".[dev]"
pytest -q                    # 25 tests today, all must stay green
```

End-to-end, once M1 lands, against a real Logbook:

```bash
dint init                    # hosted: paste key; or local: dint up
dint status                  # health, auth, engine CLIs
dint serve --mode auto &
dint job claude "Reply with only: pong"
dint list <chat_id>          # user + bot rows on the #chat-<id> thread
dint jobs                    # M2: terminal state visible
```

For M2 specifically, the failure paths need deliberate testing, not just the happy path: kill
`serve` mid-turn and restart it, post the same `#job` twice concurrently, point a job at a `cwd`
outside `DINT_JOB_ROOTS`, and run an engine that hangs.

