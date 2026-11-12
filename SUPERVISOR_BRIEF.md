UNVERIFIED LLM OUTPUT

# Athletic Performance Hub - Supervisor Brief
## Generated: 2026-11-12
## Run by: CrewAI Flow Supervisor

---
## CLOSED TASKS

brief-transport | evidence from SUPERVISOR_BRIEF.md | live, direct push + inbox + clipboard
brief-transport-cross-second-idem | 3054d6a | brief_id is content-derived
profile-hr-max | evidence from SUPERVISOR_BRIEF.md | profile.json, hr_max=198
data-layer-and-provenance | 4051291 | migrations 001-006
fit-audit-and-guard | evidence from SUPERVISOR_BRIEF.md | 0 parse failures, 72/72 GPS, guard verified
formalize-continuity-review-without-synthetic-activities | evidence from docs/VERIFICATION_REPORT.md | 1 open activity_gap; no synthetic activities may be created; accepted corpus is 72 activities
make-coaching-rationales-deterministic-and-auditable | evidence from docs/IMPLEMENTATION_INVENTORY.md | tests/recommend_snapshots.py pins every reachable coaching branch to golden JSON with fixed as_of and supplied hr_max
harden-bridge-and-release-quality-gates | evidence from docs/VERIFICATION_REPORT.md | 501 passed, 1 skipped; facts gate, rejected-brief staging, content-derived idempotency, and publish protections are tested
connect-dashboard-to-data-layer | evidence from docs/IMPLEMENTATION_INVENTORY.md and docs/VERIFICATION_REPORT.md | GET /api/activities, GET /api/load, and GET /api/coaching are served on the same origin and the dashboard fetches them

---
## VERIFICATION (open tasks from previous brief)

complete-athlete-profile-and-timezone-provenance | IN PROGRESS | Age, sex, resting heart rate, weight, and height remain null; US Central timezone is confirmed and all 72 timezone_uncertain reviews are resolved.
capture-confirmed-strength-history | IN PROGRESS | Schema and service are verified, but there are 0 real strength sessions and strength_load is null while this remains true.
implement-gated-weather-enrichment | IN PROGRESS | weather.py is gated, no coordinates are stored, and the gate returns unavailable past consent and location.
document-conservative-training-signals | IN PROGRESS | No direct evidence establishes completion of documentation for the interpretation and limits of conservative signals.
stabilize-running-load-before-progression | IN PROGRESS | Load implementation and tests exist, but progression-readiness validation and edge-case completion are not evidenced.
build-long-run-pace-durability | IN PROGRESS | No completion evidence establishes durable long-run pace work after the load foundation.
introduce-conservative-runner-strength | IN PROGRESS | The inventory reports 0 strength sessions and provides no evidence of confirmed-history-based runner-strength guidance.
establish-authenticated-athlete-ownership | BLOCKED / PARKED AND DEMOTED | Authentication is not a current delivery priority for this local, single-athlete deployment; multi-athlete isolation does not exist.

---
## STANDING NUMBERS

- FIT file count: 72. Source: docs/VERIFICATION_REPORT.md, "files inspected           : 72".
- Activity count: 72. Source: docs/VERIFICATION_REPORT.md, `{"activities": 72, "open_reviews": 1}`.
- Open review count: 1. Source: docs/VERIFICATION_REPORT.md, `{"activities": 72, "open_reviews": 1}`.
- Test result: 501 passed, 1 skipped. Source: docs/VERIFICATION_REPORT.md, "501 passed, 1 skipped (502 collected)".
- Parse failures: 0. Source: docs/VERIFICATION_REPORT.md, "parse failures            : 0".
- Files with GPS: 72. Source: docs/VERIFICATION_REPORT.md, "files with GPS            : 72".
- Open timezone_uncertain reviews: 0. Source: docs/VERIFICATION_REPORT.md, "0 open `timezone_uncertain` reviews".
- Open activity_gap reviews: 1. Source: docs/VERIFICATION_REPORT.md, "1 open `activity_gap`: `no activity 2026-06-26..2026-07-05 (8 days)`".
- Strength sessions: 0. Source: docs/VERIFICATION_REPORT.md, "0 strength sessions".
- hr_max: 198. Source: docs/VERIFICATION_REPORT.md, "with `hr_max=198` supplied by the caller".
- Nutrition rows: not stated in the newest repo docs. `nutrition_log.csv` is not mentioned in the verification report, implementation inventory, or prior supervisor brief evidence.
- Lifting rows: not stated in the newest repo docs. `lifting_log.csv` is not mentioned in the verification report, implementation inventory, or prior supervisor brief evidence.
- CalTrak integration status: not stated in the newest repo docs.
- Bodyweight trend status: not stated in the newest repo docs.

---
## FLOW UPDATES (new this run - pull these)

Run `git pull` before implementation, then open the committed files below.

- `flow_outputs/aurora_dashboard.html` at commit `f1333a000b0580348cffaa51a029149d8ed46975`.
  - This is the committed Aurora app and the source of truth for the generated app.
  - It contains six tabs.
  - It contains run report pages.
  - Its FUEL tab includes CalTrak CSV import.
  - Its LIFT logger exports `lifting_log.csv`.
  - It presents a bodyweight trend.
  - It presents a This week card.
  - Its sync queue posts to `/api/lifts` and `/api/nutrition`.
  - It includes PWA and offline behavior, including an embedded manifest and service worker exposed through blob URLs.
  - It includes local upload queues and activity polling.
  - The verification report does not verify that these features are integrated with the local server. Integration is the primary task below.

- `lifting_log.csv` at commit `d775add74616c2ec827932e6be0f275ce2adf50e`.
  - This file was created with headers only.
  - It contains no lifting rows.

- `nutrition_log.csv` at commit `b2b64eeeaafe460241a88eb9874e70f4a35d6c3f`.
  - This file was created with headers only.
  - It contains no nutrition rows.

The app was committed this run. Do not use the uncommitted, gitignored `dashboard/index.html` as a source of truth. Open and integrate `flow_outputs/aurora_dashboard.html` instead.

---
## SUPERVISOR DECISIONS

The primary decision is to adopt the committed Aurora dashboard rather than relying on the private, gitignored dashboard. The committed app is now the inspectable source for the generated UI, but it is not yet verified as reachable through `garmin_server.py`.

The existing data-layer dashboard integration is closed. The verified read-only routes are `/api/activities`, `/api/load`, and `/api/coaching`. Preserve those routes and do not reopen the completed dashboard data-layer task.

The local product now needs a server route for the committed Aurora app, mobile-network behavior, CORS and preflight handling, and upload endpoints for the app's offline sync queue. The app must use live server responses and visible errors rather than treating embedded arrays as authoritative.

The app and log templates do not establish that nutrition, lifting, bodyweight, or CalTrak data already exist. Both CSV files contain headers only. Do not claim that real nutrition or strength analysis is available until rows are recorded and ingested.

The local deployment remains single-athlete and single-user. Authentication stays parked and demoted.

No athlete decision is required for this implementation path. Use `/aurora` as the server route.

---
## PRIMARY TASK
### adopt-flow-generated-dashboard

Implement the committed Aurora app in the local product. Use `flow_outputs/aurora_dashboard.html` at commit `f1333a000b0580348cffaa51a029149d8ed46975` as the UI source. Do not read or rely on the gitignored `dashboard/index.html`.

Files to inspect and change:

- `garmin_server.py`
- `flow_outputs/aurora_dashboard.html`
- `lifting_log.csv`
- `nutrition_log.csv`
- Existing tests for `garmin_server.py`, API behavior, and dashboard serving
- Existing data-layer files used by `/api/activities`, `/api/load`, and `/api/coaching`

Server implementation:

1. Add a route such as `/aurora` in `garmin_server.py` that serves the committed `flow_outputs/aurora_dashboard.html`.
2. Preserve the existing routes and behavior for:
   - `GET /api/activities`
   - `GET /api/load`
   - `GET /api/coaching`
3. Wire the Aurora app to live API data. Embedded arrays in the generated HTML must not be treated as authoritative.
4. Bind the local server to `0.0.0.0`.
5. Return `Access-Control-Allow-Origin: *` on API responses.
6. Handle `OPTIONS` preflight requests with a successful response and the required CORS headers.
7. Keep `GET /api/activities` within the existing local-server expectation of less than 500 ms. Add or update a test that measures this behavior without using synthetic activities.
8. Add `POST /api/lifts`:
   - Request JSON shape: `{ "rows": [ ... ] }`.
   - Each row must use the expected `lifting_log.csv` schema.
   - Validate required columns and reject malformed rows with a clear non-2xx response.
   - Append valid rows to `lifting_log.csv`.
   - Accept a stable payload identifier, such as an identifier in the request body or request headers, according to the app's existing queue format.
   - If the same payload identifier was already stored, do not append it again.
   - Return a 2xx JSON response containing an accepted-row count, for example `{ "accepted": <number> }`.
   - Do not claim that any rows exist until a successful upload has stored them.
9. Add `POST /api/nutrition`:
   - Request JSON shape: `{ "days": [{ "date": ..., "kcal": ..., "protein": ..., "carbs": ..., "fat": ... }] }`.
   - Validate the date and numeric nutrition fields.
   - Upsert one daily total per date in `nutrition_log.csv`.
   - Return a 2xx JSON response containing an accepted or upserted count, for example `{ "accepted": <number>, "upserted": <number> }`.
   - Make retries safe and do not silently discard failed uploads.
10. Add visible server-error behavior in the Aurora app when a live endpoint is unavailable. Do not fall back to invented, stale, or embedded dashboard data after an API failure.
11. Preserve the app's existing behavior:
   - Six-tab navigation.
   - Run report pages.
   - FUEL tab and CalTrak CSV parsing.
   - LIFT tab and lifting log export.
   - Bodyweight trend presentation.
   - This week card.
   - Hash routing.
   - Thirty-second activity polling.
   - Offline queue behavior.
   - Embedded PWA manifest and service worker behavior through blob URLs.
12. Ensure the sync queue retries until the server returns a 2xx response. Failed uploads must remain queued and visible rather than being silently discarded.
13. Make the app's queue use the server endpoints:
   - Lifting uploads to `/api/lifts`.
   - Nutrition uploads to `/api/nutrition`.
14. Do not add HR-zone distributions, synthetic activities, the rejected 55/56/59 reconciliation, a 56-activity premise, or `OPENCODE_INSTRUCTIONS.md`.

Acceptance checks:

- `git pull` retrieves `flow_outputs/aurora_dashboard.html`, `lifting_log.csv`, and `nutrition_log.csv`.
- `GET /aurora` returns the committed Aurora HTML.
- The response is generated from `flow_outputs/aurora_dashboard.html`, not `dashboard/index.html`.
- The existing `/api/activities`, `/api/load`, and `/api/coaching` routes still return their established live data.
- `OPTIONS` requests succeed for the API routes and include CORS headers.
- API responses include `Access-Control-Allow-Origin: *`.
- The server listens on `0.0.0.0`.
- `GET /api/activities` completes within 500 ms under the local test fixture.
- A valid `POST /api/lifts` appends rows and returns an accepted-row count.
- Repeating the same lifting payload identifier does not append duplicate rows.
- A malformed lifting row is rejected clearly.
- A valid `POST /api/nutrition` upserts one row per date and returns an accepted or upserted count.
- Repeating the same nutrition dates updates existing daily totals rather than creating duplicate dates.
- Failed upload responses leave items in the client queue.
- Successful upload responses remove the corresponding items from the client queue.
- The app displays a visible error when a live endpoint fails.
- Tests cover route serving, CORS, preflight, upload validation, idempotency, nutrition upsert behavior, and the existing read-only API routes.
- The full test suite passes without introducing synthetic activities or unsupported HR-zone claims.

---
## PWA / MOBILE SETUP (for opencode)

Update `garmin_server.py` so the server binds to `0.0.0.0`. Add `Access-Control-Allow-Origin: *` to API responses and handle `OPTIONS` preflight requests. Preserve the local performance expectation that `/api/activities` responds in less than 500 ms.

Verification steps:

1. Start the server on the laptop using the normal project command.
2. Confirm the server is listening on `0.0.0.0`.
3. From the laptop, open `/aurora` and confirm the committed Aurora app loads.
4. Confirm `/api/activities`, `/api/load`, and `/api/coaching` return live responses.
5. Confirm an `OPTIONS` request succeeds and returns the CORS headers.
6. From another device on the same home Wi-Fi, open `http://<laptop-ip>:<port>/aurora`.
7. Confirm the phone can load the app and receive activity data.
8. Enter a lift and confirm the queued payload posts to `/api/lifts`.
9. Import nutrition data through the FUEL tab and confirm the queued payload posts to `/api/nutrition`.
10. Turn off or disconnect the laptop server, create a queued item, reconnect the server, and confirm the item remains queued until a 2xx response is received.
11. Confirm the app shows a visible endpoint error while the server is unavailable.
12. Add the app to the phone home screen and verify that the offline shell opens.

The generated app embeds its manifest and service worker as blob URLs. It queues uploads until the laptop answers. The queue must retry failed uploads and must not silently discard them.

---
## BACKLOG (ranked, do not execute until primary task is done)

Rank 1: caltrak-nutrition-ingestion | Add server-side CalTrak parsing and aggregation, implement `GET /api/nutrition`, and make the FUEL tab consume live nutrition data. The current logs have headers only and the verification report does not establish completed nutrition ingestion.

Rank 2: lift-logger-and-lifting-log-ingestion | Implement `GET /api/lifts`, parse lifting rows, calculate Epley e1RM, account for bodyweight plus added weight for pull-ups and dips, and return per-session bodyweight so the LIFT tab can produce real coaching data.

Rank 3: bodyweight-and-weekly-summary-endpoints | Add `GET /api/bodyweight` and `GET /api/week` so the bodyweight chart and This week card use live lifting, running, and nutrition data rather than local-only state.

Rank 4: complete-athlete-profile-and-timezone-provenance | Complete the missing athlete profile fields while retaining the evidenced US Central local-date handling and UTC timestamps.

Rank 5: capture-confirmed-strength-history | Make recorded app sessions enter the data layer and become available to coaching calculations; current evidence reports 0 real strength sessions.

Rank 6: stabilize-running-load-before-progression | Add progression-readiness validation and edge-case coverage in `loadcalc.py`, `recommend.py`, and their tests before increasing training recommendations.

Rank 7: document-conservative-training-signals | Document the interpretation limits of conservative signals and distinguish absent strength data from zero strength load.

Rank 8: build-long-run-pace-durability | Add evidence-based long-run durability guidance only after the load foundation is validated and without presenting provisional lifting guidance as measured weakness.

Rank 9: introduce-conservative-runner-strength | Convert provisional runner-strength guidance into data-backed coaching only after actual sessions, loads, repetitions, RPE, and bodyweight are recorded.

Rank 10: implement-gated-weather-enrichment | Add weather only after a provider, consent and location policy, and coordinate source exist; current evidence reports none of these.

Rank 11: establish-authenticated-athlete-ownership | Keep parked and last. This is a local, single-athlete system, and authentication is not a current delivery priority.

---
## ATHLETE ACTIONS

- `lifting_log.csv` exists with headers only. Record a lifting session in the Aurora LIFT tab or populate the file using its documented schema.
- `nutrition_log.csv` exists with headers only. Import or place a CalTrak export into the Aurora FUEL workflow to create daily nutrition rows.
- Open the Aurora app through `/aurora` after `adopt-flow-generated-dashboard` is implemented.
- On the phone, use the laptop's home-Wi-Fi IP and add the app to the home screen.
- Use the app on home Wi-Fi to test queued lift and nutrition uploads.
- Current analyses cannot calculate real e1RM progression, RPE trends, bodyweight trends, or nutrition trends while both logs have no rows.

---
## NEXT SUPERVISOR CHECK

- adopt-flow-generated-dashboard | Verify `GET /aurora`, live API wiring, CORS, preflight, `0.0.0.0` binding, activity latency, lift upload idempotency, nutrition upsert behavior, visible errors, and offline queue retry behavior.
- caltrak-nutrition-ingestion | Verify CalTrak parsing, `GET /api/nutrition`, daily aggregation, and FUEL rendering after the primary task.
- lift-logger-and-lifting-log-ingestion | Verify `GET /api/lifts`, lifting schema ingestion, Epley e1RM, pull-up and dip handling, and per-session bodyweight.
- bodyweight-and-weekly-summary-endpoints | Verify `GET /api/bodyweight`, `GET /api/week`, the bodyweight trend, and This week card against stored data.
- complete-athlete-profile-and-timezone-provenance | Verify that the remaining profile fields are populated and that local dates retain UTC provenance.
- capture-confirmed-strength-history | Verify that recorded sessions enter the data layer and that strength load is no longer null when real sessions exist.
- stabilize-running-load-before-progression | Verify progression-readiness validation and edge-case tests without synthetic activities or HR-zone distributions.
- document-conservative-training-signals | Verify the documentation distinguishes absent data from zero measured load and states the limits of conservative signals.
- build-long-run-pace-durability | Verify durable long-run guidance is based on validated load evidence.
- introduce-conservative-runner-strength | Verify runner-strength coaching uses recorded sessions rather than provisional assumptions.
- implement-gated-weather-enrichment | Verify that a provider, consent and location policy, and coordinate source exist before implementation.
- establish-authenticated-athlete-ownership | Verify only that this remains parked and demoted.
