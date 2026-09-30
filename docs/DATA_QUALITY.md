# Data quality

What the pipeline knows, what it assumed, and what it deliberately refuses to
fill in. The rule underneath everything here: **absence is recorded, never
inferred.** A gap in the data becomes a question for the athlete, not a
placeholder activity and not a zero.

## Canonical record

`activities` is the system of record. The CSV export is a published view of it,
not the other way round. Built by `migrations/001_core_activity.sql`, written by
`activities.py`.

| Concern | How it is handled |
| --- | --- |
| Identity | `activity_id` is ours and stable, `garmin:<native id>`. Where no native id exists it falls back to a digest of `(source, start_utc, sport)` so re-imports resolve to the same row. |
| Garmin's own id | Kept in `source_activity_id`, unique per source system. Never used as the key. |
| UTC | `start_utc`, observed, ISO-8601 with `Z`. |
| Local date | `start_local`, **nullable**. Populated from the FIT filename, which is the device's local date, not the athlete's confirmed one. |
| Idempotency | Re-importing identical bytes changes nothing and writes no audit rows. |

## The timezone problem

The FIT specification defines `start_time` as UTC and carries **no offset**. The
device's local date survives only in the download filename
(`YYYY-MM-DD_<id>.fit`). Three separate things follow, and conflating them is
the most common way this data gets misread:

1. `start_utc` is observed and trustworthy.
2. `start_local` is reconstructed from the filename and is therefore an
   *assumption*, recorded as `timezone_source = filename_date`,
   `value_state = assumed`, `confidence = low`.
3. Until the athlete confirms an offset, the record is
   `confirmation = confirmation_required` and a `timezone_uncertain` review
   item is open.

`activities.confirm_timezone(conn, activity_id, offset_hours)` is the only path
that upgrades a local date to `confirmed_offset` / `athlete_reported`. It also
closes the review item and writes an audit entry.

Until this is done for a record, any local-date-derived number is provisional.
`recommend.recommend()` refuses to issue a control state while any activity in
the window is still open, precisely because of this.

### Known consequence

An evening run that crosses midnight UTC has a UTC date one day later than the
local date. The current corpus has **1** such activity. Both dates are exported
in separate columns so neither has to be guessed at read time.

## Completeness

Six states, defined in `terms.COMPLETENESS_STATES`. They are not
interchangeable, and the distinctions are the point:

| State | Meaning |
| --- | --- |
| `complete` | Present, from a trustworthy source. |
| `not_imported` | No file was ever received. |
| `unavailable_from_source` | The file exists but lacks the field. |
| `awaiting_confirmation` | Value exists but the athlete has not confirmed it. |
| `present_low_confidence` | Value exists and is unverified. |
| `confirmed` | A human signed it off. |

`not_imported` is not "the athlete did not train". A sensor with no HR reading
is not the same as a watch left in a drawer, and the schema refuses to merge
them. See `docs/DATA_QUALITY_TERMINOLOGY.md`.

## Missing values are NULL

A blank field is stored as SQL `NULL`, never `0`. A NULL average heart rate and
a heart rate of zero are different facts, and volume arithmetic that cannot tell
them apart will quietly invent training.

`loadcalc.run_session_load()` returns `None` with a reason string rather than
substituting a distance proxy, because a duration-weighted distance figure
measures something other than what the load column claims to measure.

## Review queue

`review_items` holds open questions. Reasons are enumerated in
`terms.REVIEW_REASONS`:

| Reason | Raised when |
| --- | --- |
| `timezone_uncertain` | Local date is still a filename assumption. |
| `possible_duplicate` | Same sport, start within 300 s, distance within 1%. |
| `activity_gap` | More than 7 consecutive days with no activity. |
| `ambiguous_timestamp` | Reserved for offset conflicts. |
| `missing_fields` | Fields absent from an otherwise importable file. |

`review_items.activity_id` is intentionally **not** a foreign key: the queue is
shared with strength sessions, whose ids are `strength:`-prefixed and are not
rows in `activities`. Enforcing the reference would have meant inventing an
activity row for every strength session in order to file a safety flag.

## Audit history

`activity_import_audit` is append-only and has **no foreign key and no cascade**,
so the record of what happened to an activity outlives the activity row. It
captures inserts, per-field updates, timezone confirmations and review
resolutions, with actor, old value, new value and reason.

Strength writes to the same table with `strength_`-prefixed events and
`strength.`-prefixed field names, rather than standing up a parallel history
system.

## Raw references

`activity_raw_refs` stores the SHA-256, byte size, mtime, parser name and
importer per source file. A later import that reads different bytes is
detectable, and a report can state which exact files it was derived from.

## Current corpus state

From the reproducible audit (`python fit_audit.py`, see `docs/FIT_AUDIT.md`):

- 56 files, all parse, all carry GPS, all carry a usable timestamp
- 1 session per file, 499 laps, 51,653 records, 51,637 position points
- 0 files with missing session fields, 0 parse failures
- **1 open date-gap review**: no activity 2026-06-26 through 2026-07-05
- **56 open `timezone_uncertain` reviews**, one per activity, all expected
- 1 activity where the local date and the UTC date differ

The June–July gap is reported, not filled. Nothing in this pipeline creates a
placeholder session for a day with no file.
