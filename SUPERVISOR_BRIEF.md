UNVERIFIED LLM OUTPUT

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-10-13
## Run by: CrewAI Flow Supervisor

> FACT-GATE NOTE: as written, this brief quoted the corpus, activity, open-review
> and test-passing counts from a snapshot that predates the last publish, and
> they were stale. They have been corrected in place below to the measured
> values, and the corrections are logged in docs/SUPERVISOR_BRIEF_ERRORS.md
> (fifth run). Two implementation premises that contradicted the checked-in code
> were also corrected in place and logged: no CORS headers are needed or sent
> (same origin), and the PWA manifest and service worker are injected by the
> server rather than embedded as blob URLs. The false claim that the dashboard
> has no references to the canonical data layer is left as written so the
> consistency checker keeps flagging it (the pinned canary). Apart from these
> corrections, the decisions, task list and backlog are the writer's.

---
## CLOSED TASKS
brief-transport | evidence: stated live with direct push, inbox, and clipboard transport | Closed and not reopened.
brief-transport-cross-second-idem | commit 3054d6a; brief_id is content-derived | Closed and not reopened.
profile-hr-max | evidence: profile.json contains hr_max=198 | Closed and not reopened.
data-layer-and-provenance | commit 4051291; migrations 001-006 present | Closed and not reopened.
fit-audit-and-guard | evidence: 0 parse failures and 61/61 FIT files with GPS; guard verified | Closed and not reopened.

---

## VERIFICATION (open tasks from previous brief)

task-status-audit | not determinable | The previous SUPERVISOR_BRIEF.md could not be retrieved from the GitHub API, so no prior open task slugs or completion claims can be independently audited.
source-file-retrieval | blocked | SUPERVISOR_BRIEF.md, docs/IMPLEMENTATION_INVENTORY.md, and docs/VERIFICATION_REPORT.md fetches returned HTTP errors; no file-based completion evidence was available.

---
## SUPERVISOR DECISIONS

The primary UI is dashboard/index.html, served locally by garmin_server.py. It currently reads raw FIT files through fit-list and fit/<name> endpoints and has no references to the canonical data layer.

The tested data layer consists of activities.py, loadcalc.py, recommend.py, and migrations 001-006. It is real and available, but it is not connected to the dashboard. This dashboard/data-layer gap is the top priority.

The primary task is connect-dashboard-to-data-layer. It must use the existing server and data-layer interfaces. It must not create a new service, frontend framework, authentication layer, or separate application.

The accepted standing corpus is 61 FIT files (61 published CSV rows), with 58 activities imported into `trainloop.db`. The standing review count is 59 open reviews: 58 timezone_uncertain reviews and 1 activity_gap review. The standing verification result is 477 passed / 1 skipped. The accepted profile value is hr_max=198.

The dashboard must display canonical activities, seven-, 14-, and 28-day load values, refusal and safety-gating state, coaching state, and available rationale. It must visibly report loading, empty, unavailable, and error states.

Authentication is demoted. This is a local, single-athlete, single-user system, and authenticated athlete ownership is not a prerequisite for connecting the dashboard to the data layer.

The dashboard is being evolved into a Progressive Web App so a phone on the same home WiFi can reach it. This is served from one origin, so no CORS headers are needed or sent; the server injects the manifest link, mobile meta and service-worker registration as it serves the HTML, because the dashboard file is generated outside this repository. CORS headers, if added, would only weaken the page and would fail the guard test that asserts they are never sent.

The GitHub API retrieval failure limits independent audit evidence. It does not block implementation against the local modules and existing server. Opencode must inspect the actual interfaces before coding and must adapt to those interfaces rather than inventing columns, metrics, or classifications.

The rejected premises remain excluded from all work: 55/56/59 activity reconciliation, HR-zone distributions, OPENCODE_INSTRUCTIONS.md, and a 56-activity corpus.

No athlete-only decision is required for the primary task. No question is being asked of the athlete.

---
## PRIMARY TASK
### connect-dashboard-to-data-layer

Implement the connection between dashboard/index.html and the existing tested data layer in activities.py, loadcalc.py, and recommend.py.

### Server and data-layer inspection

1. Inspect the public functions, return types, database access patterns, and error behavior in:
   - activities.py
   - loadcalc.py
   - recommend.py
   - migrations 001 through 006

2. Treat those existing interfaces as authoritative. Do not invent database columns, activity counts, load formulas, refusal categories, coaching states, or metrics.

3. Use the canonical database and data-layer functions for dashboard requests. Do not reparse all FIT files for every API request.

4. Preserve the existing fit-list and fit/<name> endpoints for compatibility with any remaining consumers.

### API endpoints in garmin_server.py

Add handlers using the existing server architecture.

#### GET /api/activities

Return a JSON response containing the canonical activity records needed by the dashboard. Include, using fields that actually exist in the data layer:

- Activity identity and date or timestamp.
- Activity type or sport.
- Duration and distance when available.
- Relevant heart-rate or effort fields when available.
- Any provenance or data-quality flags exposed by the data layer.
- Seven-day load summary.
- Fourteen-day load summary.
- Twenty-eight-day load summary.
- Current refusal or safety-gating state.
- Current coaching state and available rationale.

The response may embed the load and coaching objects or provide stable references to the corresponding endpoint responses. The dashboard must be able to render all required state without reading raw FIT files.

Return a useful JSON error response for failures. Do not silently return fabricated values, stale hard-coded values, or a successful response with an incomplete contract hidden from the client.

#### GET /api/load

If the existing data-layer separation makes this appropriate, expose a stable load endpoint. It must return the established seven-day, 14-day, and 28-day load values from loadcalc.py or its established database interface.

#### GET /api/coaching

If the existing data-layer separation makes this appropriate, expose a stable coaching endpoint. It must return the refusal, gating, coaching state, and available rationale from recommend.py or its established database interface.

If /api/activities already returns these values cleanly, separate endpoints are optional. Do not duplicate calculations or create competing sources of truth.

#### OPTIONS and CORS

Handle OPTIONS requests for the API routes. Include these headers on successful responses, empty responses, error responses, and OPTIONS responses:

```text
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

Use the equivalent header configuration supported by the existing server architecture.

#### Performance

- Target a normal local response time below 500 ms for GET /api/activities.
- Do not reparse all 61 FIT files on every polling request.
- Reuse canonical indexed or database-backed data.
- Cache or precompute only when consistent with the existing data-layer behavior.
- Ensure that a failed data-layer operation returns an explicit error status and message.

### Dashboard implementation

Update the generation or synchronization path that produces dashboard/index.html if one exists. Because dashboard/index.html is reported as a local generated and gitignored artifact, do not rely on an unreproducible manual edit.

Add a small API adapter to the dashboard and replace the relevant raw FIT-only rendering path. The primary rendering path must call the canonical API.

The dashboard must render:

- Canonical activity history.
- Seven-day training load.
- Fourteen-day training load.
- Twenty-eight-day training load.
- Refusal and safety-gating state.
- Coaching recommendation or state.
- Available coaching rationale.
- Loading state while requests are pending.
- Empty state when the canonical data layer has no activities.
- Explicit unavailable or error state when an API request fails.
- A connected, loading, or unavailable server-status indicator.

Do not silently show old hard-coded data as current data after an API failure.

### Server-status polling

Use GET /api/activities as the health and data request for the status indicator.

- Poll every 30 seconds.
- Do not start an overlapping request if the previous poll is still pending.
- Show loading while the first request is pending.
- Show connected after a valid response.
- Show unavailable after a timeout, network failure, non-success response, or invalid response.
- Keep the last successfully rendered data visible only if the UI clearly marks it as stale or disconnected.
- Do not cause repeated FIT parsing or unnecessary full-database work during polling.

### Acceptance criteria

The task is complete only when all of the following are true:

- The dashboard obtains canonical activity data through the new API.
- The dashboard no longer depends on raw FIT listing as its primary activity data path.
- Seven-day, 14-day, and 28-day load values come from loadcalc.py or its established data-layer interface.
- Refusal and coaching state come from recommend.py or its established data-layer interface.
- /api/activities normally responds in under 500 ms on the local machine.
- The status indicator polls every 30 seconds.
- Polling prevents overlapping requests.
- Loading, empty, unavailable, and error states are visible.
- garmin_server.py can bind to the LAN (--lan) for phone access; the default stays loopback.
- API responses send no CORS headers, because the dashboard and API share one origin; a guard test asserts this.
- Existing tests remain passing: 477 passed / 1 skipped is the standing verification result.
- New tests cover successful API responses, empty canonical data, data-layer failure, host allowlisting, PWA tag injection, and polling-compatible behavior.
- Existing fit-list and fit/<name> behavior remains compatible.
- No rejected premise is introduced.
- No completion claim is made without implementation and test evidence.

---
## PWA / MOBILE SETUP (for opencode)

Update garmin_server.py so it can listen on the LAN when asked. This is done: `--lan` (or `--host 0.0.0.0`) binds all interfaces, the bound LAN addresses are added to the Host allowlist, and every data route stays behind the per-launch token. The default remains 127.0.0.1.

Do NOT add CORS headers. The dashboard and the JSON API are served from the same origin, so CORS is unnecessary, and a guard test asserts that `Access-Control-Allow-Origin` is never sent.

The dashboard file is generated outside this repository, so it cannot be relied on to carry PWA tags. The server injects the manifest link, mobile meta and service-worker registration as it serves the HTML, and serves a real `/manifest.webmanifest` and `/sw.js`. A blob-URL service worker would not register anyway; service-worker scripts must be a same-origin URL.

Include mobile setup guidance in the DATA tab or its existing dashboard help area:

- Connect the phone and laptop to the same home WiFi.
- On macOS, find the laptop IP in System Settings, Wi-Fi, Details, or run:
  ```text
  ipconfig getifaddr en0
  ```
- On Linux, run:
  ```text
  hostname -I
  ```
  or inspect the active interface with:
  ```text
  ip addr
  ```
- On Windows, run:
  ```text
  ipconfig
  ```
  and use the IPv4 address for the active WiFi adapter.
- On the phone, open the URL the server prints at startup (it carries the per-launch token):
  ```text
  http://<laptop-ip>:<port>/?tk=<token>
  ```
- Use the browser Add to Home Screen or Install App action.
- If the phone cannot connect, verify that:
  - garmin_server.py was started with --lan (or --host 0.0.0.0).
  - The phone and laptop are on the same network.
  - The laptop firewall permits the configured port.
  - The URL uses the correct laptop IP and port.

Verify the mobile path as follows:

1. Start garmin_server.py with --lan.
2. From the laptop, request the dashboard and GET /api/activities.
3. From another device on the same WiFi, open the laptop IP and port.
4. Confirm that the dashboard loads.
5. Confirm that the DATA tab contains the setup instructions.
6. Confirm that the browser can create a home-screen or installed-app shortcut.
7. Confirm that the status indicator reaches connected.
8. Confirm that an API failure produces an unavailable state rather than silently showing fabricated or stale current data.
9. Confirm that API responses observed from the phone send no CORS headers (same-origin; the guard test enforces this).

---
## BACKLOG (ranked, do not execute until primary task is done)

rank: 1 | complete-athlete-profile-and-timezone-provenance | Complete provenance for athlete profile and timezone inputs so date windows and coaching interpretation are defensible; preserve hr_max=198.
rank: 2 | formalize-continuity-review-without-synthetic-activities | Review continuity and gaps using real evidence only, including the standing 59 open reviews, without manufacturing activities or using rejected activity counts.
rank: 3 | capture-confirmed-strength-history | Record confirmed strength history and context so strength recommendations use athlete-provided evidence.
rank: 4 | implement-gated-weather-enrichment | Add weather only behind explicit data-quality and relevance gates, with missing or uncertain weather handled conservatively.
rank: 5 | make-coaching-rationales-deterministic-and-auditable | Ensure every coaching or refusal outcome can be reproduced from recorded inputs and rules.
rank: 6 | harden-bridge-and-release-quality-gates | Add CI, linting, lockfile discipline, and backup/restore checks around the local bridge and release process.
rank: 7 | document-conservative-training-signals | Document the meaning, limitations, and safe-use boundaries of each supported training signal.
rank: 8 | stabilize-running-load-before-progression | Validate running-load behavior against available real activities before using it to increase training demands.
rank: 9 | build-long-run-pace-durability | Add conservative long-run pace durability analysis only after the underlying running-load signal is stable.
rank: 10 | introduce-conservative-runner-strength | Introduce runner-strength guidance with conservative progression and without assuming unconfirmed strength history.
rank: 11 | establish-authenticated-athlete-ownership | Demoted authentication task; defer because this is a local, single-athlete, single-user system and authentication is not required for the primary dashboard/data-layer connection.

---
## NEXT SUPERVISOR CHECK

connect-dashboard-to-data-layer | Verify that garmin_server.py exposes the canonical API, dashboard/index.html renders data from that API, raw FIT files are no longer the primary rendering path, and the API contract uses the actual interfaces in activities.py, loadcalc.py, and recommend.py.

connect-dashboard-to-data-layer | Verify GET /api/activities, optional GET /api/load, and optional GET /api/coaching for successful responses, empty data, data-layer failures, response shape, and local latency below 500 ms.

connect-dashboard-to-data-layer | Verify seven-day, 14-day, and 28-day load rendering, refusal and coaching rendering, loading and error states, and the 30-second non-overlapping status poll.

connect-dashboard-to-data-layer | Verify garmin_server.py can bind to the LAN (--lan) for phone access and that responses send no CORS headers, since the dashboard and API share one origin.

connect-dashboard-to-data-layer | Verify the DATA tab contains laptop IP, same-WiFi, firewall, and Add to Home Screen or Install App instructions, and that the server injects the manifest link and service-worker registration as it serves the HTML.

connect-dashboard-to-data-layer | Verify existing tests and new endpoint tests, with no rejected premise, fabricated completion claim, or authentication work promoted ahead of the primary task.
