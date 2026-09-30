THIS IS UNVERIFIED LLM OUTPUT - review before acting.

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-09-30
## Run by: CrewAI Flow Supervisor

---
## VERIFICATION (from previous brief)

- `reconcile-activity-count-and-provenance`: BLOCKED - The repository documents 56 FIT files and 56 canonical activities, but does not reconcile those records with the 55-row audit or historical 59-record source.
- `profile-and-timezone-provenance`: IN PROGRESS - `profile.json` is empty, 56 timezone reviews remain open, and timestamp confidence and cross-midnight handling are incomplete.
- `activity-confirmation-and-continuity`: IN PROGRESS - Eleven recent activities require confirmation and one activity gap is recorded, but the complete athlete-facing resolution and recomputation workflow is not evidenced.
- `identity-consent-and-athlete-isolation`: BLOCKED - No authentication, REST API, UI, authorization system, or multi-athlete separation exists.
- `strength-session-ingestion`: IN PROGRESS - The strength schema and service are tested, but no real strength sessions exist and `strength_load` is null.
- `weather-provider-enrichment`: IN PROGRESS - Privacy gating exists, but there is no weather provider, coordinate resolution, observation persistence, or weather output integration.
- `confirmed-training-load-and-coaching-loop`: IN PROGRESS - Load calculations and refusal behavior are tested, but the empty profile, unresolved reviews, missing strength data, and activity-count discrepancy prevent a trusted coaching loop.
- `brief-transport-and-operational-delivery`: IN PROGRESS - The local bridge and tests exist, but cross-time idempotency, quality gates, dependency locking, and operational delivery remain incomplete.

No previous task meets its complete acceptance criteria. The repository foundation includes 152 passing tests, canonical activity storage, FIT audit provenance, strength schema foundations, load calculations, safety boundaries, privacy guards, and a local brief bridge.

---
## SUPERVISOR DECISIONS

The immediate objective is data trust and safe athlete identity, not additional prediction features. The platform must not make authoritative personalized coaching decisions until source records, timestamp provenance, athlete identity, and confirmation status are explicit and testable.

The canonical activity count is unresolved. The repository contains evidence for 55 audit records, 56 FIT files and canonical activities, and a historical 59-record discrepancy. No record may be silently dropped, duplicated, or synthetically created. The implementation must produce a durable reconciliation artifact that identifies every divergence and defines which dataset is authoritative for coaching.

The empty profile and unresolved timestamps make dates, load windows, weather policy, and recommendations provisional. The profile workflow must capture timezone, locale, units, goals, preferred activity identity, weather consent, and optional age or birth-year policy. Activities must expose `confirmed`, `inferred`, or `unknown` timestamp provenance and preserve the source and reason for every inference.

The existing refusal behavior is correct but incomplete. The confirmation workflow must allow an athlete or authorized actor to resolve activity dates, duplicates, invalid records, and continuity gaps. It must support `rest`, `illness`, `travel`, `missed_recording`, and `missing_source_data` without creating synthetic workouts. Every decision needs an actor, timestamp, reason, original value, revised status, and source provenance. Confirmed changes must trigger deterministic recomputation.

Authentication and athlete isolation are platform blockers. Consent is not authorization. Medical integration, cloud exposure, and multi-athlete operation must remain disabled until athlete identity, authorization, record ownership, protected import and export paths, consent revocation, and audit logging are implemented and tested.

Heart-rate zone results are not trustworthy because 53 of 55 runs are classified as Zone 5. The platform must label HR data as untrusted and must not generate automated HR prescriptions until configuration and classification logic are validated. Pace, effort, terrain, and symptoms should remain the safer inputs.

The current low ACWR must be treated as a re-entry state after a sharp reduction, not as permission to immediately resume peak mileage. The coaching engine must consider acute load, chronic load, inactivity, confirmation confidence, gaps, strength load, symptoms, HR trust, and terrain rather than relying on ACWR alone.

The strength foundation should be connected to real data through manual entry and structured import before broad device integration. Only confirmed strength sessions may contribute to combined load. The interface must distinguish no data, planned, draft, imported, and confirmed strength records.

Weather enrichment is deferred until identity, consent, and activity-time provenance are operational. When implemented, it should use a privacy-preserving provider integration, such as Open-Meteo, and store activity-context weather with provider and observation provenance without storing raw coordinates in weather observations.

The local brief bridge must be stabilized before cloud deployment. Stable identity must not depend on capture time. Quality gates, dependency reproducibility, repeatable verification, and backup and recovery documentation are required before operational exposure.

The immediate execution order is:

1. Reconcile activity and provenance records.
2. Build identity and authorization foundations.
3. Complete profile and timestamp provenance.
4. Complete activity confirmation and continuity.
5. Connect confirmed data to the coaching loop.
6. Add real strength ingestion and combined load.
7. Add consented weather enrichment.
8. Stabilize operational delivery and quality gates.

---
## OPENCODE TASKS

### 1. reconcile-activity-count-and-provenance

**What to do**

Create a complete source-to-canonical reconciliation for all activity records. Identify every record in the FIT-file inventory, canonical `activities` table, 55-row audit dataset, and any historical 59-record audit source available in the repository. Classify every difference as one of:

- `duplicate`
- `excluded_source_record`
- `parse_or_import_difference`
- `date_or_time_identity_difference`
- `malformed_or_unreviewed`
- `legitimate_additional_activity`

Do not delete, duplicate, or synthesize an activity to force counts to match. Define and document the single authoritative dataset used by load calculations and coaching outputs. If the historical 59-record source is unavailable, record that fact as an explicit unresolved source limitation and include the exact paths and commands used to search for it.

Add a durable reconciliation report and regression tests that detect future divergence between source inventory, audit records, and canonical records. Include source identifiers, canonical IDs, timestamps, dates, provenance references, classification, and resolution status for every divergence.

**Where**

Work in the repository `benpioske-del/garmin-export` on the main branch. Inspect the activity import and audit code, database migrations, `docs/IMPLEMENTATION_INVENTORY.md`, `docs/VERIFICATION_REPORT.md`, existing data directories, and all activity-related tests. Add the report under `docs/` and place tests beside the existing activity and import tests.

**How to verify success**

- A committed reconciliation artifact accounts for every available record in every source.
- The artifact explicitly explains the 55, 56, and 59 counts or documents which source is unavailable.
- Every canonical activity has a source or an explicit reviewed exception.
- No synthetic activity is created for a missing source record.
- Re-running the reconciliation produces the same result without duplicate rows.
- Regression tests fail if a source record is silently omitted or a canonical record loses provenance.
- The normal test suite passes.

**Priority: HIGH**

### 2. build-identity-consent-and-athlete-isolation

**What to do**

Implement a local-first athlete identity and authorization boundary before enabling medical data, cloud exposure, or multi-athlete operation. Add an immutable athlete identifier and ownership relationship to every athlete-owned record, including activities, activity reviews, continuity decisions, profiles, strength sessions, weather links, load outputs, recommendations, and sensitive import or export records.

Implement authenticated local identity suitable for the current application architecture. Add authorization checks for reads, writes, imports, exports, review decisions, and sensitive data access. Implement consent grants and revocation enforcement for health and location data. Record auditable authorization decisions and sensitive access events. Preserve the existing health consent boundary, but do not treat it as authentication.

Keep medical-record integration disabled. Do not add a cloud endpoint as part of this task.

**Where**

Work in the repository database schema, migrations, services, import and export paths, health and weather consent code, and existing test suite. Inspect the current database and service architecture before choosing implementation details. Add a migration under the existing migration sequence and document the authorization model in `docs/`.

**How to verify success**

- Every athlete-owned table has an athlete ownership field or an enforced ownership relationship.
- Reads and writes reject unauthenticated or unauthorized access.
- Tests prove that one athlete cannot read, modify, import for, or export another athlete's records.
- Revoked health or location consent blocks the corresponding operation.
- Sensitive access and authorization decisions are auditable.
- Existing single-athlete data is migrated deterministically to one explicit local athlete identity.
- Tests prove that medical integration and cloud exposure remain disabled.
- The normal test suite passes with migration tests included.

**Priority: HIGH**

### 3. complete-profile-and-timestamp-provenance

**What to do**

Implement profile completion and timestamp provenance workflows. The profile must support timezone, locale, units, training goals, preferred activity identity, location and weather consent, and an explicit optional age or birth-year policy. Validate required values and retain whether each value is user-confirmed, inferred, or unknown.

Add explicit activity timestamp provenance states: `confirmed`, `inferred`, and `unknown`. Preserve UTC timestamp, derived local date, source filename date, timezone used, and the reason for any inference. Handle cross-midnight activities through a review state instead of silently changing their dates. Ensure incomplete profiles produce safe, explicit coaching states rather than invented values.

Do not silently assume UTC for a completed profile. Existing assumptions may remain only as clearly labeled provisional provenance.

**Where**

Work in `profile.json` handling, profile services and validation, activity import and date derivation code, activity review models, load calculation inputs, recommendation gates, and related tests. Update `docs/IMPLEMENTATION_INVENTORY.md` and add a provenance contract under `docs/`.

**How to verify success**

- A valid completed profile can be stored and reloaded with all required fields and consent states.
- Invalid, incomplete, and revoked profile values are rejected or represented as explicit unknown states.
- Every activity exposes one timestamp provenance state and the supporting source fields.
- Cross-midnight fixtures enter review instead of being silently reassigned.
- Local dates are deterministic for a confirmed timezone.
- Load and recommendation outputs expose the effect of unresolved profile or timestamp data.
- Tests cover confirmed, inferred, unknown, cross-midnight, and missing-timezone cases.
- The normal test suite passes.

**Priority: HIGH**

### 4. implement-activity-confirmation-and-continuity-queue

**What to do**

Turn existing review records into an actionable confirmation and continuity workflow. Support review actions for timezone or date correction, duplicate, invalid activity, and activity confirmation. Support gap classifications of `rest`, `illness`, `travel`, `missed_recording`, and `missing_source_data`.

For every review decision, store the actor, decision timestamp, reason, original value, revised status, and source provenance. Preserve the history of changes rather than overwriting the original record. A continuity classification must not create a synthetic workout or alter source provenance. Add deterministic recomputation after a confirmation or correction, including load windows, trends, recommendations, and dashboard summaries.

Keep recommendations in a refusal or confirmation-required state while required recent records remain unresolved.

**Where**

Work in the activity review and audit services, continuity or gap models, recommendation gates, load calculation services, dashboard/report output code, migrations, and tests. Use the existing 56 timezone reviews, 11 recent confirmations, and activity gap fixtures as regression cases where available.

**How to verify success**

- The review queue lists all unresolved activity and continuity decisions with actionable allowed transitions.
- All required classifications are accepted and persisted with complete audit metadata.
- No continuity decision inserts a synthetic activity.
- Confirming or correcting a record recomputes all affected outputs deterministically.
- Repeating the same decision is idempotent.
- Recommendations remain blocked when required confirmations are open and become eligible only when the documented gate is satisfied.
- Tests cover every classification, authorization failure, audit field, recomputation, and no-synthetic-activity rule.
- The normal test suite passes.

**Priority: HIGH**

### 5. harden-coaching-state-and-confirmed-load-loop

**What to do**

Complete the coaching contract around trusted data. Explicitly expose the states `ready`, `provisional`, `confirmation_required`, and `insufficient_data`, with a machine-readable reason and human-readable explanation for each state.

Make 7-day, 14-day, and 28-day running and combined load calculations use only records whose inclusion status and provenance satisfy the documented rules. Add confirmed strength load when strength data is available. Treat a low ACWR after a recent sharp reduction as a re-entry state rather than automatically low risk. Include recent inactivity, confirmation confidence, activity gaps, strength load, symptoms, HR trust, and terrain in recommendation gating and output labels.

Do not change refusal-first behavior into permissive behavior. Do not generate HR prescriptions while HR configuration is untrusted.

**Where**

Work in the load calculation, recommendation, trend, HR classification, and report output services, plus their schemas and tests. Update the coaching-state contract in `docs/`.

**How to verify success**

- Each coaching state can be produced through a documented fixture and includes a reason.
- Confirmed running records produce deterministic 7/14/28-day loads.
- Unconfirmed, unknown-date, excluded, or unresolved records are handled according to documented rules.
- Confirmed strength records contribute to combined load; draft or planned records do not.
- A sharp recent reduction produces a re-entry warning even when ACWR is low.
- Untrusted HR data produces `hr_data_untrusted` and no automated HR prescription.
- Recommendations remain refusal-first when data is insufficient or confirmation is required.
- Tests cover all state transitions and existing 152-test behavior remains intact.

**Priority: HIGH**

### 6. validate-hr-zones-before-coaching

**What to do**

Audit and repair heart-rate zone interpretation without treating the existing 53-of-55 Zone 5 result as physiological truth. Identify whether zones are based on maximum HR, threshold HR, or heart-rate reserve, and preserve the source of the configured values. Add validation for impossible or suspicious distributions and expose an `hr_data_untrusted` state with affected metrics and required corrective action.

Block automated HR-zone prescriptions and HR-based progression while configuration is unverified. Continue to expose average HR, maximum HR, pace, elevation, effort, and provenance for defensive review.

**Where**

Work in HR configuration, activity parsing, zone classification, coaching recommendation, and report output code. Add tests using fixtures that reproduce the current Zone 5 distribution and fixtures for valid max-HR, threshold-HR, and heart-rate-reserve configurations.

**How to verify success**

- The system identifies the current HR-zone configuration and its source.
- Suspicious zone distributions are labeled untrusted instead of presented as confirmed physiology.
- Automated HR prescriptions are blocked while HR settings are unverified.
- Validated configurations produce deterministic zones with documented formulas.
- Reports show the reason, affected metrics, and corrective action for untrusted HR data.
- Tests cover invalid configuration, missing configuration, suspicious distribution, and validated configuration.
- The normal test suite passes.

**Priority: HIGH**

### 7. add-confirmed-strength-session-ingestion

**What to do**

Implement a reliable manual entry and structured import path for real strength sessions using the existing strength schema and service. Support session date and timestamp provenance, exercises, movement-pattern taxonomy, sets, repetitions, load, bodyweight where available, RPE or repetitions in reserve, laterality, pain or limitation flags, and confirmed, imported, or draft state.

Add estimated 1RM provenance and modification or deletion history. Ensure only confirmed sessions contribute to combined training load. Clearly distinguish no strength data, planned strength, draft strength, imported strength, and confirmed strength in reports and coaching output.

Do not invent historical strength sessions. Do not infer strength progression from the absence of records.

**Where**

Work in `strength.py`, the `003_strength` migration or subsequent migrations, import and service layers, combined-load code, and strength tests. Add user-facing or CLI entry points consistent with the repository's current architecture. Update implementation documentation.

**How to verify success**

- A valid strength session can be manually created, imported, reviewed, confirmed, modified, and deleted with audit history.
- Required fields and movement-pattern values are validated.
- Estimated 1RM values identify their formula, inputs, and provenance.
- Draft and planned sessions do not contribute to load.
- Confirmed sessions contribute deterministically to 7/14/28-day combined load.
- No-data output remains explicit until a session exists.
- Tests cover field validation, state transitions, laterality, pain flags, provenance, idempotent import, and combined load.
- The normal test suite passes.

**Priority: MEDIUM**

### 8. implement-consented-weather-provider-enrichment

**What to do**

After identity, consent, and timestamp provenance gates are available, add a privacy-preserving weather provider integration using Open-Meteo or the provider abstraction already present in the repository. Resolve weather for the activity context only when location consent exists and the activity time is sufficiently trusted.

Persist temperature, relative humidity, dew point, wind speed and direction, precipitation, condition code, and apparent temperature or equivalent heat metric where the provider supplies them. Store retrieval timestamp, provider, model or observation provenance, and status values for `observed`, `estimated`, `interpolated`, `unavailable`, and `consent_blocked`.

Do not store raw athlete coordinates in weather observation records. Make enrichment idempotent and expose weather context in activity and trend outputs only when data quality permits. Do not claim weather-adjusted performance from missing or insufficient data.

**Where**

Work in `weather.py`, weather migrations and models, consent and location policy code, activity enrichment services, report outputs, and privacy tests. Use provider mocking in tests and do not require live network access for the test suite.

**How to verify success**

- Enrichment is blocked without valid location consent or acceptable timestamp provenance.
- Provider responses are persisted with complete provider and retrieval provenance.
- Weather observations contain no raw coordinates.
- Repeat enrichment produces one stable result rather than duplicate observations.
- All required status values are represented and surfaced correctly.
- Activity and trend outputs display weather context only when permitted and available.
- Tests cover consent blocked, unavailable provider, observed or estimated data, repeat enrichment, and privacy rejection.
- The normal test suite passes.

**Priority: MEDIUM**

### 9. stabilize-brief-transport-and-quality-gates

**What to do**

Fix brief transport idempotency so stable identity does not depend on regenerated `captured_utc`. A byte-identical brief posted in different seconds must resolve to the same identity and must not create duplicate records. Preserve capture time as metadata, not as the identity key.

Add repository quality gates appropriate to the existing language and tooling: formatter, linter, type checker where applicable, test command, dependency lockfile, and CI configuration. Document repeatable import and verification commands and a local backup and recovery procedure. Do not deploy a cloud endpoint or expose athlete data operationally in this task.

**Where**

Work in `brief_bridge.py`, its tests, package and dependency files, CI configuration, and operational documentation under `docs/`.

**How to verify success**

- Cross-second idempotency tests pass using mocked timestamps.
- Reposting byte-identical content does not create duplicate records.
- Capture time remains available as metadata.
- Quality checks run locally and in CI.
- Dependencies are reproducible from a committed lockfile or the repository's standard equivalent.
- Import, verification, backup, and recovery commands are documented and tested.
- No cloud deployment or unauthenticated endpoint is introduced.
- The normal test suite and all quality gates pass.

**Priority: MEDIUM**

---
## NEXT SUPERVISOR CHECK

On the next run, verify that `reconcile-activity-count-and-provenance` has produced a committed record-level reconciliation and that the 55, 56, and 59 counts are either resolved or tied to explicit unavailable source evidence.

Verify that `build-identity-consent-and-athlete-isolation` has established athlete ownership, authorization, consent revocation, and cross-athlete isolation tests without enabling medical integration or cloud exposure.

Verify that `complete-profile-and-timestamp-provenance` and `implement-activity-confirmation-and-continuity-queue` have converted the empty profile, 56 timezone reviews, 11 recent confirmations, and activity gap into actionable, auditable workflows.

Verify that the coaching engine exposes the four required states, remains refusal-first, uses only eligible confirmed data, and labels the low-ACWR re-entry condition and untrusted HR data correctly.

Verify test results, migration status, documentation changes, and repository cleanliness. No task should be marked completed unless its acceptance criteria and regression evidence are present in the live repository.
