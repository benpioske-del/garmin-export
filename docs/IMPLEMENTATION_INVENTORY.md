# Implementation inventory

Supervisor brief Task 1. Verified against the working tree on 2026-10-01.

| | |
| --- | --- |
| Repository | `benpioske-del/garmin-export` |
| Branch | `main` |
| Python | 3.13.15 |
| Git | 2.53.0.windows.4 |
| Tests | 622 passed, 1 skipped (Windows symlink case) |
| `OPENCODE_INSTRUCTIONS.md` | **Absent.** Searched repository, parent, and local project directories. |

## Current status

| Task | Area | Status |
| --- | --- | --- |
| 1 | Inventory and documentation | Implemented |
| 2 | Canonical activity model, provenance, audit | Implemented |
| 3 | FIT data audit, hashes, parser versions | Implemented |
| 4 | Strength domain | Implemented |
| 5 | Training load, 7/14/28-day windows | Implemented |
| 6 | Recommendations and safety boundaries | Implemented |
| 7 | Shared terminology | Implemented |
| 8 | Health data with consent boundary | Partial â€” boundary implemented, no auth |
| 9 | Weather enrichment gate | Partial â€” gate implemented, no provider |
| 10 | Verification documentation | Implemented |
| 11 | Dashboard | Pre-existing, local-only, unversioned |
| 12 | Brief transport | Implemented, live; cross-second idempotency fixed in `3054d6a` |
| 13 | Quality gates and CI | **Not started** â€” supervisor brief Task 7 |

## Data layer

Created in this round. The brief assumed an existing data layer; there was none
(no `migrations/`, `schema.sql`, `models/`, `db/`, `api/`, and no
`sqlite3`/`sqlalchemy`/`flask`/`fastapi` import anywhere), so one was
established as the minimum that satisfies the requirement.

| Component | Path | Notes |
| --- | --- | --- |
| Connection + migration runner | `trainingdb.py` | stdlib `sqlite3`, no new dependency |
| Migrations | `migrations/001`â€“`006` | numbered SQL, applied in order, checksum-guarded |
| Database file | `trainloop.db` | **gitignored**, local only |
| Terminology | `terms.py` | shared by every module below |
| Activities | `activities.py` | canonical records, provenance, review, audit |
| Strength | `strength.py` | sessions â†’ exercises â†’ sets |
| Load | `loadcalc.py` | versioned `load-1.0.0`, windows 7/14/28 |
| Recommendations | `recommend.py` | six control states, refusal-first |
| Health | `health.py` | consent-gated, access-logged |
| Weather | `weather.py` | gate; no coordinates stored |

Design decisions:

- **stdlib `sqlite3` only.** No ORM, no new dependency, no build step. A single
  local file that is never published.
- **Editing an applied migration is a hard error.** The runner compares SHA-256
  and refuses to proceed, so schema history cannot drift silently.
- **`activities` is the system of record.** The CSV is a published view of it.
- **No REST API, no web framework, no auth, no UI** was created. None was
  present to extend, and inventing them was not in scope.

Docs: [`DATA_QUALITY.md`](DATA_QUALITY.md),
[`FIT_AUDIT.md`](FIT_AUDIT.md),
[`STRENGTH_DATA_CONTRACT.md`](STRENGTH_DATA_CONTRACT.md),
[`TRAINING_LOAD_METHODOLOGY.md`](TRAINING_LOAD_METHODOLOGY.md),
[`COACHING_SAFETY_BOUNDARIES.md`](COACHING_SAFETY_BOUNDARIES.md),
[`DATA_QUALITY_TERMINOLOGY.md`](DATA_QUALITY_TERMINOLOGY.md),
[`WEATHER_ENRICHMENT_GATE.md`](WEATHER_ENRICHMENT_GATE.md)

## Existing pipeline (unchanged)

| Component | Path | Notes |
| --- | --- | --- |
| FIT reader | `garmin_fit_reader.py` | `__version__ = 1.1.0`; asserts no GPS field escapes; attaches internal elevation diagnostics (`_ascent_smoothed_ft`, `_elev_range_ft`) that are excluded from the published CSV |
| CSV export | `garmin_export.csv` | 72 activities, 31 columns |
| Publisher | `export_publish.py` | guard, remote sync, history-safety enforcement |
| Sync | `garmin_sync.py` | OAuth, local only |
| Trigger server | `garmin_server.py` | localhost static + trigger routes, plus a read-only JSON API: `/api/activities`, `/api/load`, `/api/coaching`; `/` serves the committed Aurora app, `/classic` the local page, `/aurora` remains an alias; `GET`/`POST /api/nutrition` read and ingest the local nutrition log; `POST /api/nutrition/hook` is the token-only Health Connect bridge endpoint and `GET /api/nutrition/hook-info` its authenticated setup envelope; `POST /share-target` is the Android share-sheet fallback; `POST /sync` runs the Garmin download and import |
| Nutrition | `nutrition.py` | CalTrak CSV/JSON parse/aggregate, Health Connect ingestion, header aliases, local daily log at `paths.data_dir()/nutrition_log.csv` |
| Audit | `fit_audit.py` | rewritten: hashes, parser versions, counts only |
| Brief bridge | `brief_bridge.py` | `post` / `ingest` / `paste` / `serve` / `capture` |
| Profile | `profile.json` | `hr_max` set to 198; `age`, `sex`, `resting_hr`, `weight_lb`, `height_in` still `null` |

The profile's empty fields are still a live blocker, not a cosmetic gap: age,
sex, resting heart rate, weight and height block cohort percentiles, and a
weather location policy does not exist yet. The UTC offset is no longer part of
that gap: the athlete confirmed US Central on 2026-11-07, so every activity now
has a confirmed local date. `hr_max` is populated, so any brief describing the
profile as empty is reading an out-of-date copy of this document.

## Tooling

| Tool | Status |
| --- | --- |
| `python -m pytest` | Works. 622 passed, 1 skipped. |
| `python export_publish.py` | Works. Guard + push. |
| `python fit_audit.py` | Works. Deterministic, hash-per-file. |
| `python trainingdb.py migrate` | Works. Idempotent. |
| Linter | **None configured** |
| Formatter | **None configured** |
| Type checker | **None configured, no annotations** |
| CI | **None** â€” no workflow, no pre-commit |
| Dependency lockfile | **None** (`pyproject.toml` only) |
| `python -m build` | Not verified; the `build` package is not a declared dependency |
| Database vs export parity | **Verified 2026-11-11.** FIT directory, `garmin_export.csv` and `trainloop.db` all hold 72. Note `load` computes only; `bootstrap` is what imports. (The table drifted twice: to 58 by 2026-10-15, and to 61 by 2026-11-06 - the runs of 2026-10-13..2026-11-06 were downloaded but never imported. `bootstrap` was re-run on 2026-11-06 and imported all eight, on 2026-11-09 to import the 2026-11-08 run, and on 2026-11-11 to import the 2026-11-10 and 2026-11-11 runs.) |
| `garmin_export.csv` provenance | Rebuilt in-process with `export_publish.build_csv()` on 2026-10-03, not committed. It picks up `2026-10-01` from the FIT directory. |

Style is followed by convention rather than enforced by a tool. The root Python
modules use the existing naming and formatting, but nothing would catch a
regression in it.

## Data state

- 72 FIT files on disk, all parse, all with GPS and a usable timestamp
- 72 rows in `garmin_export.csv`
- 72 activities imported into `trainloop.db`, newest `2026-11-11`
- 650 laps, 67,446 records, 67,425 position points
- Re-import of identical files: 72 `unchanged`, 0 audit rows written
- **1 open date gap**: 2026-06-26 to 2026-07-05
- **0 open `timezone_uncertain` reviews**: all 72 local dates were confirmed by the athlete (US Central, UTC-5/-6 with DST applied per run; the 2026-11-08 run was confirmed at UTC-6 on 2026-11-10, and the 2026-11-10 and 2026-11-11 runs on 2026-11-11)
- **1 open `activity_gap` review** for the 2026-06-26 to 2026-07-05 gap
- 1 activity where the local date and UTC date differ
    (`garmin:23745136848`, local 2026-07-26T20:10:15, UTC 2026-07-27T01:10:15Z)
- 0 strength sessions. `strength_load` is `null` while this is true, which is
  not the same as zero.

All three sources now agree at **72**: FIT directory, CSV, and database. An
earlier brief asserted a 55/56/59 discrepancy; that premise was checked against
the live corpus and is not supported â€” there was nothing to reconcile. The
database fell behind three times: by one run until `trainloop bootstrap` was
re-run on 2026-10-04, by three runs (2026-10-06/08/10) until `bootstrap` was
re-run on 2026-10-15, and by eight runs (2026-10-13..2026-11-06) until it was
re-run on 2026-11-06; it is the import step that closes this, not `load`, which
only computes.

## Publish lock and repo visibility

Two scheduled tasks (`Garmin Export Publish`, `Garmin Export Publish PM`) run the
publisher unattended at 07:15 and 18:15. It commits and pushes whatever is in the
working tree, which is how half-finished work reached the public repo once already.

The coach now brackets its work with the publish lock:

```
python export_publish.py --lock      # scheduled runs stand down, exit 0, push nothing
python export_publish.py --unlock    # released even on failure; 45 min staleness anyway
```

The lock lives in the local data directory, so it can never be committed or read by
the crew. `CREW_TASKS.md` documents the protocol.

`repo_visibility` in `publish_state.json` used to be the literal string
`"public - readable without a token"`. It is now **probed** on every run, by issuing
an anonymous `HEAD` to the raw URL: that is exactly the property the supervisor flow
depends on, and it needs no token to test. The owner may make the repo private, so the
publisher prints fetch instructions that match the probed state — plain `curl` while
public, the contents API with `$GITHUB_TOKEN` while private, and the conservative
token form when the probe cannot reach GitHub.

The field lives in `publish_state.json` and not in `garmin_export.meta.json`, because
the meta file is written by `build_csv()`, which knows nothing about visibility. A test
pins that, and another fails if a document mentions `repo_visibility` without naming
the file it is in.

Making the repo private stops future reads; it does not un-publish what was already
committed while public.

`guard_token_content()` scans the text files a commit would contain for credential
patterns, reusing `SECRET_PATTERNS` from `capture_supervisor_brief.py` rather than
duplicating them. `guard_secrets()` only inspected file *names*, so a token pasted into
prose would have passed. Exemptions are explicit (`GUARD_IMPL`,
`SYNTHETIC_CREDENTIAL_FILES`) and each is pinned to a file that exists, because an
exemption for a deleted file is a silent hole.

## Coaching rationale fixtures

`tests/recommend_snapshots.py` pins the output of every reachable coaching
branch to a golden JSON file under `tests/fixtures/recommend/`, built from the
scenarios in `tests/recommend_scenarios.py`. Re-record with
`REGENERATE_SNAPSHOTS=1`, then read the diff.

Determinism is pinned two ways: `as_of` is a fixed instant, so the 7-day window
does not slide with the calendar, and `hr_max` is supplied rather than inferred.
Every scenario builds its database at an explicit path via
`trainingdb.connect(path=...)`; the environment variable is never set.

Reachability is established by sweeping 3600 database shapes rather than by
reading the source, because `STATE_DELOAD` *is* present in `recommend.py` inside
a branch nothing can reach.

Writing these found four defects, documented in
[COACHING_POLICY_AUDIT.md](COACHING_POLICY_AUDIT.md):

- `deload` is unreachable. The acute:chronic ratio is a 7-day sum over a 28-day
  sum, and the acute window is a subset of the chronic one, so the ratio is
  bounded by 1.0 while `HIGH_ACWR` is 1.5. The policy cannot recommend reducing
  load.
- The 1.3-1.5 caution band is dead for the same reason.
- `recover` is in `CONTROL_STATES` and returned by `available_states()`, but no
  branch produces it.
- A missing `hr_max` is reported as "only 0 runs in 28 days" rather than as a
  missing input, because runs without a computable load are dropped before being
  counted as days.

None are fixed here: each changes what the athlete is told, so they are policy
decisions rather than bugs to patch. Each is asserted in the suite, so a change
in either direction has to be acknowledged.

21 tests, plus 9 golden files.

## Dashboard data-source contract

`dashboard_contract.py` audits the private dashboard and writes
`docs/DASHBOARD_AUDIT.md`, which is committed. It exists because the dashboard
is gitignored: the brief process could not read it, so it described a file it
had never seen, guessed its contents twice, and re-issued
`connect-dashboard-to-data-layer` after that work was finished and merged.

The dashboard declares its own sources in a `window.DASHBOARD_SOURCES` block.
The contract checks that declaration against the document and fails on drift:

- every column-0 declaration is classified as private-journal, static table or
  scratch, so inline data cannot be added without saying what it is
- the canonical panel must fetch all three API routes, each with its own
  rejection handler, and must have a failure renderer that writes visible text
- the canonical panel may not read any private-journal declaration. This is the
  check that stops the two datasets being conflated.
- legacy features *may* still read the journal. Deleting it is not the fix: it
  holds narrative notes, splits, hydration, injury flags, weight and
  coordinates that exist in no FIT file.

Verified by mutation, not assertion. Ten realistic regressions are applied to
the real document in `tests/test_dashboard_contract.py` and every one must fail
the audit. Two of them were originally missed -- a keyword match for
"Unavailable" survived deleting the failure handler, and a forward scan for
`.then(` let one route claim another's handler. Both checks are now structural.

36 tests.

## Dashboard JSON API

Added for supervisor brief `connect-dashboard-to-data-layer`. Three read-only
same-origin GET routes, served by the existing locked-down `garmin_server.py`:

| Route | Source of truth | Notes |
| --- | --- | --- |
| `GET /api/activities` | `activities` + `review_items` + `activity_raw_refs` | canonical rows, open reviews preserved, `source_file` resolved from the raw-ref table rather than reconstructed |
| `GET /api/load` | `loadcalc.compute()` | 7/14/28 windows with real bounds; `algorithm` is `loadcalc.LOAD_VERSION` |
| `GET /api/coaching` | `recommend.recommend()` | refusal-first; `refused` is derived from `advisory`, not re-decided |

Design constraints, all test-enforced:

- **Nothing is recomputed.** The routes call the same functions the CLI calls, so
  the dashboard and `trainloop.py` cannot disagree about a number.
- **No count, version or threshold is written down.** Everything is queried. A
  brief asserting a wrong figure cannot make the API wrong.
- **`null` is not `0`.** `strength_load` stays `null` because no confirmed
  strength sessions exist; every window value is `null` on an empty database.
- **A refusal is not advice.** `refused` is true whenever `recommend` returns a
  non-advisory state, and the dashboard renders it as a refusal.
- **No stale fallback.** If the API fails the panel says so instead of falling
  back to the inline arrays still present elsewhere in the dashboard.
- **No traceback or path in a response.** 5xx returns
  `{"error": "internal error"}`; detail goes to stderr only.

Behind the existing `X-Dash-Token` gate and the `Host` header check. No CORS
headers are sent. Unknown query parameters are a 400 rather than being ignored,
because a silently ignored typo looks like a filter that did nothing. `as_of`
accepts UTC ISO-8601 and is validated.

The server also carries the mobile copy. Binding is loopback by default; `--lan`
(or `--host 0.0.0.0`) opts into LAN exposure, adds the bound IPv4 addresses to
the Host allowlist, and prints the phone URL with the token. `_host_ok()` still
requires a bound name **and** the served port. Neither page is relied on to
carry PWA tags (the classic page is generated outside the repo; the committed
Aurora artifact predates them), so the server injects the manifest link, mobile
meta and service-worker registration as it serves either HTML, and serves a real
`/manifest.webmanifest` and `/sw.js` above the token gate; the worker is
network-first with an offline fallback (it keeps the last page and its API data
on the device and uses them when the tunnel returns `5xx`) and only activates in
a secure context (https or localhost).

For exposure beyond the LAN (a tunnel whose URL is not secret) the server adds an
optional **password login**: `--password`/`GARMIN_DASH_PASSWORD` stores a salted
PBKDF2 hash locally, `GET /login` serves a form, a correct `POST /login` sets a
signed `HttpOnly` session cookie, and `GET /logout` clears it. When a password is
set the page redirects to `/login` unless authed, and every data route accepts
either the token or the cookie. `--clear-password` removes it and
`--idle-timeout 0` keeps the server up for a long-lived tunnel.

The pre-existing `fit-list`, `fit/<name>`, `ping` and cloud routes are
unchanged, covered by regression tests in `tests/test_dashboard_api_http.py`.
`sync` now runs `garmin_sync.py` and then `trainloop.py bootstrap`, so a
download cannot leave the dashboard behind; the order and the failure reporting
are pinned by `tests/test_sync_import.py`.

Tests: `tests/test_dashboard_api.py` (42), `tests/test_dashboard_api_http.py`
(91) and `tests/test_nutrition.py` (50). `smoke_dashboard_api.py` runs the same
paths against the live database and is deliberately not part of pytest.

`/` serves the committed `flow_outputs/aurora_dashboard.html` behind the same
gate; `/classic` serves the local `dashboard/index.html`, and `/aurora` remains
an alias so old bookmarks and the previous PWA `start_url` keep working. When
the committed app is missing, `/` falls back to the local page instead of a
`404`, so a clean checkout still opens a real dashboard. `launch_url()` makes
`--open` land on `/`.

The generated file bakes in its corpus and totals, so `inject_aurora_live()`
replaces them from the live API routes at serve time and says so in a badge. The
artifact's `analysis()` view had an unclosed template literal that stopped the
app from initialising; that was corrected in the committed file.

Chart parity was restored and then expanded in the artifact's `analysis()` view:
nineteen run-based charts in seven labelled groups (Volume, Intensity & effort,
Mechanics & terrain, Performance & pacing, Consistency, Body & strength,
Coaching), plus the per-mile splits chart on a run detail. The new charts are
monthly and cumulative mileage, TSS, calories, average vs maximum HR, climbing
cost, cadence, elevation gain, pace distribution, best 5K trend, latest-run
splits, a training-calendar heatmap, days between runs, and runs per month.
Charts with no data use `chartOrEmpty()` to show a named empty state instead of
a blank canvas; TSS is blank in every source record and bodyweight/strength have
no data at all. Chart.js v4.4.4 is vendored at
`flow_outputs/vendor/chart.umd.min.js`; `inject_aurora_live()` rewrites the
artifact's `cdn.jsdelivr.net` URL to `/vendor/chart.umd.min.js`, which the server
serves above the token gate. Chart creation is synchronous, because the original
`requestAnimationFrame` never ran in a background tab and left blank canvases.

`GET /api/activities` also carries the device summary fields the charts read
(`title`, `calories`, `avg_cadence`, `max_cadence`, `avg_pace_s_per_mi`,
`best_pace_s_per_mi`, `training_stress_score`) and joins `garmin_export.csv` by
`Source File` for `splits`, `best_5k_s` and `laps`. The database has no splits
table; a missing or malformed CSV yields `null` rather than an invented split.

### Nutrition ingestion

`nutrition.py` parses a CalTrak export server-side. CalTrak emits one row per
food entry, so `parse_caltrak_csv()` sums rows that share a date and returns one
daily total per date. It accepts the same header aliases the app's importer uses
(`date`/`day`, `calories`/`kcal`/`energy`, `protein`, `carbs`/`carbohydrates`/
`carb`, `fat`), normalises `YYYY-MM-DD`, `YYYY/MM/DD`, `M/D/YYYY` and `M/D/YY`,
treats empty numeric cells as zero, and rejects a missing date column,
unparseable dates, and negative or non-numeric values. `parse_caltrak_json()`
accepts a CalTrak JSON backup with no published schema by walking it for dated
nutrition objects, and `parse_export()` auto-detects CSV versus JSON.

- `GET /api/nutrition` returns `{days, count, fields, source, storage}` behind
  the token/login gate. Unknown query parameters are a `400`.
- `POST /api/nutrition` accepts `{"days": [...]}`, `{"csv": "..."}`,
  `{"json": ...}`, `{"backup": ...}`, or a raw CalTrak backup object. The CSV
  form is what makes aggregation a server responsibility rather than a browser
  one. Repeating a date upserts that day's row; it never appends a duplicate.
  It returns `{"accepted": n, "upserted": m, "total_days": k}`.
- `POST /api/nutrition/hook` is the phone bridge endpoint and sits above the
  browser gate. It requires a dedicated `X-Nutrition-Token` (or `Authorization:
  Bearer`) that is separate from the dashboard login token, accepts up to 8 MB
  of Health Connect JSON, and returns the same counts plus `source:
  "health-connect"` and `last_received`. `GET /api/nutrition/hook-info` is
  behind the normal gate and returns the path, header name, token, last upload
  time and managed-day count for the Fuel view's setup card. The token is
  stored beside the local log as `nutrition_log.hook-token`.
- Health Connect ingestion (`ingest_health_connect()`) keeps raw
  NutritionRecords by `metadata.id` in `nutrition_log.records.json`, so an
  incremental sync adds one entry without losing the rest of that day. A
  no-id record spanning an hour or more is a Daily aggregate: it is
  authoritative for its date and supersedes raw records. Health Connect clamps
  the current day to "now" and the oldest day to the 48-hour window, so the
  threshold cannot be 24 hours; a shorter no-id record is a time bucket and is
  summed. Deletions are applied by id; dates managed by the webhook are
  replaced wholesale while manually imported dates survive.
- **Seamless Android path.** CalTrak writes food entries to Android Health
  Connect. The free, open-source HC Webhook app reads Nutrition on an interval
  or on demand and POSTs it to `/api/nutrition/hook`, so no export or file
  picker is involved after one-time setup. The setup card recommends Daily
  resolution (one authoritative total per local day) and Local time so meals
  land on the right date.
- Rows are written to `paths.data_dir()/nutrition_log.csv`, not the committed
  template, so athlete nutrition is never published. `GARMIN_NUTRITION_FILE`
  overrides the path (tests use it). The committed `nutrition_log.csv` remains
  the schema of record and is still headers-only.
- The Aurora live layer (served at `/` and `/aurora`) replaces `NUTRITION` from `GET /api/nutrition` and
  overrides `window.importCSV` to POST the raw file, so the FUEL tab and the run
  detail's "Fuel that day" card show stored totals rather than localStorage.
  The committed view reads `kcal`, so the live layer maps `calories` to `kcal`
  at that seam. It exposes `window.auroraReloadAll` and
  `window.auroraReloadNutrition` so the sync button and importer redraw from
  the server.
- **Android share target.** CalTrak has no account or cloud API; its log is
  shared as a file. `MANIFEST_JSON` declares a `share_target` for
  `/share-target` (`POST`, `multipart/form-data`, file field `log`), so CalTrak's
  Share Log can go straight to the dashboard from Android's share sheet. The
  service worker intercepts the POST and forwards `{csv: text}` to
  `/api/nutrition`; `POST /share-target` is the server fallback for the first
  share before the worker is active. `multipart_file_text()` parses the body
  (Python 3.13 removed `cgi`), and both paths call `parse_export()` and
  redirect to `/?shared=ok|empty|error`.
- **One-tap Garmin sync.** The home view's `Sync Garmin now` button POSTs
  `/sync`, which runs `garmin_sync.py` and then `trainloop.py bootstrap`, and
  reloads from the API. The same button works from the phone and the laptop.

`dashboard/index.html` is untracked and gitignored because it contains
hand-entered athlete data, so the panel markup is not in version control. It is
appended as a self-contained IIFE that reads its own token from the URL and
exposes `window.refreshApiPanel()`.

## Backup and restore

| Component | Path | Notes |
| --- | --- | --- |
| Backup tool | `backup_data.py` | Zips local-only athlete data, prunes to 14 copies, writes `MANIFEST.txt` |
| Restore runbook | `docs/RESTORE.md` | Bare Windows to working dashboard, including credential regeneration |
| Destination | `%OneDrive%\CoachDashboardBackups` | Falls back to `%USERPROFILE%\Documents\CoachDashboardBackups` |
| Schedule | Task **Coach Data Backup** | Daily 12:00, `StartWhenAvailable`, 15-minute limit |

Bundled: `garmin_fit/*.fit`, `trainloop.db`, `dashboard/index.html`,
`garmin_sleep.csv`, `garmin_hr.csv`, `garmin_last_sync.json`, and, once
nutrition has been ingested, `nutrition_log.csv` and
`nutrition_log.records.json`.

Excluded by default: `.coach_dash_token`, `.coach_dash_auth`,
`nutrition_log.hook-token`, `garmin_tokens.json` and `.garmin_tokens/`. Each is
recreated after a restore, so the archive that lands in cloud storage does not
carry credentials.

The gap this closes: only the nutrition log and its Health Connect sidecar
cannot be rebuilt after a total loss. Runs come back from Garmin Connect through
the marker-based sync; `trainloop.db` comes back from `trainloop bootstrap`;
`dashboard/index.html` is gitignored and not rebuilt from anything, so the
backup is its only copy.

## Privacy posture

- Raw FIT files and `trainloop.db` are gitignored.
- Position data is never decoded into any report, doc or database row.
- `weather_observations` has no coordinate columns, enforced by a test.
- `export_publish.py` blocks any commit containing position data; the
  `dashboard/` directory is gitignored.
- **Known gap:** the guard cannot reject a bare single coordinate, because a
  decimal like `44.95` is indistinguishable from legitimate training data. The
  guard catches labelled fields, coordinate pairs, semicircle names and CSV
  coordinate columns. Manual review is still required.

## Known blockers

1. `profile.json` is **partially** populated, not empty. `hr_max` is set to
   198 (a deliberate choice above the observed 195 peak); `age`, `sex`,
   `resting_hr`, `weight_lb` and `height_in` are still `null`. The missing
   values block cohort percentiles and the weather location policy. The
   athlete's UTC offset is no longer missing: it was confirmed as US Central on
   2026-11-07, and the 2026-11-08 run was confirmed at UTC-6 on 2026-11-10,
   resolving every timezone review.
2. No authentication and no multi-athlete separation. The health boundary is
   single-subject and described that way, not dressed up as a permission system.
3. ~~The transport is not live.~~ **Resolved.** The CrewAI flow pushes
   `SUPERVISOR_BRIEF.md` directly to `main`, and the bridge additionally accepts
   inbox drops and clipboard paste. See `docs/SUPERVISOR_BRIDGE.md`.
4. ~~`commit_brief()` regenerates `captured_utc`, breaking idempotency across
   seconds.~~ **Fixed** in `3054d6a`. The file's identity is now `brief_id`, the
   SHA-256 of the brief text; `captured_utc` is metadata and no longer affects
   identity. Covered by tests that advance a frozen clock 90 seconds, because
   the previous test passed only by committing twice inside one second.
5. GitHub retains old unreachable commits by SHA. Current `main` is clean;
   removal requires deleting and recreating the repository.
6. No CI, linter, formatter, type checker or dependency lockfile. This is
   supervisor brief Task 7 and is the largest remaining gap in release
   controls.

## Corrections made to this document

The supervisor reads this file and `VERIFICATION_REPORT.md` as its evidence
base, so a stale number here becomes a wrong instruction in the next brief.
Two things were corrected on 2026-10-01 after a run acted on them:

- The **152-test** count was stale; it is now 501.
- **`profile.json` was described as empty**; it carries `hr_max` and field
  notes, and only the remaining fields are `null`.

One claim could not be sourced at all and was withdrawn rather than carried
forward: an earlier brief stated that 53 of 55 runs fall in HR Zone 5. There is
no HR zone classification anywhere in this repository â€” every occurrence of
"zone" in the source is `timezone_source` â€” and `53` and `55` appear in these
docs only inside the Git version string `2.53.0.windows.4`. Any future brief
asserting zone distribution should be treated as unfounded until code for it
exists.
