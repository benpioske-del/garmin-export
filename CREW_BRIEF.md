# Crew Brief: Garmin Training Data

## What this repository is

A read-only, sanitized export of one runner's Garmin activity log, published so an AI
crew can analyse training without access to the original device or the owner's machine.

**No GPS tracks. No routes. No credentials. No health identifiers.**
The FIT files that contain location data stay on the owner's machine and are never pushed.

---

## Files

| File | Purpose |
| --- | --- |
| `garmin_export.csv` | The activity log. 36 runs. This is the file the crew should read. |
| `garmin_export.meta.json` | Row count, date range, source files, and a staleness flag. |
| `publish_state.json` | The raw URL, branch, and last publish time. |

Read `garmin_export.meta.json` first. It tells you how current the data is.

---

## Units and formats (get these wrong and every conclusion is wrong)

| Field | Format | Notes |
| --- | --- | --- |
| `Date` | `YYYY-MM-DD HH:MM:SS` | **Local wall clock**, no timezone. Do not treat as UTC. |
| `Distance` | decimal miles | Garmin was configured in imperial. **Not km.** |
| `Time` | `H:MM:SS` | Sometimes zero-padded, sometimes not (`1:09:18` and `01:06:45` both occur). |
| `Moving Time`, `Elapsed Time` | `H:MM:SS` | Elapsed includes pauses. |
| `Avg Pace`, `Best Pace` | minutes per mile | **Higher = slower.** 9.0 is faster than 10.0. |
| `Avg HR`, `Max HR` | bpm | |
| `Total Ascent`, `Total Descent`, `Min/Max Elevation` | feet | |
| `Calories` | kcal | |
| `Steps` | count | Often empty for runs. |
| `Activity Type` | text | e.g. `Running`. |
| `Best Lap Time` | `H:MM:SS` or empty | Only for activities with laps. |
| `_source_file` | text | Provenance. Not training data. |

### Paces are strings, not numbers

`Avg Pace` is `9:57`, meaning 9 minutes 57 seconds per mile. It is **not** `9.57`, and it
is **not** a decimal fraction. Convert with:

```python
def pace_to_dec(s):
    parts = [int(p) for p in s.strip().split(":")]
    return parts[0] + sum(p * 60 ** -i for i, p in enumerate(parts[1:], 1))
```

Garmin writes some paces as `9:57` and others as `0:09:57`. Both parse with the helper above.

### Header quirk (already fixed here, but know it)

Garmin's raw export labels one column `Training Stress Score®`, with a trailing
registered-trademark symbol. The publisher strips trademark and non-breaking-space
characters from headers, so **this repo exposes the clean name `Training Stress Score`**.
If you ever read a raw Garmin export directly, expect that mangled name.

---

## Current state, honestly

- **36 runs, 2026-04-14 to 2026-08-04.**
- The owner's device holds **56 FIT files running to 2026-09-26**, and the coaching
  dashboard built from them already sees **48 runs through 2026-09-07**.

**So this export is roughly 7 weeks behind the source device.** The most recent month of
training is missing. Do not conclude the runner stopped training after 2026-08-04; they
did not. If your analysis depends on recency, say the data is incomplete rather than
inferring a break in training.

---

## Rules for the crew

1. **Do not treat the end of this dataset as the present.** Check `latest_run` in the meta
   file before making any claim about current fitness or recent form.
2. **Do not request GPS, routes, or the original FIT files.** They are deliberately excluded.
3. **Do not invent training the log does not contain.** Missing data is missing, not easy.
4. **Do not diagnose injury or medical conditions.** The log records activity, not health.
5. **Say when a conclusion is uncertain.** Distance-based pacing, partial splits, and
   Garmin's own "Training Stress Score" are all approximations.

---

## How the owner's dashboard scores things

If the crew wants to reproduce or critique the dashboard's science panel, these are the
real implementations in `Coach Dashboard v1.20.html`. They are the source of truth, not
any prose description of them.

| Function | Line | What it does |
| --- | --- | --- |
| `riegelTo5k(timeMin, distMi)` | ~4730 | Riegel race-equivalent projection. Note the constant is **3.10686 miles** (a 5 km race), not 3.1 miles. An earlier version used the wrong constant and was fixed. |
| `computeSciencePercentiles(idx, sorted)` | ~4880 | Cohort, population, and self percentiles for one run. |
| `computeRollingScienceIndex(sorted, window)` | ~4750 | Mean percentile over the last N runs, plus comparison to the prior N. |
| `computeRunGrade(idx, allRuns)` | 5070 | Letter grade for a single run. Bands: **A ≥ 90, B ≥ 78, C ≥ 65, D ≥ 50, else F.** |
| `ageFactor(age, sex)` | ~4200 | Age adjustment for the population anchor. |
| `censusPct(t5k, sex)` | ~4200 | General-population percentile from a **small hand-built anchor table**. |

### Two score scales that must not be conflated

- **The letter grade (A–F) is relative.** It measures how a run compared to the owner's
  own recent baseline. It is a performance-versus-self score, not an absolute standard.
- **Percentiles and the rolling index are absolute.** They compare pace against
  cohort and population references. Currently the rolling index reads **41/100, trending
  down**.

A run can earn a high letter grade and still sit below population. Presenting those as
the same number is the main analytical error to avoid.

### Known weak spots, disclosed

- `censusPct` uses a **crude, hand-entered anchor table** with a flat `+12`/`+13` offset
  from a world-referenced pace. Treat population percentiles as a coarse estimate, not a
  ranking. The dashboard labels this in its own UI.
- Sample size is small. 36 runs is enough to see a trend and not enough to trust a
  single percentile.
