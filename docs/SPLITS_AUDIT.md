# Split audit: the 5 km mark is now measured, not projected

Task `002` (log a 5K PR) was blocked because the published export had no splits:
any 5K time was an average-pace projection, which task 002 correctly refused to
write into `CREW_BRIEF.md` as if it were a record.

## What changed

`garmin_fit_reader` now reads two things off the FIT files, both from fields
that carry no location data (`distance` and `timestamp`; position fields are
never read):

* **`Best 5K Time`** - the clock time at which the per-record distance curve
  first reaches 5000 m, for activities long enough to contain one.
* **`Lap Splits`** - the device's auto-lap times, as `M:SS` values.

Both flow into the published CSV and into `brief_facts.json` via
`brief_consistency.measured_facts()`, which reads the *published CSV* so the
number in the facts file is exactly the number a crew can reproduce.

## Measured is not the same as fastest

A caution that matters: the 5 km crossing time is the *clock time* at 5.0 km. If
a run has a stopped section or warm-up plus a fast section, the clock at 5 km
includes the stop. It is therefore published as a **measurement**, never as a
PR. `brief_facts.json` carries the best *measured crossing* across the corpus,
and that is what any comparison must treat it as.

Consequence for `002`: `CREW_BRIEF.md` can now state a real mark and a date,
because it is quoted from the distance curve, not conjured from an average. It
would still be wrong to call it the runner's "5K PR" unless the runner confirms
that crossing was a genuine all-out attempt with no interruptions.

## Current corpus

| | |
| --- | --- |
| Activities with a measured 5 km crossing | 58 / 58 |
| Activities with lap splits | 58 / 58 |
| Fastest measured crossing (from local FIT read, before the export refresh) | 24:42 on 2026-06-16 |

The `2026-06-16` figure matches the shape of the run the task already suspected
(4.89 mi, 7:11/mi average) and replaces the projected 24:59 with a measurement.

## Privacy

The two new columns contain durations and distances only. `_best_5k_seconds`
reads nothing but `distance` and `timestamp`; `tests/test_splits.py` pins that a
record carrying `position_lat`/`position_long` still produces the same crossing.
The published CSV keeps the existing guard, which refuses any labelled
coordinate column.

## Gotchas found while building this

* A fake record with a non-`datetime` timestamp or no `start_time` must not
  crash a parse; both are guarded and yield no crossing.
* The crossing uses the first record past 5000 m. Because cumulative distance
  is monotonic on device data, that is the crossing; a spurious non-monotonic
  record later cannot rewrite it (pinned by a test).