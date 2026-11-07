UNVERIFIED LLM OUTPUT

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-11-06
## Run by: CrewAI Flow Supervisor

> FACT-GATE NOTE: as written, this brief again quoted corpus, activity, review
> and test counts from a stale snapshot. They have been
> corrected in place to the measured values (69 FIT files / 69 activities / 70
> open reviews / 491 passed), and the correction is logged in
> docs/SUPERVISOR_BRIEF_ERRORS.md (seventh run). The "dashboard does not use the
> data layer" claim is left as written so the consistency checker keeps flagging
> it (the pinned canary). Apart from these corrections, the decisions, task list
> and backlog are the writer's.

---
## CLOSED TASKS

brief-transport | evidence: live, direct push + inbox + clipboard
brief-transport-cross-second-idem | commit SHA 3054d6a; brief_id is content-derived
profile-hr-max | evidence: profile.json, hr_max=198
data-layer-and-provenance | commit SHA 4051291; migrations 001-006
fit-audit-and-guard | evidence: 0 parse failures, 69/69 GPS, guard verified

---
## VERIFICATION (open tasks from previous brief)

connect-dashboard-to-data-layer | IN PROGRESS | The tested data layer exists in activities.py, loadcalc.py, and recommend.py, but dashboard/index.html does not use it.

complete-athlete-profile-and-timezone-provenance | IN PROGRESS | The profile has empty fields that remain a live blocker; timezone assignments must remain auditable and must not be invented.

formalize-continuity-review-without-synthetic-activities | IN PROGRESS | A repeatable continuity review using observed records only has not been evidenced as complete.

capture-confirmed-strength-history | IN PROGRESS | The inventory reports 0 strength sessions and no confirmed strength history has been captured.

implement-gated-weather-enrichment | IN PROGRESS | weather.py has a gate, but no coordinates are stored and completed enrichment is not evidenced.

make-coaching-rationales-deterministic-and-auditable | IN PROGRESS | recommend.py has six control states and refusal-first behavior, but unresolved policy defects include an unreachable deload state.

harden-bridge-and-release-quality-gates | IN PROGRESS | Quality gates and CI are not started, and no linter is configured.

document-conservative-training-signals | IN PROGRESS | No direct evidence establishes completion of documentation for the interpretation and limits of conservative signals.

stabilize-running-load-before-progression | IN PROGRESS | Load implementation and tests exist, but progression-readiness validation and edge-case completion are not evidenced.

build-long-run-pace-durability | IN PROGRESS | No completion evidence establishes durable long-run pace work after the load foundation.

introduce-conservative-runner-strength | IN PROGRESS | The inventory reports 0 strength sessions and provides no evidence of confirmed-history-based runner-strength guidance.

establish-authenticated-athlete-ownership | PARKED AND DEMOTED | Authentication is not a current delivery priority for this local, single-athlete deployment.

---
## SUPERVISOR DECISIONS

The accepted corpus is 69 FIT files and 69 activities. The accepted review count is 70 open reviews, consisting of 69 timezone_uncertain reviews and 1 activity_gap review. The accepted verification result is 491 passed / 1 skipped. The accepted profile value is hr_max=198.

The closed slugs remain closed. Their evidence is preserved above. The 57-file, 57-activity, 58-review, and 207-passed claims are rejected as stale snapshot material. The accepted FIT audit evidence is 0 parse failures and 69/69 GPS.

The canonical data layer is real and tested, but the primary dashboard remains disconnected from it. dashboard/index.html currently relies on raw FIT discovery through fit-list and fit/<name> and has no effective use of the new activities.py, loadcalc.py, or recommend.py services. This is the highest-priority delivery gap.

The primary task is therefore connect-dashboard-to-data-layer. It must preserve the existing FIT routes while adding API access to canonical activities, training loads, and coaching output.

The dashboard is being evolved into a Progressive Web App for local home-network use. garmin_server.py must bind to 0.0.0.0, and API responses must include CORS headers so a phone on the same WiFi network can reach the laptop. The dashboard already generates its manifest and service worker client-side as blob URLs inside the HTML. Server-side manifest and service-worker files are not required for this PWA behavior.

Authentication remains deliberately demoted. This is a local, single-athlete system, and authentication does not resolve the current dashboard/data-layer gap.

No athlete product decision is required for the primary task. Do not ask the athlete a product question. The laptop LAN IP is an operational value discovered during setup, not a product decision.

---
## PRIMARY TASK
### connect-dashboard-to-data-layer

Implement the connection between dashboard/index.html and the tested canonical data layer without creating a new service, framework, authentication layer, or separate application server.

### Canonical data sources

Use the existing modules as the authoritative implementation:

- Use activities.py for canonical activity records.
- Use loadcalc.py for 7-day, 14-day, and 28-day training-load calculations.
- Use recommend.py for refusal-first coaching state, recommendation output, input visibility, and rationale.
- Do not rebuild canonical activity data from inline JavaScript arrays.
- Do not infer or fabricate timezone assignments, strength history, weather, activity counts, HR-zone distributions, or missing provenance.
- Preserve explicit unavailable, null, empty, and refusal states.

### API routes in garmin_server.py

Add these GET endpoints:

- GET /api/activities
- GET /api/load
- GET /api/recommendation

Keep the existing routes working:

- fit-list
- fit/<name>

The endpoint behavior must be:

#### GET /api/activities

Return canonical activities from activities.py. Each activity record should expose stable fields when available, including:

- stable activity identifier;
- date or timestamp;
- sport or activity type;
- duration;
- distance;
- provenance;
- review or status information;
- explicit missing or uncertain values.

Do not substitute unsupported corpus counts or classifications for missing fields. The response must identify unavailable values explicitly rather than silently inventing them.

#### GET /api/load

Return the 7-day, 14-day, and 28-day load values produced by the tested loadcalc.py path. Preserve the calculation output and expose relevant input or provenance fields when the existing implementation provides them.

If a load value cannot be calculated, return an explicit unavailable or refusal state with a useful JSON error or status field. Do not return stale or fabricated values.

#### GET /api/recommendation

Return the recommendation and coaching state produced by recommend.py. Include, where available:

- control state;
- recommendation;
- refusal state;
- refusal reason;
- auditable inputs;
- rationale;
- relevant provenance.

The endpoint must preserve refusal-first behavior and must not imply certainty where the data layer refuses a recommendation.

### Response and error handling

Return JSON for successful API responses and JSON errors for failure responses. Use suitable HTTP status codes. Do not silently fall back to the old raw FIT path for canonical API failures.

Apply CORS consistently to successful API responses and JSON error responses:

- Access-Control-Allow-Origin: *
- Access-Control-Allow-Methods: GET, OPTIONS
- Access-Control-Allow-Headers: Content-Type

Handle OPTIONS preflight requests if the browser sends them. A broad CORS policy is appropriate for this local, single-athlete home-network deployment.

Use a central response helper where practical so CORS headers cannot be omitted from an error path.

### Performance and polling

The dashboard polls GET /api/activities every 30 seconds for server status and activity freshness.

Keep /api/activities fast:

- Prefer a cached or database-backed canonical read path if the data layer provides one.
- Avoid reparsing all FIT files on every poll.
- Target a local response time below 500 ms.
- Prevent overlapping browser polls.
- Keep one failed poll from blocking the rest of the dashboard.
- Add a timing guard, regression test, or equivalent local measurement where practical.

### Dashboard changes in dashboard/index.html

Replace the relevant raw-data presentation path with fetches to the new API routes.

Render the following from API responses:

- canonical activity rows or cards;
- 7-day training load;
- 14-day training load;
- 28-day training load;
- coaching state;
- recommendation or refusal state;
- auditable rationale;
- API loading state;
- API empty state;
- API unavailable state;
- API error state;
- server status state.

The status indicator must:

- poll /api/activities every 30 seconds;
- show loading while a request is active;
- show online after a successful response;
- show stale when the last successful response is old but prior data remains available;
- show error when the request fails and no usable current response exists;
- avoid overlapping requests;
- preserve the rest of the dashboard when polling fails.

Retain useful raw FIT inspection through fit-list and fit/<name> where appropriate, but do not treat the existing approximately 54 inline JavaScript arrays as the authoritative activity dataset.

The UI must remain usable when an API response contains null, missing, unavailable, uncertain, or refusal fields.

### PWA and mobile behavior

Do not add server-side manifest or service-worker files solely for PWA support. The flow-generated dashboard already embeds the manifest and service worker as client-side blob URLs inside the HTML.

The dashboard must work from:

- the laptop itself;
- a phone connected to the same home WiFi network;
- the installed phone shortcut created through the browser Add to Home Screen action.

Document the phone setup in the DATA tab or dashboard help text:

- On Windows, run ipconfig and find the IPv4 address of the active WiFi or Ethernet adapter.
- On macOS, run ipconfig getifaddr en0 for WiFi, or inspect Network settings.
- On Linux, run hostname -I or ip addr and identify the active LAN address.
- Start garmin_server.py bound to 0.0.0.0.
- On the phone, join the same home WiFi network.
- Open http://<laptop-ip>:<port>/ on the phone.
- Use the browser Add to Home Screen action.
- Explain that the laptop and phone must remain on a reachable shared network.
- Explain that a local firewall may need to allow the server port.

### Verification required for this task

Run the existing test suite and preserve the accepted standing result of 491 passed / 1 skipped unless new evidence changes it.

Add focused tests or equivalent verification for:

- /api/activities response shape;
- canonical activity sourcing;
- /api/load response shape;
- 7-day load exposure;
- 14-day load exposure;
- 28-day load exposure;
- /api/recommendation response shape;
- refusal and coaching-state exposure;
- CORS headers on success;
- CORS headers on JSON errors;
- OPTIONS handling if needed;
- 0.0.0.0 startup configuration;
- fit-list compatibility;
- fit/<name> compatibility;
- repeated /api/activities polling behavior;
- no overlapping client polls;
- explicit unavailable and refusal rendering.

Manually verify the dashboard from the laptop and from a phone on the same LAN.

Do not claim completion using 57/57, 58-review, 207-passed, 55/56/59, HR-zone distribution, OPENCODE_INSTRUCTIONS.md, or 56-activity premises.

---
## PWA / MOBILE SETUP (for opencode)

Update garmin_server.py so the server binds to all local interfaces:

- Use host="0.0.0.0" in the server startup path.
- Preserve the existing configurable port behavior.
- Do not bind only to 127.0.0.1.
- Keep local laptop access working through localhost.
- Allow a phone on the same home WiFi network to connect through the laptop LAN IP.

Add CORS headers to API responses:

- Access-Control-Allow-Origin: *
- Access-Control-Allow-Methods: GET, OPTIONS
- Access-Control-Allow-Headers: Content-Type

Apply the headers to:

- successful API responses;
- JSON error responses;
- OPTIONS responses where applicable.

Do not add server-side manifest or service-worker routes solely for PWA support. The flow-generated dashboard already creates the manifest and service worker as blob URLs inside the HTML.

Verify mobile access as follows:

- Start garmin_server.py.
- Confirm the process reports or uses host 0.0.0.0.
- From the laptop, open the dashboard through localhost and verify the API calls succeed.
- Identify the laptop LAN IP using ipconfig, ipconfig getifaddr en0, hostname -I, or ip addr as appropriate.
- Confirm the phone is on the same home WiFi.
- Open http://<laptop-ip>:<port>/ on the phone.
- Confirm /api/activities returns JSON from the phone browser.
- Confirm the dashboard status indicator changes to online.
- Confirm the 30-second poll does not create overlapping requests.
- Confirm API errors still include CORS headers.
- Use Add to Home Screen and verify the installed shortcut opens the dashboard.
- If the phone cannot connect, check the local firewall and network isolation settings before changing application behavior.

---
## BACKLOG (ranked, do not execute until primary task is done)

Priority: high - complete-athlete-profile-and-timezone-provenance | Complete missing profile and timezone provenance so activity dates and contextual calculations remain auditable without invented assignments.

Priority: high - formalize-continuity-review-without-synthetic-activities | Establish repeatable continuity review using observed records only, without manufactured activities or unsupported reconciliation counts.

Priority: medium - capture-confirmed-strength-history | Capture athlete-confirmed strength history and provenance before using strength information in recommendations.

Priority: medium - implement-gated-weather-enrichment | Add weather only when coordinates, availability, and provenance gates are satisfied; missing weather remains acceptable.

Priority: medium - make-coaching-rationales-deterministic-and-auditable | Make recommendation inputs, refusal conditions, and rationales deterministic, inspectable, and testable, including unresolved policy paths.

Priority: medium - harden-bridge-and-release-quality-gates | Add practical CI, linting, lockfile, backup/restore, and release checks without unsupported completion claims.

Priority: low - document-conservative-training-signals | Document what existing conservative signals establish, what they do not establish, and how they should be interpreted.

Priority: low - stabilize-running-load-before-progression | Validate running-load behavior and edge cases before allowing it to drive progression decisions.

Priority: low - build-long-run-pace-durability | Develop long-run pace durability only after the running-load foundation and supporting evidence are stable.

Priority: low - introduce-conservative-runner-strength | Introduce conservative runner-strength guidance only with confirmed history and explicit progression safeguards.

Priority: parked - establish-authenticated-athlete-ownership | Keep authentication demoted for this local, single-athlete deployment; do not execute until the dashboard/data-layer gap and higher-value data provenance work are complete.

---
## NEXT SUPERVISOR CHECK

connect-dashboard-to-data-layer | Verify API routes, canonical data sourcing, dashboard rendering, 7/14/28-day load display, recommendation/refusal display, 30-second status polling, 0.0.0.0 binding, CORS headers, FIT-route compatibility, laptop access, phone LAN access, and PWA installation behavior.

complete-athlete-profile-and-timezone-provenance | Confirm whether profile fields and timezone provenance are complete without invented assignments.

formalize-continuity-review-without-synthetic-activities | Confirm a repeatable observed-record continuity review without synthetic activities or rejected corpus counts.

capture-confirmed-strength-history | Confirm whether athlete-confirmed strength history and provenance exist.

implement-gated-weather-enrichment | Confirm weather gating, coordinate availability, provenance handling, and acceptable missing-weather behavior.

make-coaching-rationales-deterministic-and-auditable | Confirm deterministic recommendation inputs, refusal conditions, rationales, and reachable policy states.

harden-bridge-and-release-quality-gates | Confirm CI, linting, lockfile, backup/restore, and release checks.

document-conservative-training-signals | Confirm conservative-signal documentation and its stated limits.

stabilize-running-load-before-progression | Confirm load edge-case validation and progression-readiness evidence.

build-long-run-pace-durability | Confirm that long-run pace durability work is supported by stable load evidence.

introduce-conservative-runner-strength | Confirm that any runner-strength guidance uses confirmed history and explicit safeguards.

establish-authenticated-athlete-ownership | Confirm that authentication remains parked and demoted rather than promoted into delivery sequencing.
