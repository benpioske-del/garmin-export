UNVERIFIED LLM OUTPUT

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-10-04
## Run by: CrewAI Flow Supervisor

---
## CLOSED TASKS

brief-transport | Live direct push, inbox, and clipboard transport verified. Transport is complete and must not be reopened.

brief-transport-cross-second-idem | Commit 3054d6a. Cross-second idempotency is fixed and verified.

profile-hr-max | Evidence confirms profile.json contains hr_max=198.

data-layer-and-provenance | Commit 4051291. Migrations 001 through 006 are applied and no migrations are pending.

fit-audit-and-guard | Evidence confirms 0 parse failures, 57/57 FIT files accepted, and the GPS guard is verified.

---
## VERIFICATION (open tasks from previous brief)

establish-authenticated-athlete-ownership | BLOCKED / DEMOTED | Direct evidence states that there is no authentication or multi-athlete separation; the system is intentionally local, single-subject, and single-user.

complete-athlete-profile-and-timezone-provenance | IN PROGRESS | profile.json has hr_max=198, while age, sex, resting_hr, weight_lb, and height_in remain null; 57 timezone_uncertain reviews remain open.

formalize-continuity-review-without-synthetic-activities | IN PROGRESS | One activity_gap review remains open for the 2026-06-26 to 2026-07-05 gap; no evidence supports creating synthetic activity or load records.

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

The authoritative standing facts for this run are 57 FIT files, 57 activities, 58 open reviews, 207 passed / 1 skipped, and hr_max=198. The open reviews comprise 57 timezone_uncertain reviews and 1 activity_gap review.

The five closed slugs remain closed and must not be reopened. Their evidence is listed above. In particular, profile-hr-max is complete because hr_max=198 is present, and data-layer-and-provenance is complete because migrations 001 through 006 are applied with none pending.

The primary defect is integration, not absence of implementation. activities.py, loadcalc.py, recommend.py, and migrations 001 through 006 are real and tested, but the primary dashboard is not using them. The dashboard continues to rely on raw FIT paths or inline data rather than migration-backed canonical responses.

The primary task is therefore connect-dashboard-to-data-layer. It must connect the existing dashboard to the existing server and data-layer modules without introducing a replacement service, framework, authentication layer, or duplicate calculation path.

Authentication is intentionally demoted. This is a local, single-user, single-athlete system, and no second-athlete or non-local deployment requirement is evidenced.

The 57 timezone_uncertain reviews and the single activity_gap review must remain visible. No synthetic activities, synthetic load records, HR-zone distributions, or unsupported continuity claims may be introduced.

The following premises are rejected and must not become tasks or implementation requirements:

- 55/56/59 activity reconciliation
- HR-zone distributions
- OPENCODE_INSTRUCTIONS.md
- A 56-activity corpus

The dashboard integration may preserve raw FIT display routes, but raw FIT routes must not remain the authoritative source for the new canonical activity, load, or coaching panels.

---
## PRIMARY TASK
### connect-dashboard-to-data-layer

Connect dashboard/index.html to the existing tested data layer through garmin_server.py. Do not create a new service, framework, authentication layer, database, or replacement UI.

#### Required inspection

Before editing, inspect:

- garmin_server.py route registration, request parsing, response helpers, and error conventions.
- The callable interfaces and return structures in activities.py, loadcalc.py, and recommend.py.
- The migration-backed persistence interfaces used by the existing data layer.
- dashboard/index.html to identify inline arrays, raw FIT fetches, and the panels that represent activities, load, and coaching.

Use the actual module interfaces found in the repository. Do not invent function names or duplicate calculations in the server or browser.

#### Required server routes

Add same-origin JSON routes to garmin_server.py:

##### GET /api/activities

- Call the existing activities.py data-layer interface.
- Read canonical activity records from the migration-backed data source.
- Do not rebuild the activity list from raw FIT files in the route.
- Preserve activity provenance, review status, timezone status, and any other status fields returned by the data layer.
- Return a stable JSON response using the server's existing response conventions.
- Preserve the authoritative 57-activity corpus without adding synthetic records.

##### GET /api/load

- Call loadcalc.py for the requested load windows.
- Support 7-day, 14-day, and 28-day windows through a query parameter or one stable response containing all three windows.
- Prefer a stable response containing all three windows if that matches the existing module interface and avoids repeated requests.
- Return calculated values together with availability, refusal, provenance, and review metadata supplied by the data layer.
- Do not convert null, unavailable, or refused values into numeric zero.
- Preserve strength_load as null when no confirmed strength history exists.
- Do not calculate or expose HR-zone distributions.

Malformed window parameters must produce a clear client error response. Internal data-layer failures must produce a controlled JSON error without a normal browser stack trace.

##### GET /api/coaching

- Call recommend.py directly.
- Return the current coaching or refusal state, rationale, blocking conditions, and relevant provenance and review fields exposed by the module.
- Preserve all distinctions between available, provisional, unavailable, refused, null, and numeric zero.
- Ensure unresolved timezone reviews can remain visible in the response and can block recommendations where the existing policy requires refusal.
- Do not add unsupported coaching claims or fabricate strength, weather, continuity, or HR-zone inputs.

#### Route behavior and failure handling

- Reuse existing server routing and JSON serialization conventions.
- Do not silently fall back to raw FIT calculations when a canonical data-layer call fails.
- Return appropriate status codes for malformed requests and internal failures.
- Keep error bodies machine-readable and safe for browser display.
- Do not expose Python stack traces in normal API responses.
- Keep existing raw FIT routes, including fit-list and fit/<name>, functional.

#### Required dashboard changes

Update dashboard/index.html to make same-origin fetch requests to the new routes:

- Fetch /api/activities for the canonical activity list.
- Fetch /api/load for 7-day, 14-day, and 28-day load state.
- Fetch /api/coaching for the current coaching or refusal state.

Render the API responses in the relevant dashboard panels:

- Show canonical activities from the activities response.
- Show 7-day, 14-day, and 28-day load values or their explicit unavailable/refused states.
- Show coaching status, rationale, and blocking conditions.
- Show review and provenance indicators where the API provides them.
- Keep null visibly distinct from zero.
- Keep unavailable visibly distinct from refused.
- Keep provisional and derived states visibly distinct from confirmed values.
- Keep the 57 timezone_uncertain reviews and the one activity_gap review visible through the activity or coaching status.
- Preserve strength_load as null rather than displaying it as zero.
- Do not claim a synthetic activity for the activity gap.
- Do not introduce HR-zone displays.

Remove or disable affected inline arrays as authoritative sources. Inline data may remain only for unrelated UI behavior or temporary loading and empty states. The canonical activity, load, and coaching panels must be populated from API responses.

Keep unrelated dashboard behavior intact. Existing raw FIT display paths may remain available as supporting views, but the new canonical panels must not depend on those raw endpoints.

#### Tests and verification

Add focused tests that verify:

- /api/activities returns the canonical activity response.
- /api/load supports 7-day, 14-day, and 28-day requests.
- /api/coaching returns the current coaching or refusal response.
- Malformed load parameters produce a controlled client error.
- Data-layer refusal states are returned without coercion.
- Unavailable values remain unavailable.
- null remains distinct from numeric zero.
- strength_load remains null when no confirmed strength history exists.
- Each route invokes the corresponding existing data-layer module.
- The routes do not duplicate load or recommendation calculations.
- Raw fit-list and fit/<name> routes still work.

Run the existing test suite. The standing target is 207 passed / 1 skipped unless an implementation change legitimately changes the count. Report any changed count and explain the cause.

Perform a localhost browser smoke test against dashboard/index.html. Verify through the browser network panel or equivalent evidence that:

- The dashboard requests /api/activities.
- The dashboard requests /api/load.
- The dashboard requests /api/coaching.
- The rendered canonical panels use returned API data rather than inline authoritative arrays.
- Refused, unavailable, null, zero, and review states render distinctly.
- Raw FIT display paths continue to work.

#### Completion criteria

Do not mark this task complete until all of the following are directly evidenced:

- garmin_server.py exposes /api/activities, /api/load, and /api/coaching.
- The routes call activities.py, loadcalc.py, and recommend.py.
- dashboard/index.html fetches and renders the three API surfaces.
- Inline authoritative activity, load, and coaching data is removed or disabled.
- Review, provenance, refusal, unavailable, null, and zero semantics are preserved.
- Raw FIT routes remain functional.
- Focused tests pass.
- The existing suite is run and its result is recorded.
- Local browser smoke verification confirms API-backed rendering.
- No synthetic activities, unsupported metrics, HR-zone classifications, or rejected corpus premises are introduced.

No athlete decision is required. Endpoint shape, response wrapping, and the transition away from inline authoritative arrays are engineering decisions to be made from the existing module and server conventions. No question should be sent to the athlete for this task.

---
## BACKLOG (ranked, do not execute until primary task is done)

Rank: high | complete-athlete-profile-and-timezone-provenance | Resolve remaining profile fields and document timezone provenance without weakening conservative refusal behavior; do not reopen profile-hr-max.

Rank: high | formalize-continuity-review-without-synthetic-activities | Manage the remaining activity-gap review while retaining the prohibition on synthetic activities and synthetic load records.

Rank: medium-high | capture-confirmed-strength-history | Add a safe path for recording confirmed strength sessions while preserving strength_load=null when no confirmed history exists.

Rank: medium-high | implement-gated-weather-enrichment | Complete weather enrichment only when coordinates, provider behavior, provenance, and failure handling are evidenced.

Rank: medium | make-coaching-rationales-deterministic-and-auditable | Add deterministic fixtures and rationale snapshots for recommend.py, including explicit missing, provisional, derived, unavailable, and refused inputs.

Rank: medium | harden-bridge-and-release-quality-gates | Add CI, linting, formatting, type checks, dependency locking, and backup/restore verification without reopening closed bridge idempotency work.

Rank: medium | document-conservative-training-signals | Document current training signals, refusal behavior, and missing-input handling without introducing HR-zone distributions.

Rank: medium-low | stabilize-running-load-before-progression | Complete broader load and progression validation after the dashboard exposes canonical load and refusal states; retain refusal when unresolved timezone reviews make a window unreliable.

Rank: low | build-long-run-pace-durability | Develop only from evidenced distance-band, route, elevation, and split data; do not claim within-run pace decay without per-mile splits.

Rank: low | introduce-conservative-runner-strength | Add strength recommendations only with explicit safety, injury, scheduling, and data-availability gates; do not fabricate strength load.

Demoted | establish-authenticated-athlete-ownership | Authentication and multi-athlete ownership are not current priorities for this local, single-user, single-athlete system. Reconsider only if a second athlete or non-local deployment requirement is introduced.

---
## NEXT SUPERVISOR CHECK

connect-dashboard-to-data-layer | Verify that garmin_server.py exposes the three API routes, each route invokes the existing data-layer module, dashboard/index.html fetches and renders those responses, review and null/refused semantics are preserved, raw FIT routes still work, focused tests pass, the standing suite result is recorded, and localhost browser smoke evidence confirms API-backed rendering.

complete-athlete-profile-and-timezone-provenance | Verify whether unresolved profile fields and the 57 timezone_uncertain reviews have been documented or resolved without weakening refusal behavior.

formalize-continuity-review-without-synthetic-activities | Verify the single activity_gap review remains honestly represented and that no synthetic activity or load record was created.

capture-confirmed-strength-history | Verify any recorded strength sessions are confirmed and that missing strength history remains null rather than zero.

implement-gated-weather-enrichment | Verify provider-backed weather observations have coordinates, provenance, and failure handling before any enrichment is treated as available.

make-coaching-rationales-deterministic-and-auditable | Verify deterministic fixtures and rationale snapshots cover available, provisional, unavailable, refused, and missing-input states.

stabilize-running-load-before-progression | Verify load and progression policies remain conservative while unresolved timezone reviews affect the relevant window.

build-long-run-pace-durability | Verify no unsupported within-run pace-decay claim is made without per-mile splits.

introduce-conservative-runner-strength | Verify recommendations preserve safety gates and do not convert absent strength history into zero.

harden-bridge-and-release-quality-gates | Verify release-quality tooling, dependency locking, and backup/restore evidence are present without reopening closed transport work.

document-conservative-training-signals | Verify documentation identifies missing, provisional, derived, unavailable, and refused inputs and contains no HR-zone distribution claims.
