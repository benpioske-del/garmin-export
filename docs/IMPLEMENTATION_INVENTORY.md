# Implementation inventory

Supervisor brief Task 1. Verified against the working tree on 2026-10-01.

| | |
| --- | --- |
| Repository | `benpioske-del/garmin-export` |
| Branch | `main` |
| Python | 3.13.15 |
| Git | 2.53.0.windows.4 |
| Tests | 407 passed, 1 skipped (Windows symlink case) |
| `OPENCODE_INSTRUCTIONS.md` | **Absent.** Searched repository, parent, and local project directories. |

## Current status

| Task | Area | Status |
| --- | --- | --- |
| 1 | Inventory and documentation | Implemented |
| 2 | Canonical activity model, provenance, audit | Implemented |
| 3 | FIT data audit, hashes, parser versions | Implemented |
| 4 | Strength domain | Implemented |
| 5 | Training load, 7/14/28-day windows | Implemented |
| 6 | Recommendations and safety boundaries | Implemented |
| 7 | Shared terminology | Implemented |
| 8 | Health data with consent boundary | Partial â€” boundary implemented, no auth |
| 9 | Weather enrichment gate | Partial â€” gate implemented, no provider |
| 10 | Verification documentation | Implemented |
| 11 | Dashboard | Pre-existing, local-only, unversioned |
| 12 | Brief transport | Implemented, live; cross-second idempotency fixed in `3054d6a` |
| 13 | Quality gates and CI | **Not started** â€” supervisor brief Task 7 |

## Data layer

Created in this round. The brief assumed an existing data layer; there was none
(no `migrations/`, `schema.sql`, `models/`, `db/`, `api/`, and no
`sqlite3`/`sqlalchemy`/`flask`/`fastapi` import anywhere), so one was
established as the minimum that satisfies the requirement.

| Component | Path | Notes |
| --- | --- | --- |
| Connection + migration runner | `trainingdb.py` | stdlib `sqlite3`, no new dependency |
| Migrations | `migrations/001`â€“`006` | numbered SQL, applied in order, checksum-guarded |
| Database file | `trainloop.db` | **gitignored**, local only |
| Terminology | `terms.py` | shared by every module below |
| Activities | `activities.py` | canonical records, provenance, review, audit |
| Strength | `strength.py` | sessions â†’ exercises â†’ sets |
| Load | `loadcalc.py` | versioned `load-1.0.0`, windows 7/14/28 |
| Recommendations | `recommend.py` | six control states, refusal-first |
| Health | `health.py` | consent-gated, access-logged |
| Weather | `weather.py` | gate; no coordinates stored |

Design decisions:

- **stdlib `sqlite3` only.** No ORM, no new dependency, no build step. A single
  local file that is never published.
- **Editing an applied migration is a hard error.** The runner compares SHA-256
  and refuses to proceed, so schema history cannot drift silently.
- **`activities` is the system of record.** The CSV is a published view of it.
- **No REST API, no web framework, no auth, no UI** was created. None was
  present to extend, and inventing them was not in scope.

Docs: [`DATA_QUALITY.md`](DATA_QUALITY.md),
[`FIT_AUDIT.md`](FIT_AUDIT.md),
[`STRENGTH_DATA_CONTRACT.md`](STRENGTH_DATA_CONTRACT.md),
[`TRAINING_LOAD_METHODOLOGY.md`](TRAINING_LOAD_METHODOLOGY.md),
[`COACHING_SAFETY_BOUNDARIES.md`](COACHING_SAFETY_BOUNDARIES.md),
[`DATA_QUALITY_TERMINOLOGY.md`](DATA_QUALITY_TERMINOLOGY.md),
[`WEATHER_ENRICHMENT_GATE.md`](WEATHER_ENRICHMENT_GATE.md)

## Existing pipeline (unchanged)

| Component | Path | Notes |
| --- | --- | --- |
| FIT reader | `garmin_fit_reader.py` | `__version__ = 1.1.0`; asserts no GPS field escapes; attaches internal elevation diagnostics (`_ascent_smoothed_ft`, `_elev_range_ft`) that are excluded from the published CSV |
| CSV export | `garmin_export.csv` | 58 activities, 29 columns |
| Publisher | `export_publish.py` | guard, remote sync, history-safety enforcement |
| Sync | `garmin_sync.py` | OAuth, local only |
| Trigger server | `garmin_server.py` | localhost static + trigger routes, plus a read-only JSON API: `/api/activities`, `/api/load`, `/api/coaching` |
| Audit | `fit_audit.py` | rewritten: hashes, parser versions, counts only |
| Brief bridge | `brief_bridge.py` | `post` / `ingest` / `paste` / `serve` / `capture` |
| Profile | `profile.json` | `hr_max` set to 198; `age`, `sex`, `resting_hr`, `weight_lb`, `height_in` still `null` |

The profile's empty fields are a live blocker, not a cosmetic gap: the timezone
offset and a weather location policy would live there, and neither exists yet.
`hr_max` is populated, so any brief describing the profile as empty is reading
an out-of-date copy of this document.

## Tooling

| Tool | Status |
| --- | --- |
| `python -m pytest` | Works. 407 passed, 1 skipped. |
| `python export_publish.py` | Works. Guard + push. |
| `python fit_audit.py` | Works. Deterministic, hash-per-file. |
| `python trainingdb.py migrate` | Works. Idempotent. |
| Linter | **None configured** |
| Formatter | **None configured** |
| Type checker | **None configured, no annotations** |
| CI | **None** â€” no workflow, no pre-commit |
| Dependency lockfile | **None** (`pyproject.toml` only) |
| `python -m build` | Not verified; the `build` package is not a declared dependency |
| Database vs export parity | **Verified 2026-10-04.** FIT directory, `garmin_export.csv` and `trainloop.db` all hold 58. Note `load` computes only; `bootstrap` is what imports. |
| `garmin_export.csv` provenance | Rebuilt in-process with `export_publish.build_csv()` on 2026-10-03, not committed. It picks up `2026-10-01` from the FIT directory. |

Style is followed by convention rather than enforced by a tool. The 21 Python
modules use the existing naming and formatting, but nothing would catch a
regression in it.

## Data state

- 58 FIT files on disk, all parse, all with GPS and a usable timestamp
- 58 rows in `garmin_export.csv`
- 58 activities imported into `trainloop.db`, newest `2026-10-01`
- 523 laps, 54,652 records, 54,636 position points
- Re-import of identical files: 58 `unchanged`, 0 audit rows written
- **1 open date gap**: 2026-06-26 to 2026-07-05
- **58 open `timezone_uncertain` reviews**, expected until an offset is confirmed
- **1 open `activity_gap` review** for the 2026-06-26 to 2026-07-05 gap
- 1 activity where the local date and UTC date differ
    (`garmin:23745136848`, local 2026-07-26T01:10:15, UTC 2026-07-27T01:10:15Z)
- 0 strength sessions. `strength_load` is `null` while this is true, which is
  not the same as zero.

All three sources now agree at **58**: FIT directory, CSV, and database. An
earlier brief asserted a 55/56/59 discrepancy; that premise was checked against
the live corpus and is not supported â€” there was nothing to reconcile. The
database was one run behind until `trainloop bootstrap` was re-run on
2026-10-04; it is the import step that closes this, not `load`, which only
computes.

## Publish lock and repo visibility

Two scheduled tasks (`Garmin Export Publish`, `Garmin Export Publish PM`) run the
publisher unattended at 07:15 and 18:15. It commits and pushes whatever is in the
working tree, which is how half-finished work reached the public repo once already.

The coach now brackets its work with the publish lock:

```
python export_publish.py --lock      # scheduled runs stand down, exit 0, push nothing
python export_publish.py --unlock    # released even on failure; 45 min staleness anyway
```

The lock lives in the local data directory, so it can never be committed or read by
the crew. `CREW_TASKS.md` documents the protocol.

`repo_visibility` in `garmin_export.meta.json` used to be the literal string
`"public - readable without a token"`. It is now **probed** on every run, by issuing
an anonymous `HEAD` to the raw URL: that is exactly the property the supervisor flow
depends on, and it needs no token to test. The owner may make the repo private, so the
publisher prints fetch instructions that match the probed state — plain `curl` while
public, the contents API with `$GITHUB_TOKEN` while private, and the conservative
token form when the probe cannot reach GitHub.

Making the repo private stops future reads; it does not un-publish what was already
committed while public.

`guard_token_content()` scans the text files a commit would contain for credential
patterns, reusing `SECRET_PATTERNS` from `capture_supervisor_brief.py` rather than
duplicating them. `guard_secrets()` only inspected file *names*, so a token pasted into
prose would have passed. Exemptions are explicit (`GUARD_IMPL`,
`SYNTHETIC_CREDENTIAL_FILES`) and each is pinned to a file that exists, because an
exemption for a deleted file is a silent hole.

## Coaching rationale fixtures

`tests/recommend_snapshots.py` pins the output of every reachable coaching
branch to a golden JSON file under `tests/fixtures/recommend/`, built from the
scenarios in `tests/recommend_scenarios.py`. Re-record with
`REGENERATE_SNAPSHOTS=1`, then read the diff.

Determinism is pinned two ways: `as_of` is a fixed instant, so the 7-day window
does not slide with the calendar, and `hr_max` is supplied rather than inferred.
Every scenario builds its database at an explicit path via
`trainingdb.connect(path=...)`; the environment variable is never set.

Reachability is established by sweeping 3600 database shapes rather than by
reading the source, because `STATE_DELOAD` *is* present in `recommend.py` inside
a branch nothing can reach.

Writing these found four defects, documented in
[COACHING_POLICY_AUDIT.md](COACHING_POLICY_AUDIT.md):

- `deload` is unreachable. The acute:chronic ratio is a 7-day sum over a 28-day
  sum, and the acute window is a subset of the chronic one, so the ratio is
  bounded by 1.0 while `HIGH_ACWR` is 1.5. The policy cannot recommend reducing
  load.
- The 1.3-1.5 caution band is dead for the same reason.
- `recover` is in `CONTROL_STATES` and returned by `available_states()`, but no
  branch produces it.
- A missing `hr_max` is reported as "only 0 runs in 28 days" rather than as a
  missing input, because runs without a computable load are dropped before being
  counted as days.

None are fixed here: each changes what the athlete is told, so they are policy
decisions rather than bugs to patch. Each is asserted in the suite, so a change
in either direction has to be acknowledged.

21 tests, plus 9 golden files.

## Dashboard data-source contract

`dashboard_contract.py` audits the private dashboard and writes
`docs/DASHBOARD_AUDIT.md`, which is committed. It exists because the dashboard
is gitignored: the brief process could not read it, so it described a file it
had never seen, guessed its contents twice, and re-issued
`connect-dashboard-to-data-layer` after that work was finished and merged.

The dashboard declares its own sources in a `window.DASHBOARD_SOURCES` block.
The contract checks that declaration against the document and fails on drift:

- every column-0 declaration is classified as private-journal, static table or
  scratch, so inline data cannot be added without saying what it is
- the canonical panel must fetch all three API routes, each with its own
  rejection handler, and must have a failure renderer that writes visible text
- the canonical panel may not read any private-journal declaration. This is the
  check that stops the two datasets being conflated.
- legacy features *may* still read the journal. Deleting it is not the fix: it
  holds narrative notes, splits, hydration, injury flags, weight and
  coordinates that exist in no FIT file.

Verified by mutation, not assertion. Ten realistic regressions are applied to
the real document in `tests/test_dashboard_contract.py` and every one must fail
the audit. Two of them were originally missed -- a keyword match for
"Unavailable" survived deleting the failure handler, and a forward scan for
`.then(` let one route claim another's handler. Both checks are now structural.

36 tests.

## Dashboard JSON API

Added for supervisor brief `connect-dashboard-to-data-layer`. Three read-only
same-origin GET routes, served by the existing locked-down `garmin_server.py`:

| Route | Source of truth | Notes |
| --- | --- | --- |
| `GET /api/activities` | `activities` + `review_items` + `activity_raw_refs` | canonical rows, open reviews preserved, `source_file` resolved from the raw-ref table rather than reconstructed |
| `GET /api/load` | `loadcalc.compute()` | 7/14/28 windows with real bounds; `algorithm` is `loadcalc.LOAD_VERSION` |
| `GET /api/coaching` | `recommend.recommend()` | refusal-first; `refused` is derived from `advisory`, not re-decided |

Design constraints, all test-enforced:

- **Nothing is recomputed.** The routes call the same functions the CLI calls, so
  the dashboard and `trainloop.py` cannot disagree about a number.
- **No count, version or threshold is written down.** Everything is queried. A
  brief asserting a wrong figure cannot make the API wrong.
- **`null` is not `0`.** `strength_load` stays `null` because no confirmed
  strength sessions exist; every window value is `null` on an empty database.
- **A refusal is not advice.** `refused` is true whenever `recommend` returns a
  non-advisory state, and the dashboard renders it as a refusal.
- **No stale fallback.** If the API fails the panel says so instead of falling
  back to the inline arrays still present elsewhere in the dashboard.
- **No traceback or path in a response.** 5xx returns
  `{"error": "internal error"}`; detail goes to stderr only.

Behind the existing `X-Dash-Token` gate and the `Host` header check. No CORS
headers are sent. Unknown query parameters are a 400 rather than being ignored,
because a silently ignored typo looks like a filter that did nothing. `as_of`
accepts UTC ISO-8601 and is validated.

The pre-existing `fit-list`, `fit/<name>`, `ping`, `sync` and cloud routes are
unchanged, covered by regression tests in `tests/test_dashboard_api_http.py`.

Tests: `tests/test_dashboard_api.py` (38) and `tests/test_dashboard_api_http.py`
(22). `smoke_dashboard_api.py` runs the same paths against the live database and
is deliberately not part of pytest.

`dashboard/index.html` is untracked and gitignored because it contains
hand-entered athlete data, so the panel markup is not in version control. It is
appended as a self-contained IIFE that reads its own token from the URL and
exposes `window.refreshApiPanel()`.

## Privacy posture

- Raw FIT files and `trainloop.db` are gitignored.
- Position data is never decoded into any report, doc or database row.
- `weather_observations` has no coordinate columns, enforced by a test.
- `export_publish.py` blocks any commit containing position data; the
  `dashboard/` directory is gitignored.
- **Known gap:** the guard cannot reject a bare single coordinate, because a
  decimal like `44.95` is indistinguishable from legitimate training data. The
  guard catches labelled fields, coordinate pairs, semicircle names and CSV
  coordinate columns. Manual review is still required.

## Known blockers

1. `profile.json` is **partially** populated, not empty. `hr_max` is set to
   198 (a deliberate choice above the observed 195 peak); `age`, `sex`,
   `resting_hr`, `weight_lb` and `height_in` are still `null`. The missing
   values block confirmed local dates, cohort percentiles and the weather
   location policy. The athlete's UTC offset is the single highest-value
   missing field, because 58 reviews are waiting on it.
2. No authentication and no multi-athlete separation. The health boundary is
   single-subject and described that way, not dressed up as a permission system.
3. ~~The transport is not live.~~ **Resolved.** The CrewAI flow pushes
   `SUPERVISOR_BRIEF.md` directly to `main`, and the bridge additionally accepts
   inbox drops and clipboard paste. See `docs/SUPERVISOR_BRIDGE.md`.
4. ~~`commit_brief()` regenerates `captured_utc`, breaking idempotency across
   seconds.~~ **Fixed** in `3054d6a`. The file's identity is now `brief_id`, the
   SHA-256 of the brief text; `captured_utc` is metadata and no longer affects
   identity. Covered by tests that advance a frozen clock 90 seconds, because
   the previous test passed only by committing twice inside one second.
5. GitHub retains old unreachable commits by SHA. Current `main` is clean;
   removal requires deleting and recreating the repository.
6. No CI, linter, formatter, type checker or dependency lockfile. This is
   supervisor brief Task 7 and is the largest remaining gap in release
   controls.

## Corrections made to this document

The supervisor reads this file and `VERIFICATION_REPORT.md` as its evidence
base, so a stale number here becomes a wrong instruction in the next brief.
Two things were corrected on 2026-10-01 after a run acted on them:

- The **152-test** count was stale; it is 407.
- **`profile.json` was described as empty**; it carries `hr_max` and field
  notes, and only the remaining fields are `null`.

One claim could not be sourced at all and was withdrawn rather than carried
forward: an earlier brief stated that 53 of 55 runs fall in HR Zone 5. There is
no HR zone classification anywhere in this repository â€” every occurrence of
"zone" in the source is `timezone_source` â€” and `53` and `55` appear in these
docs only inside the Git version string `2.53.0.windows.4`. Any future brief
asserting zone distribution should be treated as unfounded until code for it
exists.
