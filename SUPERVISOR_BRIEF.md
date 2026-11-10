UNVERIFIED LLM OUTPUT

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-11-10
## Run by: CrewAI Flow Supervisor

> FACT-GATE NOTE: as written, this brief again quoted corpus, review and test
> counts from a stale snapshot. They have been corrected in place to the
> measured values (70 FIT files / 70 activities / 1 open review / 496 passed),
> and the correction is logged in docs/SUPERVISOR_BRIEF_ERRORS.md (tenth
> correction, 2026-11-10). The review count is 1 because the athlete confirmed
> local dates (US Central, UTC-5/-6); the 2026-11-08 run was imported and its
> local date confirmed at UTC-6. Only the calendar-gap review remains. The
> "dashboard does not use the data layer" claim is left as written so the
> consistency checker keeps flagging it (the pinned canary). Apart from these
> corrections, the decisions, task list and backlog are the writer's.

---
## CLOSED TASKS

brief-transport | evidence: live, direct push + inbox + clipboard | Transport is complete and remains closed.

brief-transport-cross-second-idem | commit SHA 3054d6a; brief_id is content-derived | Cross-second idempotency is complete and remains closed.

profile-hr-max | evidence: profile.json, hr_max=198 | The athlete HR maximum is recorded and remains closed.

data-layer-and-provenance | commit SHA 4051291; migrations 001-006 | The canonical data layer and provenance migrations are complete and remain closed.

fit-audit-and-guard | evidence: 0 parse failures, 70/70 GPS, guard verified | FIT audit and guard work remains closed; current audit facts are 70 FIT files and 70 activities.

---
## VERIFICATION (open tasks from previous brief)

connect-dashboard-to-data-layer | IN PROGRESS | The tested data layer exists in activities.py, loadcalc.py, and recommend.py, but dashboard/index.html does not use it.

complete-athlete-profile-and-timezone-provenance | IN PROGRESS | The profile has empty fields that remain a live blocker; timezone assignments must remain auditable and must not be invented.

capture-confirmed-strength-history | IN PROGRESS | The inventory reports 0 strength sessions and no confirmed strength history has been captured.

implement-gated-weather-enrichment | IN PROGRESS | weather.py has a gate, but no coordinates are stored and completed enrichment is not evidenced.

document-conservative-training-signals | IN PROGRESS | No direct evidence establishes completion of documentation for the interpretation and limits of conservative signals.

stabilize-running-load-before-progression | IN PROGRESS | Load implementation and tests exist, but progression-readiness validation and edge-case completion are not evidenced.

build-long-run-pace-durability | IN PROGRESS | No completion evidence establishes durable long-run pace work after the load foundation.

introduce-conservative-runner-strength | IN PROGRESS | The inventory reports 0 strength sessions and provides no evidence of confirmed-history-based runner-strength guidance.

establish-authenticated-athlete-ownership | BLOCKED / PARKED AND DEMOTED | Authentication is not a current delivery priority for this local, single-athlete deployment.

---
## SUPERVISOR DECISIONS

- The authoritative corpus is 70 FIT files and 70 activities.
- There is 1 open review: the activity_gap review for 2026-06-26..2026-07-05. All 70 activities carry athlete-confirmed local dates (US Central, UTC-5/-6 with DST applied per run).
- The accepted verification result is 496 passed / 1 skipped.
- hr_max=198 is authoritative and is already covered by the closed profile-hr-max task.
- Any conflicting corpus, review or test count elsewhere in this brief is stale snapshot material and is rejected; the measured values stated above are authoritative.
- The tested canonical data layer is real and includes activities.py, loadcalc.py, recommend.py, and migrations 001-006.
- The primary dashboard still reads raw FIT data through fit-list and fit/<name> and must be connected to the canonical data layer.
- The dashboard integration is the only primary task for this run. It must preserve raw FIT route behavior while adding canonical activities, load, recommendation, provenance, review, refusal, and unavailable states.
- Authentication remains parked and demoted. It must not block local single-athlete dashboard delivery.
- No synthetic activities may be created. Missing strength history must remain null rather than being treated as zero.
- Weather enrichment remains gated until coordinates and provenance are available.
- HR-zone distributions are not an accepted premise and must not be implemented or displayed.
- The dashboard is being evolved into a Progressive Web App. The existing flow-generated manifest and service worker are embedded as client-side blob URLs inside the HTML and must remain intact.
- garmin_server.py must bind to 0.0.0.0 so a phone on the same home WiFi can reach the dashboard.
- API responses must include CORS headers, including structured error responses.
- No athlete-only implementation decision is needed for the primary task. The existing local port and tested module contracts should be retained.

---
## PRIMARY TASK
### connect-dashboard-to-data-layer

Implement the dashboard integration against the existing tested canonical data layer. Do not create a new service, framework, authentication layer, synthetic activity source, or unsupported metric.

### Server API work in garmin_server.py

Add or expose the following JSON endpoints through the existing server:

#### GET /api/activities

Return canonical activity records loaded through activities.py.

Each activity record should include, when available:

- A stable activity identifier.
- Activity timestamp and date.
- Sport or activity type.
- Duration.
- Distance.
- Source and provenance fields.
- Data-quality state.
- Timezone review state.

Preserve explicit null, unavailable, uncertain, and refusal states. Do not convert missing values to zero. Do not synthesize activities. The endpoint must represent the accepted corpus of 70 activities and the current review state without inventing data.

This endpoint is also the dashboard server-status polling endpoint. Keep its normal response time below 500 ms by reusing the canonical loading path and avoiding an unnecessary raw FIT rescan on every request. Use a cache or already-supported efficient loading path where appropriate, but do not create a second source of truth.

#### GET /api/load

Return the tested load values from loadcalc.py for:

- 7-day load.
- 14-day load.
- 28-day load.

Include calculation timestamp and provenance fields when the existing implementation supports them. Preserve null or unavailable values. Do not add HR-zone distributions or other unsupported metrics.

#### GET /api/recommendation

Return the coaching state from recommend.py.

The response must preserve:

- Refusal-first behavior.
- Existing control states.
- Recommendation state.
- Rationale or reason code exposed by the data layer.
- Provenance or supporting state where already available.
- Explicit unavailable and refused states.

A refused or unavailable recommendation must not be represented as a zero-load recommendation or as a valid training prescription.

An aggregate dashboard endpoint may be added only if it reuses these same canonical contracts. The individual endpoints remain mandatory and independently testable.

### Common API behavior

For all API success and error responses:

- Return JSON.
- Set an appropriate application/json Content-Type.
- Include Access-Control-Allow-Origin: *.
- Return structured JSON errors rather than HTML or ambiguous empty responses.
- Preserve explicit unavailable, uncertain, refusal, and null states.
- Do not add authentication.
- Keep existing fit-list and fit/<name> routes functional.
- Do not change raw FIT route semantics.
- Avoid reparsing all FIT files during the 30-second status poll when canonical data can be reused.

If the server has a centralized response helper, apply the CORS header there so errors receive the same header as successful responses. If errors are handled separately, test both paths.

### Dashboard integration in dashboard/index.html

Update the dashboard to fetch:

- /api/activities
- /api/load
- /api/recommendation

Use the API responses as the source for canonical activity summaries, load values, and coaching state.

Render the following visibly:

- Connection state: loading, connected, unavailable, or error.
- Canonical activity summaries.
- Activity timestamps, type, duration, distance, and stable identifiers where available.
- Timezone review warnings and other data-quality states.
- 7-day, 14-day, and 28-day load values.
- Recommendation state and rationale.
- Refused and unavailable states as explicit labels.
- Provenance information where supplied by the API.
- The current server status based on /api/activities polling.

The dashboard must not silently fall back to stale inline arrays when an API request fails, is refused, or returns unavailable data. Show the failure or unavailable condition instead.

Keep the existing raw FIT views available. Existing fit-list and fit/<name> behavior must continue to work.

The current dashboard contains approximately 54 inline JavaScript arrays. Replace or quarantine duplicated canonical activity data incrementally only after API-backed rendering is working. Do not use array positions as identifiers. Preserve stable activity identifiers from the canonical data layer.

The server-status indicator must poll /api/activities every 30 seconds. The poll must update connection state without replacing valid data with fabricated or stale data after an API error.

### Data and state safety

Use the existing implementations in activities.py, loadcalc.py, and recommend.py rather than duplicating their calculations in browser JavaScript.

Do not:

- Create synthetic activities.
- Infer missing timezone assignments.
- Treat missing strength history as zero strength history.
- Add HR-zone distributions.
- Convert unavailable values to zero.
- Present a refusal as a recommendation.
- Present a failed API request as valid training data.
- Add authentication as a prerequisite.
- Change the accepted corpus from 70 FIT files and 70 activities.

The implementation and tests must respect 1 open review, hr_max=198, and the accepted verification result of 496 passed / 1 skipped.

### Dashboard failure and loading behavior

Implement explicit client states for:

- Initial loading.
- Successful API response.
- Empty but valid response.
- Unavailable API data.
- Refused recommendation.
- Network failure.
- Invalid or incomplete JSON response.

The UI must identify which data section is unavailable. It must not silently display hard-coded values as current canonical data.

### PWA behavior

The flow-generated dashboard already embeds the manifest and service worker as blob URLs inside the HTML. Preserve this client-side generation. Do not add a requirement for server-side manifest or service-worker files.

Verify that the dashboard still initializes the embedded manifest and service worker when loaded from the laptop address over home WiFi.

### Tests and verification

Add or extend focused tests covering:

- /api/activities response shape.
- /api/load response shape.
- /api/recommendation response shape.
- JSON Content-Type on success.
- CORS headers on success.
- CORS headers on structured API errors.
- Canonical activity output.
- 7-day, 14-day, and 28-day load output.
- Recommendation state and refusal-state propagation.
- Existing fit-list route behavior.
- Existing fit/<name> route behavior.
- garmin_server.py binding to 0.0.0.0.
- /api/activities completion below 500 ms in the local test setup.
- Dashboard loading, connected, unavailable, refusal, and error rendering.
- 30-second /api/activities polling.
- Continued initialization of the blob-based manifest and service worker.

Use the existing project test conventions. Do not introduce unsupported corpus counts or unsupported metrics.

### Athlete decision

No athlete-only decision is required. Do not ask the athlete a question before implementing this task.

---
## PWA / MOBILE SETUP (for opencode)

Update garmin_server.py so the server binds to all local interfaces:

```python
host="0.0.0.0"
```

Retain the existing configured port unless the current server contract requires a different value. Do not bind only to 127.0.0.1.

Add CORS headers to every API response:

```text
Access-Control-Allow-Origin: *
```

Apply the header to both successful and error responses. Keep errors as JSON responses with a stable error shape.

The flow-generated dashboard already embeds the manifest and service worker as blob URLs inside the HTML. Do not create a separate server-side manifest or service-worker route unless required by existing code. Verify that the blob URLs still initialize after the dashboard is served from the laptop WiFi address.

### Verification steps for opencode

1. Start garmin_server.py with the dashboard available on the existing local port.
2. Confirm the process is listening on 0.0.0.0 rather than only 127.0.0.1.
3. Request /api/activities locally and verify JSON, CORS, canonical activity records, and normal response time below 500 ms.
4. Request /api/load and verify 7-day, 14-day, and 28-day values and their explicit unavailable states where applicable.
5. Request /api/recommendation and verify recommendation, refusal, and rationale state propagation.
6. Request an invalid API path or force a controlled API error and verify JSON plus the CORS header.
7. Verify fit-list still returns the existing FIT listing.
8. Verify fit/<name> still returns the existing FIT detail or file response.
9. Open the dashboard and verify loading, connected, unavailable, and error states.
10. Confirm the dashboard polls /api/activities every 30 seconds.
11. Confirm the embedded manifest and service worker still initialize from blob URLs.
12. Verify the implementation against 70 FIT files, 70 activities, 1 open review, hr_max=198, and 496 passed / 1 skipped.
13. Confirm no synthetic activities, HR-zone distributions, unsupported metrics, or silent refusal fallbacks were introduced.

### Athlete phone instructions

On the laptop running garmin_server.py, find the local WiFi IP address:

- Windows: run `ipconfig` and use the IPv4 address for the active WiFi adapter.
- macOS: run `ipconfig getifaddr en0`, or inspect Network settings.
- Linux: run `hostname -I`, or inspect the active network connection.

Start garmin_server.py with the dashboard bound to all local interfaces.

Connect the phone and laptop to the same home WiFi network. In the phone browser, open:

```text
http://<laptop-ip>:<port>/
```

Replace `<laptop-ip>` with the laptop WiFi IPv4 address and `<port>` with the port configured by garmin_server.py.

Install the dashboard on the phone:

- iPhone/Safari: Share -> Add to Home Screen.
- Android/Chrome: menu -> Add to Home screen or Install app.

If the page does not load:

- Confirm the phone and laptop are on the same WiFi network.
- Confirm the laptop firewall allows the configured local port.
- Confirm garmin_server.py is bound to 0.0.0.0.
- Confirm the URL uses the laptop IP rather than localhost or 127.0.0.1.

---
## BACKLOG (ranked, do not execute until primary task is done)

rank: 1 | complete-athlete-profile-and-timezone-provenance | Complete only genuinely missing profile fields and make every timezone assignment auditable without inferring or inventing timezone information.

rank: 2 | stabilize-running-load-before-progression | Validate load edge cases and progression-readiness behavior before allowing progression-oriented guidance.

rank: 3 | document-conservative-training-signals | Document interpretation, limitations, and unavailable conditions for conservative signals without introducing unsupported metrics.

rank: 4 | capture-confirmed-strength-history | Capture strength history only from confirmed athlete evidence and preserve null when no confirmed history exists.

rank: 5 | implement-gated-weather-enrichment | Complete weather enrichment only after coordinates and provenance are available; retain the existing gate when they are not.

rank: 6 | build-long-run-pace-durability | Develop long-run pace durability only after the load foundation is stable and observed athlete data supports it.

rank: 7 | introduce-conservative-runner-strength | Add conservative runner-strength guidance only when confirmed history can be distinguished from missing history.

rank: 8 | establish-authenticated-athlete-ownership | PARKED AND DEMOTED; authentication is not a delivery prerequisite for this local, single-athlete deployment and must not block the dashboard.

---
## NEXT SUPERVISOR CHECK

connect-dashboard-to-data-layer | Verify /api/activities, /api/load, and /api/recommendation contracts; canonical rendering; explicit unavailable and refusal states; 30-second polling; preserved fit-list and fit/<name> routes; CORS on success and error responses; 0.0.0.0 binding; sub-500-ms /api/activities response time; and phone access over home WiFi.

complete-athlete-profile-and-timezone-provenance | Verify that remaining profile fields and timezone assignments are either evidenced or explicitly unresolved, with no invented values.

stabilize-running-load-before-progression | Verify load edge-case tests and progression-readiness behavior before any progression guidance is enabled.

document-conservative-training-signals | Verify documentation of signal interpretation, limitations, and unavailable conditions.

capture-confirmed-strength-history | Verify that any strength history is confirmed by evidence and that missing history remains null.

implement-gated-weather-enrichment | Verify coordinates, provenance, and gated weather behavior before accepting enrichment as complete.

build-long-run-pace-durability | Verify that long-run pace work is based on stable load behavior and observed data.

introduce-conservative-runner-strength | Verify conservative guidance distinguishes confirmed strength history from missing history.

establish-authenticated-athlete-ownership | Verify that authentication remains parked and does not block local dashboard delivery.
