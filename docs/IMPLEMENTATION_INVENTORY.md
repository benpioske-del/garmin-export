# Implementation Inventory

Supervisor brief Task 1. Produced by direct inspection on 2026-09-28.
Repository: `benpioske-del/garmin-export` (public, branch `main`).

This document records only what was confirmed by inspection. Where a layer
does not exist, that is stated plainly rather than assumed.

## Headline finding

**This repository is not an application. It is a data export pipeline with a
documentation folder.** There is no frontend, no backend, no database, no
migration directory, no authentication, and no test framework.

Most of the remaining supervisor tasks (2, 3, 5, 6, 7, 8) instruct the agent to
"use the existing project's storage conventions", "add migrations in the
existing migration directory", and "add tests in the existing test directory".
**Those directories do not exist.** Implementing them means creating a
full-stack application from scratch, not extending an existing one. This is
recorded as a scoping constraint, not a defect in the brief.

## Repository contents (complete, 11 tracked files)

| Path | Role |
| --- | --- |
| `garmin_export.csv` | The published artifact. 57 rows x 26 columns. |
| `garmin_export.meta.json` | Source counts, date range, generated timestamp. |
| `profile.json` | Athlete profile template. All values currently `null`. |
| `publish_state.json` | Raw URL, branch, timestamp, `data_sha` change token. |
| `CREW_BRIEF.md` | Data schema and caveats for the supervisor. |
| `CREW_TASKS.md` | Task protocol and safety guardrails. |
| `SUPERVISOR_BRIEF.md` | Captured supervisor brief, unverified. |
| `tasks/001-example-task.md` | Example task, status `pending`. |
| `tasks/002-log-a-5k-pr.md` | Verification test, status `blocked`. |
| `.gitignore`, `.gitattributes` | Line-ending and ignore rules. |

There is **no `docs/` directory in version control** prior to this file. Task 1
creates it.

## Entry points

All executable code lives **outside the repository**, in
`C:\Users\benpi\Downloads\`. This is the most significant structural risk found:

| Script | Purpose |
| --- | --- |
| `export_publish.py` | FIT/CSV merge, safety guards, fingerprinting, git publish, remote rebase, task reporting. |
| `garmin_fit_reader.py` | FIT decoding, semicircle conversion, unit normalisation. |
| `garmin_sync.py` | Garmin Connect download using cached OAuth tokens. |
| `capture_supervisor_brief.py` | Runs the CrewAI supervisor, scans output, commits the brief. |
| `garmin_publish_task.bat` | Scheduled publisher entry point (07:15 and 18:15). |
| `Refresh Garmin Data.cmd` | Manual download-then-publish. |
| `Run CrewAI Supervisor.cmd` | Manual supervisor capture. |
| `Coach Dashboard.cmd` | Local dashboard launcher. |
| `Coach Dashboard v1.20.html` | Standalone dashboard, reads local FIT directly. |

**Risk: no pipeline code is version controlled.** The repository contains data
and documentation but not the scripts that produce them. A cleared Downloads
folder would destroy the pipeline with no recovery. Moving the scripts into the
repository is recommended before any task that depends on them surviving.

**Second risk: the dashboard is decoupled from the repository.** It reads local
FIT files directly. Repository changes, including supervisor briefs, do not
reach the dashboard.

## Data model

The only persisted model is a flat CSV, 26 columns:

```
Activity Type, Date, Favorite, Title, Distance, Calories, Time, Avg HR, Max HR,
Avg Run Cadence, Max Run Cadence, Avg Pace, Best Pace, Total Ascent,
Total Descent, Avg Stride Length, Training Stress Score, Steps, Decompression,
Best Lap Time, Number of Laps, Moving Time, Elapsed Time, Min Elevation,
Max Elevation, _source_file
```

- Units: distance km, time HH:MM:SS, pace M:SS per km, elevation m, heart rate bpm.
- `_source_file` is the only provenance field. It is a bare filename, so
  provenance does not survive the file leaving this machine.
- There is no unique canonical identifier, no UTC timestamp separate from the
  local date, no deduplication metadata, and no data-quality flags.
- `Date` is a local calendar date only. It carries no time and no offset.

This confirms supervisor Task 2 is genuinely required rather than redundant.

## Import pipeline

1. `garmin_sync.py` authenticates to Garmin Connect and downloads `.FIT` files
   into `C:\Users\benpi\Downloads\garmin_fit\`.
2. `garmin_fit_reader.py` parses each file, converting FIT semicircles to
   degrees and normalising units.
3. `export_publish.py` merges FIT rows with a manual `Activities*.csv` export,
   de-duplicates, applies safety guards, and commits to `main`.

Merge currently yields 56 FIT rows plus 1 CSV row = 57.

**Scheduling caveat:** the scheduled task only publishes. It does not download.
New activities appear only after a human runs `Refresh Garmin Data.cmd`.

## Test framework

**None.** No test files, no `pytest.ini`, no `tox.ini`, no `pyproject.toml`,
no `requirements.txt`, no `package.json`, no CI configuration.

There is no lint, format, type-check or build command to run. Supervisor Task 12
asks for formatting, linting, unit tests, integration tests, type checks and
build validation. **None of these commands exist.** That task cannot be
completed as written until a test harness is established.

`fitparse` and `garminconnect` are installed system-wide rather than pinned in
a manifest, so dependency versions are not reproducible.

## Source data

- 56 `.FIT` files, `C:\Users\benpi\Downloads\garmin_fit\`. Never committed.
- 1 manual `Activities*.csv` export in Downloads. Never committed.
- Garmin credentials in `C:\Users\benpi\Downloads\.garmin_tokens\`. Never
  committed, blocked by an explicit guard in the publisher.

No database files (`.db`, `.sqlite`, `.sqlite3`) exist anywhere.

## Requested data-presence findings

| Item | Found? | Evidence |
| --- | --- | --- |
| GPS coordinates | **Yes, in source** | 51,637 points across all 56 FIT files. See `FIT_DATA_AUDIT.md`. Deliberately excluded from all published output. |
| Time zones | **No** | No `time_zone_offset` or equivalent in any message. FIT timestamps are UTC; local time cannot be derived. |
| Raw FIT files | **Yes** | 56 files, gitignored, local only. |
| Strength data | **No** | No schema, no files, no Garmin lift data parsed. |
| Health / recovery data | **No** | Only `profile.json`, entirely `null`. |
| Weather data | **No** | No temperature, humidity, wind or precipitation anywhere, in source or output. |

## Constraints for subsequent tasks

1. No application exists. Tasks 2, 3, 5, 6, 7 and 8 describe a full-stack build
   from zero. They are not incremental work on existing code.
2. No test harness exists. Task 12 has no commands to run until one is built.
   Establishing tests should precede the tasks that claim test coverage.
3. No version control over pipeline code. Fix before substantial work.
4. Timezone is genuinely unresolvable from source. Task 2's "explicit unknown
   status" is the correct design, and local dates must continue to be treated
   as athlete-asserted rather than derived.
5. The repository is public. GPS and detailed health inputs are excluded by
   policy, not by absence.
