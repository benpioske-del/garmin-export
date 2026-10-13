UNVERIFIED LLM OUTPUT

# Athletic Performance Hub \\ Supervisor Brief
## Generated: 2026-10-13
## Run by: CrewAI Flow Supervisor

---
## CLOSED TASKS

brief-transport | evidence: live, direct push + inbox + clipboard | Brief transport was verified through live direct push, inbox, and clipboard paths.
brief-transport-cross-second-idem | commit SHA 3054d6a; brief_id is content-derived | Cross-channel brief delivery is content-derived and idempotent.
profile-hr-max | evidence: profile.json, hr_max=198 | The athlete profile contains the accepted hr_max value of 198.
data-layer-and-provenance | commit SHA 4051291; migrations 001-006 | The canonical data layer and provenance migrations are present.
fit-audit-and-guard | evidence: 0 parse failures, 57/57 GPS, guard verified | The FIT audit completed with no parse failures, GPS coverage for 57 of 57 files, and a verified guard.

---
## VERIFICATION (open tasks from previous brief)

NO-INDEPENDENTLY-VERIFIED-OPEN-SLUGS | UNVERIFIED | GitHub API retrieval failed for SUPERVISOR_BRIEF.md, docs/IMPLEMENTATION_INVENTORY.md, and docs/VERIFICATION_REPORT.md, so no previous-brief open slug can be classified without fabricating evidence.

---
## SUPERVISOR DECISIONS

- The primary task is `connect-dashboard-to-data-layer`. The tested data layer exists in `activities.py`, `loadcalc.py`, and `recommend.py`, but `dashboard/index.html` does not use it.
- The dashboard currently reads raw FIT files through `fit-list` and `fit/<name>` routes and contains approximately 54 inline JavaScript arrays. Those arrays must no longer be treated as the authoritative activity source.
- The dashboard must use canonical activity records from the data layer and must display 7-day, 14-day, and 28-day loads plus the current refusal/coaching state and available rationale metadata.
- Existing FIT routes must remain available for compatibility and detail views unless deliberate retirement is covered by tests.
- No new service, framework, authentication system, or parallel activity database is authorized for this task.
- `GET /api/activities` is the required integration boundary. It must use existing Python interfaces and database records rather than reparsing all FIT files or reconstructing activity truth in browser code.
- The endpoint must be suitable for 30-second polling and should normally complete in less than 500 ms.
- The server must bind to `0.0.0.0` so a phone on the athlete's home WiFi can reach the dashboard.
- API responses, including errors and preflight responses where needed, must include CORS support. `Access-Control-Allow-Origin: *` is appropriate for this local, single-athlete system.
- The flow-generated dashboard already embeds its manifest and service worker as client-side blob URLs. No server-side manifest or service-worker files should be added solely for PWA support.
- The accepted corpus is 57 FIT files and 57 activities. There are 58 open reviews: 57 `timezone_uncertain` and 1 `activity_gap`.
- The accepted verification total is 207 passed / 1 skipped. The accepted profile value is `hr_max=198`.
- The rejected premises remain excluded: 55/56/59 activity reconciliation, HR-zone distributions, `OPENCODE_INSTRUCTIONS.md`, and a 56-activity corpus.
- Authentication is not a current delivery priority for a local, single-athlete deployment. `establish-authenticated-athlete-ownership` is parked last in the backlog.
- No athlete-only decision is required for the primary task. Preserve the current port and existing data-layer interfaces unless code inspection identifies a concrete incompatibility.

---
## PRIMARY TASK
### connect-dashboard-to-data-layer

Implement the integration between `dashboard/index.html` and the tested data layer in `activities.py`, `loadcalc.py`, and `recommend.py`.

### Server implementation

Update `garmin_server.py` without removing the existing `fit-list` and `fit/<name>` routes.

Add:

```text
GET /api/activities
```

The endpoint must:

- Retrieve canonical activities through the existing interfaces in `activities.py`.
- Calculate or retrieve the existing 7-day, 14-day, and 28-day load values through `loadcalc.py`.
- Retrieve the current refusal/coaching state and supporting rationale or state metadata through `recommend.py`.
- Preserve nullability, uncertainty, and provenance from the data layer.
- Use stable identifiers and explicit field names.
- Avoid ordinal activity identifiers.
- Avoid reconstructing activity truth from dashboard arrays or raw FIT parsing.
- Avoid creating a second activity database or parallel calculation path.

A practical response shape is:

```json
{
  "activities": [],
  "loads": {
    "7d": {},
    "14d": {},
    "28d": {}
  },
  "coaching": {},
  "generated_at": "..."
}
```

Use the actual field names and nested structures exposed by the existing Python interfaces and migrations. Do not invent unsupported metrics. If the existing interfaces naturally separate activity, load, and coaching responses, use a stable linked response structure while preserving the same top-level meaning.

Return useful JSON errors when the data layer cannot be read. Error responses must have an appropriate HTTP status and must still receive CORS headers.

Add CORS handling to API responses:

```text
Access-Control-Allow-Origin: *
```

Support the methods and headers used by the dashboard. Handle required `OPTIONS` preflight requests. Apply the headers to successful responses, error responses, and preflight responses.

Change server startup so the HTTP server binds to:

```text
0.0.0.0
```

Retain the current port behavior unless code inspection shows that the startup interface requires an explicit port. Do not default to `127.0.0.1`.

### Performance implementation

`GET /api/activities` must normally complete in less than 500 ms during local use.

Implement this by:

- Reusing the canonical activity and database layer.
- Avoiding FIT parsing on every request.
- Avoiding migrations and schema discovery on every request.
- Caching or precomputing the response where appropriate.
- Invalidating cached data when the underlying activity data changes.
- Keeping the 30-second polling request lightweight.

Add a focused endpoint test or timing check that makes the less-than-500-ms requirement verifiable under normal local conditions.

### Dashboard implementation

Update the dashboard source or generation path and regenerate `dashboard/index.html` as required.

The dashboard must:

- Fetch `/api/activities` on initial load.
- Render canonical activities from the API response.
- Render 7-day, 14-day, and 28-day loads from the API response.
- Render the refusal/coaching state.
- Render available coaching rationale and state metadata.
- Stop treating the approximately 54 inline JavaScript arrays as the authoritative activity source.
- Avoid implementing separate browser-side load or coaching calculations.
- Preserve useful FIT-detail functionality where it remains available.
- Show a graceful empty state when the response contains no activities.
- Show a graceful error state when the endpoint is unavailable or malformed.
- Avoid a full-page reload when refreshing data.
- Avoid repeatedly downloading raw FIT files during API polling.

Add a server status indicator with at least these states:

- Connected and successfully refreshed.
- Temporarily unavailable.
- Invalid or incomplete API response.

The indicator must poll:

```text
/api/activities
```

every 30 seconds. Polling must not trigger a full-page reload.

### Tests and acceptance checks

Add or update tests covering:

- The `/api/activities` route.
- Canonical activity response content.
- 7-day, 14-day, and 28-day load response content.
- Refusal/coaching state and rationale metadata.
- Stable response field names and identifiers.
- CORS headers on successful responses.
- CORS headers on error responses.
- Required preflight handling.
- LAN binding configuration using `0.0.0.0`.
- Normal endpoint timing below 500 ms.
- Dashboard fetch and render behavior.
- Dashboard error and incomplete-response behavior.
- 30-second polling behavior.
- Continued operation of `fit-list` and `fit/<name>`.
- Continued operation of the blob-based manifest and service worker without new server-side PWA files.

Verify the following before marking the task complete:

- `garmin_server.py` binds to `0.0.0.0`.
- `GET /api/activities` is available.
- The response is derived from the canonical data layer.
- The response contains canonical activities, 7-day load, 14-day load, 28-day load, and refusal/coaching state.
- CORS is present on API success, API errors, and required preflight responses.
- The endpoint normally responds in less than 500 ms.
- The dashboard renders API-backed values.
- The status indicator polls every 30 seconds.
- Dashboard failures do not crash the page.
- Existing FIT routes continue to function.
- A phone can load the dashboard over home WiFi.
- The existing blob-based manifest and service worker still work.

### Athlete-facing mobile instructions to include in the dashboard DATA tab or related documentation

Tell the athlete to:

- Start `garmin_server.py` with the server bound to `0.0.0.0`.
- Find the laptop local IP address:
  - macOS: open System Settings, select Wi-Fi, select Details, and read the IP address; or run `ipconfig getifaddr en0`.
  - Windows: open Command Prompt, run `ipconfig`, and use the laptop IPv4 address.
  - Linux: run `hostname -I` or inspect the active network connection.
- Connect the phone to the same home WiFi network as the laptop.
- Open:

```text
http://<laptop-local-ip>:<port>/
```

Replace `<port>` with the port used by `garmin_server.py`.
- Install the PWA:
  - iPhone: Safari Share, then Add to Home Screen.
  - Android: browser menu, then Add to Home screen or Install app when offered.
- If the phone cannot connect, verify that both devices are on the same network and that the laptop firewall allows inbound connections on the dashboard port.

---
## PWA / MOBILE SETUP (for opencode)

- Change `garmin_server.py` startup binding to `0.0.0.0`.
- Preserve the existing port unless a compatibility issue requires an explicit port option.
- Add CORS headers to all API responses, including successful JSON responses, JSON error responses, and required `OPTIONS` preflight responses.
- Use:

```text
Access-Control-Allow-Origin: *
```

- Allow the request methods and headers required by the dashboard.
- Keep the existing FIT routes available.
- Confirm that a browser on another device connected to the same home WiFi can open the dashboard through the laptop local IP and server port.
- Confirm that `/api/activities` is reachable from the phone and returns the expected JSON.
- Confirm that the dashboard status indicator changes to connected after a successful phone request.
- Confirm that the status indicator continues polling `/api/activities` every 30 seconds.
- Confirm that temporary API failure produces an unavailable state rather than a page crash.
- Confirm that malformed or incomplete API JSON produces an invalid-response state.
- Confirm that the flow-generated dashboard already embeds the manifest and service worker as blob URLs inside the HTML.
- Do not add server-side manifest or service-worker routes solely for PWA support.
- Confirm that Add to Home Screen or Install app uses the existing blob-generated PWA assets.
- Verify firewall guidance and same-network access using a phone, not only a localhost browser.

---
## BACKLOG (ranked, do not execute until primary task is done)

rank: 1 | complete-athlete-profile-and-timezone-provenance | Complete profile and timezone provenance so activity dates and contextual calculations remain auditable without inventing timezone assignments.

rank: 2 | formalize-continuity-review-without-synthetic-activities | Define a repeatable continuity-review process using observed records only and never manufacture activities to fill gaps.

rank: 3 | capture-confirmed-strength-history | Capture confirmed strength history and provenance so future strength recommendations use athlete-confirmed information.

rank: 4 | implement-gated-weather-enrichment | Add weather enrichment only behind explicit data-availability and provenance gates, with missing weather remaining an acceptable state.

rank: 5 | make-coaching-rationales-deterministic-and-auditable | Make recommendation inputs, refusal conditions, and coaching rationales deterministic, inspectable, and testable.

rank: 6 | harden-bridge-and-release-quality-gates | Improve CI, linting, lockfile discipline, backup and restore procedures, and release checks without unsupported completion claims.

rank: 7 | document-conservative-training-signals | Document how existing conservative signals should be interpreted and what they do not establish.

rank: 8 | stabilize-running-load-before-progression | Validate running-load behavior and edge cases before using it to drive progression decisions.

rank: 9 | build-long-run-pace-durability | Develop long-run pace durability only after the running-load foundation and supporting evidence are stable.

rank: 10 | introduce-conservative-runner-strength | Introduce conservative runner-strength guidance using confirmed history and explicit progression safeguards.

rank: 11 | establish-authenticated-athlete-ownership | DEMOTED and parked last. Revisit only if deployment changes from local single-athlete access to a model requiring authenticated ownership.

---
## NEXT SUPERVISOR CHECK

connect-dashboard-to-data-layer | Verify `/api/activities`, canonical data-layer provenance, 7-day/14-day/28-day loads, refusal/coaching state, CORS behavior, less-than-500-ms normal response time, `0.0.0.0` binding, dashboard rendering, 30-second polling, FIT route compatibility, API failure handling, and phone access over home WiFi.

complete-athlete-profile-and-timezone-provenance | Do not classify or execute until the primary task is complete; verify only if it becomes the active backlog item.

formalize-continuity-review-without-synthetic-activities | Do not classify or execute until the primary task is complete; verify only if it becomes the active backlog item.

capture-confirmed-strength-history | Do not classify or execute until the primary task is complete; verify only if it becomes the active backlog item.

implement-gated-weather-enrichment | Do not classify or execute until the primary task is complete; verify only if it becomes the active backlog item.

make-coaching-rationales-deterministic-and-auditable | Do not classify or execute until the primary task is complete; verify only if it becomes the active backlog item.

harden-bridge-and-release-quality-gates | Do not classify or execute until the primary task is complete; verify only if it becomes the active backlog item.

document-conservative-training-signals | Do not classify or execute until the primary task is complete; verify only if it becomes the active backlog item.

stabilize-running-load-before-progression | Do not classify or execute until the primary task is complete; verify only if it becomes the active backlog item.

build-long-run-pace-durability | Do not classify or execute until the primary task is complete; verify only if it becomes the active backlog item.

introduce-conservative-runner-strength | Do not classify or execute until the primary task is complete; verify only if it becomes the active backlog item.

establish-authenticated-athlete-ownership | Remains demoted and parked; verify only after a deployment-model change makes authentication necessary.
