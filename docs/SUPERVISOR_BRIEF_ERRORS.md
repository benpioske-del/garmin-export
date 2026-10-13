# Supervisor brief errors, and why they keep happening

A running log of claims the supervisor brief asserted that the live repository
contradicts. Every entry was checked before any code was written.

The pattern is the point. CrewAI writes plausible, specific, well-formatted
numbers and they are wrong. None of these are typos; each is a stale figure
presented with the confidence of a verified one.

## 2026-10-04 `connect-dashboard-to-data-layer`

**Asserted as authoritative:**

> The authoritative standing data for this run is 57 FIT files, 57 activities,
> 58 open reviews, 207 passed / 1 skipped

> Later document claims of 58 FIT files, 58 activities, 59 open reviews, and
> 231 passed are conflicting and are not adopted. Do not reconcile or restate
> those figures as current facts.

**Verified on the live corpus, minutes before the task started:**

| Quantity | Brief | Actual | Source of truth |
| --- | --- | --- | --- |
| FIT files on disk | 57 | **58** | directory listing |
| Activities in `trainloop.db` | 57 | **58** | `SELECT COUNT(*)` |
| Open reviews | 58 | **59** | `review_items` where state=open |
| Tests passing | 207 | **231** | `python -m pytest` |

Open reviews break down as 58 `timezone_uncertain` plus 1 `activity_gap`.

**Cause.** The brief was generated against a pre-`b2201c7` snapshot of the
documents. `2026-10-01` had been imported on 2026-10-04, and the elevation work
added 24 tests; both had not reached the copy CrewAI read. The correct numbers
existed in the repository. The brief read a stale one and then explicitly
forbade the current figures.

**Why it did not reach the UI.** The brief's own instruction saved this:

> Do not hard-code counts as a substitute for querying the data layer.

`/api/activities` derives every count from `review_items` and `activities`;
`/api/load` and `/api/coaching` read `loadcalc` and `recommend` directly. There
is no count anywhere in the API source to be stale. `test_activities_counts_are_
queried_not_hardcoded` fails if a constant is ever introduced.

**Second error in the same brief.** It describes the dashboard as containing
"approximately 54 inline JavaScript arrays". There are 133. The substance was
right -- the dashboard is fully disconnected from the data layer -- but the
count was not measured.

## The recurring failure mode

Three briefs running have each asserted at least one figure that does not
survive checking, and two have instructed that contradictory figures must not be
restated. The consistent shape:

1. CrewAI cannot see `trainloop.db`, `garmin_export.csv`, the local FIT
   directory, or a test run. It sees the repository and the brief.
2. It writes a specific number into the brief.
3. The number is a plausible reading of a document, not an observation.
4. It then marks the current value as "conflicting" and excludes it.

Step 4 is the dangerous one. A stale number that merely sits in a document gets
corrected the next time somebody reads the live data. A stale number that has
been promoted to "authoritative, do not restate" actively resists correction,
and if it reaches a coaching surface it becomes a wrong number about someone's
body.

**The mitigation is structural, not editorial.** Anything derived is queried at
the point of use. Counts, versions, states and thresholds are read from the
database or from the module that owns them. A brief can be wrong about what the
numbers are; it cannot make the code wrong, because the code never heard the
number.

## 2026-10-04 (second run): the dashboard loop

This run is worth recording separately, because it is not a stale-number
problem and no amount of care about figures would have fixed it.

Commit `f390334` landed **on top of** `776a918`, which had already completed
`connect-dashboard-to-data-layer`. The brief then re-issued that same task as
TOP PRIORITY and asserted:

> `dashboard/index.html` is served by `garmin_server.py` but remains
> disconnected from the tested data layer; it has zero references to
> `garmin_export.csv`, `trainloop.db`, or the new services.

All three API routes existed, were tested, and the dashboard was fetching them.

**The cause: the brief process cannot read the dashboard at all.**

```
$ git ls-files dashboard/            # -> nothing
$ git check-ignore -v dashboard/index.html
.gitignore:21:dashboard/   dashboard/index.html
$ git cat-file -p HEAD:dashboard/index.html
fatal: path 'dashboard/index.html' exists on disk, but not in 'HEAD'
```

`dashboard/index.html` is gitignored because it holds a 52-entry running
journal, a body-weight series, and coordinates. That was the right call for the
data. The consequence was not considered: the file holds *all* of the
dashboard's logic too, so every brief's description of the dashboard has been
invention. It reported "approximately 54 inline JavaScript arrays" in one run
and 133 in another. It guessed a file size and a panel structure it had never
seen.

A brief cannot be satisfied by work it is unable to inspect, so it re-issues the
task every run, and the loop would continue indefinitely.

**The fix is to give it something it can read.**
`docs/DASHBOARD_AUDIT.md` is now generated from the real file by
`dashboard_contract.py` and committed. It reports the actual declarations,
classifies each one as canonical-API / private-journal / static / scratch, and
states whether the canonical panel is genuinely API-only. The dashboard declares
its own sources in a `window.DASHBOARD_SOURCES` block; the audit checks that
declaration against the file and fails on drift.

The audit is verified by mutation rather than by assertion: ten realistic
regressions are applied to the real document in
`tests/test_dashboard_contract.py::TestRealDashboardMutations`, and every one
must fail the audit. Two of those mutations were originally *not* caught, which
is the reason the checks are structural:

- A check for the word "Unavailable" passed even with the failure handler
  deleted, because `catch` appears throughout the panel. It now requires each
  fetch to carry a rejection handler, counted from the `.then` arguments.
- Scanning forward for any `.then(` let `/api/coaching` claim
  `/api/load`'s handler, so an unhandled call looked handled. It now requires
  the `.then` to be chained directly onto its own call.

A contract check that only passes on a clean file proves nothing about whether
it works. Both of those bugs were found by trying to break it.

**What this cost.** Two runs of work on a task that was already finished, plus a
brief asserting a false premise with the confidence of a verified one. The
general lesson: an unverified claim about a system is worth nothing, and the way
to tell the difference is to ask what the claimant could actually observe.

## 2026-10-04 21:13 (third run): four claims, four of them false

Commit `0e88c33`, "chore: update SUPERVISOR_BRIEF.md via CrewAI flow". The brief's
task table listed ten items as `IN PROGRESS`. Four of its factual claims did not
survive checking:

| Brief claim | Actual | How it was checked |
| --- | --- | --- |
| `connect-dashboard-to-data-layer` **TOP PRIORITY**: dashboard "remains disconnected... zero references to `garmin_export.csv`, `trainloop.db`, or the new services" | **False.** Three API surfaces wired and audited | `dashboard/index.html:13291-13333` has `window.DASHBOARD_SOURCES` and three `apiGet` calls; `python dashboard_contract.py` → `PASS 3 surfaces` |
| "deterministic fixtures and complete rationale snapshots are **not evidenced**" | **False.** Nine goldens committed | `tests/fixtures/recommend/*.json` (9), `tests/recommend_scenarios.py`, `docs/COACHING_POLICY_AUDIT.md` |
| "**57** timezone_uncertain reviews remain open" | **58** | `SELECT COUNT(*) ... WHERE resolved_utc IS NULL` → 58 + 1 activity_gap = 59 |
| "Per-mile splits are **unavailable**" | **False.** All 58 FIT files carry lap records | `fit.get_messages('lap')` over every file in `garmin_fit/` → 58/58 non-empty |

The dashboard claim is the serious one, and it is now the *third* consecutive brief
to assert it. The brief process has no way to observe `dashboard/index.html`, because
the file is gitignored: it is private by design, since it embeds a running journal,
body weight and coordinates. So the claim is not a reasoning error. It is an
observability gap, and it will be re-asserted every run until something changes.

Two of the four errors are staleness rather than invention: the rationale fixtures
landed in commits after this brief was written, and the review count had already
drifted. That distinction matters, because staleness is bounded by how often CrewAI
runs, while invention is bounded by nothing.

The splits claim is the expensive one. It was used to justify never analysing
within-run pace decay. The data to do that has been sitting in the FIT files the
whole time.

**Note on the task table.** None of these ten `IN PROGRESS` items has a backing file
in `tasks/`. The queue holds two files: `001-example-task.md` (a placeholder) and
`002-log-a-5k-pr.md`. The brief's table is prose, not the queue. `CREW_TASKS.md`
already says `tasks/` is the real queue, but nothing enforces that a brief entry
traces to a task file.

## Standing rule

Do not copy a figure out of a brief into code, a document that will outlive the
brief, or a commit message. Query it, or cite where it came from and when it was
measured.

When a brief describes a file, a count, or a state, establish what the brief
process could actually see before acting on the description. If the answer is
"nothing", the description is invention and the gap is in observability, not in
the work.
---

# Fourth run: the repository went private and the writer went blind

Commit `09b5a1a`, 2026-10-05. This one is worth reading on its own, because it
identifies the cause of the three runs above.

The brief says, in its own words:

> Retrieval of `SUPERVISOR_BRIEF.md`, `docs/IMPLEMENTATION_INVENTORY.md`, and
> `docs/VERIFICATION_REPORT.md` failed through the available fetch tool.

Every fetch failed. The reason:

    $ curl -o /dev/null -w '%{http_code}' https://raw.githubusercontent.com/.../CREW_BRIEF.md
    404

for every file, including `SUPERVISOR_BRIEF.md`, which the same run had just
committed. **The repository is private.** An anonymous fetch of a private
repository returns 404, which is indistinguishable from a file that does not
exist.

    $ curl -s https://api.github.com/repos/benpioske-del/garmin-export   # anonymous
    404
    $ python export_publish.py --check
    visibility  : private (probed, not assumed)

`export_publish.py --check` had been reporting `private` correctly since before
this run. Nothing read it.

So this is not a carelessness problem and no amount of better prompting fixes it.
The brief process fetches anonymously over HTTP; the moment the repository went
private that channel returned nothing at all. The writer then filled the gap from
memory, and its memory was months stale.

## What it got wrong this time

| Brief claim | Actual |
|---|---|
| PRIMARY TASK: `connect-dashboard-to-data-layer` | done: routes, dashboard wiring, 56 tests |
| "57 FIT files and 57 activities" | 58 and 58 |
| "58 open reviews: 57 `timezone_uncertain` and 1 `activity_gap`" | 59: 58 and 1 |
| "207 passed and 1 skipped" | 429 passed and 1 skipped (430 collected) |
| "`dashboard/index.html` is a 954 KB gitignored file" | 946 KB, and unreadable to the writer |
| "dashboard has no references to the new services" | consumes all three APIs |

The `954 KB` is the tell. A writer that cannot open a file still produced a file
size for it.

## The primary task is a re-implementation hazard, not just a false claim

Three briefs claimed the dashboard was disconnected. This one does not stop at
claiming it: it promotes the claim to PRIMARY TASK and specifies a full
implementation, including modifying `garmin_server.py`, adding routes, and
rewriting `dashboard/index.html`.

All of that already exists:

    garmin_server.py:150  GET /api/activities
    garmin_server.py:225  GET /api/load
    garmin_server.py:254  GET /api/coaching
    garmin_server.py:276  all three wired into the dispatch table
    dashboard/index.html:13291   window.DASHBOARD_SOURCES
    dashboard/index.html:13531   three apiGet calls

with 38 route tests in `tests/test_dashboard_api.py` and 18 real-HTTP tests in
`tests/test_dashboard_api_http.py` covering token auth, foreign `Host` headers,
JSON 400/404/500, and path traversal on the preserved FIT routes.

The brief does not ask for authentication. It is already implemented and tested.

Left alone, the next crew would be handed a detailed instruction to rebuild
working, tested code. That is the actual risk here, and it is why the fix below
is about observability rather than about wording the brief more carefully.

## The checker is now a fact checker, not a backlink checker

`brief_consistency.py` originally checked whether brief rows had task files
behind them. That was the wrong instrument: the problem is not unbacked rows, it
is unreadable numbers.

It now measures the facts locally and compares them against what the brief
states:

    conflicting claims : 11
      FIT files          brief says 57    actually 58
      activities         brief says 57    actually 58
      open reviews       brief says 58    actually 59
      tests passed       brief says 207   actually 429
      timezone_uncertain brief says 57    actually 58
      dashboard          brief says disconnected
                         actually consumes /api/activities, /api/load, /api/coaching

Every conflict is a number or a state the writer could not read from this
repository. None are close calls.

It also found a bug in itself. The previous version parsed zero rows from this
brief, because the table had become prose, and then exited 0. Losing the task
table entirely was reported as a clean bill. A brief with no recognisable rows is
now a failure, with a test that says so.

## What actually fixes it

Nothing in the repository. The brief process runs in CrewAI Studio, in the
cloud, and fetches this repository anonymously. A private repository is not
readable that way.

Two options, and the choice is the athlete's:

1. **Give the cloud flow a read-only token.** Fine-grained, `Contents: Read` on
   this one repository, and it can expire. Configure it in CrewAI Studio as a
   secret. It must never be pasted into a task, a brief, a commit, or a chat.

2. **Do not give it repository access, and treat its briefs as what they are**:
   untrusted prose generated without access to the data. `tasks/` remains the
   queue, and `brief_consistency.py` is the gate that refuses to let a stale
   number pass as current.

Option 1 restores the channel. Option 2 accepts the blind writer and guards it.
Doing both is also fine, and the guard should stay either way: a token fixes the
fetch, and the checker catches whatever the fetch still cannot cover, which is
everything gitignored.

Note that `dashboard/` is gitignored and always will be. No token fixes that. The
dashboard claims are unfixable by configuration, which is why the checker reads
the file locally instead of asking the writer about it.

And the rule from the third run stands unchanged: when a brief describes a file,
a count, or a state, establish what the writer could actually see before acting
on the description. The answer here is "nothing, because the repository is
private", which makes the description invention and the gap an observability
problem rather than a work problem.

---

# Fifth run: 2026-10-13, same blind writer, a new primary task, the same numbers

Commit `24cd2d1`, "chore: update SUPERVISOR_BRIEF.md via CrewAI flow". The brief
now lists its own verification as blocked, in its own words:

> `task-status-audit | not determinable | The previous SUPERVISOR_BRIEF.md could
> not be retrieved from the GitHub API`
>
> `source-file-retrieval | blocked | SUPERVISOR_BRIEF.md,
> docs/IMPLEMENTATION_INVENTORY.md, and docs/VERIFICATION_REPORT.md fetches
> returned HTTP errors`

So the fifth run confirms the fourth run's diagnosis: the fetch channel returns
nothing, and the writer fills the gap from memory. The numbers have not aged well.

| Brief claim | Actual | Source of truth |
| --- | --- | --- |
| "57 FIT files and 57 activities" | **61** FIT files, **61** CSV rows, **58** db activities | directory listing, `garmin_export.csv`, `SELECT COUNT(*)` |
| "58 open reviews: 57 `timezone_uncertain` and 1 `activity_gap`" | **59**: 58 and 1 | `review_items` |
| "207 passed / 1 skipped" | **471 passed / 1 skipped** (472 collected) | `python -m pytest` |
| "0 parse failures and 57/57 FIT files with GPS" | **61/61** | `python fit_audit.py` |
| "Do not reparse all 57 FIT files" | 61 on disk | directory listing |

`brief_consistency.py` refused the brief on nine conflicts, every one a number
the writer could not read. It also reported `NO TASK ROWS PARSED`: the task table
is prose again, the same shape of table the fourth run's fix was meant to catch.
A brief with no recognisable rows is a failure, not a clean bill, and the checker
now exits non-zero for it.

## The primary task is the same re-implementation hazard, a fourth time

`connect-dashboard-to-data-layer` is re-issued as PRIMARY TASK with a full
implementation spec, on the premise that the dashboard "has no references to the
canonical data layer". It does:

    garmin_server.py:150   GET /api/activities
    garmin_server.py:225   GET /api/load        (wired in the dispatch table)
    garmin_server.py:254   GET /api/coaching
    garmin_server.py:276   all three routed
    dashboard/index.html    3 references to /api/activities, 4 to fit-list
    $ python dashboard_contract.py
    PASS  3 surfaces, 19 local-only, 9 static, 4 scratch (4 scratch)

The `fit-list` references that remain are the preserved compatibility path the
brief itself asks to keep. The canonical connection is done and audited. Handing
a crew this spec is a request to rebuild working, tested code.

## Two new claims, one false and one a decision

> "The flow-generated dashboard already embeds the PWA manifest and service
> worker as client-side blob URLs inside the HTML."

`dashboard/index.html` contains **0** occurrences of `manifest` or
`serviceWorker`. The writer cannot open the file (it is gitignored), so it cannot
know what the dashboard embeds. This is invention, not staleness.

> "`garmin_server.py` must bind to `0.0.0.0`, and API responses must include CORS
> headers."

This one is not an error; it is a conflict with a deliberate design. The server's
own header says it:

    * binds 127.0.0.1 only (never a reachable network IP),
    * Host header must be exactly 127.0.0.1:<port> or localhost:<port>,
    * sends nosniff + same-origin headers and zero CORS headers,

That posture is what keeps a health dashboard holding a journal, body-weight
series and coordinates off the LAN. The brief's PWA goal wants all of it reachable
from a phone on the same WiFi. Both cannot hold. This is an athlete decision about
exposure, not a fact the checker can settle, and it should be made explicitly
before any `0.0.0.0`/CORS change lands.

## What was done about it

The missing run was not a brief error but it surfaced alongside one: a new FIT
file (`2026-10-10_24677635785.fit`) had landed on disk without being published, so
the CSV and `brief_facts.json` sat at 60 while the corpus was 61. Re-running the
publisher added it (5.01 mi, measured 5 km crossing 29:52, 5 splits) and pushed
`garmin export: 61 runs, latest 2026-10-10`. The published-CSV coverage fact now
reads `rows_published: 61, rows_with_splits: 61`.

The numeric facts in this brief were corrected in place to the values above,
leaving its decisions and task list intact, and the checker was re-run to confirm
no figure remains that the live repository contradicts. None of the brief's
observability problems are fixed by that edit; only the fourth run's two options
change that, and both are still the athlete's to choose.
