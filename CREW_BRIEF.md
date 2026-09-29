# Crew Brief: Garmin Training Data

## What this repository is

A sanitized export of one runner's Garmin activity log, published so an AI crew can
analyse training without access to the original device or the owner's machine.

**This repository is public.** Anything committed here is readable by anyone, forever
(Git history is public too, so a deleted row does not really disappear).

### What is deliberately NOT here

- **No GPS coordinates.** The source `.FIT` files contain `position_lat/long`,
  `start_position_lat/long` and `nec_lat/long` fields. These are dropped at read time,
  and the exporter raises an error if any field matching lat/lon/position/gps ever
  reaches the output.
- **No credentials.** Garmin tokens and `.env` are gitignored and never committed.
- **No activity titles.** Garmin's title field contained a city name on every run.
  A place name is a location identifier, so `Title` is now always empty. Do not treat
  its absence as missing data.

**This is still health data.** Distances, heart rates, paces and calorie burn are
private in a meaningful sense. The owner chose public visibility so the crew could
fetch it over a plain URL. Handle it accordingly.

---

## Files

| File | Purpose |
| --- | --- |
| `garmin_export.csv` | The activity log. **57 runs.** This is the file the crew reads. |
| `garmin_export.meta.json` | Row count, date range, per-source counts, and the newest `.FIT` on the device. |
| `profile.json` | Athlete parameters needed to reproduce the cohort/population math. **Unfilled by default** - see below. |
| `publish_state.json` | Raw URL, branch, last publish time, and a hash of the data. |

Read `garmin_export.meta.json` first. It reports how current the data is and where it
came from.

---

## Units and formats (get these wrong and every conclusion is wrong)

| Field | Format | Notes |
| --- | --- | --- |
| `Date` | `YYYY-MM-DD HH:MM:SS` | **Local wall clock**, no timezone. Do not treat as UTC. |
| `Distance` | decimal **miles** | Garmin is imperial here. **Not km, not metres.** |
| `Time` | `H:MM:SS` | Not zero-padded on the hours: `0:34:56`, `1:24:21`, `3:01:13`. |
| `Moving Time`, `Elapsed Time` | `H:MM:SS` | Elapsed includes pauses; they are often identical for runs. |
| `Avg Pace`, `Best Pace` | **minutes per mile** | **Higher = slower.** `9:00` is faster than `10:00`. |
| `Best Lap Time` | `H:MM:SS` | Fastest full lap, not a mile PR. |
| `Avg HR`, `Max HR` | bpm | |
| `Total Ascent`, `Total Descent` | **feet** | Converted from metres at read time. |
| `Min Elevation`, `Max Elevation` | feet | **FIT-only.** Empty on CSV-sourced rows. |
| `Avg Run Cadence` | rpm | |
| `Avg Stride Length` | feet | Sparse; many rows are empty. |
| `Training Stress Score` | Garmin's own 0-100 | **Empty on most rows.** The watch did not record it. |
| `Steps`, `Decompression` | count | Always empty for runs. Safe to ignore. |
| `Number of Laps` | count | FIT-only. |
| `_source_file` | text | Provenance: a `.FIT` filename or a CSV name. Not training data. |

### Paces are strings, not numbers

`Avg Pace` is `9:41`, meaning 9 minutes 41 seconds per mile. It is **not** `9.41`, and
it is **not** a decimal fraction. Convert with:

```python
def pace_to_dec(s):
    """'9:41' -> 9.683 minutes per mile. Handles '0:09:41' too."""
    parts = [int(p) for p in s.strip().split(":")]
    if len(parts) == 3:
        return parts[0] * 60 + parts[1] + parts[2] / 60.0
    return parts[0] + parts[1] / 60.0
```

Getting this wrong is the single most common way to produce confidently incorrect
training analysis.

### Header quirk (already fixed here, but know it)

Garmin's raw CSV export labels one column `Training Stress Score®`, with a trailing
registered-trademark symbol. The exporter strips trademark marks and non-breaking
spaces from headers, so **this repo exposes the clean name `Training Stress Score`**.
If you ever read a raw Garmin export, expect that mangled name.

---

## How this file is produced

Rows come from the watch's own `.FIT` files, which are the source of truth, with the
manually exported `Activities.csv` files as a fallback for any run the `.FIT` set is
missing. 56 of 57 rows come from `.FIT`.

This runs on a schedule twice daily, so **the data self-updates as long as the watch
has synced**. It is not a frozen snapshot. Check `latest_run` in the meta file before
making any claim about current fitness.

The publisher is at `C:\Users\benpi\Downloads\export_publish.py`, with FIT decoding in
`garmin_fit_reader.py`. It commits only when the underlying data actually changes.

### Raw URLs can lag a push by a few minutes

GitHub serves `raw.githubusercontent.com` through a CDN. Immediately after a new commit
lands, a fetch of the same URL can still return the **previous** version of a file for
a short while. GitHub's own API endpoint is not cached this way:

```
https://api.github.com/repos/benpioske-del/garmin-export/contents/<file>?ref=main
```

Consequences for the crew:

- Do not treat a repeated fetch as an error. The same data can arrive twice.
- Do not assume a successful read proves the newest commit is visible.
- Each fetch is internally consistent, so you will not get a half-written file, but you
  may get a slightly old one. `publish_state.json` carries a `data_sha` and an `at`
  timestamp: **if `data_sha` is unchanged, the data really is unchanged**, which is a
  more reliable check than the file's modification time.
- All files here are UTF-8 **without** a byte-order mark. If a parse fails on a leading
  BOM, that is a stale or mangled cached copy, not the current file.

---

## Reproducing the owner's dashboard scoring

If the crew wants to reproduce or critique the science panel, these are the real
implementations in `Coach Dashboard v1.20.html`. They are the source of truth, not any
prose description of them.

| Function | What it does |
| --- | --- |
| `riegelTo5k(timeMin, distMi)` | Riegel race-equivalent projection. The constant is **3.10686 miles** (a 5 km race), *not* 3.1 miles. An earlier version used the wrong constant and produced badly wrong science. |
| `computeSciencePercentiles(idx, sorted)` | Cohort, population, and self percentiles for one run. |
| `computeRollingScienceIndex(sorted, window)` | Mean percentile over the last N runs, compared against the prior N. |
| `computeRunGrade(idx, allRuns)` | Letter grade for one run. Bands: **A ≥ 90, B ≥ 78, C ≥ 65, D ≥ 50, else F.** |
| `ageFactor(age, sex)` | Age adjustment. **Requires `profile.json`.** |
| `censusPct(t5k, sex)` | Population percentile from a hand-built anchor table. **Requires `profile.json`.** |

### profile.json - currently unfilled

The cohort and population percentiles depend on **age and sex**, which are entered in
the dashboard UI and stored locally rather than derived from the activity log. They are
therefore **not** in this repo. `profile.json` is a template for the owner to fill in:

```json
{
  "age": null,
  "sex": null,
  "resting_hr": null,
  "weight_lb": null,
  "_comment": "age/sex enable ageFactor and censusPct. resting_hr enables Banister TRIMP load metrics."
}
```

**While `age` and `sex` are `null`, do not present cohort or population percentiles as
fact.** Either report them as unadjusted, or omit them and say why. An AI that quietly
assumes a default age will produce confident nonsense.

`resting_hr` is needed for heart-rate-strain training load (Banister TRIMP) and
recovery-debt maths, which the dashboard computes but this export cannot.

### Two score scales that must not be conflated

- **The letter grade (A–F) is relative.** It measures how a run compared to the owner's
  own recent baseline. It is a performance-versus-self score, not an absolute standard.
- **Percentiles and the rolling index are absolute.** They compare pace against cohort
  and population references.

A run can earn a high letter grade and still sit below population median. Presenting
those as the same number is the main analytical error to avoid.

### Known weak spots, disclosed

- `censusPct` uses a **crude, hand-entered anchor table** with a flat `+12`/`+13`
  offset from a world-referenced pace. Treat population percentiles as a coarse
  estimate, never as a ranking. The dashboard says so in its own UI.
- Sample size is small. 57 runs supports a trend, not a confident percentile.

---

## Rules for the crew

1. **Check `latest_run` before claiming anything about present fitness.** The file
   updates on its own, but the newest run may still be days old if the watch has not
   synced. Do not assume the last row is recent.
2. **Do not ask for GPS, routes, or the original `.FIT` files.** They are excluded on
   purpose. Do not ask the owner to add them.
3. **Do not treat the empty `Title` column as a bug or as missing data.** It is
   withheld deliberately.
4. **Do not invent training the log does not contain.** Missing data is missing, not easy.
5. **Do not diagnose injury or medical conditions.** The log records activity, not health.
6. **Convert pace strings properly** and state miles vs kilometres explicitly in any output.
7. **Flag uncertainty.** Split-level data is not in this export, `Training Stress Score`
   is mostly empty, and population percentiles depend on an unfilled profile. When a
   claim rests on those, say so.
