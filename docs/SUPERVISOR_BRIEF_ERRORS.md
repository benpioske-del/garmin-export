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

## Standing rule

Do not copy a figure out of a brief into code, a document that will outlive the
brief, or a commit message. Query it, or cite where it came from and when it was
measured.

When a brief describes a file, a count, or a state, establish what the brief
process could actually see before acting on the description. If the answer is
"nothing", the description is invention and the gap is in observability, not in
the work.