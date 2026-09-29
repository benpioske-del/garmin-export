# Data Provenance and Timestamps

Supervisor brief Task 2. What every column in `garmin_export.csv` is derived
from, and which assumptions are known rather than hidden.

## A bug this work found

The export's `Date` column was **one day wrong for at least one activity**, and
the pipeline was carrying a duplicate row because of it.

`Date` was written from the FIT session's `start_time`. The FIT specification
defines `start_time` as UTC, but `fitparse` returns it as a *naive* datetime, so
the code stored UTC wall-clock time in a column that was being read as the
athlete's local date. Any run that crossed midnight UTC was published under
tomorrow's date.

The corpus contains exactly one such run, and three independent signals agree
on the correct value:

| Signal | Value |
| --- | --- |
| FIT `start_time` (UTC) | `2026-07-27 01:10:15` |
| FIT filename local date (Garmin names downloads by local date) | `2026-07-26` |
| Garmin's own CSV export of the same activity, in local time | `2026-07-26 20:10:15` |

`2026-07-27 01:10:15Z` at UTC-5 is `2026-07-26 20:10:15`, which matches the CSV
export to the second. The local date is therefore `2026-07-26`.

The duplicate is the useful part. The same activity was also present as a row
from `Activities (1).csv`. It survived dedupe before only because the two copies
disagreed about the date — one said `07-27`, the other `07-26`, so the
date+distance dedupe key did not match. Once the date was corrected the two rows
collapsed into one. The activity count went from **57 to 56**, which is the
correct number of unique activities. The old count was inflated by a bug.

### The general rule

An activity that started between 20:00 and 04:00 UTC can be published on the
wrong calendar day. 14 activities in this corpus start at or after 20:00 UTC;
those happen to be afternoon runs locally, so their dates are unaffected. The
exposure was one row here and could be much larger for a runner in another
timezone or with a different routine.

## How it is handled now

`Date` is the athlete's **local** date and time, taken from the FIT filename's
date plus the UTC clock time. `Date (UTC)` is the unambiguous instant, in
ISO 8601 with an explicit `Z`. Neither is inferred from the other at read time.

The offset itself is still unknown. No FIT file contains a timezone, and
`profile.json` has never been filled in, so the local time is reconstructed
rather than measured. The export says so instead of implying certainty.

## Columns

| Column | Meaning | Label |
| --- | --- | --- |
| `Date` | Local date and time | device-derived, from filename + UTC clock |
| `Date (UTC)` | The instant the activity started, ISO 8601 `Z` | device-derived, UTC assumed per FIT spec |
| `Timezone Status` | What is actually known about the offset | see below |
| `Source` | Where the row came from | `Garmin FIT` or `Garmin CSV export` |
| `Source File` | The originating file's basename | device-derived |

### `Timezone Status` values

| Value | Rows | Meaning |
| --- | --- | --- |
| `assumed_utc; local date from filename` | 56 | `start_time` treated as UTC per the FIT spec; local date reconstructed from the filename. The UTC offset is **not** known. |
| `unknown; athlete-supplied date` | 0 | Would apply to a row read from a Garmin CSV, where the date is already local and no UTC instant exists. |

The label is deliberately awkward. `assumed_utc` is true and incomplete at the
same time, and a reader skimming a column should not be able to mistake it for a
resolved timezone.

## What would close the remaining gap

Filling in `profile.json` with a home timezone offset, plus whether the athlete
is affected by daylight saving, would let the local time be computed from the
UTC instant instead of reconstructed from a filename. Until then the
reconstruction is the best available source, and it is documented rather than
assumed away.

A second, independent improvement would be to record a real UTC offset per
activity. Garmin's CSV export already does this; the FIT files do not.

## Note on `Source File`

`Source File` publishes the FIT basename, for example
`2026-07-26_23745136848.fit`. The leading date is the local date and the digits
are the Garmin activity id. This was assessed for privacy: it reveals no
location and no title, and the local date is already in the `Date` column, so
publishing it adds no new information. If activity ids are ever considered
sensitive, this column is the one to drop.
