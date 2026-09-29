# FIT Data Audit

Supervisor brief Task 4. Read-only inspection, 2026-09-28.
No source file was modified.

## Command

```
python fit_audit.py          # presence, counts, message inventory
python fit_gps_validate.py   # coordinate validity and range
```

Both live alongside `garmin_fit_reader.py` and read
`C:\Users\benpi\Downloads\garmin_fit\*.fit` without writing to it.

## Results

| Metric | Value |
| --- | --- |
| Files inspected | 56 |
| Parse failures | **0** |
| Files **with** GPS | **56** |
| Files **without** GPS | **0** |
| Position points found | 51,637 |
| Points out of valid range | **0** |
| Points at null island (0, 0) | **0** |
| Coordinate spread | withheld, see note below |
| Files with lap records | 56 |
| Record messages | 51,653 |

Note on the withheld coordinate spread: an earlier version of this table
published the exact latitude and longitude range of the corpus. Those two numbers
describe a bounding box roughly 11 km by 24 km, which in a public repository
that also names the athlete's town is a location disclosure. The audit does not
need them. Every point was checked against the valid latitude and longitude
range and none fell outside it, which is the finding that matters; the
coordinates themselves stay local. Re-run `fit_audit.py` locally if the actual
bounds are needed.

Device: `garmin`, type `activity`.

## Correction to earlier guidance

An earlier statement in this project's history claimed the FIT files contained
no GPS data and that the weather-enrichment task was therefore blocked on data
availability.

**That was incorrect.** GPS is present and valid in every file. The confusion
came from conflating two different things: the publisher *deliberately strips*
position fields from all published output as a privacy measure, and that policy
was misread as an absence in the source.

The weather pipeline is not blocked for lack of location data. The actual
obstacle is a privacy decision, described below.

## Timestamps and time zones

| Field | Count | Notes |
| --- | --- | --- |
| `record.timestamp` | 51,653 | UTC by FIT specification. |
| `session.start_time` | 56 | UTC. |
| `session.timestamp` | 56 | UTC. |
| `session.total_elapsed_time` | 56 | Duration. |
| `session.total_timer_time` | 56 | Duration. |

**No time zone field exists in any message of any file.** There is no
`time_zone_offset`, no `utc_offset`, no location-based zone.

Consequences:

- Every FIT timestamp is UTC. Athlete-local time cannot be derived from source.
- The `Date` column in the published CSV is an athlete-asserted local calendar
  date, not a derived one.
- DST transitions cannot be detected from the data.
- Supervisor Task 2's requirement to store an explicit `unknown` timezone status
  is **validated as necessary**, not merely defensive.

## Laps

All 56 files contain lap messages, so per-lap and per-split data is available
if the schema is extended. The published CSV currently exposes only aggregate
values plus `Best Lap Time` and `Number of Laps`.

## Retention decision required

The brief instructs: "If the project already parses FIT files, extend it to
retain the raw source and relevant GPS/lap data."

Raw source files are already retained locally and are gitignored. They are not
version controlled and are not backed up.

GPS is available but **must not be published.** Two viable paths:

1. **Derive coarse location server-side.** Keep exact tracks local, derive a
   rounded locality or bounding box, and publish only that. Sufficient for
   weather enrichment, which needs a location to query, not a route.
2. **Athlete-asserted location.** No GPS in the pipeline at all. The athlete
   sets a training locality once. Loses per-run accuracy for runs that start
   elsewhere.

Path 1 is more accurate but publishes a location, which the current policy
excludes and which the publisher's own guard would reject if a position field
ever reached a published column. Path 2 preserves the existing privacy posture
with a small, explicit accuracy cost.

Neither path requires assuming a location, so Task 9's stated blocker is
resolvable. **This is a policy choice for the athlete and has not been made.**

## Test fixtures

The brief asks for tests covering a file with GPS, one without, and malformed
input. Of the 56 available files:

- **With GPS:** 56. Well covered.
- **Without GPS:** 0. No such fixture exists. A synthetic file is required.
- **Malformed:** 0. No such fixture exists. A truncated or corrupt file is
  required.

These two negative fixtures must be created deliberately. Note that the
publisher's guard currently *rejects* FIT files containing position fields, so
any test asserting GPS handling must target the audit and parser directly rather
than the publish path.

## Unavailable data

No strength, no recovery, no health, and no weather data is present in any
source file. These require new data entry, not new parsing.
