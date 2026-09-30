THIS IS UNVERIFIED LLM OUTPUT - review before acting.

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-09-30
## Run by: CrewAI Flow Supervisor

---
## VERIFICATION (from previous brief)

- `no-previous-tasks`: NOT APPLICABLE. The previous `SUPERVISOR_BRIEF.md` contained no actionable task definitions or stable task slugs.
- `source-availability-check`: COMPLETED. `SUPERVISOR_BRIEF.md`, `docs/IMPLEMENTATION_INVENTORY.md`, and `docs/VERIFICATION_REPORT.md` were readable; `OPENCODE_INSTRUCTIONS.md` was unavailable from GitHub and absent from searched local project directories.
- `foundation-verification`: COMPLETED IN LIVE DOCUMENTATION ONLY. The verification report records 152 passed tests and 1 skipped test, 56 imported activities, 56 raw SHA-256 references, 56 FIT files inspected, and 0 parse failures.
- `partial-capability-review`: COMPLETED IN LIVE DOCUMENTATION ONLY. Health identity isolation, weather provider integration, live brief transport, profile completion, strength data, and activity confirmation remain incomplete or limited as documented below.

---
## SUPERVISOR DECISIONS

The platform has a credible canonical-data, provenance, safety, and testing foundation. It is not yet ready for reliable personalised coaching at scale because several inputs and trust boundaries are incomplete.

The first priority is to reconcile the reported 59 retained activities with the verified 56 imported activities. Training load, continuity, and coaching outputs must use one explainable canonical dataset. No performance or injury-related conclusion should be treated as authoritative until the three-record difference is identified and represented explicitly.

Personalisation must be gated on a complete athlete profile. The empty `profile.json` prevents reliable local dates, timezone-aware continuity, location policy, and normal running-load operation. Original UTC timestamps must remain unchanged, while derived local timestamps must include provenance and confidence.

The activity confirmation loop is a required product capability. The recommendation engine correctly refuses to proceed while 11 recent activities await confirmation, but the platform needs a review queue that distinguishes rest, illness, travel, missed recording, and missing source data without fabricating sessions.

Authentication and athlete-level isolation must be implemented before medical records, cloud coaching, or broad deployment. Consent and access logging alone are not sufficient. Every athlete-owned activity, strength session, health record, weather record, recommendation, and audit event must be attributable to an authenticated athlete.

The strength domain is implemented but has no real data. A reliable strength-session capture path is needed before the system can calculate strength load, lifting fatigue, interference, progression, or strength-to-bodyweight measures.

Weather enrichment should be implemented behind the existing consent and location gate after profile readiness. Weather must be stored with provider and retrieval provenance, and weather-adjusted predictions must remain disabled until enough matched data exists.

The existing 7/14/28-day load calculations and refusal-first recommendations should be connected into an end-to-end coaching state only after confirmation, profile, identity, and provenance requirements are satisfied. Incomplete evidence must produce `ready`, `provisional`, `confirmation_required`, or `insufficient_data` states rather than false precision.

The brief bridge is not a live delivery system. Stable content identity and idempotency should be fixed before adding a cloud endpoint, tunnel, or scheduled ingest job. Dashboard work remains out of scope for this run because the existing dashboard is local-only and unversioned.

Advanced prediction and medical-record functionality are deferred. Release engineering gaps, including missing CI, linting, formatting, type checking, and dependency locking, should be addressed before broadening the deployment surface.

---
## OPENCODE TASKS

1. `reconcile-activity-count-and-provenance`

What to do:
- Inspect the repository's FIT inventory, canonical activity tables or files, import services, audit scripts, and verification documentation.
- Produce a source-to-canonical reconciliation report explaining why the coaching audit reports 59 activities while verified application import reports 56.
- Compare source filenames, activity identifiers, hashes, timestamps, local dates, import status, duplicate status, and exclusion or pending status.
- Identify each of the three records that account for the discrepancy, or document exactly which source evidence is missing.
- Define one canonical activity count for application calculations.
- Represent excluded, duplicate, pending, or unverified source records explicitly rather than silently dropping them.
- Add a regression test that fails when the audit dataset and canonical application dataset diverge without an explainable status.
- Update `docs/IMPLEMENTATION_INVENTORY.md` and `docs/VERIFICATION_REPORT.md` with the reconciliation result and the canonical counting rule.

Where:
- Repository root.
- Existing activity import, canonical record, audit, and verification modules.
- Relevant data and documentation under `docs/`.

How to verify success:
- Run the existing test suite and the new reconciliation tests.
- The report names all records in the 59-versus-56 difference or records a specific evidence limitation.
- A single documented canonical count is used by load and continuity calculations.
- Re-running the import and audit produces no unexplained count difference.
- Evidence includes the command output and final counts in `docs/VERIFICATION_REPORT.md`.

Priority: HIGH

2. `profile-and-timezone-provenance`

What to do:
- Inspect the existing profile model, `profile.json` handling, timestamp parsing, filename date parsing, location consent, weather gate, and recommendation prerequisites.
- Implement an explicit profile-completion state covering timezone, locale, units, training goals, location consent, and the repository's existing age or birth-year policy if required by current interfaces.
- Preserve every original UTC timestamp.
- Store a derived local timestamp and local date with provenance values `confirmed`, `inferred`, or `unknown`.
- Require review for cross-midnight activities and ambiguous filename-derived dates, including the activity displayed as 26 July at 01:10 with a UTC timestamp on 27 July.
- Prevent weather enrichment and local-date-dependent coaching from claiming confirmed precision when profile or timestamp confidence is incomplete.
- Keep the empty profile safe and non-personalised; do not invent athlete values.
- Add migration or validation behavior that clearly reports incomplete required profile fields.

Where:
- Repository root.
- Existing profile, timestamp, activity normalization, consent, and recommendation modules.
- `profile.json` or its configured replacement.
- Related tests and `docs/`.

How to verify success:
- Tests cover confirmed, inferred, unknown, and cross-midnight timestamp states.
- An incomplete profile causes an explicit non-ready or confirmation-required state rather than silently using assumed values.
- Original UTC values remain unchanged after processing.
- A completed test profile produces deterministic local dates.
- Weather location policy rejects or blocks requests when required profile and consent fields are absent.
- Update `docs/VERIFICATION_REPORT.md` with profile validation and timezone test results.

Priority: HIGH

3. `activity-confirmation-and-continuity`

What to do:
- Inspect the recommendation refusal path, activity confirmation fields, import status, missing-session handling, and recent activity views.
- Implement a review queue for unconfirmed activities, suspicious gaps, duplicate candidates, and records with uncertain local dates.
- Allow an authenticated athlete to classify a gap as `rest`, `illness`, `travel`, `missed_recording`, or `missing_source_data`.
- Preserve the distinction between no activity occurring and no activity being recorded.
- Do not create synthetic activities from gap classifications.
- Recompute training load and recommendations only after relevant confirmation state changes.
- Ensure the current 11 unconfirmed recent activities are visible and actionable through the review path.
- Preserve refusal-first behavior when required confirmations remain unresolved.

Where:
- Repository root.
- Existing activity, recommendation, audit, and load calculation services.
- Existing local API or command-line review interfaces.
- Related tests and `docs/`.

How to verify success:
- A test creates unconfirmed activities and a data gap, resolves each through the supported state transitions, and verifies the resulting load and recommendation state.
- Unresolved confirmations return `confirmation_required`.
- Gap classifications are stored with actor, timestamp, reason, and provenance.
- No synthetic activity is created for a classified gap.
- The review queue distinguishes missing data from confirmed rest.
- Existing safety tests continue to pass.

Priority: HIGH

4. `identity-consent-and-athlete-isolation`

What to do:
- Inspect all data access paths for canonical activities, strength sessions, health records, weather data, recommendations, profiles, and audit logs.
- Implement authenticated athlete identity and role boundaries using the repository's existing architecture and dependency conventions.
- Add an athlete identifier to every athlete-owned record that lacks one, with an explicit migration strategy for existing local data.
- Enforce athlete-level authorization on reads, writes, updates, imports, exports, recommendations, weather requests, consent changes, and audit events.
- Make consent grants and revocations attributable to the authenticated athlete.
- Preserve access logging and include actor, target athlete, resource, action, decision, and timestamp.
- Do not add medical-record integration in this task. Keep it blocked until isolation and authorization are verified.
- Ensure local single-athlete operation remains usable through an explicit local identity or development configuration that cannot bypass authorization in production mode.

Where:
- Repository root.
- Existing health consent, access logging, profile, activity, strength, weather, recommendation, and brief transport modules.
- Database schema and migrations.
- Authentication and authorization tests.
- `docs/`.

How to verify success:
- Cross-athlete read, write, update, import, export, consent, and recommendation tests are denied.
- Authorized same-athlete operations succeed.
- Every protected access produces an auditable decision.
- Consent revocation prevents subsequent protected access where required.
- Existing privacy and safety tests remain passing.
- The verification report explicitly states that medical records remain blocked until this task is complete and reviewed.

Priority: HIGH

5. `strength-session-ingestion`

What to do:
- Inspect the existing strength schema, service, load calculation, terminology, and recommendation integration.
- Implement a reliable strength-session input or import path for exercise, sets, repetitions, load, unit, RPE or RIR, rest, bodyweight where available, soreness, confirmation state, and session timestamp.
- Add exercise identity and movement-pattern taxonomy using shared terminology.
- Calculate estimated 1RM only for suitable source sets, and store the formula, inputs, and provenance.
- Feed confirmed strength sessions into the existing 7/14/28-day load windows.
- Store whether each session is athlete-confirmed, imported, or draft.
- Keep strength-based recommendations provisional while no confirmed real sessions exist.
- Do not infer strength-to-bodyweight ratios without valid bodyweight and strength inputs.

Where:
- Repository root.
- Existing strength domain, training-load, terminology, recommendation, and migration modules.
- Related tests and `docs/`.

How to verify success:
- Tests cover valid sessions, drafts, imported sessions, athlete confirmation, invalid units, missing required set fields, and estimated 1RM provenance.
- A confirmed strength session produces a non-null strength load in the correct windows.
- An unconfirmed or draft session does not affect confirmed coaching load.
- Movement-pattern terms match the shared terminology contract.
- The verification report clearly states whether real athlete strength data is present after implementation.

Priority: HIGH

6. `weather-provider-enrichment`

What to do:
- Inspect the existing weather gate, location consent, profile validation, activity timestamp handling, privacy guard, and data storage conventions.
- Integrate a provider such as Open-Meteo behind the existing gate, using approved location and activity time only when profile and consent requirements are satisfied.
- Store the raw provider response or a durable reference, provider name, query coordinates or grid reference, retrieval time, activity timestamp, schema version, and request status.
- Store available temperature, relative humidity, dew point, wind speed, wind direction, precipitation, and conditions.
- Distinguish observed, estimated, interpolated, unavailable, and consent-blocked weather.
- Make the privacy guard conservative for bare single-coordinate cases and route ambiguous locations to manual review.
- Add weather context to activity detail and trend outputs without applying automatic performance correction.
- Keep weather-adjusted predictions disabled until a documented minimum matched-data threshold exists.

Where:
- Repository root.
- Existing weather gate, profile, consent, privacy, activity enrichment, and reporting modules.
- Configuration and dependency files.
- Related tests and `docs/`.

How to verify success:
- Tests cover missing profile, missing consent, blocked location, provider success, provider timeout, malformed response, unavailable weather, and repeat enrichment.
- A permitted request stores provider and provenance fields.
- A blocked request stores no unauthorized location or weather data and returns an explicit blocked state.
- Repeated enrichment is idempotent for the same activity, provider, query, and schema version.
- Weather is shown as explanatory context only; no weather-adjusted prediction is produced.
- Update the verification report with provider configuration and test evidence without exposing secrets.

Priority: MEDIUM

7. `confirmed-training-load-and-coaching-loop`

What to do:
- Inspect canonical activity loading, strength load integration, 7/14/28-day windows, elevation load, long-run metrics, recommendation safety boundaries, profile prerequisites, and confirmation states.
- Define and implement coaching states `ready`, `provisional`, `confirmation_required`, and `insufficient_data`.
- Require canonical, confirmed data and a sufficiently complete profile before normal personalised recommendations.
- Connect confirmed running and strength records into combined load outputs.
- Expose rolling volume, long-run share, consecutive running days, elevation load, strength load, and recovery or confirmation confidence labels.
- Preserve refusal-first behavior for missing identity, consent, profile, confirmation, provenance, or source data.
- Encode the current conservative reset guidance as provisional coaching policy: approximately 6-8, 9-11, 12-14, and 14-16 running miles over four weeks only when recovery remains normal; long runs approximately 4, 5, 6, and 6-7 miles; most running easy; avoid stacking hills, quality running, long runs, and heavy lower-body lifting.
- Do not present these ranges as medical advice or as a substitute for athlete confirmation.

Where:
- Repository root.
- Existing load, recommendation, activity confirmation, strength, profile, safety, and reporting modules.
- Related tests and `docs/`.

How to verify success:
- Tests cover each coaching state and all major blocking conditions.
- Confirmed activity and strength fixtures produce deterministic 7/14/28-day outputs.
- Pending confirmation prevents `ready`.
- Missing profile or athlete identity prevents personalised output.
- Incomplete weather does not block basic coaching when weather is not required, but cannot be represented as known.
- The output includes confidence and provenance labels.
- Existing 152-pass baseline remains passing, with any changed expectations documented.

Priority: MEDIUM

8. `brief-transport-and-operational-delivery`

What to do:
- Inspect the brief bridge, `commit_brief()`, transport schemas, delivery records, configuration, and operational documentation.
- Define a stable brief identity based on source identity, athlete identity, content or canonical payload, and schema version.
- Fix idempotency so repeated delivery does not depend on a regenerated `captured_utc` value. Preserve capture time as metadata, not as the sole identity input.
- Add tests for repeated commits in the same second and across different seconds.
- Do not configure a cloud endpoint, tunnel, or scheduled ingest until authentication, athlete isolation, confirmation, and provenance controls are verified.
- Document the deferred operational deployment requirements.
- Add CI, dependency locking, linting, formatting, and type-checking configuration only if compatible with the repository's current language and package tooling; otherwise document the exact blocker and a safe follow-up.

Where:
- Repository root.
- Existing brief bridge implementation, transport schemas, configuration, build files, and operational documentation.
- `docs/`.

How to verify success:
- Identical source content and identity produce one logical delivery regardless of commit time.
- Changed content or source identity produces a new delivery.
- Tests prove the timestamp no longer breaks idempotency.
- No secrets, personal coordinates, or unauthenticated cloud endpoint are introduced.
- Documentation states that live cloud delivery remains deferred until the required controls are complete.
- Any added quality gates run successfully in a clean checkout.

Priority: LOW

---
## NEXT SUPERVISOR CHECK

On the next run, verify in this order:

1. `reconcile-activity-count-and-provenance` has identified the 59-versus-56 discrepancy and established a documented canonical count.
2. `profile-and-timezone-provenance` has implemented explicit profile and timestamp confidence states without inventing athlete data.
3. `activity-confirmation-and-continuity` has a working review path for the 11 pending activities and distinguishes missing records from confirmed rest.
4. `identity-consent-and-athlete-isolation` has passing cross-athlete authorization tests before any medical or cloud capability is expanded.
5. The full test suite still passes, and all verification documentation identifies remaining live-data limitations.
6. No task has enabled weather-adjusted predictions, medical-record integration, or cloud brief delivery while the stated gates remain incomplete.
