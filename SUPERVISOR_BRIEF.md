THIS IS UNVERIFIED LLM OUTPUT — review before acting.

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-09-30
## Run by: CrewAI Flow Supervisor

---

## VERIFICATION (from previous brief)

1. **Inspect the repository and document the existing architecture — IN PROGRESS / UNVERIFIED.** `docs/IMPLEMENTATION_INVENTORY.md` was referenced but its contents and repository architecture were not provided.

2. **Implement canonical activity records with provenance and data-quality status — UNVERIFIED.** No schema, migration, import implementation, tests, or output confirmed the required timestamp, provenance, deduplication, or data-quality fields.

3. **Add a data-completeness and athlete-confirmation workflow — UNVERIFIED.** No frontend, API, service, audit history, or tests confirmed confirmation of calendar gaps, duplicates, or timestamp discrepancies.

4. **Inspect FIT files for GPS and preserve raw activity data — UNVERIFIED.** No FIT inventory, parser output, GPS inspection, timestamp inspection, or raw-file preservation evidence was supplied.

5. **Add strength-session logging and import structures — UNVERIFIED.** No strength schema, migration, API, UI, CLI, documentation, or tests were supplied.

6. **Add consent-based health and recovery inputs without medical claims — UNVERIFIED.** No consent model, privacy controls, access controls, audit trail, or safety documentation was supplied.

7. **Implement versioned, explainable training-load calculations — UNVERIFIED.** No calculation service, stored outputs, contributing-record explanations, versioning, fixtures, or tests were supplied.

8. **Add provisional training-control recommendations with safety boundaries — UNVERIFIED.** No recommendation service, rules documentation, UI output, safety checks, or tests were supplied.

9. **Build the weather-enrichment pipeline only after location validation — BLOCKED / UNVERIFIED.** No confirmed activity locations, GPS results, weather provider integration, matched observations, or location-request workflow were supplied.

10. **Add weather-aware analysis with uncertainty safeguards — BLOCKED / UNVERIFIED.** No matched weather/activity observations, thresholds, confidence indicators, or insufficient-data safeguards were supplied.

11. **Add provisional HR-zone and data-quality labeling throughout the product — UNVERIFIED.** No product output, source changes, terminology documentation, or tests confirmed consistent provisional and missing-data labels.

12. **Run the full verification suite and produce an implementation status report — UNVERIFIED.** No `docs/VERIFICATION_REPORT.md`, test logs, build output, migration checks, import validation, or security results were supplied.

---

## SUPERVISOR DECISIONS

The previous verification report confirms only that `SUPERVISOR_BRIEF.md` was readable. It does not verify that the requested implementation exists. Opencode must inspect the repository and collect evidence before treating any feature as complete.

The implementation order is:

1. Establish a canonical data and provenance foundation.
2. Make missing, assumed, inferred, and athlete-confirmed data explicit.
3. Add run–lift logging and explainable, versioned load calculations.
4. Add conservative training-control recommendations.
5. Inspect FIT files and validate whether GPS and reliable timestamps are available.
6. Add weather enrichment only when timestamp and location requirements are satisfied.
7. Add consent-based health and recovery inputs only with privacy and safety controls.
8. Run the full verification suite and document both completed work and blockers.

The running dataset is adequate for **provisional running coaching**, but it is not sufficient for reliable weather-adjusted prediction, strength assessment, injury-risk modeling, or medical-record integration.

The following data limitations must be preserved rather than silently corrected:

- Activity timestamps may use assumed UTC and local dates derived from filenames.
- One activity has a material discrepancy: filename/local date of 26 July 2026 versus recorded UTC date of 27 July 2026.
- Zero imported lifting sessions means **“no lifting data supplied”**, not necessarily that no lifting occurred.
- Heart-rate zone output is not physiologically validated because zone boundaries and calibration are unknown.
- Weather fields are absent from the supplied CSV.
- GPS availability is unknown until raw FIT files are inspected.
- Weather must not be matched using an assumed city, default location, or fabricated coordinate.
- Terrain, elevation, route, fatigue, effort, and weather must remain separate explanatory factors.

The athlete-facing coaching strategy should remain conservative:

- Use descriptive 7-, 14-, and 28-day running trends instead of presenting ACWR as a definitive injury-risk score.
- Use a provisional four-week running stabilization block of approximately 14–16, 16–18, 18–20, and 14–16 miles.
- Keep long runs approximately 7, 8–9, 9–10, and 7–8 miles across those weeks.
- Do not increase mileage, elevation, and intensity simultaneously.
- Introduce two conservative strength sessions per week only after providing a strength logging workflow.
- Use non-diagnostic safety language and escalate persistent or concerning symptoms to an appropriate clinician.
- Make Week 1 all easy by default, with optional relaxed strides only when pain-free and recovered; do not prescribe a formal workout immediately after a high-volume or fatiguing week.

No medical records should be ingested until consent, access control, audit, retention, deletion, encryption, and legal/privacy boundaries are explicitly implemented and verified.

---

## OPENCODE TASKS

### 1. Inspect the repository and create an evidence-based implementation inventory

**What to do**

Inspect the repository from the current checkout without assuming that any prior task is complete. Identify:

- Application type, framework, package manager, and runtime versions
- Source directories and entry points
- Database schema, migrations, seed data, and storage mechanisms
- Importers and raw-data handling
- Existing run, activity, strength, health, weather, and analytics code
- API routes, services, UI pages, CLI commands, and background jobs
- Test commands, lint commands, type-check commands, build commands, and migration commands
- Existing FIT, CSV, Garmin, Open-Meteo, or other provider integrations
- Existing authentication, authorization, secret handling, and sensitive-data controls
- Existing documentation and known limitations

Read `OPENCODE_INSTRUCTIONS.md` if it exists locally. If it is absent, record that fact in the inventory rather than attempting to rely on the unavailable GitHub URL.

Create or update:

- `docs/IMPLEMENTATION_INVENTORY.md`

The inventory must distinguish verified implementation from missing, partial, blocked, or untested implementation. Include exact file paths and commands used as evidence. Do not claim a feature exists merely because it is mentioned in documentation.

**Where**

Repository root and all existing source, test, configuration, migration, and documentation directories. Primary output: `docs/IMPLEMENTATION_INVENTORY.md`.

**How to verify success**

- `docs/IMPLEMENTATION_INVENTORY.md` exists and contains the discovered architecture.
- Every claimed entry point, schema, command, and feature includes an exact path or command.
- Missing and unverified areas are explicitly listed.
- The repository’s documented test/build commands can be executed or their failure is recorded with output.
- No secrets, private health data, or raw sensitive exports are added to the repository.

**Priority: HIGH**

---

### 2. Implement canonical activity records with provenance and timestamp-quality metadata

**What to do**

Using the architecture identified in Task 1, implement or extend the canonical activity model and its migration. Preserve raw source values and do not silently rewrite ambiguous timestamps.

Each canonical activity must support, using the repository’s existing naming conventions:

- Stable activity identifier
- Raw source timestamp
- UTC timestamp
- Athlete-local timestamp
- Athlete-local date
- Timezone identifier and UTC offset when known
- Timestamp-confidence status such as `confirmed`, `inferred`, `assumed`, `unknown`, or equivalent
- Source provider
- Source file or raw-record reference
- Import batch identifier
- Parser/importer version
- Human confirmation status
- Duplicate-review status
- Data-quality flags
- Distance, duration, elevation, heart rate, cadence, and other existing metrics without changing their raw values

Flag the known 26 July/27 July timestamp discrepancy for athlete confirmation. Preserve both dates and the original source value. Do not infer a global timezone.

Update import code, serializers, API responses, and tests so downstream consumers can see the quality state and provenance.

**Where**

The canonical activity schema, database migrations, import services, API serializers, and related tests discovered in Task 1. Add a migration under the repository’s existing migration directory and update relevant documentation.

**How to verify success**

- A fresh database migration succeeds.
- Existing activity imports preserve raw source timestamps and populate canonical fields.
- The known timestamp discrepancy produces a visible data-quality flag and confirmation-required state.
- No code silently converts assumed timestamps into confirmed local dates.
- API or service output exposes provenance, confidence, and quality flags.
- Tests cover confirmed, assumed, unknown, and discrepant timestamps plus missing timezone data.
- Existing tests, type checks, lint checks, and builds pass, or failures are documented.

**Priority: HIGH**

---

### 3. Build the data-completeness, duplicate-review, and athlete-confirmation workflow

**What to do**

Implement a workflow that distinguishes:

- No data supplied
- Data not yet imported
- Athlete confirmed that an activity or field is absent
- Athlete confirmed that an activity occurred
- Confirmation required
- Inferred or assumed data

The workflow must support:

- Calendar or date-range completeness review
- Timestamp-discrepancy confirmation
- Duplicate-review status
- Confirmation actor
- Confirmation timestamp
- Confirmation reason or note
- Audit history of changes
- Reversal or correction of a prior confirmation
- Explicit status for “no lifting data supplied”
- No inference that a blank calendar day was a rest day, missed workout, injury, or noncompliance

Expose the workflow through the existing API/UI/CLI patterns. If no user interface exists, implement the service/API boundary and document the required client behavior rather than creating an unrelated framework.

**Where**

Existing activity/calendar/completeness services, API routes, UI components, database migrations, and tests. Primary documentation should be added to the existing product documentation area.

**How to verify success**

- A blank date cannot automatically become “rest day,” “missed workout,” or “injury.”
- The 26 July/27 July discrepancy can be marked confirmed or left unresolved with a complete audit record.
- Duplicate candidates can be reviewed and assigned a status.
- “No lifting data supplied” is displayed separately from “no lifting performed.”
- Every confirmation stores actor, timestamp, status, and audit history.
- Tests cover unresolved, confirmed, rejected, corrected, and reverted confirmations.
- The workflow displays an explicit confirmation-required or incomplete-data state to downstream analytics.

**Priority: HIGH**

---

### 4. Inspect FIT files and preserve raw activity data

**What to do**

Locate all FIT files or other original activity files in the repository, configured data directories, fixtures, or documented local import locations. Do not commit private raw files if they are not already intended for version control.

Implement or use a repeatable inspection command that reports, without exposing sensitive data unnecessarily:

- File inventory and checksums
- FIT parser/library version
- Activity/session/lap record presence
- Start timestamps and timestamp fields
- GPS coordinate availability and sample counts
- Coordinate validity and approximate location precision
- Timezone or offset fields, if present
- Parse errors and unsupported messages
- Raw-file references linked to canonical activities

If no FIT files are available, report that fact explicitly and implement the importer boundary and unavailable-data state. Do not fabricate GPS availability.

**Where**

FIT import/inspection code, raw-data handling directories, fixtures, CLI commands, and documentation discovered in Task 1. Add an inspection report under `docs/` or the repository’s existing audit-report directory.

**How to verify success**

- A repeatable inspection command runs against available FIT files or returns a documented no-files result.
- The report states whether GPS, timestamps, laps, sessions, and timezone data are available.
- Parse failures identify the file and failure reason.
- Raw source references and checksums are retained without exposing secrets.
- GPS-unavailable and parse-failure states are explicit.
- Tests cover valid FIT input, missing GPS, malformed input, and unavailable source files.

**Priority: HIGH**

---

### 5. Implement strength-session logging and import structures

**What to do**

Add a strength-session data model and workflow that supports:

- Session date and duration
- Multiple exercises per session
- Movement category
- Multiple sets per exercise
- Repetitions
- Load and load units
- Optional RPE or repetitions in reserve
- Tempo or range-of-motion notes where supported
- Unilateral side
- Pain, discomfort, and modification notes
- Estimated 1RM only when enough valid inputs exist
- Athlete-entered versus device-imported status
- Source and provenance
- Incomplete-session status

Do not infer that zero imported sessions means zero real-world strength training. Display the state as “no lifting data supplied” until the athlete confirms otherwise.

Provide validation for units, repetitions, loads, and optional fields. Do not require unavailable fields for a session to be saved.

**Where**

Strength schema, migrations, services, API/UI/CLI workflow, serializers, documentation, and tests identified in Task 1.

**How to verify success**

- A user can create a session containing multiple exercises and multiple sets.
- Optional RPE/RIR, pain notes, modifications, units, and provenance are stored and returned.
- Incomplete sessions are represented explicitly rather than rejected without explanation.
- Zero records produce “no lifting data supplied,” not “no lifting performed.”
- Estimated 1RM is absent or marked insufficient-data when inputs are inadequate.
- Tests cover creation, editing, units, optional fields, incomplete sessions, provenance, and invalid values.

**Priority: HIGH**

---

### 6. Implement versioned, explainable running and strength load calculations

**What to do**

Create or extend a load-calculation service that stores calculation metadata and supports:

- Separate running load and strength load
- Running volume over 7, 14, and 28 days
- Duration and elevation summaries
- Longest recent run
- Consecutive training days
- Strength session and set/volume summaries
- Missing-data and incomplete-data handling
- Calculation version
- Calculation timestamp
- Contributing record identifiers
- Explanation of excluded or low-confidence records

Do not expose a generic ACWR as a definitive injury-risk score. If a ratio is retained for compatibility, label it descriptive, provisional, and insufficient as a safety decision.

Do not present a low short-term load as automatic permission to increase training after an abrupt reduction.

**Where**

Analytics/load services, database output tables or materialized views, API serializers, dashboard/report components, and tests. Add calculation documentation under `docs/`.

**How to verify success**

- A calculation can be reproduced from stored inputs and its version.
- Each output identifies contributing records and missing-data limitations.
- Running and strength loads are not merged into an unexplained single number.
- 7-, 14-, and 28-day windows are tested at boundaries and across timezone/date discrepancies.
- No-data and incomplete-data cases return explicit states rather than zeros that imply no training.
- UI/API language does not call ACWR an injury-risk score or safety guarantee.
- Fixtures verify the expected behavior after a high-load week followed by a sharp reduction.

**Priority: HIGH**

---

### 7. Add provisional, explainable training-control recommendations

**What to do**

Implement a recommendation service or rules layer that uses available load, recovery, effort, symptoms, terrain, and data-quality signals. Recommendations must be provisional and explainable.

Implement the conservative stabilization guidance:

- Week 1: 14–16 running miles
- Week 2: 16–18 miles
- Week 3: 18–20 miles
- Week 4: 14–16 miles
- Long runs approximately 7, 8–9, 9–10, and 7–8 miles
- No simultaneous increase in mileage, elevation, and intensity
- Week 1 easy running by default
- Relaxed strides only when pain-free and recovered
- No formal workout when recent fatigue or high volume indicates otherwise

Support conservative strength guidance:

- Two sessions per week when appropriate
- Split squat, Romanian deadlift, and calf-raise patterns
- 2–3 sets
- 6–8 repetitions for primary lifts
- 8–20 repetitions for calf work
- 2–3 repetitions in reserve
- No failure training
- At least 48 hours between demanding lower-body lifting and the long run
- Reduce or omit the second lower-body session when soreness affects running mechanics

Add safety boundaries for pain altering stride, persistent/worsening symptoms, soreness beyond 48 hours, unusually difficult easy effort, unexplained cadence deterioration, or multi-session fatigue. Use non-diagnostic language and recommend appropriate clinical evaluation for persistent or concerning symptoms.

**Where**

Recommendation/rules services, API/UI/report output, configuration, documentation, and tests. Use the repository’s existing coaching architecture.

**How to verify success**

- Recommendations include the rule inputs, contributing records, calculation version, and confidence/limitation state.
- Incomplete data produces conditional recommendations or “insufficient data,” not false certainty.
- Week 1 does not require formal speedwork.
- Safety conditions reduce, defer, or stop the relevant recommendation.
- Outputs do not diagnose injury or claim to predict injury risk.
- Tests cover high recent load, sharp load reduction, pain, prolonged soreness, missing HR zones, missing strength data, and terrain-related cadence changes.

**Priority: HIGH**

---

### 8. Implement consent-based health and recovery inputs with security boundaries

**What to do**

Add only the minimum structured inputs needed for coaching, such as:

- Session RPE
- Subjective recovery
- Sleep duration or quality
- Resting heart rate with measurement protocol
- Bodyweight where consented
- Pain location, severity, duration, and movement effect
- Athlete-confirmed HR-zone settings

For every sensitive category, implement:

- Explicit consent status
- Consent version
- Consent timestamp
- Revocation workflow
- Origin label
- Least-privilege access control
- Audit logging
- Retention and deletion behavior
- Encryption in transit and at rest according to the application’s capabilities
- Separation of raw health inputs from coaching interpretations
- Non-diagnostic terminology

Do not integrate medical records or external clinical systems. If the repository lacks the required security foundation, implement a blocked boundary and documentation rather than ingesting sensitive data.

**Where**

Health/recovery schema, migrations, authorization middleware, consent services, API/UI, audit logging, security documentation, and tests.

**How to verify success**

- Sensitive fields cannot be written or read without the required authorization and consent state.
- Consent can be granted, versioned, revoked, and audited.
- Origin labels distinguish athlete-reported, device-derived, and algorithmic values.
- Deleted or revoked data follows the documented retention behavior.
- UI and API content contains no diagnostic injury or medical claims.
- Security tests cover unauthorized access, revoked consent, audit events, and cross-athlete data isolation.
- No medical record integration or unapproved sensitive import is present.

**Priority: HIGH**

---

### 9. Add consistent data-quality, HR-zone, and uncertainty labeling

**What to do**

Define a shared vocabulary and apply it across imports, API responses, dashboards, reports, and recommendations. At minimum support labels equivalent to:

- Confirmed
- Athlete-reported
- Device-derived
- Algorithmic
- Inferred
- Assumed
- Missing
- Low confidence
- Confirmation required
- Weather unavailable
- Insufficient data
- No lifting data supplied
- Non-medical guidance

Mark heart-rate zones as provisional unless zone boundaries and calibration are explicitly verified. Ensure every analytical output can show its assumptions, missing fields, calculation version, and confidence/limitation state.

Correct any product language claiming that missing weather does not block prediction or that load ratios prove safety.

**Where**

Shared types/constants, serializers, UI components, reports, analytics outputs, documentation, and tests across the repository.

**How to verify success**

- Identical data states use consistent labels across API and UI.
- Unvalidated HR zones are visibly provisional.
- Missing weather is shown as unavailable rather than zero or a fabricated observation.
- “No lifting data supplied” is distinct from zero lifting.
- Every recommendation and analytical output exposes limitations and provenance.
- Tests or snapshot checks cover each required label and prevent unsafe wording.

**Priority: MEDIUM**

---

### 10. Implement location-validated Open-Meteo weather enrichment

**What to do**

Proceed only after Tasks 2 and 4 establish reliable timestamp and location inputs. If GPS is absent or unusable, implement an athlete-provided location or route-area confirmation workflow. Do not use a default city or assumed location.

For each eligible activity, match weather using:

- Confirmed or sufficiently reliable activity start timestamp
- Validated activity location
- Appropriate Open-Meteo historical endpoint
- Provider and retrieval timestamp
- Observed, reanalysis, or forecast source label
- Location precision
- Match confidence
- Weather-unavailable state

Store, where available:

- Temperature
- Relative humidity
- Dew point
- Wind speed
- Wind direction
- Precipitation
- Weather code/conditions
- Apparent temperature
- Surface pressure

Do not enrich activities that lack the required timestamp or location confidence. Do not fabricate missing weather values.

**Where**

Weather provider client, enrichment job/service, weather schema and migration, location-confirmation workflow, API/UI, fixtures, and documentation.

**How to verify success**

- Activities without validated location remain explicitly `weather_unavailable`.
- The provider request uses the activity’s validated timestamp and location.
- Provider, retrieval time, location precision, match confidence, and weather fields are stored.
- Assumed locations and fabricated values are rejected by validation and tests.
- Provider failures are retryable or recorded with an explicit failure state.
- Tests cover valid matching, timestamp uncertainty, missing GPS, athlete-confirmed location, provider failure, and malformed responses.
- Weather enrichment is not enabled for prediction until the minimum-data rule in Task 11 is satisfied.

**Priority: MEDIUM**

---

### 11. Add uncertainty-aware weather and terrain analysis

**What to do**

After Task 10 produces valid matched observations, implement descriptive analysis that separates:

- Elevation and terrain
- Route and surface
- Weather
- Effort
- Fatigue
- Recovery
- Heart-rate confidence
- Cadence context

Require minimum sample counts and comparable route/effort conditions before producing weather correlations or weather-adjusted predictions. Otherwise return `insufficient_data` with a clear explanation.

Do not interpret slow, high-elevation activities as weather effects without controlling for terrain. Do not present correlation as causation.

**Where**

Weather analytics, activity comparison services, dashboards/reports, API responses, and tests.

**How to verify success**

- Weather-unavailable activities do not enter weather correlations.
- Insufficient matched observations suppress weather-adjusted predictions.
- Analyses expose sample count, match confidence, contributing activity IDs, and confounding limitations.
- High-elevation examples are not attributed to weather without adequate controls.
- Tests cover insufficient data, mixed route difficulty, missing weather, and adequate matched observations.

**Priority: LOW**

---

### 12. Run the complete verification suite and publish an implementation status report

**What to do**

Run all applicable repository checks discovered in Task 1:

- Unit and integration tests
- Type checks
- Lint and formatting checks
- Build
- Database migrations from a clean database
- Import validation
- FIT inspection
- Representative run workflow
- Timestamp-confirmation workflow
- Strength-session workflow
- Load-calculation workflow
- Recommendation safety checks
- Consent and authorization checks
- Weather unavailable and validated-weather workflows
- Secret and sensitive-data scans

Create or update:

- `docs/VERIFICATION_REPORT.md`

The report must include exact commands, dates, pass/fail results, relevant output summaries, implementation status for Tasks 1–11, known blockers, unavailable source data, and next actions. Do not mark a feature complete without executable evidence.

**Where**

Repository root, CI configuration, test directories, migration tooling, and `docs/VERIFICATION_REPORT.md`.

**How to verify success**

- Every applicable command is listed with its result.
- Failed or blocked checks include the reason and remediation path.
- The report distinguishes implemented, partially implemented, unavailable, blocked, and unverified.
- Representative workflows run against safe fixtures without committing secrets or private raw data.
- The report confirms whether GPS, weather, strength, HR-zone, health, and recovery data are actually available.
- The repository is clean of generated secrets and unintended sensitive exports.

**Priority: HIGH**

---

## NEXT SUPERVISOR CHECK

On the next run, the supervisor will verify:

1. `docs/IMPLEMENTATION_INVENTORY.md` exists and accurately describes the repository architecture with executable evidence.
2. The repository’s actual test, type-check, lint, build, and migration commands have been identified and run.
3. Canonical activity schema and migration fields preserve raw timestamps, local/UTC interpretations, provenance, confidence, duplicate status, and data-quality flags.
4. The 26 July/27 July timestamp discrepancy is represented as confirmation-required rather than silently corrected.
5. FIT files, GPS availability, timestamps, parser failures, and raw-file references have been inspected and documented.
6. The completeness workflow distinguishes missing data from rest days, missed workouts, injuries, and zero lifting.
7. Strength-session logging supports multiple exercises and sets, optional RPE/RIR, units, pain/modification notes, and provenance.
8. Load calculations are versioned, explainable, separated by running and strength, and tested over 7-, 14-, and 28-day windows.
9. Recommendations are provisional, safety-bounded, and do not present ACWR, cadence, HR zones, or missing data as definitive medical or injury-risk conclusions.
10. Consent, authorization, audit, retention, and non-diagnostic controls exist before any sensitive health or recovery data is accepted.
11. Weather enrichment remains unavailable unless timestamp and location validation pass; no default or fabricated location/weather values are used.
12. `docs/VERIFICATION_REPORT.md` records the full verification results, unresolved blockers, and evidence for every completed task.

After committing, report the commit SHA and confirm the file was written. If the supervisor brief is empty or missing, report: NO DATA: supervisor output returned nothing — commit not attempted.

Expected output: Confirmation that SUPERVISOR_BRIEF.md was successfully committed to benpioske-del/garmin-export on the main branch, including the commit SHA. Or a clear error message if the action failed. If the brief input was empty, report: NO DATA: supervisor output returned nothing — commit not attempted.