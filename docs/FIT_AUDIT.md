# FIT data audit

Supervisor brief Task 3. Regenerate at any time:

```
python fit_audit.py                      # text report to stdout
python fit_audit.py --json out.json      # machine-readable manifest
```

- **Parser:** `fitparse` 1.2.0
- **Reader:** `garmin_fit_reader` 1.0.0
- **Source:** `C:\Users\benpi\Downloads\garmin_fit\*.fit` (56 files, local only)
- **Run:** 2026-09-29

Results are reproducible: every file is hashed with SHA-256 and the parser
version is printed alongside the counts, so a later run can prove it read
identical bytes under the same code.

## Rollup

| Measure | Value |
| --- | --- |
| Files inspected | 56 |
| Parse failures | 0 |
| Files readable | 56 |
| Files with GPS | 56 |
| Files without GPS | 0 |
| Files with usable timestamp | 56 |
| Files without timestamp | 0 |
| Session messages | 56 |
| Lap messages | 499 |
| Record messages | 51,653 |
| Position points (count only) | 51,637 |
| Position points out of range | 0 |
| Position points at 0,0 | 0 |
| Files missing expected fields | 0 |

Warnings: **none**.

## Per-file schema coverage

Each of the 56 files carries a single session message with all 13 fields the
reader depends on:

`sport`, `start_time`, `total_distance`, `total_timer_time`,
`total_elapsed_time`, `total_calories`, `avg_heart_rate`, `max_heart_rate`,
`avg_running_cadence`, `max_running_cadence`, `total_ascent`, `total_descent`,
`num_laps`

`fields_missing` is populated per file and is empty across the corpus. A file
missing any of these is reported as a warning rather than silently producing a
partial row.

### Manifest sample

```
2026-04-14_22528049459.fit   bee24904e9899ad4  gps=True  ts=True  laps=14  missing=0
2026-09-20_24437064180.fit   5b5f1538944875f5  gps=True  ts=True  laps=5   missing=0
2026-09-22_24460815350.fit   5633e98c3ec58b4f  gps=True  ts=True  laps=7   missing=0
2026-09-24_24487279921.fit   78e71591791bcecf  gps=True  ts=True  laps=17  missing=0
```

Full per-file SHA-256 values are in the `--json` manifest.

## Timestamps and timezones

Every file has a usable `start_time`. **Zero** files expose a session
`time_zone` or `utc_offset` field — the audit counts these explicitly
(`tz_fields`) because that absence is the evidence behind the
`assumed_utc` provenance label in the export. It is why
`activities.confirm_timezone()` is the only path to a confirmed local date.

## Gaps and inconsistencies

The audit covers the files. The cross-activity view lives in
`docs/DATA_QUALITY.md` and is produced by the canonical database:

- **1 date gap:** no activity 2026-06-26 through 2026-07-05 (8 days). Reported
  as an open `activity_gap` review item. No placeholder sessions are created.
- **1 activity** whose UTC date and filename-derived local date differ.
- **56 `timezone_uncertain` reviews** — one per activity, expected until the
  athlete confirms an offset.

## Privacy: coordinates are counted, never decoded

The previous version of `fit_audit.py` printed a latitude/longitude range for
the corpus. That is a route fingerprint, and it is the same class of leak
recorded in `docs/PRIVACY_INCIDENT.md`. It has been removed.

This audit now:

- never decodes a semicircle into degrees for output. Range validity is
  *checked* against `-90/90` and `-180/180` and only a count of violations is
  kept;
- exposes no `lat_min`, `lat_max`, `lon_min` or `lon_max` field;
- stores no coordinate anywhere in the database
  (`test_weather_schema_stores_no_coordinates` and
  `test_audit_output_contains_no_coordinates` enforce both).

`test_audit_output_contains_no_coordinates` is a regression guard: it walks the
entire audit result and fails if any key or value looks like a position. The
earlier version of the test suite asserted the athlete's coordinates fell
inside a specific region — that assertion both hardcoded the location into a
tracked file and is now inverted.

Position data remains available locally through `fitparse` for anyone who
deliberately opens the FIT files. It is not published, not audited into
`docs/`, and not written to the database.
