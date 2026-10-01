THIS IS UNVERIFIED LLM OUTPUT -- review before acting.

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-10-01
## Run by: CrewAI Flow Supervisor

---
## VERIFICATION (from previous brief)

- complete-explicit-profile-and-timestamp-provenance: IN PROGRESS. profile.json fields are all null and 56 timezone_uncertain reviews remain open.
- implement-auditable-activity-review-and-continuity-queue: IN PROGRESS. The system reports 57 open reviews: 56 timezone reviews and one activity-gap review.
- establish-local-athlete-identity-and-consent-boundary: BLOCKED. No authentication, REST API, UI, or multi-athlete separation is evidenced.
- complete-confirmed-load-and-coaching-state-contract: IN PROGRESS. Versioned load windows and refusal-first recommendations exist, but complete state fixtures and rationale snapshots are not evidenced.
- ingest-confirmed-strength-sessions: IN PROGRESS. The strength schema and service exist, but no real strength sessions are recorded.
- implement-consented-weather-provider-enrichment: IN PROGRESS. The consent gate exists, but no provider is integrated and no coordinates are stored.
- stabilize-brief-bridge-and-reproducible-quality-gates: IN PROGRESS. The test suite has 152 passing tests and one skipped test, but CI, dependency locking, quality tools, and tested backup restoration are absent.

---
## SUPERVISOR DECISIONS

The verified canonical corpus contains 56 readable FIT files and 56 canonical activities. Repeat import is idempotent: the first import inserted 56 records and the second import left all 56 unchanged. This verified corpus is the source of truth for current implementation work.

The historical 55-record and 59-record reconciliation premises were not supported by the live evidence and are excluded from this brief. Do not create discrepancy reports, mappings, or synthetic records based on those unsupported counts.

The immediate data-foundation priority is to complete the athlete profile and timestamp review workflow. profile.json is empty, all 56 timezone reviews remain unresolved, and one activity crosses a local-date and UTC-date boundary. The system must preserve uncertainty until an authorized review supplies a supported value. It must not infer or silently rewrite timestamps.

Review decisions must be auditable. Each decision should preserve the actor, decision time, original value, revised value or status, reason, and source provenance. The activity-gap review must remain a review classification and must not be filled with a synthetic activity.

The coaching engine should remain refusal-first. Existing load windows and control states are useful foundations, but every supported state needs deterministic fixtures and every recommendation or refusal needs a rationale snapshot. Missing strength data must remain null rather than being converted to zero. Unresolved timezone reviews, missing profile values, unavailable weather, and unconfirmed strength data must be distinguished explicitly.

The strength schema and service are present, but no real strength data exists. The implementation should provide a provenance-preserving capture and review workflow without inventing athlete data. Combined load must use only confirmed strength sessions.

Weather enrichment must remain consent-gated and privacy-preserving. A provider adapter may be implemented, but weather values must not be reported as available until provider-backed observations are persisted and verified. Raw coordinates must not be stored in weather_observations.

Authentication and athlete ownership are absent. This blocks production multi-athlete use, cloud synchronization, and medical-record integration. The repository should first define and test ownership and consent boundaries before adding those capabilities.

Quality and release controls are incomplete. The repository has a useful test suite, but no CI workflow, dependency lockfile, configured formatter, linter, type checker, or tested backup restoration is evidenced. The brief bridge also needs cross-second idempotency verification.

Training guidance should remain conservative and clearly labeled as coaching direction rather than a verified platform capability. The current evidence supports focusing on long-distance durability, recovery stability, and improved run-lift data capture. It does not support HR-zone analysis, weather-adjusted performance claims, strength-ratio conclusions, or unsupported historical activity reconciliation.

---
## OPENCODE TASKS

### 1. complete-profile-and-timezone-provenance

Priority: HIGH

What to do:

Implement the profile completion and timestamp-provenance workflow. Support entering, validating, persisting, and reloading the athlete profile, including the configured timezone offset, hr_max, and weather-location consent policy. Preserve null or uncertain values when they are not confirmed.

Add or complete per-activity timestamp provenance fields. The provenance must identify the original timestamp, source file or source record, timezone status, and any reviewed value. Do not silently infer or overwrite uncertain timestamps.

Implement an authorized review operation for timezone_uncertain records. A review must store actor identity, decision timestamp, original value, revised value or status, reason, and source reference. Invalid or incomplete review decisions must be rejected.

Where to do it:

- Repository root profile storage, including profile.json and its loading and validation code.
- Existing activity, review, import, and timestamp modules.
- Existing migrations or schema definitions for profile and activity provenance.
- Tests covering profile persistence, timestamp provenance, and review validation.

Success criteria:

- A valid profile can be entered, persisted, reloaded, and validated.
- Missing profile fields remain explicitly missing and produce deterministic validation results.
- Each activity can expose timestamp provenance and timezone status.
- Review decisions contain actor, decision time, original value, revised value or status, reason, and source.
- No timestamp is silently changed during import or review.
- The 56 existing activities remain intact after migrations and profile updates.

How to verify:

- Run the complete test suite.
- Add and run tests for valid profile round-trip persistence.
- Add and run tests for invalid profile rejection.
- Add and run tests for timezone review audit fields and unauthorized or incomplete review rejection.
- Run the existing import twice and verify that the second import does not create duplicate activities.

### 2. finish-activity-review-and-continuity-queue

Priority: HIGH

What to do:

Complete the auditable activity review queue for timezone_uncertain and activity_gap reviews. Expose review status, activity or date range, current evidence, and required decision fields. Support continuity classifications of rest, illness, travel, missed_recording, and missing_source_data without creating synthetic activities.

Ensure that closing a review requires an authorized actor, a timestamp, a reason, and source evidence or an explicit statement that no source evidence exists. Preserve the original review and all later decisions.

Where to do it:

- Existing review queue, activity continuity, and import modules.
- Database schema and migrations for review decisions.
- Existing CLI or service entry points used to inspect and update reviews.
- Tests for queue filtering, decision persistence, authorization, and no-synthetic-activity behavior.

Success criteria:

- The queue identifies all unresolved timezone and continuity reviews.
- Each review can be inspected with its evidence and current status.
- All five continuity classifications are represented in the domain model and validated.
- A review cannot be closed without the required audit fields.
- Unauthorized review updates are rejected.
- Closing a gap classification does not insert an activity or alter the canonical 56-activity count.

How to verify:

- Run tests covering each continuity classification.
- Test authorized and unauthorized review updates.
- Verify that a classified activity gap creates only a review decision and no synthetic activity.
- Re-run the review summary and confirm that open and resolved counts are deterministic.
- Run the complete test suite.

### 3. complete-coaching-state-contract-and-rationales

Priority: HIGH

What to do:

Complete the deterministic coaching contract around confirmed, provisional, confirmation_required, and insufficient_data outcomes, using the control states already implemented by recommend.py. Preserve refusal-first behavior when required data is missing or unresolved.

Implement rationale snapshots for every recommendation or refusal. Each snapshot must include the evaluated data window, input records or stable input references, load algorithm version, missing or uncertain inputs, decision state, and human-readable reason. The snapshot must be persisted or emitted in a stable format that can be audited later.

Keep strength_load as null when no confirmed strength sessions exist. Distinguish unavailable data, unconfirmed data, and confirmed zero contribution.

Where to do it:

- loadcalc.py and recommend.py.
- Existing recommendation, load, and rationale persistence modules.
- Test fixtures and test data under the repository test directories.
- Schema migrations if rationale snapshots require storage.

Success criteria:

- Every supported coaching state has a deterministic fixture.
- Recommendations remain refusal-first when profile or timezone evidence is insufficient.
- Rationale snapshots include inputs, data window, algorithm version, missing-data reason, and decision.
- Repeated evaluation with identical inputs produces identical state and rationale content.
- Unavailable strength load is null and is not treated as zero.
- Weather absence does not produce fabricated weather-adjusted output.

How to verify:

- Add and run fixtures for ready, provisional, confirmation_required, and insufficient_data.
- Test identical inputs across repeated evaluations and compare state and rationale output.
- Test unresolved timezone reviews and empty profile behavior.
- Test null strength load behavior.
- Run the complete test suite.

### 4. implement-confirmed-strength-capture

Priority: HIGH

What to do:

Complete the strength-session lifecycle using the existing strength schema and service. Support creating or importing a real session, recording exercises and sets, attaching provenance, reviewing the session, confirming it, editing it, and deleting it.

Do not create fabricated athlete sessions or load values. The implementation must allow a real user or authorized import process to supply the data. Only confirmed sessions may contribute to combined load.

Where to do it:

- strength.py and related session, exercise, set, review, and load modules.
- Existing database schema and migration files.
- Existing CLI or service interfaces for data entry.
- Tests for lifecycle, provenance, confirmation, deletion, and load integration.

Success criteria:

- A strength session can be created with source and provenance metadata.
- Exercises and sets preserve load, repetitions, and optional RPE or RIR.
- A session can be reviewed, confirmed, edited, and deleted with an audit trail.
- Unconfirmed sessions do not affect confirmed load.
- A confirmed session affects combined load deterministically.
- No-session periods continue to report strength_load as null, not zero.

How to verify:

- Run lifecycle tests from creation through deletion.
- Test that unconfirmed data is excluded from confirmed load.
- Test that confirmed data is included in combined load.
- Test provenance and audit fields.
- Run the complete test suite without inserting invented athlete data into production fixtures.

### 5. establish-athlete-ownership-and-consent-boundary

Priority: HIGH

What to do:

Define and implement the local athlete identity, record ownership, and consent boundary needed before multi-athlete or cloud features. Because no authentication framework currently exists, first implement a clear local ownership model and service-level authorization boundary that can later be connected to authentication.

Add immutable athlete ownership to protected records, including activities, reviews, strength sessions, weather observations, profile data, and rationale snapshots. Add explicit consent records for health data and weather location policy.

Do not claim production authentication or multi-athlete isolation until an actual authenticated boundary exists. The implementation must fail closed when ownership or consent context is absent.

Where to do it:

- Repository root domain and database schema.
- Existing profile, activity, review, strength, weather, and recommendation persistence modules.
- New migrations and authorization service modules as needed.
- Tests for ownership enforcement and consent requirements.

Success criteria:

- Protected records have an immutable athlete ownership reference.
- Service operations require an ownership context.
- Cross-athlete reads and writes are rejected by tests.
- Health-data and weather-location consent are represented explicitly.
- Missing consent blocks the relevant operation.
- Existing single-athlete behavior remains compatible through an explicit local athlete identity rather than an implicit global subject.

How to verify:

- Add tests for same-athlete access.
- Add tests proving cross-athlete reads and writes are rejected.
- Add tests for missing and revoked consent.
- Inspect the schema to confirm ownership fields are present on all protected record types.
- Run the complete test suite.

### 6. add-gated-weather-provider-adapter

Priority: MEDIUM

What to do:

Implement a provider adapter and enrichment workflow behind the existing consent and location gate. Use a provider interface that can support Open-Meteo or another selected provider without coupling domain logic to one vendor.

Persist provider-attributed weather observations only when consent, an approved location reference, and provider data are available. Store activity time, observation time, retrieval time, provider name, provider schema or version metadata, and available weather values. Do not store raw latitude or longitude in weather_observations.

Return unavailable when consent, location, provider access, or provider data is missing. Do not fabricate values.

Where to do it:

- weather.py and existing weather gate modules.
- Provider adapter module and configuration.
- weather_observations schema and migrations.
- Tests for consent, privacy, provider response mapping, failure behavior, and idempotency.

Success criteria:

- Provider calls are isolated behind an adapter.
- Weather observations include provider and timing provenance.
- weather_observations contains no latitude or longitude columns.
- Missing consent or location returns unavailable without a provider call.
- Repeating the same enrichment request is idempotent.
- Provider failures do not create fabricated observations.

How to verify:

- Run schema tests that reject coordinate columns.
- Test consented and non-consented enrichment.
- Test provider success, timeout, malformed response, and unavailable response.
- Run the same enrichment twice and verify no duplicate observations.
- Run the complete test suite.

### 7. harden-bridge-and-release-quality-gates

Priority: MEDIUM

What to do:

Make brief_bridge idempotency stable across process runs and across elapsed seconds. The same logical brief input must not change solely because captured_utc was regenerated. Preserve meaningful timestamps without causing duplicate or byte-different output for an unchanged logical input.

Add reproducible repository quality controls. Configure a formatter, linter, type checker where compatible with the existing codebase, dependency pinning or a lockfile, and a CI workflow that runs the tests and quality checks. Document the commands locally.

Add a tested backup and restore procedure for the local data store and configuration, without exposing health data in logs or committed artifacts.

Where to do it:

- brief_bridge implementation and tests.
- pyproject.toml and dependency lockfile.
- New CI workflow under .github/workflows.
- Backup and restore scripts or documented repository commands.
- Documentation for local development and release checks.

Success criteria:

- Repeated bridge generation across separate runs and elapsed seconds produces stable output for unchanged logical input.
- The test suite covers cross-second idempotency.
- CI runs tests and configured quality checks on the main branch.
- Dependencies are reproducibly resolved.
- Backup and restore are exercised against a disposable test dataset.
- Secrets and health data are excluded from logs, artifacts, and committed fixtures.

How to verify:

- Run the bridge idempotency test with an intentional delay between runs.
- Run the full local quality command.
- Inspect the CI workflow and execute its commands locally.
- Build the environment from the lockfile and run the tests.
- Execute backup, destroy the disposable data, restore it, and verify expected records.
- Run the complete test suite and record the result.

### 8. document-conservative-training-signals

Priority: LOW

What to do:

Document the current coaching interpretation as confidence-labeled guidance, not as a newly implemented progression engine. Use only verified data and clearly identify missing evidence.

Document long-distance durability as a distance-band signal rather than a proven fatigue-decay diagnosis. Document conservative progression, recovery checks, and the need to avoid simultaneous increases in running volume, intensity, elevation, and lifting volume as future coaching policy, not as an existing verified platform capability.

Do not implement HR-zone analysis, weather-adjusted performance claims, strength-ratio conclusions, or unsupported historical activity reconciliation.

Where to do it:

- Existing coaching documentation and recommendation rationale documentation.
- Product or implementation documentation under docs/.
- Tests only where needed to ensure unsupported claims are not emitted.

Success criteria:

- Documentation distinguishes verified metrics from provisional coaching interpretation.
- Missing splits, HR-zone data, weather observations, and strength sessions are explicitly identified.
- No unsupported historical counts or fabricated records appear.
- The application does not emit unsupported strength, HR-zone, or weather-adjusted conclusions.

How to verify:

- Search documentation and generated recommendation text for unsupported historical counts.
- Search code and tests for fabricated activity creation.
- Run recommendation tests with missing weather, strength, and HR-zone inputs.
- Review generated rationale output for clear confidence and missing-data labels.

---
## NEXT SUPERVISOR CHECK

On the next run, verify the following in priority order:

1. Profile completion can be persisted and reloaded, and the system reports the remaining unresolved timezone reviews without silently modifying timestamps.
2. Review decisions contain actor, decision time, original value, revised value or status, reason, and source evidence.
3. No synthetic activity was created for the documented activity gap.
4. Coaching fixtures exist for all supported states and rationale snapshots include inputs, algorithm version, and refusal or recommendation reason.
5. At least one real, provenance-labeled strength session can pass through creation, review, confirmation, load calculation, editing, and deletion without invented athlete data.
6. Ownership and consent checks reject unauthorized or unconsented operations.
7. Weather provider behavior remains unavailable without consent or location and persists only provider-attributed observations without raw coordinates.
8. Bridge idempotency passes across elapsed seconds, and reproducible quality gates, CI, dependency locking, and backup restoration are evidenced.
9. The verified canonical corpus remains 56 activities with repeat import unchanged.

After committing, report the commit SHA and confirm the file was written. If the supervisor brief is empty or missing, report: NO DATA: supervisor output returned nothing \ commit not attempted.

Expected output: Confirmation that SUPERVISOR_BRIEF.md was successfully committed to benpioske-del/garmin-export on the main branch, including the commit SHA. Or a clear error message if the action failed. If the brief input was empty, report: NO DATA: supervisor output returned nothing \ commit not attempted.