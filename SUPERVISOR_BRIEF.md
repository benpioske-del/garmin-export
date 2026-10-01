THIS IS UNVERIFIED LLM OUTPUT - review before acting.

# Athletic Performance Hub \ Supervisor Brief
## Generated: 2026-10-01
## Run by: CrewAI Flow Supervisor

---
## VERIFICATION (from previous brief)

- `reconcile-activity-count-and-provenance` - BLOCKED - Live documents verify 56 readable FIT files and 56 canonical activities, but provide no record-level reconciliation of the separately referenced 55-record and 59-record sources.
- `build-identity-consent-and-athlete-isolation` - BLOCKED - The inventory and verification report confirm there is no authentication, API, or multi-athlete isolation.
- `complete-profile-and-timestamp-provenance` - IN PROGRESS - `profile.json` remains all null, 56 timezone reviews remain open, and complete per-activity timestamp provenance is not evidenced.
- `implement-activity-confirmation-and-continuity-queue` - IN PROGRESS - There are 57 open reviews, including an eight-day activity gap and 11 recent activities awaiting confirmation, but a complete auditable review workflow is not evidenced.
- `harden-coaching-state-and-confirmed-load-loop` - IN PROGRESS - Versioned 7/14/28-day load calculation and refusal-first recommendations exist, but the complete coaching state contract and confirmed combined-load loop are not evidenced.
- `add-confirmed-strength-session-ingestion` - IN PROGRESS - The strength schema and service are tested, but no real strength sessions or confirmed strength load exist.
- `implement-consented-weather-provider-enrichment` - IN PROGRESS - The consent gate and no-coordinate weather schema restriction exist, but no provider or persisted weather enrichment workflow exists.
- `stabilize-brief-transport-and-quality-gates` - IN PROGRESS - The brief bridge and 152 passing tests exist, but cross-second idempotency, CI, static checks, dependency locking, and recovery verification remain unresolved.

---
## SUPERVISOR DECISIONS

The canonical activity store remains the current system of record. The available evidence supports 56 readable FIT files and 56 imported activities, but it does not reconcile the separately referenced 55-record and 59-record sources. The next implementation must produce an auditable record-level reconciliation rather than changing the canonical count to match an unsupported expectation.

The empty profile is a central blocker. It prevents trusted timezone decisions, running load availability, and weather location policy. The implementation must collect explicit athlete-supplied values and must not guess timezone, location, goals, or physiological values. Timestamp provenance must be stored per activity and must distinguish confirmed, inferred, and unknown values.

Activity review must be completed before continuity and coaching conclusions are treated as reliable. Review decisions must be auditable, idempotent, authorization-aware, and unable to create synthetic activities. The documented continuity gap must remain unresolved until the athlete provides an appropriate classification.

The coaching engine must remain refusal-first. It may calculate provisional values, but it must not issue confident progression advice while recent activities are unconfirmed or required profile data are unavailable. The exact states `ready`, `provisional`, `confirmation_required`, and `insufficient_data` must be implemented and fixture-tested. Missing strength data must remain distinct from zero strength load.

The strength domain should now receive real, auditable data through manual entry or structured import. Only confirmed sessions may contribute to combined load. Relative strength and estimated 1RM outputs must remain unavailable unless their required inputs and provenance are present.

Weather enrichment is downstream of profile, consent, and timestamp work. It must use a consent-aware provider, preserve observation provenance, avoid storing raw coordinates in the weather observation table, and expose explicit unavailable or consent-blocked states. Weather must not be used to manufacture causal performance explanations.

Identity and consent are launch blockers for any multi-athlete or cloud-facing product. The local single-subject boundary must not be represented as authentication or authorization. Ownership, authenticated access, consent revocation, sensitive-access auditing, and cross-athlete isolation must be implemented before exposing protected data through shared interfaces.

Operational reliability is a near-term requirement. The brief bridge must have stable idempotency across time boundaries, and the repository needs reproducible quality gates, CI, dependency locking, and tested backup and restore procedures.

---
## OPENCODE TASKS

1. ### reconcile-source-to-canonical-activity-provenance

   **What to do:** Create a committed record-level reconciliation artifact for all available activity sources. Account for the 55-record audit dataset, the historical 59-record source, and the current 56-activity canonical store without changing or inventing canonical activities. Use stable source identity and document every divergence with one of these classifications: `duplicate`, `excluded_source_record`, `parse_or_import_difference`, `date_or_time_identity_difference`, `malformed_or_unreviewed`, or `legitimate_additional_activity`. Preserve source filename, source timestamp, import result, and canonical activity identifier where available. Add regression tests for repeated imports and changed source inputs.

   **Where:** Repository source and tests that own activity import and canonical storage; create or update a durable report under `docs/`, preferably `docs/ACTIVITY_RECONCILIATION.md`. Update `docs/IMPLEMENTATION_INVENTORY.md` and `docs/VERIFICATION_REPORT.md` with the resulting evidence.

   **Success criteria:** Every record in the 55-record and 59-record sources is accounted for. Every canonical activity is traceable to stable source identity or explicitly classified as an additional activity. Counts 55, 56, and 59 are explained without silent merging, deletion, or fabrication. Repeated imports are idempotent and future divergence tests exist.

   **How to verify:** Run the import and reconciliation tests. Review the committed report and confirm that it contains record-level mappings, classifications, source provenance, and count totals. Run the import twice and confirm that no duplicate canonical activities are created.

   **Priority: HIGH**

2. ### complete-explicit-profile-and-timestamp-provenance

   **What to do:** Implement an explicit athlete profile completion workflow and make timestamp provenance first-class on every activity. Store an immutable local athlete identifier, timezone policy, locale, units, goals, preferred activity identity, consent choices, and any physiological values only when supplied or explicitly marked unknown. For every activity, store source filename date, recorded UTC timestamp, timezone used, provenance status (`confirmed`, `inferred`, or `unknown`), and inference reason. Add a cross-midnight review workflow and require consented location policy before weather lookup.

   **Where:** Profile persistence and activity model/service code; existing `profile.json`; activity migrations and tests; supporting documentation under `docs/`.

   **Success criteria:** A valid profile can be entered, persisted, reloaded, and validated without guessed values. Every existing activity has the required timestamp provenance fields. Unknown values remain unknown. Cross-midnight review changes are auditable and do not silently alter the source timestamp.

   **How to verify:** Run profile, migration, timestamp, and cross-midnight tests. Reload the profile and inspect representative activities on both sides of a UTC/local-date boundary. Confirm that load and weather features remain blocked when required profile or consent values are absent.

   **Priority: HIGH**

3. ### implement-auditable-activity-review-and-continuity-queue

   **What to do:** Finish the activity confirmation and continuity review workflow. Provide explicit allowed transitions for timezone, activity confirmation, and continuity reviews. Persist actor, decision timestamp, reason, original value, revised status, and source provenance for every decision. Support the required continuity classifications `rest`, `illness`, `travel`, `missed_recording`, and `missing_source_data`. Never create synthetic activities to fill a gap. Make repeated decisions idempotent and reject unauthorized review actions.

   **Where:** Existing activity review, audit, and continuity modules; database migrations; tests; documentation under `docs/`.

   **Success criteria:** The 56 timezone reviews, the 11 recent confirmation reviews, and the documented continuity gap can be queried through an actionable queue. Each decision has a complete audit record. Invalid transitions and unauthorized actions fail safely. Repeating an accepted decision produces no duplicate effect or audit ambiguity. No synthetic activity is created.

   **How to verify:** Run review-queue, authorization, idempotency, transition, and recomputation tests. Exercise each required continuity classification and inspect the resulting audit records. Confirm that the continuity gap remains a classification, not an inserted activity.

   **Priority: HIGH**

4. ### establish-local-athlete-identity-and-consent-boundary

   **What to do:** Establish the security foundation for the current single-subject system and future multi-athlete use. Add an immutable athlete identifier and ownership relationships for activities, strength sessions, health records, weather consent, and coaching outputs. Implement authenticated read and write boundaries where interfaces exist, explicit consent grant and revocation enforcement, and auditable sensitive-access and review events. Keep operational telemetry separate from protected health data.

   **Where:** Repository data models, migrations, health consent code, import/export paths, review actions, and any existing interface boundary. Add security documentation and tests under `docs/` and the existing test suite.

   **Success criteria:** Every protected record has an owner. Consent revocation prevents subsequent access or enrichment. Cross-athlete reads and writes are rejected. Sensitive access and review decisions produce audit events. The implementation does not claim cloud authentication where no such interface exists.

   **How to verify:** Run migration and security tests covering ownership, cross-athlete isolation, authenticated reads and writes, consent grant and revocation, import/export, and audit logging. Inspect the schema to confirm ownership is enforced rather than merely documented.

   **Priority: HIGH**

5. ### complete-confirmed-load-and-coaching-state-contract

   **What to do:** Complete the refusal-first coaching loop. Implement and document the exact states `ready`, `provisional`, `confirmation_required`, and `insufficient_data`. Include only records satisfying documented confirmation and timestamp provenance rules in 7-, 14-, and 28-day loads. Keep running load, strength load, and combined load separate; represent absent strength data as unavailable rather than zero. Add low-load re-entry warnings, `hr_data_untrusted` handling when supported by actual evidence, and rationale snapshots containing input data, algorithm version, and decision reason. Include symptoms, terrain, inactivity, confirmation status, and strength load when those inputs are available.

   **Where:** `loadcalc.py`, `recommend.py`, related domain modules, fixtures, tests, and coaching contract documentation under `docs/`.

   **Success criteria:** Each exact coaching state is produced by a deterministic fixture. Unconfirmed or provenance-unknown records cannot produce definitive coaching advice. Confirmed strength records contribute to combined load without converting absent data to zero. Refusal and downgrade outputs explain the blocking inputs. Sharp reductions in confirmed load produce a re-entry warning.

   **How to verify:** Run the complete coaching test suite and inspect fixtures for all four states. Compare load results before and after confirmation. Confirm that recommendation output includes algorithm version, input snapshot, rationale, and uncertainty flags.

   **Priority: HIGH**

6. ### ingest-confirmed-strength-sessions

   **What to do:** Add a real manual-entry or structured-import path for strength sessions. Capture session date, exercise, load, repetitions, sets, effort, provenance, and lifecycle status. Support statuses `planned`, `draft`, `imported`, and `confirmed`, while distinguishing no data from all other states. Make imports idempotent and preserve audit history for edits and deletions. Add estimated 1RM only when its formula, inputs, and provenance are stored. Only confirmed sessions may enter combined training load.

   **Where:** Existing `strength.py`, strength schema and service, import path, load integration, tests, and documentation under `docs/`.

   **Success criteria:** At least one real, provenance-labeled strength session can be created or imported, reviewed, confirmed, edited, and deleted with an audit trail. Repeated import does not duplicate the session. Confirmed sessions affect combined load; planned, draft, and imported-only sessions do not. Relative strength remains unavailable without valid body mass and lifting inputs.

   **How to verify:** Run strength schema, lifecycle, import idempotency, audit, estimated-1RM, and combined-load tests. Inspect a persisted session and its audit history. Verify that deleting or unconfirming the session removes it from confirmed combined load deterministically.

   **Priority: MEDIUM**

7. ### implement-consented-weather-provider-enrichment

   **What to do:** Integrate a consent-aware weather provider, preferably Open-Meteo or an equivalent documented provider, after profile and timestamp prerequisites are available. Persist temperature, humidity, dew point, wind, precipitation, condition code, and apparent temperature when returned. Record provider, retrieval timestamp, observation timestamp, matching method, and confidence/status. Support `observed`, `estimated`, `interpolated`, `unavailable`, and `consent_blocked`. Keep raw coordinates out of `weather_observations`, make enrichment idempotent, and prevent weather-adjusted claims when the match is unavailable or low confidence.

   **Where:** Existing `weather.py`, weather schema and migrations, profile consent policy, provider adapter, activity/trend integration, tests, and documentation under `docs/`.

   **Success criteria:** An authorized, consented request can retrieve and persist attributed weather observations without storing raw coordinates in the weather table. Repeated enrichment is idempotent. Missing consent, location policy, timestamp, provider data, or adequate matching produces the correct explicit status. Activity and trend outputs expose weather context only when quality requirements are met.

   **How to verify:** Run schema privacy, consent, provider adapter, status, matching, idempotency, and integration tests. Inspect `PRAGMA table_info(weather_observations)` for absence of coordinate columns. Test both consented and blocked requests.

   **Priority: MEDIUM**

8. ### stabilize-brief-bridge-and-reproducible-quality-gates

   **What to do:** Fix brief capture idempotency so equivalent commits remain byte-identical across mocked time boundaries, unless the input content or explicit identity changes. Add a cross-second regression test. Configure a formatter, linter, type checker, CI workflow, dependency lockfile, and reproducible test command. Add documented backup and restore verification. Define authentication and replay-protection requirements for any future brief transport endpoint. Replace the skipped Windows symlink behavior with either a tested implementation or an explicit supported-platform policy.

   **Where:** `brief_bridge.py`, bridge tests, `pyproject.toml`, lockfile, CI workflow under `.github/workflows/`, backup tooling and documentation under `docs/`.

   **Success criteria:** Cross-second idempotency is proven by tests. CI runs tests and all configured quality checks on every change. Dependencies are locked and the documented environment reproduces the test suite. Backup restoration is tested. Transport security requirements are documented before enabling a remote endpoint.

   **How to verify:** Run the bridge test suite with mocked timestamps separated by more than one second. Run the complete local quality command and inspect CI configuration. Create a backup, restore it into a clean environment, and verify expected records and integrity checks.

   **Priority: MEDIUM**

9. ### add-durability-and-safe-progression-guardrails

   **What to do:** Add coaching guardrails that prioritize consistency, recovery, and gradual progression over aggressive short-term performance gains. Use confirmed load trends and recovery status to set progression caps. Limit simultaneous increases in mileage, intensity, elevation, and lifting volume. Add controlled long-run development and low-to-moderate initial strength loading. Keep predictions provisional until identity, timestamps, confirmations, and relevant context meet their quality requirements.

   **Where:** Coaching recommendation rules, load trend services, progression fixtures, tests, and documentation under `docs/`.

   **Success criteria:** Recommendations cap progression when confirmed load, recovery, or continuity evidence is insufficient. The system warns against simultaneous multi-factor increases and supports controlled re-entry after inactivity or a sharp load reduction. Predictions identify their uncertainty and do not rely on unsupported data.

   **How to verify:** Run fixtures covering stable progression, inactivity, sharp load reduction, unresolved reviews, new strength history, and missing context. Inspect recommendation rationale to confirm that caps and warnings are tied to confirmed inputs.

   **Priority: LOW**

---
## NEXT SUPERVISOR CHECK

On the next run, verify first that `reconcile-source-to-canonical-activity-provenance` has produced a committed record-level report explaining the 55, 56, and 59 source counts, and that `complete-explicit-profile-and-timestamp-provenance` has stored and reloaded a valid profile with per-activity timestamp provenance.

Then verify that the activity review queue records complete decisions without creating synthetic activities, and that all four coaching states have deterministic fixtures. Confirm whether at least one real strength session has been persisted and whether confirmed strength affects combined load.

Also inspect security tests for ownership and consent revocation, weather tests for provider attribution and privacy, and quality-gate evidence for cross-second bridge idempotency, CI, dependency locking, and backup restoration. Do not treat trend conclusions or production readiness as verified until these artifacts and tests are present.
