UNVERIFIED LLM OUTPUT

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-10-05
## Run by: CrewAI Flow Supervisor

---
## CLOSED TASKS

brief-transport | evidence: closed; live direct push, inbox, and clipboard | Transport paths are established and must not be reopened.

brief-transport-cross-second-idem | commit 3054d6a | `brief_id` is content-derived and the task is closed.

profile-hr-max | evidence: closed; `profile.json` establishes `hr_max=198` | The accepted maximum heart rate is 198.

data-layer-and-provenance | commit 4051291 | Migrations `001-006` establish the data layer and provenance foundation.

fit-audit-and-guard | commit 0; evidence: zero parse failures and `57/57` GPS coverage | The FIT audit and guard are closed.

---
## VERIFICATION (open tasks from previous brief)

No previous open task slug can be classified from direct evidence in this run. Retrieval of `SUPERVISOR_BRIEF.md`, `docs/IMPLEMENTATION_INVENTORY.md`, and `docs/VERIFICATION_REPORT.md` failed through the available fetch tool. No completion, in-progress, blocked, or fabricated-premise status is asserted for an unverified previous task.

Standing verification facts supplied for this run:

standing-corpus | accepted | 57 FIT files and 57 activities are the accepted corpus.

open-review-state | accepted | 58 open reviews: 57 `timezone_uncertain` and 1 `activity_gap`.

test-state | accepted | 207 passed and 1 skipped.

profile-state | accepted | `hr_max=198`.

---
## SUPERVISOR DECISIONS

- The primary task is `connect-dashboard-to-data-layer`. The dashboard/data-layer gap is the highest-priority implementation issue.
- `dashboard/index.html` is the primary UI. It is a 954 KB gitignored file served locally by `garmin_server.py`.
- The current dashboard reads raw FIT files through `fit-list` and `fit/<name>` and still relies on inline JavaScript arrays for displayed training data.
- The dashboard has no references to `garmin_export.csv`, `trainloop.db`, or the new services. The tested modules `activities.py`, `loadcalc.py`, and `recommend.py`, together with migrations `001-006`, are real but are not connected to normal dashboard rendering.
- The existing FIT routes must remain available for diagnostics and compatibility, but they must no longer be the primary source for dashboard activity, load, or coaching views.
- The dashboard must consume canonical activities from `activities.py`, canonical 7-, 14-, and 28-day loads from `loadcalc.py`, and coaching or refusal state from `recommend.py`.
- Missing, refused, or unavailable data must be represented explicitly. The UI must not turn unavailable values into zero, stale inline values, or a normal recommendation.
- The accepted corpus remains 57 FIT files and 57 activities. Do not introduce reconciliation claims involving 55, 56, or 59 activities.
- The accepted review state is 58 open reviews: 57 `timezone_uncertain` and 1 `activity_gap`. Review and provenance state should be visible where it affects interpretation.
- `hr_max=198` is established by `profile.json`. Do not add HR-zone distribution work to this brief.
- The verification report could not be fetched from the requested GitHub API files. Therefore, no additional task status or completion claim is made beyond the supplied closed-task evidence and standing facts.
- Authentication is intentionally demoted. This is a local, single-athlete, single-user system, so authenticated ownership is not required for the primary integration.

---
## PRIMARY TASK
### connect-dashboard-to-data-layer

Implement the dashboard integration through the existing localhost server. Do not add a new service, framework, authentication layer, or replacement server.

### Server inspection

1. Inspect `garmin_server.py` and locate the existing `fit-list` and `fit/<name>` routes.
2. Inspect the callable interfaces and return values exposed by:
   - `activities.py`
   - `loadcalc.py`
   - `recommend.py`
3. Preserve the existing FIT routes for compatibility and diagnostics.
4. Reuse the existing data-layer functions and definitions. Do not duplicate load calculations or recommendation logic inside the server or dashboard.

### Required server routes

Add JSON routes to `garmin_server.py` backed by the canonical data layer.

#### `GET /api/activities`

Return canonical activities from `activities.py`.

Each activity object should include, when available from the existing data-layer interface:

- A stable activity identifier.
- Activity timestamp or date in a consistent serialized format.
- Activity type.
- Relevant distance, duration, and load fields.
- Provenance information.
- Review state, including relevant refusal or uncertainty information.
- Explicit availability state for fields that cannot be computed.

Do not synthesize missing activities, infer unsupported classifications, or create a fabricated activity corpus.

#### `GET /api/load`

Return canonical load values produced by `loadcalc.py` for:

- 7 days
- 14 days
- 28 days

The response must:

- Use the existing load definitions and date handling.
- Distinguish valid, unavailable, and refused values.
- Include provenance or reason information when a value is unavailable or conservative.
- Avoid representing unavailable data as numeric zero.
- Avoid adding HR-zone distributions or unsupported metrics.

#### `GET /api/coaching`

Return coaching and recommendation state produced by `recommend.py`.

The response must:

- Preserve the data layer's recommendation state.
- Include refusal state and refusal reasons.
- Include conservative fallback state when the data layer declines to recommend.
- Serialize unavailable inputs explicitly.
- Never silently convert a refusal into a normal recommendation.

#### Optional `GET /api/dashboard`

If useful for reducing duplicate requests, add a composed endpoint that returns:

- `activities`
- `load`
- `coaching`
- shared provenance and review information
- structured error or availability information

The composed endpoint must call the existing modules and must not duplicate their calculations. It must contain the same canonical values as the individual routes.

### JSON and error contract

Use stable identifiers for activities and API resources. Do not use ordinal positions as identifiers.

Use one consistent serialization format for dates and timestamps. Prefer the format already used by the repository's data layer. Document the selected format in code or tests.

Return structured JSON errors for unavailable or malformed data. Do not return fabricated empty values. At minimum, distinguish:

- Valid data
- Unavailable data
- Refused data
- Internal or malformed-data errors

Preserve enough provenance and review information for the dashboard to explain why a value is unavailable, uncertain, or conservative.

Do not add fields or calculations based on rejected premises, including:

- 55, 56, or 59 activity reconciliation
- HR-zone distributions
- `OPENCODE_INSTRUCTIONS.md`
- A fabricated 56-activity corpus

### Dashboard integration

Modify `dashboard/index.html` with a small existing-style JavaScript loading layer using `fetch`.

1. Identify every inline array currently used for:
   - Activity display
   - Load display
   - Coaching or recommendation display
2. Add one normalized client-side response model for the API data.
3. Replace relevant inline-array consumers with API-backed consumers.
4. Use `/api/activities`, `/api/load`, and `/api/coaching`, or use `/api/dashboard` if that composed endpoint is implemented.
5. Ensure normal production rendering uses the data-layer response.
6. Remove only inline arrays that are no longer referenced. Do not perform an unrelated dashboard rewrite.
7. Keep the raw FIT display available where it remains useful for detail or diagnostics.
8. Do not silently fall back to stale inline arrays when an API request fails.

Render the following:

- The canonical activity list and its summary.
- The canonical 7-day load.
- The canonical 14-day load.
- The canonical 28-day load.
- Coaching state from `recommend.py`.
- Refusal reasons and conservative fallback state.
- Relevant provenance.
- Relevant review state, including timezone uncertainty or activity-gap review where supplied by the data layer.

Add explicit UI states for:

- Loading
- No available data
- Refused or conservative result
- Server error
- Malformed response

The UI must not display missing data as zero or display a refused recommendation as valid coaching.

### Compatibility and transition rules

- Preserve `fit-list` and `fit/<name>`.
- Do not make raw FIT responses an implicit API fallback for dashboard summary data.
- Do not retain stale inline data as a silent fallback.
- A temporary development-only console warning is acceptable during migration, but normal rendering must use the canonical API.
- Keep the implementation local to the existing server and dashboard unless the repository's existing structure requires a small supporting module.

### Tests

Add or extend Python tests covering each new route.

Cover:

- Valid canonical activity data.
- Valid 7-, 14-, and 28-day load data.
- Valid coaching data.
- Refused coaching data.
- Unavailable load data.
- Unavailable activity data.
- Malformed or internal data-layer errors.
- Stable JSON field and identifier behavior.
- Preservation of existing FIT endpoint behavior.

Add an integration check that exercises or starts `garmin_server.py` and verifies the expected JSON shape.

Add a dashboard-side check, using mocked API responses if the existing test setup supports it, that verifies the dashboard renders from API responses rather than old inline arrays.

Run the existing test suite and preserve the standing verification state of 207 passed / 1 skipped unless repository evidence shows an intentional, explained change.

Manually verify the dashboard at its normal localhost URL. Confirm that:

- Activities load from the canonical API.
- Load cards show 7-, 14-, and 28-day values or explicit availability states.
- Coaching refusal and review messaging are visible.
- Server failures are visible and are not represented as valid data.
- Raw FIT diagnostics remain available.
- No rejected premise is introduced.

### Athlete decision

**Should the dashboard make a hard cutover to the canonical API immediately, or should it retain a temporary raw-FIT/inline-array fallback if an API request fails?**

Recommended decision: hard cutover for normal rendering, with an explicit error or refusal state instead of silently falling back to stale inline data. Existing FIT endpoints remain available for diagnostics without acting as an implicit dashboard fallback.

---
## BACKLOG (ranked, do not execute until primary task is done)

rank: 1 | complete-athlete-profile-and-timezone-provenance | Complete profile and timezone provenance so activity timestamps and downstream calculations can be interpreted consistently.

rank: 2 | formalize-continuity-review-without-synthetic-activities | Make continuity and activity-gap review explicit without inventing activities or filling gaps with synthetic records.

rank: 3 | capture-confirmed-strength-history | Record only athlete-confirmed strength history so future recommendations have reliable context.

rank: 4 | implement-gated-weather-enrichment | Add weather data only behind explicit availability, provenance, and quality gates.

rank: 5 | make-coaching-rationales-deterministic-and-auditable | Ensure each coaching outcome and refusal can be reproduced from recorded inputs and rules.

rank: 6 | harden-bridge-and-release-quality-gates | Improve CI, linting, lockfile discipline, backup and restore procedures, and release checks without expanding product scope.

rank: 7 | document-conservative-training-signals | Document how current signals should be interpreted conservatively, including their limitations and refusal conditions.

rank: 8 | stabilize-running-load-before-progression | Validate and stabilize the existing running-load calculations before using them to drive progression decisions.

rank: 9 | build-long-run-pace-durability | Add a conservative, evidence-based view of long-run pace durability once the underlying load and activity signals are stable.

rank: 10 | introduce-conservative-runner-strength | Add conservative runner-strength guidance only after confirmed history and supporting training signals are available.

rank: 11 | establish-authenticated-athlete-ownership | Authentication and athlete ownership remain intentionally demoted. Reconsider only when a second athlete or multi-user deployment exists.

---
## NEXT SUPERVISOR CHECK

connect-dashboard-to-data-layer | Verify that `garmin_server.py` exposes the canonical activity, load, and coaching JSON routes; verify that `dashboard/index.html` renders from those routes; verify explicit loading, unavailable, refusal, review, provenance, and server-error states; verify existing FIT routes remain intact; verify tests and the local dashboard path.

No backlog task is to be executed until `connect-dashboard-to-data-layer` is verified complete.
