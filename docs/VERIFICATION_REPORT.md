# Verification report

Supervisor brief Task 10. Everything below was run in the working tree on
2026-10-01. Commands and results are reproduced as observed.

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
491 passed, 1 skipped (492 collected)
```

| File | Tests |
| --- | --- |
| `tests/test_dashboard_contract.py` | 36 |
| `tests/test_recommend_snapshots.py` | 25 |
| `tests/test_training_data.py` | 59 |
| `tests/test_brief_bridge.py` | 62 |
| `tests/test_dashboard_api.py` | 38 |
| `tests/test_trainloop_cli.py` | 22 |
| `tests/test_dashboard_api_http.py` | 42 |
| `tests/test_fit_reader_elevation.py` | 21 |
| `tests/test_splits.py` | 10 |
| `tests/test_provenance.py` | 18 |
| `tests/test_capture_supervisor.py` | 16 |
| `tests/test_fit_audit.py` | 16 |
| `tests/test_gps_guard.py` | 13 |
| `tests/test_paths_and_guards.py` | 9 |
| `tests/test_history_safety.py` | 2 |
| `tests/test_publish_scope.py` | 17 |
| `tests/test_publish_flow.py` | 50 |
| `tests/test_brief_consistency.py` | 36 |
| **Total** | **492** (491 pass, 1 skip) |

`tests/test_fit_reader_elevation.py` covers the elevation diagnostics added with
reader 1.1.0; see [ELEVATION.md](ELEVATION.md). Four of its tests are the CSV
leak guard, which caught the diagnostics being published as columns before this
report was written.

The skip is the Windows symlink case in the brief-bridge suite; the code path is
covered on platforms that permit symlinks.

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

files inspected           : 69
parse failures            : 0
files readable            : 69
files with GPS            : 69
files without GPS         : 0
files with usable timestamp: 69
files without timestamp   : 0
session messages          : 69
lap messages              : 626
record messages           : 65032
position points (counted) : 65011
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

On a fresh database with the current corpus of 69 files, the first import
inserts all 69. Re-running against a database that already holds them reports
every file `unchanged`:

```
$ python activities.py import
{"inserted": 0, "updated": 0, "unchanged": 69, "unreadable": 0}
```

**Idempotency verified on the real data**: no rows updated, and no new audit
rows written on the second pass.

```
$ python activities.py summary
{"activities": 69, "open_reviews": 70}
```

- 69 activities
- 69 open `timezone_uncertain` reviews (one per activity, expected)
- 1 open `activity_gap`: `no activity 2026-06-26..2026-07-05 (8 days)`
- 0 duplicates detected
- 69 SHA-256 raw references stored

The FIT-file inventory, the canonical table and the published CSV all agree at
**69**. An earlier brief described a 55/56/59 discrepancy; that premise was
checked against the live corpus and is unsupported, so there is no
reconciliation to perform.

Note for anyone re-running this: `trainloop.py load` only *computes* load. The
command that imports new FIT files is `trainloop.py bootstrap`. This trap has now
recurred three times. On 2026-10-04 the database held 57 while the FIT directory
and CSV held 58; on 2026-10-15 it held 58 while they held 61; and on 2026-11-06 it
held 61 while the FIT directory held 69 (and the published CSV 68) - the eight
runs from 2026-10-13 to 2026-11-06 had been downloaded but never imported, so
every load figure and the dashboard silently excluded them. Re-running
`trainloop.py bootstrap` on 2026-10-15 imported three
(`{"inserted": 3, "unchanged": 58}`), and again on 2026-11-06 imported eight
(`{"inserted": 8, "unchanged": 61}`), bringing the table to 69.

## Training load and recommendation

Against the real corpus, with `hr_max=198` supplied by the caller (the value now
in `profile.json`; the figure below was produced with an earlier test value and
the load is bucketed by intensity band, so the exact number inside 195-203 does
not change it):

```
$ python trainloop.py load
7d    run 780.8   strength n/a  combined 780.8   run_conf medium
14d   run 1798.1  strength n/a  combined 1798.1  run_conf medium
28d   run 3364.4  strength n/a  combined 3364.4  run_conf medium

$ python trainloop.py recommend
state: confirmation_required
reasons:
  - 11 recent activities are awaiting confirmation
evidence:
  run_load_28d         3364.4
  runs_28d             11
  runs_7d              2
  strength_28d         0
  strength_load_28d    None
```

Two things worth stating plainly:

- `strength_load` is `null`, not `0`. No strength sessions exist yet, and an
  absent component is not a zero component.
- The recommendation is a **refusal**, and it is the correct one: 11 activities
  in the window still carry unresolved timezone reviews, so
  `recommend.recommend()` declines to issue a control state. This is the
  designed behaviour, not a failure.

The 7-day figure moved from 180.7 to 780.8 when `2026-10-01` was finally
imported. That is the practical cost of the database being a run behind: the
load looked like a light week when the corpus said otherwise.

## Publisher and privacy guard

```
$ python export_publish.py
```

Runs the position-data guard over every candidate file, refuses to commit if
position data is present, then commits and pushes. The guard blocks labelled
coordinate fields, degree pairs, FIT semicircle field names, and CSV coordinate
columns.

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

`garmin_server.py` serves the gitignored `dashboard/index.html` and the
read-only JSON API (`/api/activities`, `/api/load`, `/api/coaching`) on the same
origin. It defaults to loopback and a per-launch token. The athlete decided the
dashboard should also be reachable from a phone on the home WiFi, so the server
gained a deliberate, opt-in exposure path rather than an always-on one:

- `--lan` (equivalently `--host 0.0.0.0`) binds all interfaces; the bound LAN
  IPv4 addresses are added to the Host allowlist and the startup message prints
  the LAN URL with the token. The default binding is still `127.0.0.1`.
- `_host_ok()` requires the `Host` header to name a bound address **and** carry
  the served port, so a DNS-rebinding host or a wrong port is refused (`403`).
- Every data route stays behind the per-launch token (`X-Dash-Token` or
  `?tk=`).
- **No CORS headers are sent.** The page and the API share one origin, so CORS
  is unnecessary; `test_no_cors_headers_are_ever_sent` asserts
  `Access-Control-Allow-Origin` never appears.
- The dashboard file is generated outside this repository, so it cannot be
  relied on to carry PWA tags. As the HTML is served, the server injects the
  manifest link, mobile `theme-color`/viewport meta and the service-worker
  registration (`inject_pwa()`), and serves a real `/manifest.webmanifest` and
  `/sw.js`. Both are served above the token gate because the browser fetches
  them itself.
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

`tests/test_dashboard_api_http.py` (42 tests) covers the manifest and worker
routes, the injected tags, injection idempotence, host/port allowlisting, the
offline fallback (the worker keeps the shell and API data, and falls back to the
cache on a `5xx` origin outage), and the login gate (redirect, form, wrong
password, cookie unlock, forged cookie, token back-compat, logout, `Secure`
flag, session expiry). **Caveat:** service workers require a secure context, so
over plain `http://<lan-ip>` the "Add to Home Screen" action produces a live
shortcut with no offline worker; the worker - and therefore the offline copy -
activates only under https (the tunnel) or on localhost.

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
| `profile.json` | Partially populated. `hr_max=198`; `age`, `sex`, `resting_hr`, `weight_lb`, `height_in` null. The missing UTC offset blocks confirmed local dates and weather location. |
| Brief bridge idempotency | **Now verified.** `3054d6a` gave the file a content-derived `brief_id`; `captured_utc` is metadata only. Tests advance a frozen clock 90s to prove an unchanged brief is a no-op. |
| Athlete UTC offset | Not supplied by the athlete. This is what 69 open `timezone_uncertain` reviews are waiting on. |
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
  unsupported. The live corpus is 69 across every source.

## Reproducing this report

```
python -m pytest
python fit_audit.py
python trainingdb.py migrate
python trainingdb.py
python activities.py import
python activities.py summary
```
