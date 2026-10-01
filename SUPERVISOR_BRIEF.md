THIS IS UNVERIFIED LLM OUTPUT - review before acting.

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-10-01
## Run by: CrewAI Flow Supervisor

---
## VERIFICATION (from previous brief)

- complete-profile-and-timezone-provenance: IN PROGRESS - profile.json has hr_max=198 but age, sex, resting_hr, weight_lb, and height_in are null; 57 timezone_uncertain reviews remain open; persistence and provenance completion are not evidenced.
- finish-activity-review-and-continuity-queue: IN PROGRESS - the current corpus contains 57 activities and 58 open reviews: 57 timezone reviews and one activity-gap review for 2026-06-26 through 2026-07-05; required workflow safeguards are not evidenced.
- complete-coaching-state-contract-and-rationales: IN PROGRESS - refusal-first behavior and null strength_load are evidenced, but deterministic fixtures and auditable rationale snapshots are not evidenced.
- implement-confirmed-strength-capture: IN PROGRESS - strength schema and service exist, but zero real strength sessions have been recorded and no end-to-end reviewed session is evidenced.
- establish-athlete-ownership-and-consent-boundary: BLOCKED - authentication, multi-athlete separation, API, and UI are absent; the current database is local and single-subject.
- add-gated-weather-provider-adapter: IN PROGRESS - the consent and location gate exists and raw coordinates are excluded, but no provider adapter or persisted provider observations are evidenced.
- harden-bridge-and-release-quality-gates: IN PROGRESS - brief bridge idempotency is verified, but CI, quality tooling, dependency locking, and tested backup and restore are absent.
- document-conservative-training-signals: IN PROGRESS - unsupported HR-zone and historical-count claims were withdrawn, but generated rationales do not yet explicitly identify all relevant missing or provisional inputs.

The live documents establish 57 FIT files and 57 canonical activities. The prior 56-activity premise, the historical 55/56/59 reconciliation premise, the HR-zone premise, and the OPENCODE_INSTRUCTIONS.md premise are rejected and are not tasks in this brief.

---
## SUPERVISOR DECISIONS

1. Treat 57 activities as the current canonical corpus.
   The inventory and verification report agree on 57 readable FIT files and 57 imported activities with zero duplicates. Do not reconcile unsupported historical counts or create work based on the rejected 56, 55, or 59 premises.

2. Preserve refusal-first coaching behavior.
   Incomplete profile data, unresolved timezone reviews, absent strength history, missing weather, and unavailable split-level data must remain visible limitations. The system must not convert absent data into zeroes or confident interpretations.

3. Complete provenance before relying on longitudinal interpretation.
   Profile values must be validated, persisted, and reloadable. Timestamp review decisions must preserve original values and record who decided, when, why, what source was used, and any revised value. Date-based coaching remains provisional until this work is complete.

4. Formalize continuity review without inventing activities.
   The documented activity gap must remain a gap unless source evidence establishes otherwise. A continuity classification is a review decision, not a synthetic activity, distance, load, or recovery record.

5. Treat athlete ownership and authorization as a release boundary.
   The existing consent boundary is not authentication or multi-athlete isolation. Any future multi-user interface or API must enforce ownership on every athlete-owned record and must test rejection of cross-athlete reads and writes.

6. Move strength from schema readiness to one confirmed real workflow.
   The system may capture a real athlete session, but it must not invent historical lifting data. Confirmed strength load may contribute to combined load only after review and confirmation. No sessions must remain null, not zero.

7. Add weather only behind the existing privacy gate.
   A provider adapter may persist privacy-preserving observations only after consent and location prerequisites pass. Raw latitude and longitude must not be added to weather_observations. Provider failures must not block core activity ingestion.

8. Make rationale output deterministic and auditable.
   Each recommendation must identify its evaluation window, stable inputs, algorithm version, missing or uncertain inputs, decision state, and human-readable reason. Repeated evaluation with identical inputs must produce equivalent rationale output.

9. Add release controls before production deployment.
   The repository needs automated tests, a linter, formatter, type checking where applicable, dependency pinning, CI, and a tested backup and restore procedure. Existing bridge idempotency must remain protected.

10. Keep training guidance conservative.
    The system should favor stable weekly loading, change one stressor at a time, and avoid presenting provisional load metrics as medical or injury diagnoses. Long-run durability and conservative strength guidance may be expressed as coaching recommendations, but all limitations must be visible.

---
## OPENCODE TASKS

### 1. establish-authenticated-athlete-ownership

What to do:
- Implement authentication, athlete identity, authorization checks, and multi-athlete isolation for all athlete-owned data.
- Add immutable athlete ownership references to activities, activity reviews, strength sessions, weather observations, profile data, and coaching rationale snapshots.
- Ensure consent checks remain separate from authorization checks.
- Reject cross-athlete reads and writes, including attempts using an invalid, missing, or different athlete identifier.
- Preserve compatibility with the current single-subject local workflow where possible, but do not treat the existing local database as an authorization system.
- Do not expose a REST API or UI as production-ready unless these ownership checks are enforced by the underlying service layer.

Where:
- Inspect the repository data model, migrations, persistence modules, service modules, and tests.
- Update the existing activity, review, profile, strength, weather, coaching, and consent modules rather than creating an unrelated parallel storage path.
- Add migrations in the repository's existing migration location and tests in the existing test suite.

Success criteria:
- Every athlete-owned record has an immutable athlete ownership reference.
- Service operations require an authenticated athlete context and enforce ownership.
- Cross-athlete reads and writes fail with a deliberate authorization error.
- Missing or revoked consent blocks each operation that requires consent.
- Existing single-athlete tests continue to pass or are updated with explicit athlete context.
- No health or coaching record can be accessed solely because it exists in the local database.

How to verify:
- Run the complete test suite.
- Add and run tests creating two athletes, then prove that each athlete can access only their own activities, reviews, profile, strength sessions, weather observations, and rationale snapshots.
- Test missing authentication, wrong ownership, and revoked consent separately.
- Inspect the schema and migration output to confirm ownership references are non-null and immutable after creation.

Priority: HIGH

### 2. complete-athlete-profile-and-timezone-provenance

What to do:
- Implement validated profile entry, persistence, reload, and update behavior for age, sex, resting_hr, weight_lb, height_in, hr_max, and the athlete UTC offset or timezone confirmation.
- Preserve null values when the athlete has not supplied a field; do not infer or fabricate profile data.
- Implement an explicit workflow for reviewing each timezone_uncertain activity.
- For every timestamp review, record status, actor, decision time, original timestamp or offset, revised value when applicable, reason, and source reference. Permit an explicit no-source-evidence statement.
- Preserve original imported timestamps and values; any accepted revision must be additive and auditable rather than a silent mutation.
- Keep date-window calculations visibly provisional while required profile or timezone inputs remain unresolved.

Where:
- Update the existing profile persistence and validation code, activity review code, timestamp normalization code, database migrations, and related tests.
- Use the existing `profile.json` and review storage conventions rather than creating a second profile format.
- Add fixtures for the current 57-activity corpus without changing source FIT files.

Success criteria:
- A valid profile can be entered, persisted, reloaded, validated, and safely updated.
- Invalid ranges and invalid enum values are rejected with clear errors.
- The athlete can explicitly confirm a UTC offset or timezone.
- Every closed timestamp review contains actor, decision time, original value, status or revised value, reason, and source reference or an explicit no-source-evidence statement.
- Original timestamps remain recoverable after review.
- The system reports the remaining unresolved review count accurately.

How to verify:
- Run unit and integration tests for profile validation, persistence, reload, and update.
- Create a test timezone review, close it with evidence, reload it, and verify all provenance fields.
- Create a no-source-evidence review and verify that it is distinguishable from an evidenced decision.
- Run the current corpus audit and confirm that no activity is silently dropped or duplicated and that unresolved reviews are counted.

Priority: HIGH

### 3. formalize-continuity-review-without-synthetic-activities

What to do:
- Complete the activity-gap review workflow for the documented gap from 2026-06-26 through 2026-07-05.
- Support and validate exactly these continuity classifications: rest, illness, travel, missed_recording, and missing_source_data.
- Require actor, decision time, reason, and source evidence or an explicit no-source-evidence statement before a review can close.
- Keep the gap as a review decision only. Never create synthetic activities, mileage, elevation, duration, load, or recovery records from a classification.
- Ensure gap classifications are included in audit output and are available to coaching rationale generation as a data limitation.

Where:
- Update the continuity review model, review service, audit logging, activity-gap detection, and tests.
- Use the existing activity review and audit persistence mechanisms.
- Do not modify the canonical FIT import records to make the gap disappear.

Success criteria:
- All five classifications are represented in validation and test fixtures.
- An open gap cannot be closed without the required provenance fields.
- A closed gap classification creates no activity row and changes no activity load totals.
- The documented gap remains visible as a classified interval.
- Reopening or editing a review creates an audit event and does not erase prior decisions.

How to verify:
- Run tests covering each classification, missing required fields, explicit no-source-evidence, reopening, and editing.
- Compare activity count, distance, duration, and load before and after classifying the gap; values must not increase because of the classification.
- Run the audit report and verify the gap decision and its complete provenance.
- Confirm the current corpus remains 57 activities unless a real source import independently adds a record.

Priority: HIGH

### 4. capture-confirmed-strength-history

What to do:
- Implement one complete real-data strength workflow using an explicitly entered or imported athlete session, without inventing historical sessions.
- Support session, exercise, and set capture, including the fields already defined by the strength contract.
- Add review, confirmation, editing, deletion, and audit behavior.
- Keep strength_load null when no confirmed strength sessions exist. Distinguish a confirmed zero-load session from absent strength history.
- Include confirmed strength load in combined load only after the session passes the required review and confirmation state.

Where:
- Update `strength.py`, its persistence layer, review and audit services, combined-load calculation, and tests.
- Follow the existing strength schema and `sessions -> exercises -> sets` structure.
- Add deterministic test fixtures and a clearly marked non-production sample workflow if no athlete-authorized session is available locally.

Success criteria:
- A real or explicitly authorized test session can be created with exercises and sets.
- The session can be reviewed, confirmed, edited, and deleted with an audit trail.
- Unconfirmed or deleted sessions do not contribute to confirmed combined load.
- Confirmed sessions contribute exactly once and repeated evaluation is idempotent.
- No-session output remains null rather than zero.
- The workflow does not fabricate historical strength data.

How to verify:
- Run strength schema and service tests.
- Execute an end-to-end test through create, review, confirm, edit, delete, and audit operations.
- Verify combined load before confirmation, after confirmation, after repeated calculation, and after deletion.
- Inspect stored records to distinguish absent strength history from a confirmed zero-load session.

Priority: HIGH

### 5. implement-gated-weather-enrichment

What to do:
- Implement a provider adapter using an approved weather provider such as Open-Meteo or the provider already selected by the repository.
- Keep the existing consent and location gate as a hard prerequisite.
- Persist privacy-preserving observations with observation timestamp, timezone context, temperature, relative humidity, wind speed and direction, dew point or equivalent, precipitation and conditions when available, provider, retrieval status, freshness, and provenance.
- Do not add raw latitude or longitude columns to `weather_observations` and do not persist raw coordinates elsewhere unless an explicit privacy decision and migration authorize it.
- Handle provider success, timeout, malformed response, unavailable response, missing consent, missing location, and repeated enrichment idempotently.
- Never block core activity import when weather enrichment fails.

Where:
- Update `weather.py`, weather persistence and migrations, the consent and location gate, provider adapter code, and weather tests.
- Preserve the existing weather schema privacy test and expand it as needed.
- Store only the minimum location context needed to explain the observation without retaining raw coordinates.

Success criteria:
- The provider is called only when consent and location prerequisites pass.
- Successful responses are validated and persisted with provenance and freshness.
- Timeout, malformed, unavailable, missing-consent, and missing-location cases produce explicit statuses without corrupting activity data.
- Repeating the same enrichment request does not create duplicate observations.
- `weather_observations` contains no latitude, longitude, lat, or lon columns.
- Coaching output can distinguish observed weather from unavailable weather.

How to verify:
- Run unit tests with deterministic mocked provider responses for success and every failure mode.
- Run schema inspection against `PRAGMA table_info` and verify that raw coordinate columns are absent.
- Execute enrichment twice for the same activity and confirm one logical observation.
- Test activity ingestion with a provider timeout and confirm that the activity still imports successfully.
- Run consent and authorization tests to prove weather access boundaries.

Priority: HIGH

### 6. make-coaching-rationales-deterministic-and-auditable

What to do:
- Document and enforce the six existing coaching control states, including refusal and confirmation-required behavior.
- Add deterministic fixtures for every supported state and for missing profile, unresolved timezone, absent strength, absent weather, and unavailable split-level data.
- Persist or emit rationale snapshots containing the evaluated data window, stable input references or input values, algorithm version, missing or uncertain inputs, decision state, human-readable reason, and safety boundary.
- Ensure repeated evaluation with identical inputs produces identical rationale content apart from explicitly defined metadata such as generation time.
- Keep `strength_load` null when strength history is absent and make that limitation explicit in the rationale.
- Ensure facts are distinguished from provisional coaching interpretation.

Where:
- Update `recommend.py`, coaching state definitions, rationale serialization and persistence, algorithm versioning, and tests.
- Update `DATA_QUALITY.md`, `TRAINING_LOAD_METHODOLOGY.md`, `COACHING_SAFETY_BOUNDARIES.md`, and `DATA_QUALITY_TERMINOLOGY.md` where they describe recommendation behavior.
- Do not add HR-zone logic or unsupported historical corpus metrics.

Success criteria:
- Every supported coaching state has a deterministic fixture and expected result.
- Each rationale includes window, inputs or stable references, algorithm version, limitations, state, and human-readable reason.
- Identical inputs produce equivalent rationale snapshots.
- Missing or uncertain data cause refusal, confirmation-required, or clearly provisional output according to the existing contract.
- Rationale text explicitly identifies absent weather, absent strength sessions, unresolved timezone reviews, and unavailable split data when relevant.
- No rationale claims an HR-zone distribution or other unsupported metric.

How to verify:
- Run the complete coaching test suite twice with identical fixtures and compare serialized rationale outputs after excluding approved metadata.
- Inspect representative rationale snapshots for every control state.
- Test that absent strength history is represented as null and not zero.
- Test that changing one input or resolving one limitation changes only the expected rationale fields.
- Search generated output and documentation for unsupported HR-zone claims and rejected historical count premises.

Priority: HIGH

### 7. stabilize-running-load-before-progression

What to do:
- Update recommendation policy so incomplete continuity, profile, and timezone provenance reduces or blocks progression recommendations.
- Prefer stable weekly loading over rapid rebound after a low week.
- Change only one major stressor at a time: mileage, elevation, or intensity.
- Preserve rest and low-impact recovery recommendations.
- Describe load ratios and other proxies as provisional indicators, never as definitive injury diagnoses.
- Include the data limitations that affected each recommendation.

Where:
- Update the coaching policy and recommendation modules, rationale generation, training methodology documentation, and deterministic coaching fixtures.
- Use only verified activity data and the existing load calculations.
- Do not add HR-zone rules or unsupported injury metrics.

Success criteria:
- An unresolved continuity or timezone state prevents an unjustified progression recommendation or marks it explicitly provisional.
- Recommendations favor consistency and single-stressor progression.
- Rest and recovery days remain represented.
- Output includes a safety disclaimer and the specific missing data affecting confidence.
- No recommendation presents a provisional load proxy as a medical diagnosis.

How to verify:
- Run fixtures for stable history, volatile history, unresolved reviews, and missing profile fields.
- Verify that recommendations become more conservative when unresolved reviews are introduced.
- Inspect rationale snapshots for the selected stressor and stated limitations.
- Run the complete coaching and regression test suite.

Priority: MEDIUM

### 8. build-long-run-pace-durability

What to do:
- Add conservative long-run durability guidance based on distance-band evidence and comparable-route context.
- Prefer mostly easy long runs, flatter or moderate-elevation routes during durability blocks, and limited controlled end segments only after consistent symptom-free training.
- Include fueling practice for runs longer than approximately 75 minutes where appropriate.
- Do not claim measured within-run pace decay because per-mile splits are unavailable.
- Treat elevation as a confounder when comparing pace across activities.

Where:
- Update coaching policy, recommendation rationale templates, training methodology documentation, and deterministic fixtures.
- Use existing activity distance, duration, elevation, and route context fields only.
- Do not introduce fabricated splits or unsupported performance metrics.

Success criteria:
- Recommendations distinguish distance-band durability from within-run split decay.
- Elevation and route comparability affect interpretation.
- Long-run progression is gated by recent consistency and unresolved data quality issues.
- Fueling and recovery guidance is included where the duration threshold applies.
- Output labels the evidence as provisional coaching interpretation.

How to verify:
- Run fixtures with comparable and non-comparable routes, high and low elevation, and missing split data.
- Confirm that no synthetic split records are created.
- Inspect rationale output for the distance-band limitation and elevation confounder.
- Run the complete recommendation test suite.

Priority: MEDIUM

### 9. introduce-conservative-runner-strength

What to do:
- Add conservative strength recommendations only when the athlete confirms no active injury limitation and the strength data boundary permits recommendation.
- Recommend two low-to-moderate-volume full-body sessions per week, using a three-week build and one-week deload pattern.
- Cover a hinge, unilateral lower-body movement, calf work, trunk work, and modest upper-body support.
- Use RPE or RIR progression until confirmed athlete history exists.
- Avoid failure training and avoid heavy lower-body work immediately before the long run.
- Keep absent strength history as null and state that recommendations are not based on measured strength ratios, asymmetry, or lifting fatigue.

Where:
- Update coaching recommendation rules, strength-related rationale templates, safety boundaries, and tests.
- Integrate with the confirmed strength workflow without inventing sessions or loads.
- Do not calculate strength-to-bodyweight ratios until required profile and strength data exist.

Success criteria:
- Recommendations are gated by injury confirmation and relevant profile or data limitations.
- The proposed schedule and movement categories are represented without prescribing unsupported absolute loads.
- The engine does not claim measured strength progression, asymmetry, or lifting fatigue without confirmed data.
- Strength recommendations do not silently convert absent strength history into zero training stress.

How to verify:
- Run fixtures with no strength sessions, confirmed sessions, active injury limitation, and missing profile values.
- Verify the recommendation state and rationale for each fixture.
- Confirm no fabricated strength session is persisted.
- Run strength and coaching regression tests.

Priority: MEDIUM

### 10. harden-bridge-and-release-quality-gates

What to do:
- Preserve the existing content-derived brief_id behavior and cross-second idempotency.
- Configure a repository-appropriate linter, formatter, and type checker where applicable.
- Add a dependency lockfile using the project's supported dependency tooling.
- Add CI that installs locked dependencies and runs tests, linting, formatting checks, and type checks.
- Document and test a backup and restore procedure for the local database and configuration needed to recover it.
- Add regression coverage for bridge publication, unchanged-brief no-op behavior, and changed-brief publication.

Where:
- Update `pyproject.toml`, dependency lock files, CI workflow files, backup and restore documentation, bridge code, and tests.
- Use the repository's existing Python tooling conventions where present.
- Do not weaken existing privacy, provenance, or schema tests to make the gates pass.

Success criteria:
- CI runs automatically on pull requests and pushes to the main branch.
- Lint, format, type, and test commands are explicit and reproducible.
- Dependencies are pinned through a committed lockfile.
- Backup and restore are documented and pass an automated or scripted smoke test.
- Unchanged brief content remains a no-op even when publication occurs across clock boundaries.
- Changed brief content creates a new content-derived identity.

How to verify:
- Run every configured local quality command from a clean environment.
- Execute CI-equivalent commands locally and inspect the workflow definition.
- Run the backup, delete or move the test database, restore it, and verify representative records and audit history.
- Run bridge idempotency tests with a clock advanced by at least 90 seconds.
- Confirm the complete suite passes before committing.

Priority: HIGH

### 11. document-conservative-training-signals

What to do:
- Update documentation and generated recommendation terminology so verified metrics, provisional coaching interpretation, unavailable data, and refusal states are distinct.
- Explicitly document missing splits, absent HR-zone classification, absent weather observations, absent strength sessions, unresolved timezone reviews, and profile limitations where they affect interpretation.
- Document that the current corpus is 57 activities and that unsupported historical count discrepancies are not part of the product model.
- Remove or prevent unsupported exact claims from generated reports.
- Ensure safety documentation states that recommendations are not medical diagnoses.

Where:
- Update `DATA_QUALITY.md`, `FIT_AUDIT.md`, `STRENGTH_DATA_CONTRACT.md`, `TRAINING_LOAD_METHODOLOGY.md`, `COACHING_SAFETY_BOUNDARIES.md`, `DATA_QUALITY_TERMINOLOGY.md`, and `WEATHER_ENRICHMENT_GATE.md`.
- Update rationale templates and report-generation code as needed.
- Do not add HR-zone classification or attempt to reconcile rejected historical counts.

Success criteria:
- Documentation defines the difference between verified fact, provisional interpretation, unavailable data, and refusal.
- Generated rationale identifies relevant missing data consistently.
- No document or generated output presents unsupported HR-zone distributions or rejected corpus counts as facts.
- The current 57-activity corpus statement is consistent across live documentation.
- Safety and privacy boundaries are explicit.

How to verify:
- Run documentation and report-generation tests.
- Search the repository and generated outputs for rejected 55, 56, or 59 corpus claims and unsupported HR-zone metrics.
- Review representative reports for explicit limitation labels.
- Compare terminology across the listed documents for contradictions.

Priority: MEDIUM

---
## NEXT SUPERVISOR CHECK

On the next run, verify the following in order:

1. `complete-athlete-profile-and-timezone-provenance`: confirm profile round-trip tests, validation behavior, and complete provenance for at least one accepted timestamp review and one explicit no-source-evidence review.
2. `formalize-continuity-review-without-synthetic-activities`: confirm all five classifications are validated, the documented gap can be closed with provenance, and no synthetic activity or load is created.
3. `establish-authenticated-athlete-ownership`: confirm whether authentication and ownership enforcement exist across every listed domain and whether cross-athlete isolation tests pass.
4. `capture-confirmed-strength-history`: confirm whether an authorized real or test session completed create, review, confirmation, edit, deletion, and audit, and whether combined load updates correctly.
5. `implement-gated-weather-enrichment`: confirm provider adapter behavior, privacy-preserving persistence, failure handling, and enrichment idempotency.
6. `make-coaching-rationales-deterministic-and-auditable`: confirm deterministic fixtures for every coaching state and rationale snapshots containing all required fields.
7. `harden-bridge-and-release-quality-gates`: confirm CI, quality tooling, dependency locking, and a tested backup and restore procedure.
8. Re-read the live inventory and verification report to ensure the canonical corpus remains 57 activities and that no rejected premise has reappeared as an implementation task or generated claim.
