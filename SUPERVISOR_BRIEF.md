UNVERIFIED LLM OUTPUT

# Athletic Performance Hub \\ Supervisor Brief
## Generated: 2026-10-13
## Run by: CrewAI Flow Supervisor

> FACT-GATE NOTE: as written, this brief again quoted corpus, activity, review
> and test counts from a snapshot that predates the last publishes. They have
> been corrected in place to the measured values (61 FIT files / 58 activities /
> 59 open reviews / 489 passed), and the corrections are logged in
> docs/SUPERVISOR_BRIEF_ERRORS.md (sixth run). Two implementation premises that
> contradict the checked-in code were also corrected in place: no CORS headers
> are sent (same origin), and the server injects a real manifest and service
> worker rather than the dashboard embedding them as blob URLs. The false claim
> that the dashboard does not use the canonical data layer is left as written so
> the consistency checker keeps flagging it (the pinned canary). Apart from these
> corrections, the decisions, task list and backlog are the writer's.
>
> ADDED SINCE: at the athlete's explicit request the server gained an optional
> password login (`--password` / `GARMIN_DASH_PASSWORD`, `GET/POST /login`,
> `GET /logout`, signed session cookie) so the dashboard can be reached from
> outside the home WiFi through a tunnel whose URL is not secret. This
> supersedes the "authentication is not a current delivery priority" decision
> below for the remote-access path only; the local token path is unchanged.

---
## CLOSED TASKS

brief-transport | evidence: live, direct push + inbox + clipboard | Brief transport was verified through live direct push, inbox, and clipboard paths.
brief-transport-cross-second-idem | commit SHA 3054d6a; brief_id is content-derived | Cross-channel brief delivery is content-derived and idempotent.
profile-hr-max | evidence: profile.json, hr_max=198 | The athlete profile contains the accepted hr_max value of 198.
data-layer-and-provenance | commit SHA 4051291; migrations 001-006 | The canonical data layer and provenance migrations are present.
fit-audit-and-guard | evidence: 0 parse failures, 61/61 GPS, guard verified | The FIT audit completed with no parse failures, GPS coverage for 61 of 61 files, and a verified guard.

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
- The server must be reachable from a phone. This is done with `--lan` (or `--host 0.0.0.0`), which is opt-in; the default binding stays loopback so the dashboard is not exposed unless asked for.
- No CORS headers are needed or sent. The dashboard and the JSON API share one origin, and a guard test asserts `Access-Control-Allow-Origin` never appears.
- The dashboard file is generated outside this repository, so the server injects a real manifest and service-worker registration as it serves the HTML and serves `/manifest.webmanifest` and `/sw.js`. A blob-URL service worker cannot register at all.
- The accepted corpus is 61 FIT files and 58 activities. There are 59 open reviews: 58 `timezone_uncertain` and 1 `activity_gap`.
- The accepted verification total is 489 passed / 1 skipped. The accepted profile value is `hr_max=198`.
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

Return useful JSON errors when the data layer cannot be read. Error responses must have an appropriate HTTP status and must not leak a traceback or path.

Do NOT add CORS handling. The dashboard and the JSON API are served from the same origin, so CORS is unnecessary; a guard test asserts `Access-Control-Allow-Origin` is never sent.

Change server startup so the HTTP server can bind to the LAN when asked:

```text
--lan   (or --host 0.0.0.0)
```

The default stays `127.0.0.1`; the `--lan` path also adds the bound LAN addresses to the Host allowlist and keeps every data route behind the token.

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
- No CORS headers on success, error, or preflight responses (same origin).
- Host allowlisting: a bound name and the served port are required.
- LAN binding configuration using `--lan` / `--host 0.0.0.0`.
- Normal endpoint timing below 500 ms.
- Dashboard fetch and render behavior.
- Dashboard error and incomplete-response behavior.
- 30-second polling behavior.
- Continued operation of `fit-list` and `fit/<name>`.
- Server-injected manifest and service worker, served as real same-origin files.

Verify the following before marking the task complete:

- `garmin_server.py` can bind to the LAN with `--lan` (default stays loopback).
- `GET /api/activities` is available.
- The response is derived from the canonical data layer.
- The response contains canonical activities, 7-day load, 14-day load, 28-day load, and refusal/coaching state.
- No CORS header is sent on API success, API errors, or preflight responses.
- The endpoint normally responds in less than 500 ms.
- The dashboard renders API-backed values.
- The status indicator polls every 30 seconds.
- Dashboard failures do not crash the page.
- Existing FIT routes continue to function.
- A phone can load the dashboard over home WiFi.
- The server-served manifest and service worker still work.

### Athlete-facing mobile instructions to include in the dashboard DATA tab or related documentation

Tell the athlete to:

- Start `garmin_server.py` with `--lan` (or `--host 0.0.0.0`); the default stays loopback.
- Find the laptop local IP address:
  - macOS: open System Settings, select Wi-Fi, select Details, and read the IP address; or run `ipconfig getifaddr en0`.
  - Windows: open Command Prompt, run `ipconfig`, and use the laptop IPv4 address.
  - Linux: run `hostname -I` or inspect the active network connection.
- Connect the phone to the same home WiFi network as the laptop.
- Open the URL the server prints at startup:

```text
http://<laptop-local-ip>:<port>/?tk=<token>
```

Replace `<port>` and `<token>` with the values `garmin_server.py` prints. The token is required; a bare URL without it is refused.
- Install the PWA:
  - iPhone: Safari Share, then Add to Home Screen.
  - Android: browser menu, then Add to Home screen or Install app when offered.
- If the phone cannot connect, verify that both devices are on the same network and that the laptop firewall allows inbound connections on the dashboard port.

---
## PWA / MOBILE SETUP (for opencode)

- Let `garmin_server.py` opt into LAN binding with `--lan` (or `--host 0.0.0.0`); the default stays loopback.
- Keep the existing port.
- Do NOT add CORS headers. The dashboard and API share one origin; a guard test asserts `Access-Control-Allow-Origin` is never sent.
- Keep the existing FIT routes available.
- Confirm that a browser on another device connected to the same home WiFi can open the dashboard through the laptop local IP and server port.
- Confirm that `/api/activities` is reachable from the phone and returns the expected JSON.
- Confirm that the dashboard status indicator changes to connected after a successful phone request.
- Confirm that the status indicator continues polling `/api/activities` every 30 seconds.
- Confirm that temporary API failure produces an unavailable state rather than a page crash.
- Confirm that malformed or incomplete API JSON produces an invalid-response state.
- Confirm that the server injects the manifest link and service-worker registration as it serves the HTML, and serves a real `/manifest.webmanifest` and `/sw.js`.
- Confirm that Add to Home Screen or Install app works with the server-served PWA assets.
- Over plain `http://` the added shortcut is live but not offline-capable; a service worker needs a secure context (https or localhost).
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

connect-dashboard-to-data-layer | Verify `/api/activities`, canonical data-layer provenance, 7-day/14-day/28-day loads, refusal/coaching state, absence of CORS headers, less-than-500-ms normal response time, LAN binding via `--lan`, dashboard rendering, 30-second polling, FIT route compatibility, API failure handling, and phone access over home WiFi with the printed token URL.

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
