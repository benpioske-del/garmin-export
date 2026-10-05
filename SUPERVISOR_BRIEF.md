UNVERIFIED LLM OUTPUT

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-10-05
## Run by: CrewAI Flow Supervisor

---
## CLOSED TASKS

brief-transport | Evidence from SUPERVISOR_BRIEF.md: live direct push, inbox, and clipboard transport verified; transport is complete and must not be reopened.
brief-transport-cross-second-idem | Commit 3054d6a; cross-second idempotency is fixed and verified.
profile-hr-max | Evidence confirms profile.json contains hr_max=198.
data-layer-and-provenance | Commit 4051291; migrations 001 through 006 are applied and no migrations are pending.
fit-audit-and-guard | Evidence confirms 0 parse failures, 57/57 FIT files accepted, and the GPS guard is verified.

---
## VERIFICATION (open tasks from previous brief)

establish-authenticated-athlete-ownership | BLOCKED / DEMOTED | Direct evidence states there is no authentication or multi-athlete separation; the system is intentionally local, single-subject, and single-user.
complete-athlete-profile-and-timezone-provenance | IN PROGRESS | profile.json has hr_max=198, while age, sex, resting_hr, weight_lb, and height_in remain null; 57 timezone_uncertain reviews remain open.
formalize-continuity-review-without-synthetic-activities | IN PROGRESS | One activity_gap review remains open; no evidence supports creating synthetic activity or load records.
capture-confirmed-strength-history | IN PROGRESS | There are 0 confirmed strength sessions; strength_load is null, which is not equivalent to zero.
implement-gated-weather-enrichment | IN PROGRESS | weather.py has a gate, but no coordinates or provider-backed observations are evidenced.
make-coaching-rationales-deterministic-and-auditable | IN PROGRESS | recommend.py provides six control states and refusal-first behavior, but deterministic fixtures and complete rationale snapshots are not evidenced.
stabilize-running-load-before-progression | IN PROGRESS | Refusal is correctly returned while 11 activities in the relevant window have unresolved timezone reviews; broader progression fixtures and policy validation remain incomplete.
build-long-run-pace-durability | IN PROGRESS | Per-mile splits are unavailable, so within-run pace decay must not be claimed; distance-band guidance, route comparability, and elevation handling are not fully evidenced.
introduce-conservative-runner-strength | IN PROGRESS | The safety boundary is present because strength_load remains null; recommendation rules, injury gating, scheduling, and fixtures are not fully evidenced.
harden-bridge-and-release-quality-gates | IN PROGRESS | No linter, formatter, type checker, CI workflow, pre-commit configuration, or dependency lockfile is configured; bridge idempotency is already closed.
document-conservative-training-signals | IN PROGRESS | Unsupported HR-zone claims were withdrawn, but generated rationales do not yet explicitly identify all missing, provisional, derived, and refused inputs.
connect-dashboard-to-data-layer | IN PROGRESS - TOP PRIORITY | dashboard/index.html is served by garmin_server.py but remains disconnected from the tested data layer; it has zero references to garmin_export.csv, trainloop.db, or the new services.

---
## SUPERVISOR DECISIONS

The data layer is implemented and tested. activities.py, loadcalc.py, recommend.py, and migrations 001 through 006 are real and tested, but dashboard/index.html is not using them. The primary work is therefore to connect the existing dashboard to the existing server-backed data layer.

The authoritative corpus contains 57 FIT files and 57 activities. The verification baseline is 207 passed / 1 skipped. These values must be preserved and must not be replaced with a different activity count or reconciliation premise.

There are 58 open reviews: 57 timezone_uncertain reviews and 1 activity_gap review. These reviews must remain visible in provenance and limitation state. The dashboard must not silently treat unresolved data as complete, and it must not create synthetic activities or synthetic load records to close gaps.

profile.json has hr_max=198. Other profile values remain null where they are not supported by evidence. Null values must remain distinct from zero or an inferred athlete value.

The recommendation system is refusal-first. The dashboard must render available, missing, provisional, unresolved, and refused states explicitly, including the reason for a refusal. strength_load remains null and must not be displayed as zero.

The dashboard must continue to be dashboard/index.html served by garmin_server.py. The integration must use the tested Python modules directly. No replacement service, framework, database, authentication layer, or duplicate JavaScript calculation path is authorized.

The closed slugs remain closed and must not be reopened. Authentication and athlete ownership are intentionally demoted because this remains a local, single-athlete system with no current multi-user requirement.

Rejected premises remain rejected: 55/56/59 reconciliation, HR-zone distributions, OPENCODE_INSTRUCTIONS.md, and a 56-activity corpus must not become implementation requirements or backlog tasks.

---
## PRIMARY TASK

### connect-dashboard-to-data-layer

Implement the server-backed dashboard integration without replacing the existing local workflow.

#### Scope and constraints

- Keep `dashboard/index.html` as the primary UI.
- Keep `garmin_server.py` as the local HTTP server.
- Use the existing data-layer modules:
  - `activities.py` for canonical activity data.
  - `loadcalc.py` for load calculations.
  - `recommend.py` for coaching, refusal, and recommendation state.
  - Existing provenance and review structures for uncertainty and unavailable data.
- Do not introduce a new service, web framework, database, authentication layer, or duplicate calculation path.
- Do not calculate canonical activities, load, or recommendations in JavaScript.
- Do not parse FIT files directly from the browser.
- Do not add synthetic activities, synthetic load records, HR-zone distributions, unsupported classifications, or inferred athlete profile values.

#### Inspect the existing interfaces

Before editing, inspect the public functions, data structures, and error behavior in:

- `activities.py`
- `loadcalc.py`
- `recommend.py`
- `garmin_server.py`
- `dashboard/index.html`

Reuse the existing interfaces wherever possible. If an adapter is needed, keep it in `garmin_server.py` or a small existing server-side module and make it a thin serialization layer. Do not create a second interpretation of the activity corpus.

#### Add JSON API routes to garmin_server.py

Add localhost JSON routes using the server's existing routing conventions:

- `GET /api/activities`
  - Return the canonical activity collection from `activities.py`.
  - Include the authoritative activity count and activity rows.
  - Preserve activity identifiers, timestamps, dates, sport/type, duration, distance, and other fields already exposed by the data layer.
  - Include review and provenance fields when available.
  - Preserve unresolved timezone status rather than silently normalizing it away.

- `GET /api/load`
  - Return the load values produced by `loadcalc.py`.
  - Include the 7-day, 14-day, and 28-day windows.
  - Include the calculation status and relevant provenance or limitation state.
  - Preserve null, missing, provisional, and refused values without converting them to zero.
  - Ensure unresolved reviews affect the response according to the existing load policy.

- `GET /api/coaching`
  - Return recommendation and coaching state from `recommend.py`.
  - Include the control state, recommendation status, refusal state, rationale, and input provenance.
  - Expose missing, unresolved, provisional, derived, available, and refused inputs.
  - Preserve `strength_load: null` as null.
  - Return the refusal reason when the recommendation system refuses to provide a recommendation.

Route names may follow existing local conventions if equivalent routes are already present, but the dashboard must have stable JSON endpoints with the behavior above. Responses must include an appropriate JSON content type and controlled error payloads.

#### Preserve provenance and refusal semantics

The API and UI must make limitations visible:

- The 57 `timezone_uncertain` reviews and 1 `activity_gap` review must remain represented in review or provenance state.
- Relevant recommendations must remain refused while required timezone reviews are unresolved.
- Missing profile fields must remain missing.
- `strength_load` null must remain distinct from numeric zero.
- No unresolved review may be hidden by a browser-side fallback.
- No unsupported HR-zone chart or HR-zone classification may be added.
- No synthetic activity or load record may be generated.

Use a consistent response shape where practical, for example an object containing `data`, `status`, `provenance`, `reviews`, and `errors`. Match existing project conventions when they differ. The exact shape is implementation-owned, but it must be documented in code or tests and consumed consistently by the dashboard.

#### Replace the dashboard authoritative data source

Update `dashboard/index.html` so initial loading uses the server JSON routes.

- Fetch `/api/activities`, `/api/load`, and `/api/coaching` through the same origin.
- Render API responses as the authoritative state.
- Remove the approximately 54 inline JavaScript arrays as authoritative state.
- Legacy arrays may remain only as explicitly marked fallback or debug data if removal would break compatibility; they must never override successful API responses.
- Do not allow fallback data to hide API errors or unresolved review state.
- Keep existing `fit-list` and `fit/<name>` behavior unless verification shows that a route is no longer needed.
- Ensure the page is loaded through `garmin_server.py`, not opened as a standalone file.

#### Render required dashboard state

The dashboard must render:

- The canonical activity total and activity rows from `/api/activities`.
- The 7-day load from `/api/load`.
- The 14-day load from `/api/load`.
- The 28-day load from `/api/load`.
- Review counts and relevant provenance limitations.
- Recommendation and coaching state from `/api/coaching`.
- Refused recommendations with their refusal reason.
- Missing values as missing or unavailable.
- Provisional or unresolved values with a visible status.
- Null strength data as unavailable or not recorded, never as zero.

The interface may preserve its current visual presentation, but displayed activity, load, and coaching values must originate from the API responses.

#### Add integration coverage

Add or update tests to verify:

- Each new API route returns JSON.
- Each route uses the real `activities.py`, `loadcalc.py`, and `recommend.py` data-layer behavior.
- The activities endpoint returns the standing corpus of 57 activities.
- The load endpoint returns 7-day, 14-day, and 28-day values from `loadcalc.py`.
- The coaching endpoint returns refusal state while relevant timezone reviews remain unresolved.
- Review and provenance information is preserved in serialized responses.
- `strength_load: null` is not converted to zero.
- Malformed requests return controlled JSON errors.
- Data-layer exceptions return controlled JSON errors without exposing an uncontrolled traceback to the browser.
- The dashboard consumes API data and does not use inline arrays as authoritative state.
- No second activity interpretation is introduced.
- The existing baseline remains at 207 passed / 1 skipped, or any changed result is explained with direct evidence.

Do not write tests based on rejected premises. Do not add tests for HR-zone distributions, 55/56/59 reconciliation, a 56-activity corpus, or OPENCODE_INSTRUCTIONS.md.

#### Validate through the local workflow

Run the existing test command and record the result. Then:

1. Start `garmin_server.py`.
2. Fetch `/api/activities` with a local HTTP client.
3. Fetch `/api/load` with a local HTTP client.
4. Fetch `/api/coaching` with a local HTTP client.
5. Confirm each response is valid JSON and contains the required provenance and status fields.
6. Load `dashboard/index.html` through the local server.
7. Confirm the browser console has no data-loading errors.
8. Confirm the activity table, load values, review state, and coaching state are API-backed.
9. Confirm refused recommendations and null strength data are rendered correctly.
10. Confirm legacy inline arrays do not override API responses.
11. Confirm the existing `fit-list` and `fit/<name>` compatibility behavior remains intact.
12. Report the final test result and the routes verified.

No athlete-only decision is required for this implementation. Endpoint naming and response serialization should be chosen consistently by the implementation while preserving the existing dashboard presentation.

---
## BACKLOG (ranked, do not execute until primary task is done)

rank: high | complete-athlete-profile-and-timezone-provenance | Complete supported profile fields and resolve or document the 57 timezone-uncertain reviews without inventing athlete data.

rank: high | formalize-continuity-review-without-synthetic-activities | Resolve the remaining activity-gap review using evidence and continuity documentation, never by creating synthetic activities or load records.

rank: medium | capture-confirmed-strength-history | Add only athlete-confirmed strength sessions so null strength load remains distinct from zero.

rank: medium | implement-gated-weather-enrichment | Use weather enrichment only when coordinates, provider observations, and the existing gate are available and auditable.

rank: medium | make-coaching-rationales-deterministic-and-auditable | Add deterministic fixtures and complete rationale snapshots for the existing refusal-first coaching states.

rank: medium | harden-bridge-and-release-quality-gates | Add appropriate CI, linting, formatting, dependency, and backup/restore safeguards while leaving closed bridge idempotency work closed.

rank: medium | document-conservative-training-signals | Document missing, provisional, derived, available, and refused inputs without introducing unsupported HR-zone claims.

rank: medium | stabilize-running-load-before-progression | Complete running-load policy validation and fixtures while preserving refusal during unresolved timezone conditions.

rank: low | build-long-run-pace-durability | Establish evidence-based distance-band and route-comparable guidance without claiming within-run pace decay where per-mile splits are unavailable.

rank: low | introduce-conservative-runner-strength | Define strength recommendation rules, injury gating, scheduling, and fixtures only after the null-strength safety boundary is preserved.

rank: demoted-last | establish-authenticated-athlete-ownership | Defer authentication and athlete ownership until a second athlete or multi-user requirement exists; the current system remains local and single-athlete.

---
## NEXT SUPERVISOR CHECK

connect-dashboard-to-data-layer | Verify that `garmin_server.py` serves the new JSON routes, that dashboard/index.html consumes them as its authoritative source, that 57 activities are rendered from the data layer, that 7-day, 14-day, and 28-day loads are server-backed, that unresolved reviews and refusal state remain visible, that null strength data is not rendered as zero, and that the test baseline is 207 passed / 1 skipped or has a directly documented variance.

complete-athlete-profile-and-timezone-provenance | Recheck supported profile fields and the count and provenance of the 57 timezone_uncertain reviews.

formalize-continuity-review-without-synthetic-activities | Recheck the remaining activity_gap review and confirm no synthetic activity or load record was introduced.

capture-confirmed-strength-history | Recheck whether any strength session is athlete-confirmed and ensure null remains distinct from zero.

implement-gated-weather-enrichment | Recheck coordinates, provider-backed observations, and weather gate behavior.

make-coaching-rationales-deterministic-and-auditable | Recheck deterministic fixtures, rationale snapshots, and refusal-first behavior.

stabilize-running-load-before-progression | Recheck timezone review gating, running-load fixtures, and progression refusal behavior.

build-long-run-pace-durability | Recheck evidence for distance-band guidance and confirm no unsupported within-run pace decay claim.

introduce-conservative-runner-strength | Recheck strength safety boundaries, recommendation rules, injury gating, and fixtures.

harden-bridge-and-release-quality-gates | Recheck quality-gate configuration while preserving the closed bridge idempotency evidence.

document-conservative-training-signals | Recheck that generated rationales identify missing, provisional, derived, available, and refused inputs without adding HR-zone claims.

establish-authenticated-athlete-ownership | Recheck that authentication remains demoted and is not treated as a prerequisite for dashboard integration.
