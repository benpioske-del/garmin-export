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

## Standing rule

Do not copy a figure out of a brief into code, a document that will outlive the
brief, or a commit message. Query it, or cite where it came from and when it was
measured.