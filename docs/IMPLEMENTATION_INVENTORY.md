# Implementation Inventory

Established by direct repository inspection on 2026-09-29. Every path below was
confirmed to exist (or confirmed absent) by reading the working tree, not inferred.

## OPENCODE_INSTRUCTIONS.md

**Result: NOT FOUND.** The file does not exist in this repository, its parent
directory, the CrewAI bridge project, or the Downloads folder, and a recursive
case-insensitive search of the repository returned zero matches. No
`AGENTS.md`, `CLAUDE.md`, or `CONTRIBUTING.md` exists either.

This inventory therefore uses **repository evidence only**. Nothing here is
inferred from an instruction file.

## What this project actually is

A **single-athlete, single-user local pipeline**, not a web application. It
downloads Garmin FIT files, converts them to one CSV, and publishes that CSV to
a public GitHub repository for a browser-rendered dashboard to consume.

There is no database, no ORM, no migration system, no web framework, no user
accounts, and no frontend build. The "backend" is a set of Python scripts and
one localhost-only file server.

This distinction matters for the task list: several requested tasks specify
"the project's existing schema layer", "the existing API/service layer", or
"existing auth and authorization patterns". **None of those exist.** Those tasks
are greenfield, not modification, and are recorded as such under Blockers.

## Repository layout

| Path | Role |
|---|---|
| `export_publish.py` | Publishes the CSV. Owns the privacy guards and the remote-sync logic. 683 LOC, the largest module. |
| `garmin_fit_reader.py` | Parses FIT files into activity records. The only parser. 180 LOC. |
| `garmin_sync.py` | Logs into Garmin Connect and downloads FIT files. 518 LOC. |
| `garmin_server.py` | Localhost-only file server for the dashboard. 418 LOC. |
| `capture_supervisor_brief.py` | Captures a supervisor brief and scans it for sensitive content. 194 LOC. |
| `brief_bridge.py` | Receives a brief from the cloud flow over three transports and commits it. 1 file, see `docs/SUPERVISOR_BRIDGE.md`. |
| `fit_audit.py` | Audits FIT parsing results. 104 LOC. |
| `fit_gps_validate.py` | Validates whether FIT files carry usable GPS. 66 LOC. |
| `paths.py` | Central path resolution. 39 LOC. |
| `profile.json` | Athlete parameters. **All values null.** |
| `garmin_export.csv` | The canonical published dataset: 56 rows, 29 columns. |
| `garmin_export.meta.json` | Publisher bookkeeping. |
| `publish_state.json` | Publisher bookkeeping. |
| `docs/` | Audit, provenance, privacy, and labelling documentation. |
| `tests/` | 65 pytest tests across 7 files. |
| `dashboard/` | **Gitignored.** Local-only HTML; embeds exact per-run GPS. |

## Data model

There is no schema file. The canonical record is the **CSV header**, which is the
contract for the published data:

```
Activity Type, Date, Favorite, Title, Distance, Calories, Time, Avg HR, Max HR,
Avg Run Cadence, Max Run Cadence, Avg Pace, Best Pace, Total Ascent,
Total Descent, Avg Stride Length, Training Stress Score, Steps, Decompression,
Best Lap Time, Number of Laps, Moving Time, Elapsed Time, Min Elevation,
Max Elevation, Date (UTC), Timezone Status, Source, Source File
```

- `Date` is a **local date reconstructed from the FIT filename**, not a
  timezone-corrected instant.
- `Date (UTC)` and `Timezone Status` were added to make that limitation explicit
  rather than silent. See `docs/PROVENANCE.md`.
- `Title` is blank by policy. GPS columns are excluded by policy.

## Importers and parsers

- **FIT**: `garmin_fit_reader.py`, using `fitparse`. This is the only parser and
  is reused for all FIT work. It reads UTC from the FIT timestamp, reconstructs
  the local date from the filename, and deliberately drops `position_lat` /
  `position_long` / `nec_lat` / `nec_long`.
- **Garmin Connect download**: `garmin_sync.py`, using `garminconnect`.
- **CSV fallback**: handled in `export_publish.py`. A 57th row from a stale CSV
  fallback was a duplicate of a FIT record and was collapsed during Task 2.
- No strength, health, recovery, or weather importer exists.

## HTTP surface

`garmin_server.py` is the only server. It binds `127.0.0.1` only, requires a
per-launch random `X-Dash-Token`, validates the `Host` header to defeat DNS
rebinding, serves an allowlist of known filenames, and self-terminates after ~20
idle minutes.

| Route | Purpose |
|---|---|
| `GET /ping` | Health check |
| `GET /garmin_sleep.csv` | Sleep data |
| `GET /garmin_hr.csv` | Heart-rate data |
| `GET /fit-list` | Lists available FIT files |
| `GET /cloud-check` | Cloud backup status |
| `GET /fit/<name>` | Serves a single FIT file |
| `GET /sync` | Triggers a sync |
| `GET /cloud-backup` | Triggers a cloud backup |

There is **no REST API, no JSON activity endpoint, and no authentication beyond
the single-user local token.**

## Auth, secrets, and sensitive-data handling

- No user accounts, sessions, roles, or authorization model exist. The system is
  single-athlete by construction, so there is nothing to authorize against.
- Garmin credentials are read from the environment; they are never committed.
- `garmin_server.py` uses `secrets` for its per-launch token.
- The publication guard refuses to commit files containing coordinates, FIT
  semicircle fields, or CSV latitude/longitude columns. See
  `docs/PRIVACY_INCIDENT.md`.
- **Two live leaks were found and fixed on 2026-09-29** (see Verification
  Report). The guard's own blind spot has been closed and regression-tested.

## Commands

| Purpose | Command | Status |
|---|---|---|
| Install | `pip install -e .` | Works |
| Run tests | `python -m pytest` | **Works. 90 passed, 1 skipped.** |
| Publish | `python export_publish.py` | Works |
| Check only | `python export_publish.py --check` | Works |
| Audit FIT | `python fit_audit.py` | Works |
| Validate GPS | `python fit_gps_validate.py` | Works |
| Serve dashboard | `python garmin_server.py --open` | Works |
| Lint | — | **Not available.** No ruff/flake8 config or dependency. |
| Format | — | **Not available.** No formatter configured. |
| Type check | — | **Not available.** No mypy/pyright config or dependency. |
| Build | `python -m build` | Present via setuptools config, but no lockfile and never run in CI. |
| Migrations | — | **Not applicable.** No database. |
| CI | — | **None.** No `.github/workflows`. |
| Scheduled publish | `garmin_publish_task.bat` via Windows Task Scheduler | Works. AM and PM both verified. |

## Tests

90 tests across 8 files, all passing (1 skipped where symlinks are unavailable):
| File | Covers |
|---|---|
| `tests/test_gps_guard.py` | Coordinate scanning, including the 2026-09-29 regression cases. |
| `tests/test_capture_supervisor_brief.py` | Brief capture and its content scanner. |
| `tests/test_history_safety.py` | Refuses to auto-reset a rewritten history. |
| `tests/test_brief_bridge.py` | Bridge auth, traversal, size caps, content scan, idempotency, rollback. |
| `tests/test_provenance.py` | UTC/local date reconstruction and timezone status. |
| `tests/test_fit_audit.py` | FIT audit behaviour. |
| `tests/test_paths_and_guards.py` | Path resolution and secret scanning. |
| `tests/conftest.py` | Shared fixtures. |

Test fixtures use synthetic open-ocean coordinates only, enumerated explicitly in
`SYNTHETIC_PAIRS` in `export_publish.py`.

## Blockers and unknowns

These are stated as facts, not gaps to be guessed at later.

1. **No database, ORM, or migration system.** Any task requiring "the existing
   schema layer" is greenfield. Building one is a decision, not an implementation.
2. **No web framework or REST API.** The localhost file server is not an API.
3. **No authentication or authorization.** Consent gating and per-athlete access
   control (tasks 6, 7) have nothing to build on.
4. **No frontend build.** The dashboard is a single gitignored HTML file, so its
   Task 11 edits are not version-controlled and are lost if the file is lost.
5. **No linter, formatter, type checker, or CI.** Task 12's suite is tests only.
6. **No strength, health, recovery, or weather data exists**, and no importer
   produces any. Tasks 5, 6, 8, 10, and 11 start from zero.
7. **Timezone offset is unknown.** `profile.json` is null, so local dates remain a
   documented reconstruction rather than a confirmed value.
8. **The 26 July timestamp discrepancy is unresolved by design.** It is recorded
   in `docs/PROVENANCE.md` and deliberately not silently corrected.
9. **GitHub retains unreachable objects.** The old leaking commit is no longer on
   `main` but is still served by SHA and by the raw CDN. Only recreating the
   repository guarantees removal.

## Unrelated or generated files confirmed absent

No `.env`, no credential file, no raw FIT file, and no health data is tracked.
`C:\Users\benpi\Downloads\garmin_fit\` holds the 56 GPS-bearing FIT files and is
outside the repository and gitignored.
