# Implementation inventory

Supervisor brief Task 1. Verified against the working tree on 2026-10-01.

| | |
| --- | --- |
| Repository | `benpioske-del/garmin-export` |
| Branch | `main` |
| Python | 3.13.15 |
| Git | 2.53.0.windows.4 |
| Tests | 207 passed, 1 skipped (Windows symlink case) |
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
| 8 | Health data with consent boundary | Partial — boundary implemented, no auth |
| 9 | Weather enrichment gate | Partial — gate implemented, no provider |
| 10 | Verification documentation | Implemented |
| 11 | Dashboard | Pre-existing, local-only, unversioned |
| 12 | Brief transport | Implemented, live; cross-second idempotency fixed in `3054d6a` |
| 13 | Quality gates and CI | **Not started** — supervisor brief Task 7 |

## Data layer

Created in this round. The brief assumed an existing data layer; there was none
(no `migrations/`, `schema.sql`, `models/`, `db/`, `api/`, and no
`sqlite3`/`sqlalchemy`/`flask`/`fastapi` import anywhere), so one was
established as the minimum that satisfies the requirement.

| Component | Path | Notes |
| --- | --- | --- |
| Connection + migration runner | `trainingdb.py` | stdlib `sqlite3`, no new dependency |
| Migrations | `migrations/001`–`006` | numbered SQL, applied in order, checksum-guarded |
| Database file | `trainloop.db` | **gitignored**, local only |
| Terminology | `terms.py` | shared by every module below |
| Activities | `activities.py` | canonical records, provenance, review, audit |
| Strength | `strength.py` | sessions → exercises → sets |
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
| FIT reader | `garmin_fit_reader.py` | `__version__ = 1.0.0`; asserts no GPS field escapes |
| CSV export | `garmin_export.csv` | 57 activities, 29 columns |
| Publisher | `export_publish.py` | guard, remote sync, history-safety enforcement |
| Sync | `garmin_sync.py` | OAuth, local only |
| Trigger server | `garmin_server.py` | localhost static + trigger routes; **not** an API |
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
| `python -m pytest` | Works. 207 passed, 1 skipped. |
| `python export_publish.py` | Works. Guard + push. |
| `python fit_audit.py` | Works. Deterministic, hash-per-file. |
| `python trainingdb.py migrate` | Works. Idempotent. |
| Linter | **None configured** |
| Formatter | **None configured** |
| Type checker | **None configured, no annotations** |
| CI | **None** — no workflow, no pre-commit |
| Dependency lockfile | **None** (`pyproject.toml` only) |
| `python -m build` | Not verified; the `build` package is not a declared dependency |

Style is followed by convention rather than enforced by a tool. The 19 Python
modules use the existing naming and formatting, but nothing would catch a
regression in it.

## Data state

- 57 FIT files, all parse, all with GPS and a usable timestamp
- 57 activities imported, 0 unreadable
- 505 laps, 52,213 records, 52,197 position points
- Re-import of identical files: 57 `unchanged`, 0 audit rows written
- **1 open date gap**: 2026-06-26 to 2026-07-05
- **57 open `timezone_uncertain` reviews**, expected until an offset is confirmed
- 1 activity where the local date and UTC date differ
  (`garmin:23745136848`, local 2026-07-26T01:10:15, UTC 2026-07-27T01:10:15Z)
- 0 strength sessions. `strength_load` is `null` while this is true, which is
  not the same as zero.

These three sources agree at **57** each. An earlier brief asserted a
55/56/59 discrepancy; that premise was checked against the live corpus and is
not supported — there is nothing to reconcile.

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
   missing field, because 57 reviews are waiting on it.
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

- The **152-test** count was stale; it is 207.
- **`profile.json` was described as empty**; it carries `hr_max` and field
  notes, and only the remaining fields are `null`.

One claim could not be sourced at all and was withdrawn rather than carried
forward: an earlier brief stated that 53 of 55 runs fall in HR Zone 5. There is
no HR zone classification anywhere in this repository — every occurrence of
"zone" in the source is `timezone_source` — and `53` and `55` appear in these
docs only inside the Git version string `2.53.0.windows.4`. Any future brief
asserting zone distribution should be treated as unfounded until code for it
exists.
