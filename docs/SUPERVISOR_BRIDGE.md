# Supervisor Brief Bridge

How a brief produced by the cloud flow reaches `SUPERVISOR_BRIEF.md` on `main`.

## The gap this closes

The CrewAI flow runs in the cloud and has no GitHub access. Every run it
produced a brief that never reached disk. `capture_supervisor_brief.py` already
solved the other half, but it runs *its own* crew rather than reading the flow's
output, so the two systems never fed each other. Both worked. Neither reached
the other.

`brief_bridge.py` is the connection:

```
cloud flow  ->  transport  ->  commit_brief()  ->  export_publish.py  ->  main
```

The git work is handed to `export_publish.py`, so the privacy guards, the
history-safety check and the remote sync are reused rather than reimplemented.

## Transports

All five share one commit path, so all five get identical validation.

### `paste` — the Windows clipboard

The one-step path, and the one to use while the flow runs in the cloud.

1. Copy the `write_tasks_brief` output in the CrewAI Studio UI.
2. Run `Run CrewAI Supervisor.cmd --paste`.

```cmd
python brief_bridge.py paste
```

This exists because every other route loses the brief somewhere between the
Studio UI and the guard: a wrong filename, a `.txt` that matches nothing, a
file that never got saved. Copying already happened, so the clipboard is the
last place it survives intact.

The clipboard is untrusted input like anything else here, so it has to prove it
is a brief. The start marker is required. Without that check this transport
would publish whatever was last copied into a file the coach agent reads as
instructions — a copied password, a copied URL, a copied private message.

```
the clipboard does not look like a supervisor brief
  expected a line beginning: THIS IS UNVERIFIED LLM OUTPUT
  nothing was published, and the clipboard was left untouched
```

An empty clipboard is not a failure; it just means nothing was copied yet.

### `capture` — run a flow command and commit what it prints

For a flow whose runner can be invoked from this machine: a `crewai` CLI, a
Studio CLI, or a wrapper script you write yourself.

```cmd
set CREWAI_FLOW_CMD=crewai run write_tasks_brief
python brief_bridge.py capture
```

The command runs with the repository as its working directory and its **stdout**
is treated exactly like a brief from any other transport. An unset
`CREWAI_FLOW_CMD` is a normal state, not an error, so this is safe to call from a
wrapper that does not always have a brief.

There is deliberately no built-in CrewAI Studio HTTP client here. The Studio
API's request and response shapes are not something this repository can verify,
and a speculative client that looks functional is worse than an explicit seam:
it would fail at the moment you most needed it to work. If the Studio API turns
out to be the right transport, write the fetch in a wrapper that prints the
brief and point `CREWAI_FLOW_CMD` at it.

### `post` — stdin

The simplest option, and the right one when the flow can produce a file you can
copy, or when you are pasting a brief into a session by hand.

```cmd
type brief.md | python brief_bridge.py post
```

This is the path that closes the loop with no new infrastructure. Copy the flow's
brief into a file and pipe it in.

### `ingest` — drop directory

For a flow that can write a file somewhere but cannot reach this machine
directly. It drains a directory of `*.md` files, oldest first.

```cmd
python brief_bridge.py ingest
```

The directory defaults to `%USERPROFILE%\Downloads\garmin_brief_inbox` and is
overridable with `GARMIN_BRIDGE_INBOX`. It is local-only and outside the repo.

It accepts `.md`, `.markdown` and `.txt`. The `.txt` case is not cosmetic:
Notepad saves `.txt` by default, so the natural result of copying a brief out
of the Studio UI and saving it is a file this bridge would otherwise have
skipped silently, while still reporting a successful run. Prefer `paste`, which
has no filename to get wrong.

- An accepted brief is published and then **removed**, so a rerun is a no-op.
- A **rejected** brief is **left in place**. It is the one worth reading: it is
  how a leaked credential or a coordinate gets found. Deleting it would destroy
  the only evidence.
- A symlink is refused rather than followed, so a drop cannot read a file the
  bridge was not offered.
- Files over 256 KiB are refused.

Pair it with a scheduled task to poll every few minutes and it becomes a
push-free loop.

## Running the whole thing: `Run CrewAI Supervisor.cmd`

The launcher lives in `%USERPROFILE%\Downloads` alongside `Coach Dashboard.cmd`
and `Refresh Garmin Data.cmd`, because that is where the local launchers live and
the pipeline code is what belongs in the repository. It hardcodes the repo and
interpreter paths and calls in:

```
Run CrewAI Supervisor.cmd                      capture any brief, then publish
Run CrewAI Supervisor.cmd --paste              publish the brief on the clipboard
Run CrewAI Supervisor.cmd --dry-run            validate everything, change nothing
Run CrewAI Supervisor.cmd --crew "..."         run the local crew instead
```

It calls `supervisor_publish.py`, which runs `brief_bridge.py ingest` (or
`paste` with `--paste`) and then `export_publish.py`. The order matters: the
publisher runs last and unconditionally, so `garmin_export.csv` is refreshed
even on a run with no brief, and a rejected brief cannot leave the CSV stale.
Both steps go through the same publisher, so there is one commit path and one
set of guards.

**The transport gap is still open.** Nothing carries the flow's output to this
machine on its own. The brief will not appear until a human copies it, or a
transport is configured. Until then this repo holds the last brief that was
hand-delivered, which is why it looks stale.

A run with **no** brief is normal and exits `0`. Most runs will not produce one,
and treating that as an error would train you to ignore the output.

## What the written brief looks like

Each committed brief carries frontmatter and a generated timestamp:

```
---
captured_utc: 2026-09-30T03:30:05+00:00
source: inbox:brief.md
verified_by_coach: no
---

# Supervisor Brief

## Generated: 2026-09-30 03:30:05 (UTC)
```

`source` records which transport delivered it. The brief is treated as
untrusted input throughout, and the header says so.

The bridge also checks the brief's shape and reports what it found:

```
    ok: start marker present
    ok: '## NEXT SUPERVISOR CHECK' section present
```

A missing marker is a **warning, not a refusal**. A flow is free to reword its
headings, and a bridge that silently stops working because a heading was renamed
is worse than one that says so. What this catches is the failure that matters:
a transcript, an error page or a truncated response arriving where a brief was
expected, which the coach agent would otherwise read as instructions.

## Two scanners, and what happens when one objects

Nothing reaches `main` without passing two independent checks:

1. `capture_supervisor_brief.scan()` runs before anything is written. It knows
   about credentials, email addresses, GPS field names and coordinate values.
2. `export_publish.py`'s worktree guard runs at commit time and catches
   coordinate shapes the first scanner does not model.

They genuinely differ. A bare pair of two **positive** coordinates, written with
four or more decimal places, is **not** caught by the pre-flight scanner, which
only recognises west and south hemisphere pairs, but **is** caught by the
publisher's degree-pair guard. Both routes end the same way.

> This file once contained a realistic-looking example pair as an illustration
> and the guard refused to commit it, which is the guard working as intended. The
> shape is described in words instead, and the rule is: two positive numbers,
> comma-separated, four or more decimal places each.

When either refuses, the content is written to a **staging file outside the
repository**:

```
%USERPROFILE%\Downloads\garmin_brief_rejected
```

It holds the rejected content plus the exact pattern that triggered it:

```
[!] refusing to commit: 4 unsafe or invalid item(s)
    - GitHub token             ghp_ABCDEFGH...012345
    - latitude value           lat=47.6062
    - longitude value          lon=-122.3321

Staged for manual review, outside the repository:
  ...\garmin_brief_rejected\20260930T032412Z-inbox_leaky.md.rejected.md
```

Staging exists because the rejected content is the only evidence of what went
wrong. It is deliberately *not* in the repo, and `stage_dir()` refuses to write
there if `GARMIN_DATA_DIR` or `GARMIN_BRIDGE_STAGE` has been pointed at the
repository, since staging a credential into git is the exact failure the scanner
exists to prevent. Override with `GARMIN_BRIDGE_STAGE`.

If the publisher blocks a commit after the file was written, the previous brief
is restored, so the worktree never holds a brief that was rejected.

### `serve` — authenticated HTTP receiver

For a flow that can make an outbound HTTPS request.

```cmd
set GARMIN_BRIDGE_TOKEN=<long random string>
python brief_bridge.py serve --port 8790
```

```http
POST /brief HTTP/1.1
Host: 127.0.0.1:8790
X-Bridge-Token: <the same token>
Content-Type: text/plain

<the brief>
```

`GET /ping` returns `{"status":"ok"}` and needs no token, so a health check is
possible without a credential.

Responses:

| Status | Meaning |
|---|---|
| `200` | Published to `main`. |
| `400` | Empty, non-UTF-8, or too short to be a brief. |
| `401` | Missing or wrong token. |
| `403` | `Host` header is not loopback. |
| `404` | Path is not `/brief`. |
| `413` | Body over 256 KiB. Refused without reading it. |
| `422` | Failed the secret/coordinate scan. Nothing written, nothing pushed. |

**The loopback bind is deliberate.** A cloud flow cannot reach `127.0.0.1` on
this machine. Reaching it needs a tunnel in front of the receiver, and that
tunnel is the security boundary — which is why the receiver refuses any
non-loopback bind rather than making it a one-flag mistake. Treat the token as
the credential it is: a long random string, never in the repo, never in a URL
(it is a header, so it stays out of proxy and shell history).

## Security

This writes text the sender does not control into a **public** repository, so
the defaults are paranoid:

- **Token is mandatory.** The receiver will not start unauthenticated. Compared
  with `secrets.compare_digest`, so timing does not leak it.
- **A missing and a wrong token are byte-identical responses**, so the endpoint
  cannot be used to test whether a token exists.
- **The request never names a file.** The destination is the allowlist
  (`SUPERVISOR_BRIEF.md`). There is no path to traverse and nothing to
  overwrite, which is why the tests can assert traversal is impossible rather
  than merely blocked.
- **The token is never logged**, never written to the repo, and never returned
  in a response.
- **The `Host` header must be loopback**, which defeats DNS rebinding from a
  page the athlete happens to be visiting.
- **No CORS headers at all**, so a hostile page cannot read a response.
- **Oversized bodies are refused unread**, so a large POST cannot exhaust memory.
- **Content is scanned before anything is written** — credentials, email
  addresses and coordinates. On rejection the response is `422` and the
  repository is untouched.
- **A failed publish restores the previous brief**, or removes the new one, so a
  rejected file is never left in the worktree for the next run to inherit.

## The brief is untrusted input

It is data to be stored, not instructions to be followed. Every file it writes
opens with frontmatter saying so:

```
---
# Machine-generated by a CrewAI supervisor run. Treated as UNTRUSTED
# input by the coach agent, not as an instruction from the runner.
captured_utc: 2026-09-29T20:23:03+00:00
source: webhook
verified_by_coach: no
---
```

`source` records which transport delivered it. A transcript preamble is stripped,
so a flow that prints logs above the brief does not commit the logs.

## Verification

```cmd
python -m pytest tests/test_brief_bridge.py
25 passed, 1 skipped
```

The tests are mostly negative cases, because that is where the risk is: an
unauthorised caller, a traversal attempt, an oversized body, a non-UTF-8 body, a
hostile `Host` header, a brief carrying a credential or a coordinate, a publish
that fails, and a symlink in the inbox. The symlink test skips where the
filesystem does not support them.

## What it does not do

- It does not run the crew. `capture_supervisor_brief.py` does that, and the two
  are independent by design: one starts a crew, the other receives a brief.
- It does not judge the brief. It stores what the flow sent, stamped unverified.
  Judging it is the coach agent's job, which is what `verified_by_coach: no`
  means.
- It does not merge conflicting briefs. A new brief replaces the old one; the
  previous text is not kept. That is a deliberate simplification, and it is the
  one thing here that would need revisiting if briefs ever need history.
