# Verification report

Supervisor brief Task 10. Everything below was run in the working tree on
2026-11-07 and refreshed on 2026-11-17 after the CrewAI dashboard rewrite was
merged and re-wired. Commands and results are reproduced as observed.

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
853 passed, 3 skipped (856 collected)
```

The same suite passes with an empty `GARMIN_DATA_DIR` and no local FIT corpus:
`832 passed, 24 skipped`. The live-corpus tests
skip via `requires_real_fit`, `requires_real_db` and `requires_live_corpus` in
`tests/conftest.py`; the dashboard-contract and brief checks that read the
gitignored page skip when it is absent; one symlink case skips on Windows; the
JavaScript syntax check skips where `node` is not installed (GitHub's runners
have it, so CI still parses the injected script); the `bash -n` check on the
deployment scripts skips where `bash` is not installed (CI runs it). CI fails
only on a real defect. `ruff check .` is clean.

CI runs the suite on Python 3.12 and 3.13. `garminconnect>=0.3.13` declares
`Requires-Python >=3.12`, so `requires-python` is now `>=3.12` and the old 3.10
job was removed: it could never install the dependency, and it failed before
lint or tests ran.

| File | Tests |
| --- | --- |
| `tests/test_training_data.py` | 64 |
| `tests/test_brief_bridge.py` | 62 |
| `tests/test_nutrition.py` | 58 |
| `tests/test_publish_flow.py` | 50 |
| `tests/test_dashboard_api.py` | 42 |
| `tests/test_dashboard_api_http.py` | 104 |
| `tests/test_brief_consistency.py` | 37 |
| `tests/test_dashboard_contract.py` | 36 |
| `tests/test_manual_runs.py` | 30 |
| `tests/test_aurora_template.py` | 32 |
| `tests/test_recommend_snapshots.py` | 25 |
| `tests/test_trainloop_cli.py` | 22 |
| `tests/test_fit_reader_elevation.py` | 21 |
| `tests/test_provenance.py` | 18 |
| `tests/test_backup_data.py` | 18 |
| `tests/test_publish_scope.py` | 17 |
| `tests/test_capture_supervisor.py` | 16 |
| `tests/test_fit_audit.py` | 16 |
| `tests/test_gps_guard.py` | 13 |
| `tests/test_splits.py` | 10 |
| `tests/test_paths_and_guards.py` | 9 |
| `tests/test_sync_import.py` | 8 |
| `tests/test_history_safety.py` | 2 |
| `tests/test_cloud_deploy.py` | 20 |
| **Total** | **730** (727 pass, 3 skip) |

`tests/test_fit_reader_elevation.py` covers the elevation diagnostics added with
reader 1.1.0; see [ELEVATION.md](ELEVATION.md). Four of its tests are the CSV
leak guard, which caught the diagnostics being published as columns before this
report was written.

The skip is the Windows symlink case in the brief-bridge suite; the code path is
covered on platforms that permit symlinks. The other two skips on this laptop are
the `node` and `bash` syntax checks; both tools are present on CI, where they run.

Up from 90 passed / 1 skipped at the start of the data-layer round. The brief
bridge grew from 26 to 62 tests since then: clipboard and `.txt` transports,
rejected-brief staging, and a `frozen_clock` fixture that advances the clock 90
seconds to prove republishing an unchanged brief is a no-op. `test_trainloop_cli.py`
is new.

The facts gate came last: 6 bridge tests pin a brief being refused when its
numbers contradict `measured_facts()`, the refusal naming the right number, the
rejected brief being staged outside the repo, `--tolerate-facts` merging the
contradiction on the record, and the compare being skipped for prose with no
numeric claims. The conflict checkers in `test_brief_consistency.py` gained a
`text=` argument used by that gate and an aggregation/dedupe test.

The splits hardening next: `garmin_fit_reader.py` now falls back to per-mile
splits computed from the distance curve when a file carries no lap messages, so
a run is never published with an empty split column. `brief_facts.json` carries
the published-CSV coverage (`rows_published` / `rows_with_splits`); if a backfill
ever drifts from the CSV they stop matching and the fact gate can see it.
`test_splits.py` grew to 10 tests and `test_brief_consistency.py` to 36.

## FIT data audit

```
$ python fit_audit.py
FIT data audit
parser: fitparse=1.2.0 reader=1.1.0

files inspected           : 75
parse failures            : 0
files readable            : 75
files with GPS            : 75
files without GPS         : 0
files with usable timestamp: 75
files without timestamp   : 0
session messages          : 75
lap messages              : 682
record messages           : 70728
position points (counted) : 70705
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
`RuntimeError: migration NNN changed after it was applied` â€” covered by
`test_edited_migration_is_a_hard_error`.

## Import against the real corpus

On a fresh database with the current corpus of 75 files, the first import
inserts all 75. Re-running against a database that already holds them reports
every file `unchanged`:

```
$ python activities.py import
{"inserted": 0, "updated": 0, "unchanged": 75, "unreadable": 0}
```

**Idempotency verified on the real data**: no rows updated, and no new audit
rows written on the second pass.

```
$ python activities.py summary
{"activities": 75, "open_reviews": 4}
```

- 75 activities
- 3 open `timezone_uncertain` reviews: the three newest runs, 2026-11-14
  (`garmin:25080247947`), 2026-11-17 (`garmin:25113046573`) and 2026-11-19
  (`garmin:25135653593`), whose local date
  is derived from the filename and still needs athlete confirmation. Every
  earlier local date was confirmed (US Central, UTC-5/-6 with DST applied per
  run; the 2026-11-08 run at UTC-6 on 2026-11-10, and the 2026-11-10 and
  2026-11-11 runs on 2026-11-11)
- 1 open `activity_gap`: `no activity 2026-06-26..2026-07-05 (8 days)`
- 0 duplicates detected
- 75 SHA-256 raw references stored

The FIT-file inventory, the canonical table and the published CSV all agree at
**75**. An earlier brief described a 55/56/59 discrepancy; that premise was
checked against the live corpus and is unsupported, so there is no
reconciliation to perform.

Note for anyone re-running this: `trainloop.py load` only *computes* load. The
command that imports new FIT files is `trainloop.py bootstrap`. This trap has now
recurred four times. On 2026-10-04 the database held 57 while the FIT directory
and CSV held 58; on 2026-10-15 it held 58 while they held 61; and on 2026-11-06 it
held 61 while the FIT directory held 69 (and the published CSV 68) - the eight
runs from 2026-10-13 to 2026-11-06 had been downloaded but never imported, so
every load figure and the dashboard silently excluded them. Re-running
`trainloop.py bootstrap` on 2026-10-15 imported three
(`{"inserted": 3, "unchanged": 58}`), and again on 2026-11-06 imported eight
(`{"inserted": 8, "unchanged": 61}`), bringing the table to 69. On 2026-11-09
the 2026-11-08 run was imported (`{"inserted": 1, "unchanged": 69}`), bringing
the table to 70. On 2026-11-11 two more runs (2026-11-10 and 2026-11-11) were
imported (`{"inserted": 2, "unchanged": 70}`), bringing the table to 72. On
2026-11-17 the two newest runs (2026-11-14 and 2026-11-17) were imported
(`{"inserted": 2, "unchanged": 72}`), bringing the table to 74. The 2026-11-10
run was the fourth recurrence: it was on disk but absent from the dashboard.
`POST /sync` now runs `trainloop.py bootstrap` after `garmin_sync.py`, and the
import is attempted even when the download fails, so the dashboard path can no
longer stop after the download.

On 2026-11-20 the 2026-11-19 run (13.11 mi, `garmin:25135653593`) was already in
the database and the FIT directory while the published CSV still held 74.
`python trainloop.py bootstrap` reported
`{"inserted": 0, "updated": 0, "unchanged": 75, "unreadable": 0}`, and the next
publish brought the CSV to 75. This is the first observed case of the CSV
lagging the database rather than the other way round: the sync imported the run,
but nothing had published since.

## Training load and recommendation

Against the real corpus, with `hr_max=198` supplied by the caller (the value now
in `profile.json`; the figure below was produced with an earlier test value and
the load is bucketed by intensity band, so the exact number inside 195-203 does
not change it):

```
$ python trainloop.py load
7d    run 149.3   strength n/a  combined 149.3   run_conf medium
14d   run 780.8   strength n/a  combined 780.8   run_conf medium
28d   run 2592.3  strength n/a  combined 2592.3  run_conf medium

$ python trainloop.py recommend
state: data_insufficient
advisory: no
reasons:
  - only 1 training days with runs in 7 days, need 3
evidence:
  days_since_last_run  1
  run_days_28d         8
  run_days_7d          1
  run_load_28d         2592.3
  strength_days_28d    0
  strength_load_28d    None
```

Two things worth stating plainly:

- `strength_load` is `null`, not `0`. No strength sessions exist yet, and an
  absent component is not a zero component.
- The recommendation is a **refusal**, and it is the correct one: the acute
  window holds only one run day (2026-11-06), below the three the method needs
  to compare against the chronic window. This is the designed behaviour, not a
  failure. The earlier `confirmation_required` refusal was cleared on
  2026-11-07 when the athlete confirmed the local UTC offset; it is no longer
  blocking.

The 7-day figure is 149.3 because only one run falls inside the acute window.
When the database was a run behind, that figure was understated; the import step
is what keeps it honest.

## Publisher and privacy guard

```
$ python export_publish.py
```

Runs the position-data guard over every candidate file, refuses to commit if
position data is present, then commits and pushes. The guard blocks labelled
coordinate fields, degree pairs, FIT semicircle field names, and CSV coordinate
columns.

**Raw URL freshness, observed 2026-11-20:** after the 75-run publish, the
`main` raw URL below still served the older 74-run blob from the CDN, while the
same URL pinned to the published commit SHA and the GitHub contents API both
served the current 75-run blob. A crew that needs current numbers should fetch
the commit-pinned raw URL built from `brief_facts.json`'s `commit` field, or the
contents API, rather than trusting the unpinned `main` URL. This is a CDN cache
behaviour, not a git problem: `origin/main` and the local blob both point at the
75-run file.

**Known limitation, unchanged:** the guard cannot reject a bare single
coordinate, because a decimal such as `44.95` is indistinguishable from
legitimate training data. Manual review remains necessary. This is recorded in
the inventory rather than papered over.

### `brief_facts.json` regeneration, and the loop it briefly caused

The publisher now regenerates `brief_facts.json` on every run so a brief can
quote machine-readable figures instead of recalling them. Regenerating it also
means deciding whether anything actually changed, and that decision briefly went
wrong in a way worth recording:

`export_publish.py` decides to stand down by comparing recorded digests against
current ones. Three fields had to be excluded from the facts digest before that
comparison was correct, and each exclusion was found by watching it fail:

| Field | Why it had to go |
| --- | --- |
| `generated_utc` | A fresh stamp on identical figures is not a change. Hashing it made every run commit. |
| `facts_sha` | A digest cannot cover its own output. |
| `commit` | The subtle one. `commit` is HEAD, so publishing moved the value being hashed: HEAD moved, the file recorded the new HEAD, the digest differed, it committed again. Unbounded. |

The third one is self-reference, not a timestamp bug, and it is the reason
`commit` sits outside the digest while still being published in the file. The
first two attempts are visible in history as six commits sharing the message
`garmin export: 58 runs, latest 2026-10-01`; they are harmless and were already
pushed, so they were left rather than force-rewritten.

Verification is a three-run check: run twice with no data change and the second
run must print `data unchanged since last publish - no commit needed.` and leave
`git status` clean. The early-return path restores `brief_facts.json` along with
`publish_state.json`, because a quiet run rewrites its timestamp and would
otherwise leave the tree permanently dirty.

Pinned by `test_facts_digest_ignores_the_timestamp`,
`test_facts_digest_excludes_the_commit_it_describes`, and
`test_two_generations_of_the_same_state_agree` in
`tests/test_brief_consistency.py`.

## Dashboard server and mobile copy

`garmin_server.py` serves the committed Aurora app at `/`, the gitignored
`dashboard/index.html` at `/classic`, and the read-only JSON API
(`/api/activities`, `/api/load`, `/api/coaching`) on the same origin. It defaults to loopback and a per-launch token. The athlete decided the
dashboard should also be reachable from a phone on the home WiFi, so the server
gained a deliberate, opt-in exposure path rather than an always-on one:

- `--lan` (equivalently `--host 0.0.0.0`) binds all interfaces; the bound LAN
  IPv4 addresses are added to the Host allowlist and the startup message prints
  the LAN URL with the token. The default binding is still `127.0.0.1`.
- `_host_ok()` requires the `Host` header to name a bound address **and** carry
  the served port, so a DNS-rebinding host or a wrong port is refused (`403`).
- Every data route stays behind the per-launch token (`X-Dash-Token`, `?tk=`
  or the local `dash_local` cookie) or a valid login session.
- **No CORS headers are sent.** The page and the API share one origin, so CORS
  is unnecessary; `test_no_cors_headers_are_ever_sent` asserts
  `Access-Control-Allow-Origin` never appears.
- Neither dashboard file is relied on to carry PWA tags. The classic page is
  generated outside this repository, and the committed Aurora artifact predates
  them. As either HTML is served, the server injects the manifest link, mobile
  `theme-color`/viewport meta and the service-worker registration
  (`inject_pwa()`), and serves a real `/manifest.webmanifest` and `/sw.js`.
  Both are served above the token gate because the browser fetches them itself.
- The service worker is **network-first with an offline fallback** (`SW_JS`). It
  keeps the last dashboard page and its API responses in the device's Cache
  Storage so the app still opens when the laptop - and therefore the tunnel - is
  off. It only caches GET responses already served to a signed-in browser on
  that device; it never caches `POST`s, the login page, or a non-2xx
  origin-outage page. A dead tunnel answers `502`/`503`/`504` (not a network
  error), so the worker treats those as "use the cache" rather than showing the
  error. It also adds the `ngrok-skip-browser-warning` header to its data
  requests so the free-tier interstitial cannot corrupt a JSON response.

### Password login

Reaching the dashboard from outside the LAN (a tunnel whose URL is not secret)
needs more than the token, so the server gained an additive password gate:

- `--password` (or `GARMIN_DASH_PASSWORD`) enables it; the password is stored
  only as a salted PBKDF2-SHA256 hash (`hash_password`) in the local data dir,
  never in the repo and never echoed to a response. `--clear-password` removes
  it.
- `GET /login` renders a self-contained sign-in form; `POST /login` verifies
  with a constant-time compare and sets a signed, `HttpOnly`, `SameSite=Lax`
  session cookie (`make_session`/`session_valid`, an HMAC over the cookie's own
  expiry). `GET /logout` clears it. Repeated failures are throttled.
- When a password is set, the dashboard page redirects to `/login` unless the
  request is authed; **both the page and every data route accept either the
  local token or a valid session cookie**. The token path is unchanged, so local
  `?tk=` use and every pre-existing test still work.
- The cookie is marked `Secure` only when the request arrives over TLS
  (`X-Forwarded-Proto: https`), so it still works over plain LAN http.
- `--idle-timeout 0` disables the idle shutdown, which is needed for a
  long-lived tunnel.

### Local session cookie and the classic placeholder

The launch URL carries the token as `?tk=`, but a PWA launch (`start_url: "/"`),
a bookmark, a restored tab or a second visit does not. Those loads used to get
`403` from every data call and from `Sync Garmin now`, which read like a Garmin
failure. Serving `/` or `/classic` now sets an `HttpOnly`, `SameSite=Strict`
`dash_local` cookie carrying the local token, so the page authenticates its own
fetches without a query string.

- `SameSite=Strict` is deliberate: a cross-site `POST` cannot carry the cookie,
  so the CSRF protection of the token gate is unchanged. `HttpOnly` keeps page
  script from reading the token back out.
- In password mode the signed `dash_session` cookie already covers the page, so
  `dash_local` is only set when no password is configured.
- The classic page refuses `/sync` without `?tk=`, so when an already-authed
  request reaches `/classic` with no token in the query, the server injects
  `inject_classic_session()`. It sets `tk=session` with
  `history.replaceState`; the literal string `session` is not a credential, the
  cookie is. A real `?tk=` URL is left unchanged, and the real token never
  enters the URL, history or a tunnel log.

`tests/test_dashboard_api_http.py` (104 tests) covers the manifest and worker
routes, the injected tags, injection idempotence, host/port allowlisting, the
offline fallback (the worker keeps the shell and API data, and falls back to the
cache on a `5xx` origin outage), the login gate (redirect, form, wrong
password, cookie unlock, forged cookie, token back-compat, logout, `Secure`
flag, session expiry), the local cookie (set on `/`, authenticates a data route,
a wrong cookie refused), the classic placeholder, and the manual-run route.
**Caveat:** service workers require a secure context, so
over plain `http://<lan-ip>` the "Add to Home Screen" action produces a live
shortcut with no offline worker; the worker - and therefore the offline copy -
activates only under https (the tunnel) or on localhost.

### Aurora is the dashboard (`/`), classic page at `/classic`

The CrewAI flow commits a self-contained app at
`flow_outputs/aurora_dashboard.html`. It is now the canonical dashboard at `/`
behind the same token/login gate as the data routes. The pre-Aurora page is
kept at `/classic`, and `/aurora` remains an alias so old bookmarks and the
previous PWA `start_url` keep working. If the committed artifact is absent (a
clean checkout), `/` falls back to the local page rather than returning `404`.

- **Chart parity, then expansion.** The flow artifact had only three canvases
  (load, fitness, splits). The Analysis view now renders nineteen run-based
  charts in seven labelled groups: Volume (training load, weekly mileage,
  monthly mileage, cumulative mileage, distance by run), Intensity & effort
  (pace and heart rate, training stress score, calories, average vs maximum HR,
  climbing cost), Mechanics & terrain (cadence, elevation gain), Performance &
  pacing (fitness scatter, run bubbles, pacing fade, pace distribution, best 5K
  trend, latest-run splits), Consistency (training-calendar heatmap, days
  between runs, runs per month), Body & strength, and Coaching. The run detail
  keeps the per-mile splits chart. Charts with no data show a named empty state
  (`chartOrEmpty`) rather than a blank canvas: TSS is blank in every source
  record, and bodyweight and strength have no data at all.
- **No CDN.** Chart.js v4.4.4 is vendored at
  `flow_outputs/vendor/chart.umd.min.js` (205,749 bytes, SHA-256
  `B38076762F7363BC9E912B68B8E034826798DB5DF26BB61F000EC2E7A3137BC7`) and
  served at `/vendor/chart.umd.min.js`. The server rewrites the artifact's
  `cdn.jsdelivr.net` URL at serve time, so the committed file stays exactly as
  the flow produced it and the app works offline or behind a blocked CDN.
- **Synchronous chart creation.** The artifact used `requestAnimationFrame`,
  which never runs in a background tab and left blank canvases. Charts are now
  created as soon as the view's HTML is in the DOM.
- `GET /api/activities` now exposes the device summary fields the charts need
  (`title`, `calories`, `avg_cadence`, `max_cadence`, `avg_pace_s_per_mi`,
  `best_pace_s_per_mi`, `training_stress_score`) and joins the published CSV by
  `Source File` for `splits`, `best_5k_s` and `laps`. The database has no splits
  table; a missing or malformed CSV yields null, never an invented split.
- The committed file bakes in its run corpus, `SUMMARY` totals and ACWR. The
  server injects `AURORA_LIVE_SCRIPT` at serve time (`inject_aurora_live()`,
  idempotent via the `aurora-live-v1` marker) to replace the corpus and totals
  from `/api/activities`, derive ACWR from `/api/load`, and repaint the
  training-signal card from `/api/coaching`. A failed call leaves the committed
  snapshot in place and the badge says the API was unavailable; it never invents
  a value. The generated narrative panels remain the committed snapshot.
- `inject_pwa()` is applied to Aurora as well as the classic page, so the
  manifest, mobile meta and service-worker registration work on the dashboard
  the athlete actually uses.
- **Artifact bug fixed:** the generated `analysis()` view had an unclosed
  template literal (`` `card")} `` instead of `` `card`)} ``), which raised
  `SyntaxError: missing ) after argument list` at line 148 and stopped the whole
  app from initialising. It was corrected in place in the committed artifact.
- Verified in-browser against the live database at 72 runs: nineteen Analysis
  charts with data (72 points on each run-based chart, 62 weeks, 16 months, 115
  heatmap days), six mile splits on the latest run, and no console errors.
  The corpus has since grown to 75; the same page served by the live server
  reports 75 activities and 4 open reviews, and `/classic` still renders its ten
  canvases with no console errors.
- Wire tests cover the routes and the mobile paths: `/` serves Aurora with the
  live bootstrap and PWA tags, `/aurora` remains an alias, `/classic` serves the
  local page, `/` falls back when Aurora is absent, the token gate still applies,
  the CDN rewrite and vendored file, injection idempotence, the manifest
  `share_target`, multipart parsing, `/share-target` ingestion, the live layer's
  reload hooks, and the token-only phone webhook (valid, missing, wrong and
  Bearer tokens, incremental records, deletions, Daily records, JSON backups).
- `--open` lands on `/`, the canonical dashboard; `launch_url()` no longer
  chooses between two pages.

### Quick log (`POST /api/runs`, `manual_runs.py`)

The Aurora "Log a run" form used to write only to `localStorage`, so a typed run
vanished on the next reload and a Garmin sync never saw it. It now POSTs to
`/api/runs`.

- `manual_runs.py` validates the payload and stores it at
  `paths.data_dir()/manual_runs.json` with an atomic replace. One entry per local
  date, so re-saving a day replaces it. Bodies are capped at 64 KB. An
  impossible date, zero distance or unreadable time is a `400` with a detail
  string.
- The entry is **not** a canonical `activities` row. `/api/activities` merges it
  in with `source_system: "manual"`, `value_state: athlete_reported`,
  `splits: null` and `manual: true`, so `loadcalc`, the review queue and coaching
  never count a typed entry as device-recorded. A Garmin activity on the same
  local date hides the typed copy, which is the promise the form makes.
- The page waits for the response and shows `Run not saved: <detail>` on
  failure. The run feed and report label manual rows "manual entry"; a manual run
  has no lap profile, cadence or elevation, and the report says so.
- `manual_runs.json` is in `paths.DATA_FILES` and bundled by `backup_data.py`.
- `tests/test_manual_runs.py` (30 tests) covers duration parsing, validation,
  atomic writes, date replacement, merge, same-day dedupe, idempotence and the
  refusal to claim device provenance.
- The same form is now an editor. A manual run's report links back to
  `#log/run/<date>`; `log(editDate)` prefills distance, time, HR, RPE, the fuel
  event table and the note. The date is read-only because it is the identity of
  a manual run. Saving posts the run and its intake together: `POST /api/runs`
  accepts an optional `fuel` object with `events`, `note`, `source` and
  `needs_review`, validates it with `run_fuel.normalize_entry()` before writing
  either sidecar, and forces the key to the canonical `manual:YYYY-MM-DD` id so
  a form cannot attach intake to a device activity. `{delete:true}` removes the
  intake entry; editing with an empty table and no note sends that delete.
  Omitting `fuel` leaves existing intake untouched.
- In-browser check through a token-free local proxy: `#log/run` rendered the
  fuel table and `+ Add event` added a row; a synthetic manual run's report
  showed `Edit run`, and `#log/run/2026-11-20` prefilled `6.25` miles, `52:30`,
  HR `151`, RPE `7`, one `fuel` event and the note. A fetch spy confirmed the
  submit body carried those fields plus `fuel.events` and `fuel.note`. Nothing
  was written to the live data sidecars and no dashboard token entered the
  browser URL or history.
- `tests/test_dashboard_api_http.py` covers combined run-and-fuel storage,
  canonical fuel identity, editing that replaces the events, the delete path,
  and validation failure that saves neither sidecar;
  `tests/test_aurora_template.py` pins the editor form, the `#log/run/<date>`
  route and the RPE round-trip.

Verified on the live server: `POST /api/runs` stored one entry, and
`/api/activities` then reported `count 75, manual 1` with `manual: true` on the
new row (74 device runs plus the typed one at the time). The probe row was
removed afterwards. With a session cookie and the
classic placeholder header, `POST /sync` returned `{"ok": true}` and
`activities: 74, open reviews: 3` at that time.

### Nutrition ingestion (`nutrition.py`, `/api/nutrition`)

Cronometer's Daily Nutrition export uses its own wide header (`Day`,
`Energy (kcal)`, `Protein (g)`, `Carbs (g)`, `Fat (g)`), so
`parse_cronometer_csv()` matches those columns exactly: substring matching would
add `Net Carbs (g)` on top of carbs and `Trans-Fats (g)` on top of fat. When a
day carries both diary-group rows and a totals row, only the totals row is
summed, so a day cannot be counted twice. CalTrak exports one row per food
entry, so `parse_caltrak_csv()` aggregates rows that share a date into one daily
total. Both accept the app's header aliases, four date formats and empty numeric
cells as zero, and reject a missing date column, unparseable dates, and negative
or non-numeric values. `parse_export()` sends a CSV to the Cronometer parser
when the five exact columns are present and to the CalTrak parser otherwise.

- `GET /api/nutrition` is token/login-gated, rejects unknown query parameters
  with a `400`, and returns `{days, count, fields, source, storage}`.
- `POST /api/nutrition` accepts `{"days": [...]}`, `{"csv": "..."}`,
  `{"json": ...}`, `{"backup": ...}`, or a raw CalTrak backup object and
  upserts one row per date, returning `{accepted, upserted, total_days}`. The
  `csv` form auto-detects a Cronometer export, a CalTrak CSV or a JSON backup.
  Repeating a date updates it instead of appending a duplicate.
- **Phone webhook.** `POST /api/nutrition/hook` is the only route above the
  browser gate. It authenticates with a dedicated `X-Nutrition-Token` header
  (or `Authorization: Bearer`) that is separate from the dashboard login token
  and grants access to nothing else. The secret is generated once and stored
  beside the local log as `nutrition_log.hook-token`; `GET
  /api/nutrition/hook-info` (behind the normal gate) returns the URL path,
  header name, token, last upload time and managed-day count for the Fuel view's
  setup card. Payloads up to 8 MB are accepted.
- Health Connect ingestion stores raw NutritionRecords by their `metadata.id`
  in `nutrition_log.records.json`, so an incremental sync can add one food
  entry without replacing the rest of that day. A no-id record spanning an hour
  or more is a Daily aggregate, treated as the authoritative total for its date;
  Health Connect clamps the current day to "now" and the oldest day to the
  48-hour window, so a 24-hour threshold would double-count a partial day. A
  shorter no-id record is a time bucket and is summed. Deletions are applied by
  id. Dates the webhook manages are replaced wholesale, so a deleted record can
  remove a day, while manually imported dates are preserved.
- **Seamless Android path.** Cronometer's Android app writes Food entries to
  Android Health Connect (Cronometer documents Food and Water as export types).
  HC Webhook reads Nutrition from Health Connect on an interval or on demand and
  POSTs it to `/api/nutrition/hook`. Setup is one-time: enable Nutrition at Daily
  resolution, add the webhook URL and custom header, then use its interval,
  widget, Quick Settings tile or broadcast trigger. No export and no file picker
  are needed after that. It is the only no-export path, because Cronometer has no
  personal webhook or public API. The manual CSV import remains the free
  fallback.
- The log is stored at `paths.data_dir()/nutrition_log.csv`, never in the
  committed template, so athlete nutrition is not published.
  `GARMIN_NUTRITION_FILE` overrides the path for tests. The committed
  `nutrition_log.csv` remains headers-only.
- The Aurora live layer (served at `/` and `/aurora`) replaces `NUTRITION` from the API, overrides
  `window.importCSV` to POST the raw CSV, and maps `calories` to the `kcal`
  field the committed FUEL view reads. It also exposes
  `window.auroraReloadAll` and `window.auroraReloadNutrition`, so the Garmin
  sync button and the importer redraw from the server instead of a browser-only
  copy.
- **Android share target.** Cronometer exports only from its website, so the
  file arrives as a download rather than from a native app. The web manifest
  declares a `share_target` for `/share-target` (`POST`,
  `multipart/form-data`, one file field named `log` accepting `text/csv`,
  `text/plain`, JSON and `.csv`/`.json`). After the PWA is installed, the
  downloaded `dailysummary.csv` can be shared straight to Coach Dashboard from
  the browser's download notification; choosing it posts the file to the server,
  which parses and upserts it. Chrome normally routes the POST through the
  service worker, which forwards `{csv: text}` to `/api/nutrition`; the server
  route is the fallback for the first share before the worker is active. Both
  paths call `parse_export()`, which auto-detects a Cronometer export, a CalTrak
  CSV or a JSON backup, and redirect to `/?shared=ok|empty|error`.
- **One-tap Garmin sync.** The home view has a `Sync Garmin now` button that
  POSTs `/sync` with the session cookie (or `?tk=`), runs `garmin_sync.py` then
  `trainloop.py bootstrap`, and reloads from the API when it finishes. The same
  button works on the phone and the laptop.
- **Sync feedback is a persistent status line.** A 2.5-second toast could not
  outlive a 15-90 second sync, so the button snapped back to `Sync Garmin now`
  and a finished sync looked like nothing had happened. The sync bar now carries
  `#syncstatus`: `Syncing - this usually takes 15 to 90 seconds` while it runs,
  then `Synced HH:MM - N new runs, M total`, or `Sync failed: <reason>`. The
  server parses the count from `garmin_sync.py`'s
  `Done: N new run(s) downloaded` line and returns it as `new_runs`, so a quiet
  day says `0 new runs` instead of looking like a no-op.
- **A quote bug in the injected bootstrap.** The nutrition-hook setup rendered
  `onclick="copyNutritionHook('url')"` inside a single-quoted JavaScript
  string, which terminated the string early. The whole injected script failed
  to parse, so the page stayed on the committed SNAPSHOT: 72 runs, a
  `SNAPSHOT` badge, and `ACWR unavailable`. The Sync button lives in a separate
  script block and kept working, which made the page look like a sync problem.
  The attribute quotes are now HTML-encoded (`&apos;`), and a test parses the
  injected script with `node --check` where node is available.
- **A refusal is delivered, not reset.** The server now drains a small request
  body before answering `403`, so Windows does not answer with a connection
  reset that the page reports as a bare network error. A 32 KiB unauthenticated
  POST is pinned to a readable `403`.
- Verified in-browser with a synthetic two-day log: the FUEL tab listed both
  days (`Calories 2100 · Protein 150g`) and the run detail showed
  `1950 kcal · 140g protein · 200g carbs`, with no console errors.

### In-run fuel and fade (`run_fuel.py`, `/api/fuel`)

In-run fluid, fuel and electrolyte intake was recorded once, in the classic
journal, and became unreachable when Aurora replaced `/`: three runs carried
structured `fnotes` (`{mi, kind, what}`) and nine narrative notes mentioned
intake (one of them as dehydration rather than a drink). Nothing had been
deleted. The data was still in
`dashboard/index.html`, but no view read it and no API served it. It is now a
first-class sidecar, and it is the input needed to test whether late-run fade
tracks under-fuelling.

- **Storage.** `paths.data_dir()/run_fuel.json`, a list of entries keyed by
  `activity_id` when one is known and by local date otherwise. It is not the
  canonical database: intake is athlete-entered context and must never become a
  training-load input. `GARMIN_RUN_FUEL_FILE` overrides the path for tests.
- **Schema.** Each entry carries `date`, optional `activity_id`, `events`,
  `note`, `source` (`manual`, `journal`, `journal-note`) and `needs_review`.
  An event is `{mile, at, kind, what, oz, kcal, carbs_g, sodium_mg}`. `kind` is
  one of `water|electrolyte|fuel|other`; `mile` accepts a number, `start`,
  `mid` or `finish`; amounts may be blank. Blank is not zero, and a blank never
  becomes a chart point or a total.
- **Validation.** `normalize_entry()` rejects a non-ISO or impossible date, a
  non-list `events`, more than 40 events, overlong text, NaN and out-of-range
  amounts, and a non-string `activity_id`. Writes are atomic, so a crash cannot
  leave a half-written store. `upsert()` matches by activity id before date and
  keeps a known id when a later body omits it.
- **Fade.** `fade()` uses at least four usable lap splits, ignores blank,
  zero and non-numeric values, and reports mean second-half pace minus mean
  first-half pace as `fade_s_per_mi` and `fade_pct`. Positive means slowing
  down. The definition is shared by the API and the page.
- **Serving.** `GET /api/fuel` returns `{runs, count, fields, storage}`;
  `POST /api/fuel` replaces one run's events, or removes the entry when
  `delete: true` is set. Unknown kinds and bad dates return a `400` with
  `invalid fuel payload`; an unwritable store returns a `500`. The route sits
  behind the same token/login gate as the rest of the API.
- **Merging.** `attach()` adds `row["fuel"]` to `/api/activities`, where the
  summary carries `events`, `items`, `totals`, per-hour `rates`, `fade`,
  `note`, `source` and `needs_review`. `items` exists so the editor renders the
  stored events, not just a count. The merge runs after the manual-run merge
  and is never fed to `loadcalc` or `recommend`.
- **Journal recovery.** `python run_fuel.py import-journal` scans all 52 journal
  entries and seeds 10: three with structured events (`journal`, no review
  needed) and seven note-only (`journal-note`, `needs_review: true`). The
  importer also reads `note2`, which held the 2026-09-13 recovery run's
  "hydration 0 oz · electrolytes none"; that becomes two explicit zeroes and
  replaces the blank `fnotes` water placeholder. `dehydration`/`bonk` count as
  intake words, so 2026-05-08 is recovered as a note-only entry. A note-only
  entry is not silently converted: "no water" stays prose until saved, and a
  blank placeholder is upgraded only when a literal `0 oz`/`none` observation
  exists. `suggest_events()` proposes events in the editor and the athlete
  saves them. Suggestions turn "no water", "no gel" and trailing "none"/"0 oz"
  into explicit zeroes, keep a mile marker, apply the athlete's calibration
  (gel/GU 100 kcal and 21 g carbs, generic "electrolytes" → LMNT, full vest
  1.5 L) and leave unmeasured snacks blank. A vest is never counted as water
  when the note also says "no water".
- **Editing.** The run report has a "Fuel & fade" card with totals, rates,
  events and the fade, plus an inline editor: add or remove rows, Save, Clear,
  and "Use journal suggestions" for note-only entries. `#analysis` adds a
  "Fuel vs fade" scatter (recorded energy against fade, only where both exist)
  and a "Worst fades" table showing each run's fade next to what was recorded
  as taken in. The `#fuel` tab is now labelled `NUTRITION`, so daily nutrition
  and in-run fuel are not confused.
- **Manual runs.** The quick log is the same editor, opened prefilled from the
  manual run's report at `#log/run/<date>`. Intake events and the note travel in
  the `POST /api/runs` body beside distance, time, HR and RPE, so a typed run and
  its fuel are one editable record. See "Quick log" above for the validation and
  identity rules.
- **What the recovered notes already say.** 2026-05-08 was a dehydration bonk
  in low-70s breezy weather (prose, left for review); 2026-06-07 was a bonk at
  mile 14 after water ran out; 2026-06-04 was deliberately under-hydrated;
  2026-05-28 was LMNT only with no gel; 2026-09-11 and 2026-09-13 both recorded
  zero water and zero electrolytes. 2026-09-09 lists a vest, a gel, two fruit
  snacks, a GU and an LMNT with only the snack and refuel miles recorded. The
  point of the scatter and the table is to test the pattern against the runs
  that did not fade, rather than to guess unlocated fuel or assume it.
- **Plumbing.** `run_fuel.json` is in `paths.DATA_FILES`,
  `backup_data.DATA_FILES`, `.gitignore`, `export_publish.IGNORE`,
  `export_publish.PUBLISHED_MODULES` (`run_fuel.py`, `fade_points.py`) and the
  cloud migration file list, so it is backed up, never published, and carried
  to a VM.
- `tests/test_run_fuel.py` covers parsing, validation, the store, fade, attach,
  suggestions, journal import, payload and the CLI; twelve HTTP tests cover
  GET/POST/delete, the token gate, validation, the `/api/activities` merge and
  the combined run-and-fuel path; `tests/test_aurora_template.py` pins the
  editor, the scatter, the normalize-copy contract and the manual-run edit form.

### Fade points and intersections (`fade_points.py`)

The old fade only surfaced on runs that also had a fuel entry. Of the live
corpus's 73 runs with at least four usable splits, 62 had no intake record, so
their fade was invisible to the analysis. `fade_points.attach()` now adds one
canonical fade point to **every** such run in `/api/activities`, using
`run_fuel.fade()` rather than a second formula. The per-row copy is what Aurora
maps into each run; the top-level `fade_points` list and `fade_analysis` block
are the same data for the analysis view. No new route was added, so the pinned
three-route API surface is unchanged.

- **Intake stays honest.** Each point reports totals and hourly rates from the
  fuel summary, plus a status for water, fuel and electrolytes: `recorded` (a
  positive amount was logged), `none` (an explicit zero was logged),
  `unmeasured` (an item was logged without an amount) or `not recorded` (no
  event). `None` and `0.0` are never merged, and a note-only entry stays
  `needs_review: true` rather than becoming an invented event.
- **Temperature is read from the athlete's own words only.** The parser accepts
  an explicit `88F`, a range (`85-86F` → 85.5), a decade with a modifier
  (`low-70s` → 72, `80s` → 85) and a recorded `tempF` from the classic journal.
  A bare "heat" or "hot" is never a temperature. `feels-like 100F` stays in
  `feels_like_f` and is kept out of the air-temperature band. The journal is
  gitignored and read through a cached, mtime-keyed helper; a clean checkout
  simply has no journal context. This module does not use the weather gate,
  call a provider or make a weather-performance claim.
- **Intersections are descriptive and gated.** `intersections()` groups fade
  percentages by hydration, fuel, electrolyte and temperature band. Groups with
  fewer than three runs are hidden and listed with their `n` rather than shown
  as a shaky median. On the live corpus the current readout is 73 fade points;
  the 80s band has seven runs (median +6.5% fade) against 61 runs with no notes
  temperature (median +3.3%). That difference is confounded by distance, hills
  and effort and is presented with an explicit caveat, not as a finding.
- **Aurora.** The run report's worst-fades table now has a temperature column
  and uses the canonical fade point for every run. `#analysis` adds a "Fade
  intersections" card with the gated medians and the suppressed-group counts.
  The live layer stores the server's analysis on `window.FADE_ANALYSIS`; the
  page formats it synchronously and never recomputes statistics from a stale
  snapshot. `normalizeRun()` and the live `mapRun()` both carry `fadePoint`.
- `tests/test_fade_points.py` adds 26 tests for the parser, the four intake
  statuses, explicit zeros, note-only entries, group gating, feels-like
  separation and idempotent attach; four `journal_notes()` tests were added to
  `tests/test_run_fuel.py`, one template contract and two HTTP tests cover the
  carried field and the unchanged route registry.

## Local data backup and restore

`backup_data.py` bundles the data that git does not carry: the FIT corpus,
`trainloop.db`, `dashboard/index.html`, the sleep/HR exports, the sync marker,
the nutrition log with its Health Connect sidecar, and the manual-run sidecar
`manual_runs.json` (typed quick-log runs are not rebuilt from Garmin, so a
backup that omitted them would lose them). It writes one timestamped zip,
prunes older copies (default 14) and writes a `MANIFEST.txt` naming the code
commit and every file it bundled.

Credentials are excluded by default: `.coach_dash_token`, `.coach_dash_auth`,
`nutrition_log.hook-token`, `garmin_tokens.json` and `.garmin_tokens/`. All of
them are recreated after a restore, and a zip that ends up in cloud storage
should not carry them. `--include-secrets` exists but is documented as requiring
an encrypted archive.

Verified on this machine:

```
$ python backup_data.py --dry-run
destination: %OneDrive%\CoachDashboardBackups
files      : 77
excluded   : .coach_dash_token, .coach_dash_auth, nutrition_log.hook-token,
             .garmin_tokens/

$ python backup_data.py
backup   : %OneDrive%\CoachDashboardBackups\coach-data-2026-11-12_225431.zip
files    : 77
size     : 2.2 MB
```

The zip was reopened and its manifest read back: 78 entries (77 files plus the
manifest), `dashboard/index.html` present, and the manifest naming the code
commit the backup was taken from.

A scheduled task, **Coach Data Backup**, runs it daily at 12:00 with
`StartWhenAvailable`; a manual `Start-ScheduledTask` returned `LastTaskResult 0`
and wrote a second copy.

`tests/test_backup_data.py` (18 tests) pins the archive contents, the credential
exclusion and its manifest line, `--include-secrets`, retention pruning, the
empty-directory failure path, the dry run writing nothing, the OneDrive-then-
Documents destination order, and the git marker reader.

Restore steps are in [RESTORE.md](RESTORE.md).

## Cloud deployment kit

`deploy/cloud/` moves the host off the laptop: the same server, sync and tunnel
on a free Ubuntu VM. `tests/test_cloud_deploy.py` (20 tests) pins the properties
that make it safe rather than the prose:

- the server unit still runs `garmin_server.py --idle-timeout 0` with no
  `--host`/`--lan`, and no file in the kit contains `0.0.0.0` or a CORS header;
- `GARMIN_DATA_DIR`, `TRAINLOOP_DB` and `GARMINTOKENS` point at
  `/srv/coach-dashboard/data`, outside the checkout an upgrade resets;
- the tunnel unit `Requires=coach-dashboard.service`, reads its token from
  `/etc/coach-dashboard/ngrok.env`, and never embeds it;
- the timer is nightly, `Persistent=true`, and targets the one-shot sync unit;
- the sync unit has `StandardInput=null`, so an expired Garmin token fails
  instead of hanging on a password prompt;
- `sync.sh` runs download, import and export in order and records a failure
  without skipping the remaining steps;
- `refresh_export.py` calls `export_publish.build_csv()` and contains no git or
  subprocess call;
- the migration copies only named files, deletes its local archive in `finally`,
  and never prints a copied file;
- `export_publish.code_paths()` now stages `deploy/` so the unattended publisher
  cannot silently leave the kit behind, and the secret scanner covers the new
  file types.

Run directly, with `GARMIN_REPO` pointed at a temporary directory:

```
$ python deploy/cloud/refresh_export.py
export refreshed: 75 runs, latest 2026-11-19
```

The generated `garmin_export.csv` was 21,155 bytes, the same size as the
published copy, so the cloud path uses the same builder as the laptop.

The PowerShell migration script parses cleanly with
`[System.Management.Automation.Language.Parser]::ParseFile`. `bash -n` on the
three shell scripts skips on this laptop because `bash` is not installed; CI runs
it.

**Not verified:** no VM was provisioned, so the systemd units have not been
started on Ubuntu and the end-to-end tunnel handover has not been exercised. The
kit is verified as files, plus the one script that can run on Windows.

## Privacy checks

- Raw FIT files are gitignored; the local `trainloop.db` is gitignored.
- `weather_observations` has no `lat`/`lon`/`latitude`/`longitude` column â€”
  asserted against `PRAGMA table_info` by
  `test_weather_schema_stores_no_coordinates`.
- `test_audit_output_contains_no_coordinates` walks the entire FIT audit result
  and fails if any key or value resembles a position.
- The audit no longer reports a latitude/longitude range. The previous test
  suite asserted the athlete's coordinates fell inside a specific region; that
  test both hardcoded a location into a tracked file and depended on the leak.
  It has been inverted into a regression guard.
- Current `main` is clean through the authoritative GitHub API.
- The dashboard server binds loopback and requires a per-launch token by
  default; the explicit `--lan` path widens the Host allowlist to the bound
  addresses and still requires the token, sends no CORS headers, and serves the
  PWA files above the gate only because the browser needs them. See
  [Dashboard server and mobile copy](#dashboard-server-and-mobile-copy).

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
| `profile.json` | Partially populated. `hr_max=198`; `age`, `sex`, `resting_hr`, `weight_lb`, `height_in` null. The UTC offset is now confirmed (US Central), so local dates are settled; the remaining fields block cohort percentiles and the weather location policy. |
| Brief bridge idempotency | **Now verified.** `3054d6a` gave the file a content-derived `brief_id`; `captured_utc` is metadata only. Tests advance a frozen clock 90s to prove an unchanged brief is a no-op. |
| Athlete UTC offset | **Confirmed**: US Central (UTC-5/-6, DST applied per activity). Every `timezone_uncertain` review was resolved except the two newest runs (2026-11-14 and 2026-11-17), which remain open pending athlete confirmation; only the calendar-gap review is otherwise outstanding. |
| Elevation accuracy | **Derived, not measured.** These FIT files carry no `barometer_pressure`, so altitude is GPS-derived and noisy. The device figure and a smoothed recomputation differ by up to ~25% on real runs. See [ELEVATION.md](ELEVATION.md). |

## Withdrawn claims

Recorded so they are not reintroduced by a later brief:

- **"53 of 55 runs are classified as Zone 5."** No HR zone classification
  exists in this repository. Every occurrence of "zone" in the source is
  `timezone_source`; the CSV carries `Avg HR` and `Max HR` but no zone column;
  and `53`/`55` appear in these documents only inside the Git version string
  `2.53.0.windows.4`. The claim could not be traced to any code, fixture or
  command output, and was withdrawn rather than investigated as a real finding.
- **"dashboard/index.html ... remains disconnected from the tested data layer;
  it has zero references to garmin_export.csv, trainloop.db, or the new
  services."** Asserted by the `connect-dashboard-to-data-layer` brief of
  2026-10-04, in a commit landing *on top of* `776a918`, which had already
  implemented and tested all three routes. The dashboard was fetching them. The
  brief process cannot read `dashboard/index.html` -- it is gitignored and holds
  private athlete data -- so every dashboard claim it has made is invention,
  including two different inline-array counts (54, then 133). Now that
  `docs/DASHBOARD_AUDIT.md` is generated from the real file and committed, the
  claim is checkable. See [SUPERVISOR_BRIEF_ERRORS.md](SUPERVISOR_BRIEF_ERRORS.md).
- **"The standing verification state is 57 FIT files, 57 activities, 58 open
  reviews, 207 passed / 1 skipped."** Asserted as authoritative by the
  `connect-dashboard-to-data-layer` brief of 2026-10-04, which also instructed
  that the correct figures (58 / 58 / 59 / 231) "are not adopted" and must not be
  restated. The brief was working from a pre-`b2201c7` snapshot of these
  documents. Every one of those numbers was verified wrong on the live corpus
  before any code was written, and the brief's own instruction -- "do not
  hard-code counts as a substitute for querying the data layer" -- is what
  prevents the error from reaching the UI. The API queries every count; none is
  written down. See [SUPERVISOR_BRIEF_ERRORS.md](SUPERVISOR_BRIEF_ERRORS.md).
- **"55 audit records and a historical 59-record source."** Both counts are
  unsupported. The live corpus is 75 across every source.

## Reproducing this report

```
python -m pytest
python fit_audit.py
python trainingdb.py migrate
python trainingdb.py
python activities.py import
python activities.py summary
```
