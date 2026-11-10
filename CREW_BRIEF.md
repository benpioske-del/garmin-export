# Crew Brief: Garmin Training Data

## What this repository is

A sanitized export of one runner's Garmin activity log, published so an AI crew can
analyse training without access to the original device or the owner's machine.

> ### READ THIS FIRST: check visibility before you fetch
>
> The repository was private from 2026-10-05. The 2026-11-10 publish probed it as
> **public**, so anonymous fetches currently succeed. Do not assume either state:
> `publish_state.json` and `brief_facts.json` carry `repo_visibility`, probed on
> every publish. A 404 while private does not mean a file is missing; it means
> you are unauthenticated.
>
> **If you cannot fetch this file, you cannot fetch anything here, and you must not
> write a brief from memory.** Four briefs have been written that way and all four
> were wrong about the same things: the dashboard integration (done since long
> before), the corpus size (61, not 57), the open review count (59, not 58), and the
> test count (429, not 207). Those are not judgement errors. They are the shape of
> a writer with no access to the data.
>
> Before writing any number or asserting any state, ask how you obtained it. If the
> answer is "I recall", it does not go in the brief.
>
> For a read-only fetch, use the contents API with a fine-grained token
> (`Contents: Read`, this repository only). See below. Never put the token in a
> brief, a task, a commit, or a chat message.

**The publisher probes whether the repository is public, and does not assume it.**
Anything committed here while it was public is readable by anyone, forever
(Git history is public too, so a deleted row does not really disappear).

### If the repo is later made private

This already happened. Nothing here needed to change for it to work, but **the
plain URLs stopped working**, so check first:

- `publish_state.json` carries `repo_visibility`, which is **probed on every publish**,
  not assumed. Treat it as the source of truth, not this paragraph.
- `public`: fetch over plain `raw.githubusercontent.com`, no credentials needed.
- `private`: the raw URL returns **404**. Use the contents API with a read-only token:

  ```
  gh api repos/benpioske-del/garmin-export/contents/garmin_export.csv --jq .content | base64 -d
  ```

  or, without `gh`:

  ```
  curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
    https://api.github.com/repos/benpioske-del/garmin-export/contents/garmin_export.csv
  ```

- `unknown`: the probe could not reach GitHub (offline). Assume a token is required.

**Never ask the runner to paste a token into a task file, a commit, or any file in
this repo.** Read it from the environment at fetch time. If the repo goes private and
the crew cannot authenticate, say so in your output rather than silently reporting
stale data as current.

Note the trade-off: private visibility protects the data going forward, but it does
**not** un-publish anything already committed while the repo was public.

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
| `garmin_export.csv` | The activity log. This is the file the crew reads. Row count changes as the watch syncs, so take the number from `garmin_export.meta.json` rather than from this file. |
| `garmin_export.meta.json` | Row count, date range, per-source counts, and the newest `.FIT` on the device. |
| `profile.json` | Athlete parameters needed to reproduce the cohort/population math. **Unfilled by default** - see below. |
| `publish_state.json` | Raw URL, branch, last publish time, a hash of the data, and the probed `repo_visibility`. |

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
missing. Every published row currently comes from a `.FIT` file.

This runs on a schedule twice daily, so **the data self-updates as long as the watch
has synced**. It is not a frozen snapshot. Check `latest_run` in the meta file before
making any claim about current fitness.

The publisher is `export_publish.py` **in this repository**, with FIT decoding in
`garmin_fit_reader.py`. It commits only when the underlying data actually changes. It
probes repo visibility on every run and records the result in `publish_state.json`
as `repo_visibility`.

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

### Current verified state, 2026-10-05

> **Fetch `brief_facts.json` first.** It is regenerated on every publish and holds
> these same figures as machine-readable JSON, with the commit it describes. Quote
> it; do not recall it. The table below is the same content for a human reader and
> it goes stale — that is the whole problem.

If you cannot fetch this file, this is the last known good. It is a floor, not a
source. Re-derive it if you can.

| Fact | Value | How to re-derive |
|---|---|---|
| Repository visibility | **public** (probed 2026-11-10) | `publish_state.json` → `repo_visibility` |
| FIT files | 70 | count in the local export |
| Activities | 70 | `SELECT COUNT(*) FROM activities` |
| Open reviews | 1 | 1 `activity_gap` (2026-06-26..2026-07-05); timezone reviews resolved (2026-11-07, and the 2026-11-08 run on 2026-11-10) |
| FIT files with lap records | 70 of 70 | `python brief_consistency.py` |
| Splits published | yes (`Best 5K Time`, `Lap Splits`) | header of `garmin_export.csv` |
| Fastest measured 5 km crossing | 24:42 on 2026-06-16, measured | `brief_facts.json` → `best_5k` |
| Tests | 496 passed, 1 skipped (497 collected) | `python -m pytest` |
| Dashboard API routes | 3, implemented and tested | `python dashboard_contract.py` |
| Dashboard consumes the API | yes, all three | `python dashboard_contract.py` |

**Quote `brief_facts.json`, never memory.** The bridge now refuses a brief whose
numbers contradict measured facts, staging it for review and printing the correct
value. If you cannot fetch the file, say you could not fetch it rather than
recalling a count.

**`connect-dashboard-to-data-layer` is complete.** `garmin_server.py` serves
`/api/activities`, `/api/load` and `/api/coaching` from the canonical data layer,
`dashboard/index.html` consumes all three, and 80 tests cover it including 42
against a real bound HTTP server. Four briefs have asked for this work. Do not
rebuild it. Verify with `python dashboard_contract.py`, which prints `PASS`.

**The mobile copy is done without CORS.** The server defaults to loopback and a
per-launch token; `--lan` (or `--host 0.0.0.0`) opts into phone access by adding
the bound LAN addresses to the Host allowlist and printing the token URL. No CORS
headers are sent - the page and API share one origin, and a test asserts
`Access-Control-Allow-Origin` never appears. The dashboard file is gitignored, so
the server injects the manifest link and service-worker registration as it serves
the HTML and serves a real `/manifest.webmanifest` and `/sw.js`. The worker is
network-first with an **offline fallback**: it keeps the last dashboard page and
its API data on the device so the app opens when the laptop is off, and falls
back to that cache when the tunnel returns a `5xx`. A service worker only runs in
a secure context, so over plain `http://<lan-ip>` the home-screen shortcut is
live but offline caching is not (it activates under the https tunnel or on
localhost). Do not ask for CORS or `0.0.0.0` by default; both were decided
against.

**A password login now exists (added at the athlete's request).** For access
from outside the home WiFi, `--password`/`GARMIN_DASH_PASSWORD` enables a login:
`GET /login` serves a form, a correct `POST /login` sets a signed `HttpOnly`
session cookie, and `GET /logout` clears it. The password is stored only as a
salted PBKDF2 hash. When set, the page redirects to `/login` unless authed and
every data route accepts either the token or the cookie. `--clear-password`
removes it and `--idle-timeout 0` keeps the server alive for a long-lived tunnel.

The task queue is `tasks/`, which holds two files: `001-example-task.md` (a
placeholder) and `002-log-a-5k-pr.md` (**done** - the measured 5 km crossing is
24:42 on 2026-06-16, in `best_5k`).
`SUPERVISOR_BRIEF.md` is prose and is not the queue. A brief naming a task with no
file in `tasks/` is not a task.

### Known weak spots, disclosed

- `censusPct` uses a **crude, hand-entered anchor table** with a flat `+12`/`+13`
  offset from a world-referenced pace. Treat population percentiles as a coarse
  estimate, never as a ranking. The dashboard says so in its own UI.
- Sample size is small. The run count (see `garmin_export.meta.json`) supports a
  trend, not a confident percentile.

### Splits: measured 5 km crossing, now published
**Do not claim per-mile splits are unavailable.** They are not. Every one of the 70
FIT files carries lap records, and since this publish `garmin_export.csv` has two
new columns:

- **`Best 5K Time`** - the measured clock time at which the distance curve first
  reaches 5 km, per activity. Not a projection from average pace.
- **`Lap Splits`** - the device's auto-lap times. If a file never records lap
  messages, per-mile splits are computed from the distance curve instead, so the
  column is never empty.

`brief_facts.json` carries the fastest measured crossing across the corpus along
with its date. **Measured, not a PR**: a crossing that contains a stop is the
clock time at the distance, not the quality of the effort. Treat any mark as a
measurement unless the runner confirms it was a genuine attempt.

Task `002` previously dragged the requested "24:34 on 2026-05-21" because that
figure contradicted the logs. The export can now support a measured mark; keep
quoting `brief_facts.json` rather than recalling any number.

`Source File` still matters: `Best Lap Time`, `Number of Laps`, `Best 5K Time`
and `Lap Splits` are FIT-only, so a CSV-only row carries no split information.

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
