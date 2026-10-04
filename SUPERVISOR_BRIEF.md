UNVERIFIED LLM OUTPUT

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-10-04
## Run by: CrewAI Flow Supervisor

---
## CLOSED TASKS

`brief-transport` | Evidence: previous brief states live direct push, inbox, and clipboard transport | Transport is complete and must not be reopened.

`brief-transport-cross-second-idem` | Commit `3054d6a` | Cross-second idempotency is fixed and verified.

`profile-hr-max` | Evidence: `profile.json` contains `hr_max=198` | The authoritative maximum heart rate is complete.

`data-layer-and-provenance` | Commit `4051291`; migrations `001` through `006` applied; pending migrations: none | Canonical data, provenance, review, audit, load, and recommendation components are implemented.

`fit-audit-and-guard` | Evidence: 0 parse failures, 57/57 FIT files accepted, GPS guard verified | FIT audit and guard work is closed. Do not reopen it because of conflicting later corpus claims.

---
## VERIFICATION (open tasks from previous brief)

`establish-athlete-ownership-and-consent-boundary` | BLOCKED / DEMOTED | Direct evidence states there is no authentication or multi-athlete separation; the current system is explicitly single-subject, local, and single-user.

`complete-athlete-profile-and-timezone-provenance` | IN PROGRESS | `profile.json` has `hr_max=198`, while `age`, `sex`, `resting_hr`, `weight_lb`, and `height_in` remain `null`; 57 `timezone_uncertain` reviews remain open.

`formalize-continuity-review-without-synthetic-activities` | IN PROGRESS | One `activity_gap` review remains open for the 2026-06-26 to 2026-07-05 gap; no evidence supports creating synthetic activity or load records.

`capture-confirmed-strength-history` | IN PROGRESS | There are 0 confirmed strength sessions; `strength_load` is `null`, which is not equivalent to zero.

`implement-gated-weather-enrichment` | IN PROGRESS | `weather.py` has a gate, but no coordinates are stored and no provider-backed observations are evidenced.

`make-coaching-rationales-deterministic-and-auditable` | IN PROGRESS | `recommend.py` provides six control states and refusal-first behavior, but deterministic fixtures and complete rationale snapshots are not evidenced.

`stabilize-running-load-before-progression` | IN PROGRESS | Refusal is correctly returned while 11 activities in the relevant window have unresolved timezone reviews; broader progression fixtures and policy validation remain incomplete.

`build-long-run-pace-durability` | IN PROGRESS | Per-mile splits are unavailable, so within-run pace decay must not be claimed; distance-band guidance, route comparability, and elevation handling are not fully evidenced.

`introduce-conservative-runner-strength` | IN PROGRESS | The safety boundary is present because `strength_load` remains `null`; recommendation rules, injury gating, scheduling, and fixtures are not fully evidenced.

`harden-bridge-and-release-quality-gates` | IN PROGRESS | No linter, formatter, type checker, CI workflow, pre-commit configuration, or dependency lockfile is configured; bridge idempotency is already closed under `brief-transport-cross-second-idem`.

`document-conservative-training-signals` | IN PROGRESS | Unsupported HR-zone claims were withdrawn, but generated rationales do not yet explicitly identify all missing, provisional, derived, and refused inputs.

`connect-dashboard-to-data-layer` | IN PROGRESS - TOP PRIORITY | `dashboard/index.html` is served by `garmin_server.py` and still reads raw FIT endpoints; no evidence shows it invokes `activities.py`, `loadcalc.py`, `recommend.py`, or the migration-backed database.

---
## SUPERVISOR DECISIONS

The authoritative standing data for this run is 57 FIT files, 57 activities, 58 open reviews, 207 passed / 1 skipped, and `hr_max=198`. The 58 open reviews consist of 57 `timezone_uncertain` reviews and 1 `activity_gap` review.

Later document claims of 58 FIT files, 58 activities, 59 open reviews, and 231 passed are conflicting and are not adopted. Do not reconcile or restate those figures as current facts.

The existing dashboard is the primary user interface, but it is disconnected from the tested data layer. The data layer already contains canonical activities and provenance in `activities.py`, versioned 7/14/28-day load calculations in `loadcalc.py`, and refusal-first coaching controls in `recommend.py`. The highest-value action is therefore to connect the existing dashboard to those components through same-origin JSON routes in `garmin_server.py`.

Authentication and multi-athlete ownership are demoted because this is a local, single-athlete, single-user system. Do not add authentication as part of the primary task. Revisit ownership only when a second athlete or a real ownership boundary exists.

Unresolved reviews must remain visible in the UI. The integration must not silently resolve timezone uncertainty, close the activity gap, create synthetic activities, or turn unavailable values into zero. In particular, `strength_load=null` must remain distinct from numeric zero.

Do not create tasks based on 55/56/59 reconciliation, HR-zone distributions, `OPENCODE_INSTRUCTIONS.md`, or a 56-activity corpus. These premises are rejected and must not appear in implementation or verification work.

---
## PRIMARY TASK

### connect-dashboard-to-data-layer

Connect the existing `dashboard/index.html`, served by `garmin_server.py`, to the tested data layer. The implementation must use the existing server and modules. Do not create a new web framework, service, API server, authentication layer, or parallel FIT parser.

#### Scope and constraints

- Preserve the existing raw FIT endpoints:
  - `fit-list`
  - `fit/<name>`
- Reuse canonical data and existing calculations from:
  - `activities.py`
  - `loadcalc.py`
  - `recommend.py`
- Use the migration-backed database with migrations `001` through `006` applied.
- Do not duplicate activity parsing or load calculations in JavaScript or in `garmin_server.py`.
- Do not fabricate activity records, strength sessions, timezone resolutions, load values, HR-zone distributions, or continuity classifications.
- Preserve `null`, unavailable, unresolved, and refused states as distinct from numeric zero or affirmative results.
- Keep all routes same-origin. Do not add CORS or authentication.

#### Server changes in `garmin_server.py`

First inspect the existing request dispatch, database configuration, and public interfaces of `activities.py`, `loadcalc.py`, and `recommend.py`. Adapt to the actual function names and return structures rather than guessing or duplicating them.

Add these JSON GET routes using the existing localhost server mechanism.

##### `GET /api/activities`

Return canonical activity records from the data layer.

Each activity object should include, where available:

- Stable activity identifier.
- Activity date and time.
- Sport or activity type.
- Duration.
- Distance.
- Provenance state.
- Review state.
- Review details, including `timezone_uncertain` and `activity_gap`.
- Any existing source or FIT filename identifier needed to open raw FIT details.

The response must preserve all applicable unresolved review states. The response must not suppress the 57 `timezone_uncertain` reviews or the one `activity_gap` review. Do not create a synthetic row for the documented gap.

Use a stable response shape, for example:

```json
{
  "activities": [],
  "review_summary": {
    "open_reviews": 58,
    "timezone_uncertain": 57,
    "activity_gap": 1
  },
  "data_version": "..."
}
```

Use the repository's actual version fields where available. Do not hard-code counts as a substitute for querying the data layer.

##### `GET /api/load`

Return current load calculations from `loadcalc.py`.

The response must include:

- 7-day load.
- 14-day load.
- 28-day load.
- Calculation window boundaries.
- Load algorithm and version, including `load-1.0.0` when supplied by the existing implementation.
- Input provenance status.
- Refusal, unavailable, or uncertainty state where applicable.
- Strength load only when supported by confirmed data; preserve `strength_load=null` when no confirmed strength sessions exist.

Use a stable response shape, for example:

```json
{
  "algorithm": "load-1.0.0",
  "windows": {
    "7d": {
      "value": null,
      "start": "...",
      "end": "...",
      "status": "..."
    },
    "14d": {
      "value": null,
      "start": "...",
      "end": "...",
      "status": "..."
    },
    "28d": {
      "value": null,
      "start": "...",
      "end": "...",
      "status": "..."
    }
  },
  "strength_load": null,
  "provenance": {}
}
```

The exact fields must follow the existing data-layer contracts. Do not replace unavailable values with zero.

##### `GET /api/coaching`

Return the existing refusal-first result from `recommend.py`.

The response must include:

- Control state.
- Whether coaching is refused, limited, or available.
- Blocking conditions.
- Rationale fields supplied by the recommendation layer.
- Relevant provenance and missing-input information.
- Recommendation version or rule version when available.

When unresolved reviews or missing inputs trigger refusal, pass that refusal through to the dashboard. Do not weaken it into a normal progression recommendation.

Use a stable JSON shape rather than requiring the dashboard to parse prose, for example:

```json
{
  "state": "...",
  "refused": true,
  "blocking_conditions": [],
  "rationale": [],
  "provenance": {},
  "version": "..."
}
```

#### API behavior

- Set `Content-Type: application/json` on successful and error responses.
- Return structured JSON errors for API routes.
- Return a clear 4xx response for malformed query parameters.
- Return a clear 5xx response for unexpected server failures.
- Close database connections and cursors reliably.
- Do not leak tracebacks or sensitive filesystem details to the browser.
- Ensure API failure cannot silently fall back to stale inline dashboard data.
- Preserve compatibility with the existing raw FIT routes.

#### Dashboard changes in `dashboard/index.html`

Add a small data-loading layer that fetches all three routes from the same origin:

- `/api/activities`
- `/api/load`
- `/api/coaching`

Load the data on page load and provide a refresh action if the existing dashboard has a refresh mechanism.

Render the following.

##### Activity and review panel

- Canonical activity list from `/api/activities`.
- Stable activity identity.
- Date, sport, duration, and distance where available.
- Provenance indicator.
- Review indicator.
- Visible distinction for `timezone_uncertain`.
- Visible distinction for `activity_gap`.
- Link or control to retain access to the existing raw FIT detail view.

The review summary must make unresolved state visible. Do not imply that all activities are fully reviewed.

##### Load panel

Render separate cards for:

- 7-day load.
- 14-day load.
- 28-day load.

Each card should show:

- Numeric value when available.
- Calculation window.
- Algorithm/version.
- Provenance or status.
- A clear unavailable or uncertain label when the value is not available.

Render `null` differently from zero. Do not use old inline values when the API fails.

##### Coaching panel

Render:

- Current control state.
- Refused or limited status.
- Blocking conditions.
- Rationale and provenance details.
- Missing or unresolved inputs.

A refusal must be visually unmistakable and must not be presented as an affirmative training recommendation.

#### Inline data removal or isolation

The dashboard contains approximately 54 inline JavaScript arrays. Do not treat them as authoritative for canonical activity, load, or coaching panels.

They may remain temporarily for unrelated legacy display behavior, but:

- Canonical activity rendering must come from `/api/activities`.
- Canonical load rendering must come from `/api/load`.
- Coaching rendering must come from `/api/coaching`.
- API failure must show an explicit unavailable or error state.
- Do not silently display fabricated, stale, or hard-coded fallback values.

#### Verification requirements

Add or update focused tests for:

- `/api/activities` JSON serialization.
- `/api/load` JSON serialization.
- `/api/coaching` JSON serialization.
- Structured 4xx and 5xx API errors.
- Null handling.
- Refusal handling.
- Stable activity identifiers.
- Preservation of raw FIT endpoint behavior.
- Database resource cleanup where the project has a test seam for it.

Run the dashboard through `garmin_server.py` in a browser or equivalent local smoke test and verify:

- The page loads without JavaScript errors.
- Network requests reach all three API routes.
- Canonical activities are rendered from the API.
- 57 `timezone_uncertain` reviews remain visible.
- 1 `activity_gap` review remains visible.
- 7/14/28-day values originate from `loadcalc.py`.
- Refusal output remains visible when unresolved reviews or missing inputs trigger refusal.
- `strength_load=null` is not rendered as zero.
- API failure produces an explicit unavailable state.
- Raw FIT inspection still works.
- No alternate corpus count is introduced. The standing verification state remains 57 FIT files, 57 activities, 58 open reviews, 207 passed / 1 skipped, and `hr_max=198`.

#### Athlete decision

No athlete decision is required for this implementation. Use the existing data-layer contracts and refusal-first behavior.

---
## BACKLOG (ranked, do not execute until primary task is done)

`complete-athlete-profile-and-timezone-provenance` | Rank: next | Complete remaining profile fields and provenance workflows without changing `hr_max=198` or silently resolving the 57 timezone reviews.

`formalize-continuity-review-without-synthetic-activities` | Rank: following | Define and validate continuity classifications around the documented gap while preserving the open `activity_gap` review unless source evidence closes it.

`capture-confirmed-strength-history` | Rank: following | Add a reviewed workflow for real strength sessions and preserve `strength_load=null` until confirmed data exists.

`implement-gated-weather-enrichment` | Rank: following | Add provider-backed weather observations only behind existing consent, location, privacy, and availability gates.

`make-coaching-rationales-deterministic-and-auditable` | Rank: following | Add deterministic fixtures and complete rationale snapshots for the existing refusal-first control states.

`harden-bridge-and-release-quality-gates` | Rank: following | Add proportionate linting, formatting, tests, CI, dependency reproducibility, and backup/restore checks without reopening closed bridge idempotency work.

`document-conservative-training-signals` | Rank: following | Document measured, derived, unavailable, provisional, and refused signals while excluding rejected HR-zone claims.

`stabilize-running-load-before-progression` | Rank: following | Formalize conservative progression gates and fixtures around unresolved continuity, timezone, and profile provenance.

`build-long-run-pace-durability` | Rank: following | Provide distance-band durability guidance using available evidence and explicitly handle missing per-mile splits, route comparability, and derived elevation effects.

`introduce-conservative-runner-strength` | Rank: following | Implement strength recommendation rules, injury gating, scheduling, and fixtures without fabricating strength history or converting `strength_load=null` to zero.

`establish-athlete-ownership-and-consent-boundary` | Rank: deferred | Authentication and multi-athlete ownership remain demoted for this local single-user system and should be revisited only when a second athlete or actual ownership boundary exists.

---
## NEXT SUPERVISOR CHECK

Verify `connect-dashboard-to-data-layer` first:

- Confirm `garmin_server.py` exposes `/api/activities`, `/api/load`, and `/api/coaching`.
- Confirm the routes call the existing data-layer modules rather than duplicating calculations.
- Confirm dashboard activity, load, and coaching panels use API responses instead of inline authoritative data.
- Confirm unresolved review states remain visible: 57 `timezone_uncertain` and 1 `activity_gap`.
- Confirm `null`, unavailable, refused, and zero states render distinctly.
- Confirm raw FIT routes remain functional.
- Confirm focused tests and local browser smoke verification pass.
- Confirm standing numbers remain 57 FIT files, 57 activities, 58 open reviews, 207 passed / 1 skipped, and `hr_max=198`.

After the primary task is verified, check `complete-athlete-profile-and-timezone-provenance` as the next backlog item.
