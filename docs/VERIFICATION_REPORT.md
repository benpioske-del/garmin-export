# Verification report

Supervisor brief Task 10. Everything below was run in the working tree on
2026-10-01. Commands and results are reproduced as observed.

## Environment

| | |
| --- | --- |
| Python | 3.13.15 |
| Git | 2.53.0.windows.4 |
| Platform | Windows, win32 |
| Repo | `benpioske-del/garmin-export`, branch `main` |

## Test suite

```
$ python -m pytest
207 passed, 1 skipped in 100.63s
```

| File | Tests |
| --- | --- |
| `tests/test_brief_bridge.py` | 56 |
| `tests/test_training_data.py` | 59 |
| `tests/test_trainloop_cli.py` | 22 |
| `tests/test_capture_supervisor.py` | 16 |
| `tests/test_fit_audit.py` | 16 |
| `tests/test_provenance.py` | 15 |
| `tests/test_gps_guard.py` | 13 |
| `tests/test_paths_and_guards.py` | 9 |
| `tests/test_history_safety.py` | 2 |
| **Total** | **208** (207 pass, 1 skip) |

The skip is the Windows symlink case in the brief-bridge suite; the code path is
covered on platforms that permit symlinks.

Up from 90 passed / 1 skipped at the start of the data-layer round. The brief
bridge grew from 26 to 56 tests since then: clipboard and `.txt` transports,
rejected-brief staging, and a `frozen_clock` fixture that advances the clock 90
seconds to prove republishing an unchanged brief is a no-op. `test_trainloop_cli.py`
is new.

## FIT data audit

```
$ python fit_audit.py
FIT data audit
parser: fitparse=1.2.0 reader=1.0.0

files inspected           : 57
parse failures            : 0
files readable            : 57
files with GPS            : 57
files without GPS         : 0
files with usable timestamp: 57
files without timestamp   : 0
session messages          : 57
lap messages              : 505
record messages           : 52213
position points (counted) : 52197
files missing fields      : 0

warnings:
   none
```

Full report and schema documentation: [`FIT_AUDIT.md`](FIT_AUDIT.md).

## Data layer

```
$ python trainingdb.py migrate
applied 001 001_core_activity
applied 002 002_provenance_audit
applied 003 003_strength
applied 004 004_load_and_health_access
applied 005 005_health
applied 006 006_weather

$ python trainingdb.py
applied: [1, 2, 3, 4, 5, 6]
pending: none
```

Re-running is a no-op. Editing an applied migration raises
`RuntimeError: migration NNN changed after it was applied` — covered by
`test_edited_migration_is_a_hard_error`.

## Import against the real corpus

On a fresh database with the current corpus of 57 files, the first import
inserts all 57. Re-running against a database that already holds them reports
every file `unchanged`:

```
$ python activities.py import
{"inserted": 0, "updated": 0, "unchanged": 57, "unreadable": 0}
```

**Idempotency verified on the real data**: no rows updated, and no new audit
rows written on the second pass.

```
$ python activities.py summary
{"activities": 57, "open_reviews": 58}
```

- 57 activities
- 57 open `timezone_uncertain` reviews (one per activity, expected)
- 1 open `activity_gap`: `no activity 2026-06-26..2026-07-05 (8 days)`
- 0 duplicates detected
- 57 SHA-256 raw references stored

The FIT-file inventory, the canonical table and the published CSV all agree at
**57**. An earlier brief described a 55/56/59 discrepancy; that premise was
checked against the live corpus and is unsupported, so there is no
reconciliation to perform.

## Training load and recommendation

Against the real corpus, with `hr_max=198` supplied by the caller (the value now
in `profile.json`; the figure below was produced with an earlier test value and
the load is bucketed by intensity band, so the exact number inside 195-203 does
not change it):

```
7-day window: run_load 1174.9, strength_load null, combined_load 1174.9,
              run_confidence medium
recommend(): confirmation_required
             "11 recent activities are awaiting confirmation"
```

Two things worth stating plainly:

- `strength_load` is `null`, not `0`. No strength sessions exist yet, and an
  absent component is not a zero component.
- The recommendation is a **refusal**, and it is the correct one: 11 activities
  in the window still carry unresolved timezone reviews, so
  `recommend.recommend()` declines to issue a control state. This is the
  designed behaviour, not a failure.

## Publisher and privacy guard

```
$ python export_publish.py
```

Runs the position-data guard over every candidate file, refuses to commit if
position data is present, then commits and pushes. The guard blocks labelled
coordinate fields, degree pairs, FIT semicircle field names, and CSV coordinate
columns.

**Known limitation, unchanged:** the guard cannot reject a bare single
coordinate, because a decimal such as `44.95` is indistinguishable from
legitimate training data. Manual review remains necessary. This is recorded in
the inventory rather than papered over.

## Privacy checks

- Raw FIT files are gitignored; the local `trainloop.db` is gitignored.
- `weather_observations` has no `lat`/`lon`/`latitude`/`longitude` column —
  asserted against `PRAGMA table_info` by
  `test_weather_schema_stores_no_coordinates`.
- `test_audit_output_contains_no_coordinates` walks the entire FIT audit result
  and fails if any key or value resembles a position.
- The audit no longer reports a latitude/longitude range. The previous test
  suite asserted the athlete's coordinates fell inside a specific region; that
  test both hardcoded a location into a tracked file and depended on the leak.
  It has been inverted into a regression guard.
- Current `main` is clean through the authoritative GitHub API.

**Unresolved:** GitHub still retains unreachable historical commits by SHA.
Deleting and recreating the repository is the only guaranteed purge. This has
not been done, as it would break the public URL and all existing automation.

## Not verified

Stated rather than implied:

| Item | Status |
| --- | --- |
| Linter / formatter / type checker | None configured. Nothing was run. |
| CI | None. No workflow exists, so nothing runs on push. |
| `python -m build` | Not run. `build` is not a declared dependency and no lockfile pins the environment. |
| Dependency pinning | `pyproject.toml` only. No lockfile, so a future resolve may drift. |
| `python -m pip install .` | Not re-run this round. |
| Multi-athlete isolation | Does not exist. The database is local and single-subject. |
| Weather provider | None. The gate returns `unavailable` past consent and location. |
| Strength data | Schema and service verified by tests; no real strength sessions recorded yet. |
| `profile.json` | Partially populated. `hr_max=198`; `age`, `sex`, `resting_hr`, `weight_lb`, `height_in` null. The missing UTC offset blocks confirmed local dates and weather location. |
| Brief bridge idempotency | **Now verified.** `3054d6a` gave the file a content-derived `brief_id`; `captured_utc` is metadata only. Tests advance a frozen clock 90s to prove an unchanged brief is a no-op. |
| Athlete UTC offset | Not supplied by the athlete. This is what 57 open `timezone_uncertain` reviews are waiting on. |

## Withdrawn claims

Recorded so they are not reintroduced by a later brief:

- **"53 of 55 runs are classified as Zone 5."** No HR zone classification
  exists in this repository. Every occurrence of "zone" in the source is
  `timezone_source`; the CSV carries `Avg HR` and `Max HR` but no zone column;
  and `53`/`55` appear in these documents only inside the Git version string
  `2.53.0.windows.4`. The claim could not be traced to any code, fixture or
  command output, and was withdrawn rather than investigated as a real finding.
- **"55 audit records and a historical 59-record source."** Both counts are
  unsupported. The live corpus is 57 across every source.

## Reproducing this report

```
python -m pytest
python fit_audit.py
python trainingdb.py migrate
python trainingdb.py
python activities.py import
python activities.py summary
```
