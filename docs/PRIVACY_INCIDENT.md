# Privacy Incident: Coordinates Published to a Public Repository

Date: 2026-09-29. Repository: `benpioske-del/garmin-export` (public).

Exact GPS coordinates, the athlete's town, and a coordinate bounding box were
published to a public repository and were recoverable from its history after
being removed from the current tree. History was rewritten to remove them.

## What was published

| Item | Where | Detail |
| --- | --- | --- |
| Per-run coordinates | `dashboard/index.html`, commits `ddc04b8` and `f713e13` | 12 latitude/longitude pairs, one per activity, with dates |
| Athlete's town | `Title` column of `garmin_export.csv`, 6 commits | Named the home town on 36 activity rows |
| Bounding box | `docs/FIT_DATA_AUDIT.md` | Latitude and longitude range of all 51,637 points: an 11 km × 24 km box around the home |
| Realistic test fixtures | `tests/test_capture_supervisor.py`, `tests/test_gps_guard.py` | literal:the athlete's home area city centre and downtown literal:the home metro |

The bounding box and the test fixtures were found only while auditing for this
cleanup. The first two were known at the time of the initial containment; the
other two would have survived a fix scoped only to the dashboard.

## How it happened

The dashboard is generated locally and embeds one latitude and longitude per
activity so it can fetch weather without a network round trip per run. A routine
code move into the repository committed it, because the guard in place checked
for secrets and tokens but not for coordinates, and nothing marked the file as
local-only.

## What is now in place

- `export_publish.py` has a content guard that refuses to publish any file
  containing a coordinate-shaped value, a FIT semicircle field, or a CSV
  latitude/longitude column.
- `dashboard/` is gitignored.
- Test fixtures use synthetic open-ocean coordinates (41.6001, -30.5001). They
  trip the scanner by shape and mean nothing geographically.

## History rewrite

Three `git-filter-repo` passes over all 28 commits:

1. `--invert-paths --path dashboard/index.html` removed the file entirely.
2. A blob callback blanked the `Title` column in every historical CSV.
3. `--replace-text` (see `tools/privacy_replacements.txt`) removed the bounding
   box and the superseded fixture coordinates from earlier commits.

Verification after the rewrite: every commit was grepped for all eight known
coordinate values, the dashboard path, and the town name. All clean, including
unreachable objects.

## The rewrite was silently undone once

This is the part worth remembering.

`sync_with_remote()` in `export_publish.py` recovers from a rebase conflict by
running `git reset --hard origin/<branch>`, so the scheduled publisher can never
get wedged behind a commit made by someone else. After the rewrite, the next
publisher run saw the rewritten remote as "behind", tried to rebase, hit a
conflict, and reset the local repository back onto the old remote history. It
then pushed, and the leaked commits went straight back onto GitHub.

The rewrite itself was correct. The publisher threw it away and reported success
while doing so, because a plain `git push` of the resurrected history
succeeded.

The fix is a `merge-base` check: a rewritten history shares no common ancestor
with the old one, and that is never auto-resolved. The publisher now aborts and
tells the operator to force-push. `tests/test_history_safety.py` covers it with
a genuinely divergent history, built as an orphan commit because an amended
force-push still shares an ancestor and would not exercise the check.

**Lesson: any destructive history operation has to be defended against the
automation that runs unattended.** A scheduled job that can reset the working
tree will eventually undo a manual repair and report that it succeeded.

## Residual exposure

**GitHub retains unreachable objects for a period after a force-push.** The old
commit is no longer reachable from `main` and no longer appears in the branch
history, but `raw.githubusercontent.com` and the commits API still served it
while this was being written. That is server-side retention, not a failed
rewrite; there is no way to force it from the client. It resolves on GitHub's
own schedule. If any of this needs to be gone sooner, deleting and recreating
the repository is the reliable option, at the cost of the URL changing.

Anyone who cloned or forked the repository before the rewrite still has the
original objects locally. The rewrite makes the data unreachable through normal
browsing; it cannot recall what was already downloaded.

The pre-rewrite local mirror taken as a rollback safety net has been deleted
after the rewrite was verified.

**This repository is public. That is the underlying risk.** Exact home
coordinates in a public dataset are a durable disclosure. The pipeline can
enforce "never publish coordinates"; it cannot make the data non-sensitive.

## Verifying, and the CDN trap

Check the result through the **GitHub contents API**, not `raw.githubusercontent.com`.
The raw CDN served stale content for several of the checks above, which
produced false positives for files that were already fixed. A cache-busting
query parameter does not reliably defeat it.

Note also that `docs/PRIVACY_INCIDENT.md` legitimately contains the coordinate
values it documents removing, and a docstring may name the old fixtures. A grep
for known values across the published tree will hit those on purpose. The
meaningful checks are the published CSV, the audit doc, and the test fixtures.

## If this recurs

`git-filter-repo` is installed (`pip install git-filter-repo`). Verify with a
per-commit grep of the known values rather than trusting the tool's report, and
run `export_publish.py` afterwards to confirm it did not reset the rewrite back
onto the remote.
