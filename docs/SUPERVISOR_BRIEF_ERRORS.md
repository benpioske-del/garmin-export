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

## Follow-up: the exposure decision, and the rest of the brief corrected

The exposure question above was put to the athlete and answered: **bind on the
LAN, keep the token over HTTP**. That is now implemented in `garmin_server.py`
(details in `docs/VERIFICATION_REPORT.md`), so the brief's PWA goal is kept
without opening the JSON API to anything but a token-bearing same-origin page.

With that decision made, the remaining contradictions in the fifth brief were
corrected in place, and the guard was taught the writer's new phrasing:

- The `## PWA / MOBILE SETUP` section and the acceptance criteria were rewritten
  to match what was built: `--lan` (default stays loopback), **no** CORS headers
  (a guard test asserts this), and a real server-served `/manifest.webmanifest`
  and `/sw.js` with the tags injected as the HTML is served. The "blob URLs"
  premise is false — a service worker cannot register from a blob URL at all.
- The backlog rows were restored to the `rank: N | slug | prose` shape the
  checker parses; the fifth brief had reverted them to `N. slug | prose`, which
  is why the checker reported `NO TASK ROWS PARSED`.
- The false dashboard claim ("has no references to the canonical data layer") is
  **left as written on purpose**: it is the pinned canary. `dashboard_conflict()`
  now allows a sentence break and up to 200 characters between "dashboard" and
  the claim, and also catches the reverse order ("not connected to the
  dashboard"), so the writer's rephrasing of the same false claim is still
  flagged.

Because the brief's numbers now agree with the repository, `KNOWN_CONFLICTS` in
`tests/test_brief_consistency.py` is empty: the pinned-conflict test now asserts
the brief states **no** wrong number, so a *new* fabrication fails the suite,
which is the drift worth catching.

---

# Sixth run: 2026-10-13, the same brief with the same numbers, again

Commit `8b86398`, "chore: update SUPERVISOR_BRIEF.md via CrewAI flow". This is
the fifth run's brief reproduced almost verbatim, including the numbers that
were corrected one commit earlier:

| Brief claim | Actual | Source of truth |
| --- | --- | --- |
| "57 FIT files and 57 activities" | **61** FIT files, **61** CSV rows, **58** db activities | directory listing, `garmin_export.csv`, `SELECT COUNT(*)` |
| "58 open reviews: 57 `timezone_uncertain` and 1 `activity_gap`" | **59**: 58 and 1 | `review_items` |
| "207 passed / 1 skipped" | **477 passed / 1 skipped** (478 collected) | `python -m pytest` |
| "0 parse failures and 57/57 FIT files with GPS" | **61/61** | `python fit_audit.py` |

The same two contradicting implementation premises returned with it: bind to
`0.0.0.0`, send `Access-Control-Allow-Origin: *`, and "the flow-generated
dashboard already embeds its manifest and service worker as client-side blob
URLs". The first two were decided against and the third is false (the server
serves real same-origin PWA files now). All three were corrected in place as in
the fifth run.

The dashboard premise was also reissued, this time as "`dashboard/index.html`
does not use it". `dashboard_conflict()` was widened to catch that phrasing, so
the false claim is still flagged as the pinned canary.

## What this says about the fix

The numbers are not drifting; they are frozen at a pre-`b2201c7` snapshot and
restated every run. Correcting them in place is a holding action. The only thing
that stops it is the authenticated fetch channel (`GITHUB_TOKEN`) from the fourth
run's Option 1, which is still unset. Until then the writer is blind and the
guard is the only defence.

---

# Seventh run: 2026-11-06, the blind writer repeats the pre-`b2201c7` snapshot

Commit `483b2a9`, "chore: update SUPERVISOR_BRIEF.md via CrewAI flow". The brief
reissued the same frozen numbers again:

| Brief claim | Actual | Source of truth |
| --- | --- | --- |
| "57 FIT files and 57 activities" | **69** FIT files, **69** CSV rows, **69** db activities | directory listing, `garmin_export.csv`, `SELECT COUNT(*)` |
| "58 open reviews: 57 `timezone_uncertain` and 1 `activity_gap`" | **70**: 69 and 1 | `review_items` |
| "207 passed / 1 skipped" | **491 passed / 1 skipped** (492 collected) | `python -m pytest` |
| "0 parse failures and 57/57 FIT files with GPS" | **69/69** | `python fit_audit.py` |

The brief also insisted the correct 61-era figures were "rejected as stale or
contradictory snapshot material". The measured corpus is now 69/69/70, so those
instructions were inverted along with the counts. The numbers were corrected in
place and the "dashboard does not use the data layer" premise was left as the
pinned canary.

## Structural change: the backlog is no longer `rank: N`

The seventh brief also changed the backlog's shape. Previous briefs wrote
`rank: N | slug | prose`; this one writes `Priority: high - slug | prose`. It
also promoted the primary task, `connect-dashboard-to-data-layer`, into a row of
"VERIFICATION (open tasks from previous brief)". Two consistency tests failed on
that alone: no `RANKED` rows were parsed, and the primary task appeared as a new
unbacked row.

Neither is a fabrication, so neither was "corrected" in the brief. The writer
owns its task list and wording. Instead `brief_consistency.py` now parses the
`Priority: ... - slug | prose` shape as `RANKED`, and
`tests/test_brief_consistency.py` pins `connect-dashboard-to-data-layer` in
`KNOWN_UNBACKED` (it has no task file under `tasks/`, like the rest of the
table). The guard stayed at one conflict: the pinned dashboard canary.

## Publish hazard found on this run

`export_publish.py` folds remote commits in with `reset --hard origin/main`. Any
uncommitted hand-edits to `docs/` or `SUPERVISOR_BRIEF.md` are discarded by that
reset; only `CREW_BRIEF.md` is restored automatically. Commit doc and brief
corrections *before* publishing, or the publish silently reverts them.

---

# Eighth correction: 2026-11-07, the review count moved because the data moved

This one is not a writer error. On 2026-11-07 the athlete confirmed the local UTC
offset as US Central (UTC-5/-6, DST applied per run). ctivities.confirm_timezone()
then resolved all 69 `timezone_uncertain` reviews and stamped every activity
`timezone_source=confirmed_offset`. The open review count fell from 70 to **1**,
the calendar-gap review for 2026-06-26..2026-07-05.

| Before | After | Source of truth |
| --- | --- | --- |
| 69 `timezone_uncertain` + 1 `activity_gap` = 70 open | 1 `activity_gap` only | `review_items` |
| `confirmation_required`, "9 recent activities are awaiting confirmation" | `data_insufficient`, "only 1 training days with runs in 7 days, need 3" | `trainloop.py recommend` |

The briefs and docs were reconciled to the new state, and
`docs/PROVENANCE.md` now records that the published CSV still carries the
FIT-derived `assumed_utc` label while the database and dashboard carry confirmed
local times. `trainloop.py status` was also corrected: it no longer says an open
review blocks a recommendation when none of the open reviews fall inside the
28-day window.

## Second fix on this run: the facts file recorded a false reason

`brief_consistency.py::_coaching_facts()` called `recommend.recommend(conn)`
without `hr_max`, so it recorded "running load unavailable: no hr_max supplied"
even though `profile.json` supplies 198 and the dashboard passes it. It now
resolves `hr_max` through `trainloop._hr_max()`, the same path the server uses,
so `brief_facts.json` quotes the real reason.

---

# Ninth correction: 2026-11-09, three completed rows still read "not evidenced"

The 2026-11-06 brief still carried three verification rows whose prose described
work that had already landed. Each was corrected in place to `DONE` with the
evidence attached:

| Brief claim | Measured state | Evidence |
| --- | --- | --- |
| The continuity review "has not been evidenced as complete" | Implemented from observed records only and pinned | five tests in `tests/test_training_data.py`; invariant in `docs/DATA_QUALITY_TERMINOLOGY.md` |
| "unresolved policy defects include an unreachable deload state" | `deload` and `recover` are reachable | `tests/test_recommend_snapshots.py` sweep; `tests/fixtures/recommend/deload-band-concentration.json` (ACWR 1.54); `docs/COACHING_POLICY_AUDIT.md` |
| "Quality gates and CI are not started, and no linter is configured" | CI and lint exist and pass | `.github/workflows/ci.yml`; ruff `E9,F` in `pyproject.toml`; clean-checkout suite passes with no FIT files, database, or dashboard |

Rows 35, 41 and 43 were the only changes. Row 31's "dashboard/index.html does
not use the data layer" premise was deliberately left untouched: it is the pinned
canary that keeps the consistency checker honest. No task was removed, added, or
reprioritised, and no number in the brief changed on this pass.

---

# Tenth correction: 2026-11-10, the brief reverted to the pre-data snapshot

The 2026-11-10 brief (`60a95ad`) arrived with the same stale figures as the
2026-10-04 brief: **57 FIT files, 57 activities, 58 open reviews, 207 passed**.
The measured state at correction time was **70 FIT files, 70 activities, 1 open
review, 496 passed**, because two things had moved since the previous brief:

- The athlete's US Central confirmation (2026-11-07) had already resolved every
  `timezone_uncertain` review, leaving only the calendar-gap review.
- The 2026-11-08 run (`garmin:25013986837`, `2026-11-08T20:57:40Z`) had been
  downloaded on 2026-11-09 but never imported, because the scheduled publish was
  still failing. It was imported with `trainloop.py bootstrap`
  (`{"inserted": 1, "unchanged": 69}`) and its local date confirmed at **UTC-6**
  (CST) under the athlete's standing US Central confirmation, taking the corpus
  to 70.

| Brief claim | Measured state | Source of truth |
| --- | --- | --- |
| 57 FIT files, 57 activities | 70 / 70 | FIT directory; `SELECT COUNT(*) FROM activities` |
| 58 open reviews | 1 (`activity_gap`, 2026-06-26..2026-07-05) | `review_items` |
| 207 passed / 1 skipped | 496 passed / 1 skipped (497 collected) | `python -m pytest` |
| 69/69 GPS | 70/70 GPS | `python fit_audit.py` |

Eight passages were corrected in place: the closed-task evidence row, the
accepted-state block, the endpoint corpus sentence, the "do not change" line,
the test-constraint sentence, and backlog item 12. A `FACT-GATE NOTE` at the top
records the correction.

One wording change is worth recording. The brief's line rejecting the "other"
numbers was rewritten without numerals. `claim_conflicts()` checks every numeric
claim in the file, including numbers inside a sentence that calls them stale, so
a rejection list written as "57 FIT files, 58 reviews, 207 passed are rejected"
is itself five conflicts. The note now says that any conflicting count is stale
snapshot material, without restating a number the checker would measure.

The pinned `connect-dashboard-to-data-layer` claim remains untouched, so
`brief_consistency.py` still exits 1 on the dashboard canary and zero on every
numeric claim.

## State found at publish time: visibility

The publish that followed this correction probed the repository as **public**
(an anonymous `api.github.com` request returned 200, `private=false`), not
private. `CREW_BRIEF.md` still said "private" in its READ THIS FIRST block and
its fact table. Both now say visibility is probed on every publish and is
currently public, with `publish_state.json` as the source of truth. This is a
measured state change, not a writer error: the same probe reported private on
earlier runs.

---

# Eleventh correction: 2026-11-11, two runs arrived after the brief

This is not a writer error. The corpus moved from 70 to **72** because two runs
were downloaded on 2026-11-11 at 17:40 and imported the same day:

| Run | Distance | UTC start | Local (CST) |
| --- | --- | --- | --- |
| 2026-11-10 (`garmin:25035907052`) | 10.25 mi | 2026-11-10T19:04:39Z | 2026-11-10T13:04:39 |
| 2026-11-11 (`garmin:25047812302`) | 6.48 mi | 2026-11-11T19:31:07Z | 2026-11-11T13:31:07 |

Both were confirmed at **UTC-6** under the athlete's standing US Central
confirmation. `trainloop.py bootstrap` reported
`{"inserted": 2, "unchanged": 70}`, taking the corpus to 72 activities with one
open review (the calendar gap). `fit_audit.py` is clean at 72 files, and the
coaching state left `data_insufficient` for **`build`** (ACWR 1.19,
`run_days_7d=4`).

The brief's corpus numbers were corrected in place from 70 to 72 and the
FACT-GATE NOTE now cites this correction as well. `CREW_BRIEF.md`,
`docs/VERIFICATION_REPORT.md` and `docs/IMPLEMENTATION_INVENTORY.md` were
reconciled to 72.

## Why the run was late

Downloading and importing are separate steps. `garmin_sync.py` (the
`Garmin Daily Sync` task / `Refresh Garmin Data.cmd`) writes FIT files to disk.
`trainloop.py bootstrap` is what inserts them into `trainloop.db`, and the
dashboard reads the database. The twice-daily `export_publish.py` task rebuilds
the CSV from the FIT directory but does **not** import into the database, so the
dashboard can lag the CSV until someone runs `bootstrap`. That is what happened
here: the 11/10 run was on disk and absent from the dashboard until the import
was run manually.

---

# Twelfth correction: 2026-11-11, the sync import gap and the test count

This is a code fix, not a writer error. The 2026-11-10 run exposed a structural
gap: the dashboard's "Sync Garmin now" action ran only `garmin_sync.py`, which
writes `.FIT` files to disk, and never ran the importer that fills
`trainloop.db`. The dashboard reads the database, so a downloaded run could stay
invisible until someone ran `trainloop.py bootstrap` by hand.

## What changed

- `garmin_server.py::_run_sync()` now runs `trainloop.py bootstrap` after
  `garmin_sync.py`. The import is attempted even when the download fails, so any
  file that did arrive is still picked up. The response reports `download_ok`
  and `import_ok` separately; `ok` is true only when both succeed.
- `garmin_publish_task.bat` now runs `trainloop.py bootstrap` before
  `export_publish.py`, so the scheduled publish cannot leave the database behind
  the CSV. It still publishes the CSV when the import fails, but the task result
  carries the import failure.
- `tests/test_sync_import.py` pins the order (download, then bootstrap), the
  import-after-failed-download behaviour, failure reporting, and the timeout
  message.

## Verified

- End-to-end `POST /sync` against the live server:
  `ok=True download_ok=True import_ok=True`, 0 new runs, 72 unchanged,
  1 open review.
- Live suite: **501 passed, 1 skipped** (502 collected).
- Clean checkout with no FIT files, no `trainloop.db` and no
  `dashboard/index.html`: **472 passed, 30 skipped**.
- `ruff check .` clean.

The brief and docs were corrected in place from 496 passed to **501 passed**
(the test count moved because five tests were added), and the clean-checkout
figure from 467 to **472 passed**.

---

# Thirteenth correction: 2026-11-11, the CalTrak/Aurora flow update

This entry records a flow update, not a writer fabrication. The CrewAI flow ran
at **2026-11-11 22:24 CST** (`2026-11-12T04:24Z`) and pushed four commits
straight to `origin/main`:

| Commit | Change |
| --- | --- |
| `52f0da8` | `SUPERVISOR_BRIEF.md` rewritten |
| `f1333a0` | new `flow_outputs/aurora_dashboard.html` |
| `b2b64ee` | `nutrition_log.csv` template (headers only) |
| `d775add` | `lifting_log.csv` template (headers only) |

The local tree was four commits behind because the flow pushes to GitHub and
does not write the local brief inbox or the local CrewAI output database. Both
were still empty when the update was looked for. The commits were pulled with
`git pull --ff-only`; nothing was rewritten on the remote.

## What the brief got right

The measured numbers matched the repository, so the facts gate found no numeric
or reason conflict: 72 FIT files / 72 activities, 1 open `activity_gap` review,
0 `timezone_uncertain`, 0 strength sessions, `hr_max=198`, and both new CSV
templates correctly described as headers only. The primary task
`adopt-flow-generated-dashboard` and the `Rank 1` backlog item
`caltrak-nutrition-ingestion` describe work that genuinely does not exist yet.

## What was corrected in place

- **Date.** The brief said `Generated: 2026-11-12`, which is the UTC date of the
  run. It was corrected to `2026-11-11 (US Central; flow ran
  2026-11-12T04:24Z)`, consistent with the timezone decision already recorded.
- **`0.0.0.0` binding.** The brief reissued "bind the server to `0.0.0.0`". That
  was decided against: the server keeps its loopback default and `--lan`/`--host`
  is the explicit opt-in. The requirement, acceptance check, setup step and
  next-check row were all corrected.
- **CORS and preflight.** The brief reissued `Access-Control-Allow-Origin: *`
  and `OPTIONS` preflight handling. Both were decided against: the dashboard and
  API are same-origin and a guard test asserts that no CORS header is sent. The
  requirement, acceptance check and next-check row were corrected.
- **Backlog shape.** The writer switched from `Priority: high - slug | prose` to
  `Rank 1: slug | prose`. `brief_consistency.py` gained a `NUMBERED` pattern so
  those rows are still parsed as ranked backlog instead of silently dropped.
- **Pinned canary retained.** The flow moved `connect-dashboard-to-data-layer`
  into `CLOSED TASKS`. The deliberately false sentence ("dashboard/index.html
  does not use it") is still required by `test_dashboard_conflict_detects_the_prose_claim`,
  so it is retained as a labelled PINNED CANARY note at the top of the brief.
  `KNOWN_UNBACKED` no longer contains that slug.
- **New unbacked rows pinned.** Three legitimate ranked backlog slugs arrived
  with the update and were added to `KNOWN_UNBACKED`:
  `caltrak-nutrition-ingestion`, `lift-logger-and-lifting-log-ingestion`, and
  `bodyweight-and-weekly-summary-endpoints`. A new test,
  `test_numbered_rank_backlog_rows_are_counted`, pins the `Rank N:` parser.
- **Test count.** Adding that test moved the live suite from 501 to **502
  passed, 1 skipped** (503 collected) and the clean checkout from 472 to **473
  passed, 30 skipped**. `docs/VERIFICATION_REPORT.md`,
  `docs/IMPLEMENTATION_INVENTORY.md`, `CREW_BRIEF.md`, `brief_facts.json` and
  the brief's quoted figures were updated to match.

## Still the athlete's decision

The flow's primary task is not implemented and was not started here. Serving
`flow_outputs/aurora_dashboard.html` at `/aurora` would replace the local
dashboard, and the CalTrak ingestion work depends on nutrition data that does
not exist yet (the CSV is headers only). Both need the athlete to say whether
Aurora becomes the product UI before any code changes.

After these edits the consistency checker reports exactly one conflict, the
pinned dashboard canary, and exits 1 on it as designed. No other figure or state
in the brief is contradicted by the live repository.

---

# Fourteenth correction: 2026-11-12, the Aurora artifact bug and the preview route

This is a code change, not a writer error. The athlete chose to **preview**
Aurora at `/aurora` rather than adopt it as the product UI, so the local
dashboard stays the default at `/`.

## The generated artifact was broken

`flow_outputs/aurora_dashboard.html` (commit `f1333a0`) could not run at all.
The generated `analysis()` view contained an unclosed template literal:

```
... </p>`,`card")} ${card(`<div class="eyebrow">Fitness trend</div>...
```

The `` `card")} `` is missing its closing backtick; it should be `` `card`)} ``.
The browser reported `SyntaxError: missing ) after argument list` at line 148,
so the entire script failed to parse, `RUNS`/`SUMMARY` were never defined, and
the page rendered blank. Serving it unchanged would have shipped a dead app. The
literal was corrected in place in the committed artifact.

## What the preview does

- `garmin_server.py` gained `resolve_aurora_html()` and a token/login-gated
  `/aurora` route. `/` is untouched and still serves the athlete's local
  dashboard; the preview is additive.
- The artifact bakes in a corpus snapshot, `SUMMARY` totals and ACWR. Rather
  than editing the generated file's data, the server injects
  `AURORA_LIVE_SCRIPT` at serve time (`inject_aurora_live()`, idempotent via the
  `aurora-live-v1` marker). It replaces the corpus and totals from
  `/api/activities`, derives ACWR from `/api/load`, and repaints the
  training-signal card from `/api/coaching`.
- It never invents a value: if a call fails, the committed snapshot stays and
  the badge says the API was unavailable. The generated narrative panels remain
  the committed snapshot; replacing them is part of full adoption, which was not
  requested.
- A `LIVE PREVIEW` badge links back to `/` with the token preserved.

## Verification

- Live in-browser against the real database: 72 runs, live ACWR **1.19**, the
  signal card showing **BUILD** from `/api/coaching`, and no console errors. The
  committed snapshot had `this_week_miles=16.73`; the live layer computed
  **25.82** from `/api/activities`.
- Five wire tests were added to `tests/test_dashboard_api_http.py`: the route is
  served with the bootstrap, the token is required, a query token is accepted,
  the route is `404` when the file is absent, and injection is idempotent.
- That moves the live suite from 502 to **507 passed, 1 skipped** (508
  collected) and the clean checkout from 473 to **478 passed, 30 skipped**.
  `docs/VERIFICATION_REPORT.md`, `docs/IMPLEMENTATION_INVENTORY.md`,
  `CREW_BRIEF.md`, `brief_facts.json` and the brief's quoted figures were
  updated to match.

## Still not done

CalTrak nutrition ingestion and the lifting-log importer remain unimplemented;
both CSVs are headers only, so there is no real data to ingest yet. Full Aurora
adoption (retiring the local dashboard) also remains the athlete's decision.

---

# Fifteenth correction: 2026-11-12, CalTrak nutrition ingestion

This is a code change, not a writer error. The athlete selected **Start CalTrak
ingestion** after the `/aurora` preview shipped. The backlog's Rank 1 task
`caltrak-nutrition-ingestion` is now implemented and moved to CLOSED TASKS; the
lifting importer and the rest of full Aurora adoption remain open.

## What was built

- `nutrition.py` parses a CalTrak export server-side. CalTrak emits one row per
  food entry, so `parse_caltrak_csv()` sums rows that share a date into one
  daily total. It accepts the app's header aliases (`date`/`day`,
  `calories`/`kcal`/`energy`, `protein`, `carbs`/`carbohydrates`/`carb`, `fat`),
  normalises `YYYY-MM-DD`, `YYYY/MM/DD`, `M/D/YYYY` and `M/D/YY`, treats empty
  numeric cells as zero, and rejects a missing date column, unparseable dates,
  and negative or non-numeric values.
- `GET /api/nutrition` is token/login-gated, rejects unknown query parameters
  with a `400`, and returns `{days, count, fields, source, storage}`. It is
  dispatched before `_api()` because it needs neither the database nor an
  `as_of` window, and it is deliberately not added to `API_ROUTES` so the
  `test_exactly_the_three_brief_routes_exist` pin still holds.
- `POST /api/nutrition` accepts `{"days": [...]}` or `{"csv": "..."}`. The CSV
  form keeps aggregation on the server instead of only in the browser. It
  upserts one row per date and returns `{accepted, upserted, total_days}`.
- The `/aurora` live layer now replaces `NUTRITION` from `GET /api/nutrition`,
  overrides `window.importCSV` to POST the raw CSV and reload, and maps the
  API's `calories` to the `kcal` field the committed FUEL view reads. Without
  that mapping the FUEL tab would have shown "not recorded" for every calorie
  total.

## Where the rows live

The committed `nutrition_log.csv` is a schema template and stays headers-only.
Ingested rows are written to `paths.data_dir()/nutrition_log.csv`, so athlete
nutrition is never published to the public repository. `GARMIN_NUTRITION_FILE`
overrides the path and the tests use it; no test reads or writes the athlete's
real log.

## Verification

- `tests/test_nutrition.py` (33 tests): aggregation across rows, sorted dates,
  fractional totals, empty cells, missing columns, header aliases, four date
  formats, every rejection path, payload normalisation, read/upsert idempotency,
  repeated-date update, schema header, corrupt-header error, missing file, and
  the committed template staying headers-only.
- `tests/test_dashboard_api_http.py` grew by 12 tests: the empty GET envelope,
  the token gate, query-parameter rejection, upsert and repeat-date update, raw
  CSV POST, malformed/non-JSON/non-object payloads, no CORS, and the Aurora
  bootstrap wiring.
- Verified in-browser against a synthetic two-day log: the FUEL tab listed both
  days (`Calories 2100 · Protein 150g`) and the run detail showed
  `1950 kcal · 140g protein · 200g carbs`, with no console errors.
- `nutrition.py` was added to `export_publish.PUBLISHED_MODULES`; without that
  the publish-scope guard reports a new root module as an unpublished stray.
- The live suite moves from 507 to **552 passed, 1 skipped** (553 collected) and
  the clean checkout from 478 to **523 passed, 30 skipped**.
  `docs/VERIFICATION_REPORT.md`, `docs/IMPLEMENTATION_INVENTORY.md`,
  `CREW_BRIEF.md`, `brief_facts.json` and the brief's quoted figures were
  updated to match. `KNOWN_UNBACKED` in `tests/test_brief_consistency.py`
  dropped `caltrak-nutrition-ingestion` because the brief now carries it in
  CLOSED TASKS.

## Still not done

The lifting-log importer (`GET`/`POST /api/lifts`, e1RM, bodyweight-adjusted
pull-ups/dips) is Rank 2 and remains unimplemented. `lifting_log.csv` is still
headers only. The bodyweight and weekly-summary endpoints, the queue retry
semantics, and retiring the local dashboard remain open.

# Sixteenth correction: 2026-11-12, what the launcher actually opens

## The gap

The fifteenth correction described `/aurora` and the nutrition work, but it did
not say how the athlete reaches the preview. The double-click launcher runs
`garmin_server.py --open`, and `--open` opened `/` - the unchanged local
dashboard - while the Aurora URL was only printed in the console window. The
athlete launched the dashboard, saw the old page, and reasonably concluded that
nothing had shipped. That was a reporting and product gap, not a data error.

## What changed

- `launch_url()` now returns `/aurora?tk=...` when the committed
  `flow_outputs/aurora_dashboard.html` exists, so `--open` lands on the
  preview.
- The fallback is `/`: a clean checkout without the committed app opens the
  local dashboard rather than a `404`.
- `/` remains the default route and still serves the local dashboard. Only the
  launch target changed; the server's canonical page did not.
- The existing-instance branch uses the same launch target, so double-clicking
  while a server is already up no longer reopens the old page.

## Verification

- Three wire tests pin the two branches and the port/token carried in the URL.
- The live suite is **555 passed, 1 skipped** (556 collected) and the clean
  checkout is **526 passed, 30 skipped**. `docs/VERIFICATION_REPORT.md`,
  `docs/IMPLEMENTATION_INVENTORY.md`, `SUPERVISOR_BRIEF.md` and
  `brief_facts.json` carry the new counts.

## Still not done

The full `adopt-flow-generated-dashboard` task remains open: the lifting
importer, bodyweight and weekly-summary endpoints, queue retry semantics, PWA
install path, and retiring the local dashboard are all still unimplemented.
`/aurora` is still a preview.

# Seventeenth correction: 2026-11-12, Aurora adopted, charts restored, mobile explained

## The gap

The athlete asked three questions after the sixteenth correction: why Aurora was
still a preview, why the graphs had disappeared, and why mobile had stopped
working. The honest answers were that adoption had never been finished, that
Aurora shipped with three canvases where the local page had ten, and that the
ngrok tunnel was simply not running. This entry records the code change and the
mobile finding.

## Aurora is the dashboard

- `/` now serves the committed `flow_outputs/aurora_dashboard.html` behind the
  existing token/login gate. The pre-Aurora page moved to `/classic`.
- `/aurora` remains an alias, so old bookmarks and the previous PWA `start_url`
  keep working.
- `/` falls back to the local page when the committed app is absent, so a clean
  checkout still opens a real dashboard instead of a `404`.
- `launch_url()` now always opens `/`; it no longer has to choose between two
  pages. `inject_pwa()` is applied to Aurora as well as the classic page.
- The live-data badge now reads `LIVE DATA` and links to `/classic` instead of
  pointing back at the page it is already on.

## Charts

- The artifact had three canvases (load, fitness, splits). The Analysis view now
  renders seven run-based charts: training load, weekly mileage, distance by run
  coloured by distance band, pace and heart rate, fitness scatter, run bubbles,
  and pacing fade. The run detail keeps the per-mile splits chart.
- Bodyweight and strength remain honest empty states: there is no bodyweight
  measurement and no confirmed strength session.
- Chart.js v4.4.4 is vendored at `flow_outputs/vendor/chart.umd.min.js` and
  served at `/vendor/chart.umd.min.js`. The server rewrites the artifact's
  `cdn.jsdelivr.net` URL at serve time, so charts work offline or behind a
  blocked CDN without editing the flow output.
- Chart creation is synchronous. The original `requestAnimationFrame` never ran
  in a background tab, which left blank canvases.
- `GET /api/activities` now carries `title`, `calories`, `avg_cadence`,
  `max_cadence`, `avg_pace_s_per_mi`, `best_pace_s_per_mi`,
  `training_stress_score`, and joins `garmin_export.csv` by `Source File` for
  `splits`, `best_5k_s` and `laps`. The database has no splits table; a missing
  or malformed CSV yields `null`, never an invented split.

## Mobile

- ngrok is installed at `C:\Users\benpi\coach-dashboard\ngrok.exe` (3.39.11),
  the saved authtoken is valid, and the reserved domain
  `https://foam-tackiness-header.ngrok-free.dev` starts successfully. **No new
  authtoken is needed.** The tunnel was not running, so the public URL was dead.
- `start-dashboard.cmd` starts the server and the tunnel together; the athlete
  must keep its window open. The public `/ping` returns `200`, and `/` and
  `/aurora` return the login page until the athlete signs in.
- LAN mode was re-verified on port 8804: `--lan` served `/ping` and `/aurora`
  over `http://192.168.12.146:8804`. Service workers still require https or
  localhost, so offline install works through the tunnel, not plain LAN http.

## Verification

- In-browser against the live database: 72 runs; the seven Analysis charts
  rendered with 72/72/72/31/72/72/72 points; the run-detail splits chart showed
  six mile splits; `/classic` still rendered its ten canvases; no console errors
  on either page.
- New tests cover the API summary fields and CSV splits (4), the CDN rewrite,
  vendored file and PWA tags (3), and the routing switch: `/` serves Aurora,
  `/aurora` aliases it, `/classic` serves the local page, and `/` falls back
  when Aurora is absent (3).
- The live suite is **565 passed, 1 skipped** (566 collected) and the clean
  checkout is **536 passed, 30 skipped**. `docs/VERIFICATION_REPORT.md`,
  `docs/IMPLEMENTATION_INVENTORY.md`, `SUPERVISOR_BRIEF.md` and
  `brief_facts.json` carry the new counts.

## Still not done

The lifting importer (`GET`/`POST /api/lifts`, e1RM, bodyweight-adjusted
pull-ups/dips) is still unimplemented, so the strength chart stays an empty
state. Bodyweight and weekly-summary endpoints, queue retry semantics, and
replacing the generated narrative panels with live text remain open. The
`Garmin Daily Sync` scheduled task is still Disabled.

# Eighteenth correction: 2026-11-12, CalTrak share target, one-tap Garmin sync, chart expansion

## The gap

After Aurora became canonical, the athlete still had to email a CalTrak CSV to
himself to get nutrition into the dashboard, and the Analysis view still felt
sparse compared with the classic page. This entry records the phone capture path
and the chart expansion.

## Phone capture

- CalTrak has no account or cloud API; its log lives on the device. The web
  manifest now declares a `share_target` for `/share-target` (`POST`,
  `multipart/form-data`, one file field `log`), so once the PWA is installed,
  CalTrak's Share Log appears in Android's share sheet and posts the CSV straight
  to the server.
- Chrome routes the POST through the service worker, which forwards
  `{csv: text}` to `/api/nutrition`. `POST /share-target` is the server fallback
  for the first share before the worker is active. `multipart_file_text()`
  parses the body because Python 3.13 removed `cgi`. Both paths aggregate with
  `parse_caltrak_csv()` and redirect to `/?shared=ok|empty|error`.
- The Aurora FUEL importer now POSTs to `/api/nutrition` instead of writing
  browser `localStorage`, so the phone and laptop share one log.
- The home view has a `Sync Garmin now` button that POSTs `/sync` (download then
  `trainloop.py bootstrap`) and reloads from the API. The same button works on
  the phone and the laptop. No new ngrok authtoken is needed.

## Charts

- The Analysis view now renders nineteen run-based charts in seven labelled
  groups: Volume, Intensity & effort, Mechanics & terrain, Performance &
  pacing, Consistency, Body & strength, Coaching.
- New data-backed charts: monthly mileage, cumulative mileage, TSS, calories,
  average vs maximum HR, climbing cost, cadence, elevation gain, pace
  distribution, best 5K trend, latest-run splits, training-calendar heatmap,
  days between runs, and runs per month.
- `chartOrEmpty()` gives every no-data chart a named empty state instead of a
  blank canvas. TSS is blank in every source record; bodyweight and strength
  have no data at all.
- The live layer exposes `window.auroraReloadAll` and
  `window.auroraReloadNutrition`, and `mapRun` now carries `tss` and
  `maxCadence`.

## Verification

- In-browser against the live database: 72 runs; nineteen Analysis charts
  rendered with data (72 points on each run-based chart, 62 weeks, 16 months,
  115 heatmap days); six mile splits on the latest run; no console errors.
- New wire tests cover the manifest `share_target`, multipart parsing (3),
  `/share-target` ingestion (3), and the live layer's reload hooks (1).
- The live suite is **573 passed, 1 skipped** (574 collected) and the clean
  checkout is **544 passed, 30 skipped**. `docs/VERIFICATION_REPORT.md`,
  `docs/IMPLEMENTATION_INVENTORY.md`, `SUPERVISOR_BRIEF.md` and
  `brief_facts.json` carry the new counts.

## Still not done

The lifting importer is still unimplemented, so the strength chart stays an
empty state. Bodyweight and weekly-summary endpoints, queue retry semantics,
and replacing the generated narrative panels with live text remain open. The
`Garmin Daily Sync` scheduled task is still Disabled.

# Nineteenth correction: 2026-11-12, seamless Health Connect nutrition, JSON backups

## The gap

The eighteenth correction made CalTrak's share sheet reach the server, but that
still required the athlete to open CalTrak, choose Share Log, and pick Coach
Dashboard every time. The request was for a path where none of that is
required. The same correction also assumed CalTrak exports CSV; the app's
backup is JSON.

## What was verified before coding

- CalTrak has no account or cloud API. On Android it can write food, weight and
  body-fat entries to **Health Connect** when the athlete grants that access.
- **HC Webhook** (`com.hcwebhook.app`) reads Health Connect and POSTs JSON to a
  configurable URL, on an interval, on a schedule, on demand, or from a widget,
  Quick Settings tile or broadcast. It supports Nutrition fields
  (`calories`, `protein_grams`, `carbs_grams`, `fat_grams`, etc.), custom
  headers, and a Daily resolution (`RESOLUTION_DAILY = -1`) that sends one
  authoritative total per calendar day.
- The app is a one-time purchase on the Play Store (about $14.99) and also
  publishes a free FOSS APK on GitHub releases (v1.9.32,
  `app-foss-release.apk`, 3,698,980 bytes). The free APK is the recommended
  path.
- Its default sync is incremental over a rolling 48-hour window. Keeping raw
  records by Health Connect id is therefore necessary so a later payload with
  one new food entry does not replace the whole day.
- Payload timestamps must stay on **Local time**; a UTC daily record is
  ambiguous without a zone offset.

## What changed

- `nutrition.py` now accepts a CalTrak JSON backup as well as CSV, via
  `parse_caltrak_json()` and `parse_export()` auto-detection. The backup schema
  is unpublished, so a tolerant walker finds dated nutrition objects and stops
  at the first nutrition-bearing dict so a meal total and its child items are
  never counted twice.
- `POST /api/nutrition` accepts `{"days": [...]}`, `{"csv": "..."}`,
  `{"json": ...}`, `{"backup": ...}`, or a raw backup object. `POST
  /share-target` and the service worker's `{csv: text}` forward both go through
  `parse_export()`, so a JSON share works too.
- New `POST /api/nutrition/hook` is the phone bridge endpoint and sits above the
  browser session gate. It requires a dedicated `X-Nutrition-Token` (or
  `Authorization: Bearer`) that is separate from the dashboard login token and
  grants access to nothing else. The secret is generated once and stored beside
  the local log as `nutrition_log.hook-token`; it is never committed.
- New `GET /api/nutrition/hook-info` is behind the normal gate and returns the
  path, header name, token, last upload time and managed-day count. The Fuel
  view has an **Automatic upload** card that shows these values, copy buttons,
  and the one-time setup steps; the manual importer is now labelled **Import
  backup** and accepts `.csv` or `.json`.
- `ingest_health_connect()` keeps raw NutritionRecords by `metadata.id` in
  `nutrition_log.records.json`. A Daily record (interval at least 20 hours, no
  id) supersedes raw records for its date. Deletions are applied by id. Dates
  the webhook manages are replaced wholesale, while manually imported dates are
  preserved.

## Verification

- Unit tests in `tests/test_nutrition.py` cover daily and raw Health Connect
  records, incremental sync, edits, deletions, daily-supersedes-raw, manual-day
  preservation, JSON backups, `parse_export()`, hook-token stability and
  `hook_info()` (48 tests).
- Wire tests in `tests/test_dashboard_api_http.py` cover `hook-info` auth and
  stability, valid/missing/wrong/dashboard tokens, Bearer auth, incremental
  records, deletions, Daily records, no CORS headers, JSON `/api/nutrition`
  forms, and a JSON `/share-target` (91 tests).
- The live suite is **603 passed, 1 skipped** (604 collected) and the clean
  checkout is **588 passed, 16 skipped**. `ruff check .` is clean.
- The webhook has not yet received a live phone payload, and CalTrak's Health
  Connect write behavior has not been confirmed on the athlete's specific
  device. Those remain the acceptance step, not a claim.

## Still not done

The lifting importer is still unimplemented, so the strength chart stays an
empty state. Bodyweight and weekly-summary endpoints, queue retry semantics,
and replacing the generated narrative panels with live text remain open. The
`Garmin Daily Sync` scheduled task is still Disabled.
