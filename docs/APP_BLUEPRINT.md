UNVERIFIED LLM OUTPUT
# Aurora App Blueprint

Platform: Android only (the athlete uses an Android phone; no iOS build)

## Why an app now

Aurora is currently a single-file PWA served by `garmin_server.py` on the athlete's laptop.

Current reference:

- Repository: `benpioske-del/garmin-export`
- Branch: `main`
- Commit: `60baa538f480d7e347030dbe5c84e8c7fd4f8392`
- File: `flow_outputs/aurora_dashboard.html`
- File size: 33,047 bytes

The current analysis covers 74 runs and found the clearest measured weakness in long-run durability:

- 7 of 24 long runs broke down.
- Median estimated breakdown: 7.79 miles, or 52.0% of the run.
- All 4 runs in the 16-mile like-for-like group broke down between 6.97 and 10.16 miles.
- The worst recorded fade was 602 seconds per mile on 2026-06-07, after 6.97 miles, with three stop/walk laps.
- Segment-level export was unavailable.
- The analysis used audited activity-table lap splits.
- Nutrition, hydration, in-run fuelling, sleep, weather and lifting data were not recorded.

The app extends the laptop-based Aurora system. It does not replace the laptop analysis service in the first release.

The first product remains:

- One athlete.
- One Android phone.
- One laptop-hosted Aurora service.
- Local-first encrypted capture.
- Native Android background ingestion and notifications.
- Laptop-side analysis as the authoritative processing environment.

## Capability map

| Capability | Priority | Requirement |
|---|---|---|
| Automatic Garmin sync of new activities | MUST | New Garmin activities arrive in Aurora without manual export, using a supported Garmin data-access path. |
| Automatic Garmin FIT-file acquisition | MUST | Preserve original FIT files, including trackpoints, lap records, heart-rate records and other available data. |
| Garmin integration failure reporting | MUST | Distinguish authorization failure, unavailable network, duplicate activity, malformed FIT file, Garmin source unavailable and laptop-unreachable states. |
| Read Android Health Connect data | MUST | Read sleep, resting heart rate, HRV, weight, hydration and workout records when the source writes them and the athlete grants permissions. |
| Health Connect consent and provenance | MUST | Store source, timestamp, unit, permission state and last-sync state. Distinguish not recorded from unavailable to Aurora. |
| Per-0.1-mile segment data | MUST | Derive pace, heart rate, elevation and stop/walk behavior where the source FIT file contains adequate trackpoints. |
| Segment derivation and breakdown detection | MUST | Keep calculation on the laptop and use the laptop as the authoritative analysis environment. |
| Segment data-quality status | MUST | Label data as measured, derived, estimated or unavailable. Do not present false precision. |
| Reliable background sync of lifts | MUST | Capture bodyweight and strength-session context offline and deliver it to the laptop with retries. |
| Reliable background sync of nutrition | MUST | Capture calories, carbohydrate and protein records offline and deliver them to the laptop with retries. |
| Hydration logging | MUST | Record hydration before and during runs with persistent local storage. |
| In-run fuel logging | MUST | Record timestamp, quantity and type of carbohydrate or other fuel. |
| New-run-analysed notification | MUST | Notify the athlete after a new activity is imported and analysed, with a deep link where available. |
| Sync-failure notification | MUST | Report Garmin, Health Connect and laptop-delivery failures. |
| Rest-day reminders | SHOULD | Use explicit rules based on activity history and available recovery context. Do not claim a validated recovery model. |
| Local encrypted storage | MUST | Encrypt FIT files, Health Connect-derived records, context records, sync queues and pending uploads. |
| Offline-first capture and upload queue | MUST | Save records locally before network delivery and retry later without manual re-entry. |
| Laptop connection and delivery protocol | MUST | Support idempotent activity IDs, duplicate protection, retries and explicit receipt acknowledgements. |
| Home-screen widgets | SHOULD | Show sync state, latest analysed activity, hydration shortcut and pending-upload count. |
| Notification actions for hydration and fuel | SHOULD | Support low-friction phone capture without opening the main app. |
| Share-sheet import of CalTrak CSVs | SHOULD | Receive, retain, validate, deduplicate and queue CalTrak CSV files. The exact parser depends on a supplied CSV. |
| Android activity and context review | SHOULD | Show sync state, latest run, missing context and measured or estimated breakdown status. |
| Incomplete-context notification | SHOULD | Prompt for missing sleep, hydration, fuel, nutrition or lifting context without inventing values. |
| Sync-status history | MUST | Keep an audit trail of Garmin acquisition, Health Connect reads, FIT upload and laptop acknowledgement. |
| Data export and recovery | SHOULD | Provide user-triggered export of captured records and pending files. |
| Authentication | LATER | No new user-account feature is required for the single-athlete laptop-local deployment. Device pairing should use a local authorization mechanism. |

## Stack decision

Build a Capacitor Android application that reuses the existing Aurora HTML dashboard.

The repository should contain:

```text
app/
  package.json
  capacitor.config.ts
  src/
  android/
flow_outputs/
  aurora_dashboard.html
garmin_server.py
garmin_segments.csv
fit/
  raw/
scripts/
  build_segments.py
  import_fit.py
docs/
```

The Android project is the only native platform project.

Chosen stack:

- Capacitor.
- Android platform only.
- Existing Aurora HTML and JavaScript as the initial UI.
- Kotlin or Java Android integration where required.
- SQLite-backed local storage.
- Android Keystore-backed key management.
- WorkManager for durable background work.
- Health Connect through `@capacitor/health-fitness` where its data model is sufficient.
- A custom Capacitor Android plugin using `androidx.health.connect` if the required records or change-token behavior are unavailable through the official plugin.
- Local notifications by default.
- Firebase Cloud Messaging only if remote notification delivery is required.
- Android file picker and share-sheet intake for FIT and CalTrak files.
- Laptop-side FIT parsing and segment generation.

The exact SQLite package, database-encryption implementation, FIT parser library, transport and pairing mechanism are UNVERIFIED and must be selected and tested during implementation.

React Native or Expo is not selected for the first release because the current product is an HTML dashboard, and equivalent researched coverage for Health Connect, WorkManager-backed queue processing, FIT acquisition, encrypted SQLite and Android share-sheet handling is UNVERIFIED.

## Architecture and sync contract

### System roles

```text
Android app
    capture records locally
    store original FIT files locally
    create queue entries
    run WorkManager retries
    send requests to garmin_server.py

Laptop garmin_server.py
    remain the analysis authority
    receive phone data
    read and process FIT files
    generate segments
    expose Aurora analysis endpoints
    return explicit acknowledgements
```

### Local-first rules

The Android app must:

1. Work without the laptop being reachable.
2. Persist user entries before attempting network delivery.
3. Retain failed records and their failure reasons.
4. Retry delivery through WorkManager.
5. Avoid silently deleting records after failed requests.
6. Preserve provenance and source timestamps.
7. Support user-triggered export and recovery.
8. Display queued, uploading, acknowledged, retrying, failed, blocked by permission and blocked by configuration states.

### Local data model

The local encrypted database should contain tables equivalent to:

- `activities`
- `nutrition`
- `lifts`
- `hydration`
- `fuel_events`
- `health_records`
- `segments`
- `sync_queue`
- `sync_events`
- `app_state`

Important fields include:

```text
activities:
  activity_id
  activity_date
  activity_type
  source
  fit_local_path
  fit_sha256
  analysis_status
  data_quality_status

health_records:
  health_record_id
  health_type
  start_time
  end_time
  value_json
  unit
  source_package
  source_name
  provenance_json
  health_connect_record_id

segments:
  activity_id
  segment_start_mi
  segment_end_mi
  elapsed_s
  pace_s_per_mi
  avg_hr
  cadence
  altitude_ft
  grade_pct
  data_quality

sync_queue:
  queue_id
  entity_type
  entity_id
  operation
  payload_json
  file_path
  idempotency_key
  status
  attempt_count
  next_attempt_at
  last_error_code
  last_error_message

sync_events:
  sync_event_id
  operation
  endpoint
  entity_type
  entity_id
  started_at
  completed_at
  result
  http_status
  error_code
  error_message
```

### Existing browser storage migration

The current web flow uses:

```text
aurora_nutrition
aurora_sync_queue
aurora_last_api
```

On first Android launch:

1. Open or create the encrypted SQLite database.
2. Check the schema version.
3. Read available legacy web storage.
4. Migrate the three keys.
5. Record migration success or failure.
6. Keep an exportable copy until migration succeeds.
7. Use SQLite as the source of truth after migration.

The exact JSON shape of all three keys is UNVERIFIED and must be inspected in `aurora_dashboard.html` and an existing browser profile.

### WorkManager

Use WorkManager for:

- FIT uploads.
- Nutrition, hydration and lifting uploads.
- Health Connect reconciliation.
- Retry processing.
- FCM-triggered sync work.
- Queue cleanup after acknowledgement.

WorkManager supports persistent work requests, constraints, retry and backoff, but execution timing is approximate. It is not an always-running daemon.

Use a foreground service only for a visible, user-initiated long operation such as a large FIT upload. A foreground service must show a notification and requires the appropriate service type and permission on current Android versions.

### Idempotency

Every upload must include an idempotency key. A proposed form is:

```text
{idempotent_entity_type}:{entity_id}:{operation}:{content_hash}
```

The laptop must treat duplicate requests as safe retries and return the original acknowledgement.

The existing duplicate-protection behavior in `garmin_server.py` is UNVERIFIED and must be inspected.

### Response envelope

For new or modified endpoints, use:

```json
{
  "ok": true,
  "request_id": "uuid",
  "server_time": "2026-11-16T12:00:00Z",
  "data": {},
  "error": null
}
```

Failure responses should identify an error code, message and whether the error is retryable.

This is a proposed contract for new Android integration work. The current response format of existing endpoints is UNVERIFIED.

### Existing and planned endpoints

Existing or planned endpoints are:

```text
GET  /api/activities
GET  /api/load
GET  /api/coaching
POST /api/lifts
POST /api/nutrition
GET  /api/segments
POST /api/health
```

The exact request and response schemas are UNVERIFIED and must be recovered from `garmin_server.py`.

A FIT upload endpoint is required but its exact name is UNVERIFIED. A proposed endpoint is:

```text
POST /api/activities/fit
Content-Type: multipart/form-data
Idempotency-Key: activity-fit:{activity_id}:{sha256}
```

The phone must retain the original FIT file until:

1. The file is uploaded.
2. The laptop acknowledges receipt.
3. The app records the acknowledgement.
4. The configured retention policy permits deletion.

### Connectivity

The first release should work automatically when the laptop is reachable on the local network. Away from home, the app should:

- Capture locally.
- Keep records queued.
- Show laptop-unreachable status.
- Retry periodically.
- Upload when a reachable route becomes available.

The exact VPN, relay, public endpoint, TLS certificate and pairing implementation are UNVERIFIED. The first release must not assume that exposing `garmin_server.py` to the public Internet is safe.

### Notifications

Prefer local notifications for laptop-local completion and failure events.

Use Firebase Cloud Messaging only if the laptop or another service must notify the phone remotely. FCM requires:

- A Firebase project.
- The Android application registered in Firebase.
- Firebase Android configuration.
- Firebase Messaging SDK or a Capacitor push plugin.
- A trusted sender environment.
- Google Play services or Google APIs on the device.
- `POST_NOTIFICATIONS` permission on Android 13 and later.

FCM is not end-to-end encrypted. Sensitive health and nutrition values must not be placed directly in FCM payloads.

## Segment data (garmin_segments.csv)

The laptop remains authoritative for segment calculation:

```text
Android:
    acquire and preserve FIT files

Laptop:
    parse FIT files
    derive 0.1-mile segments
    generate garmin_segments.csv
    expose /api/segments
```

The required CSV is:

```csv
activity_id,date,segment_start_mi,segment_end_mi,elapsed_s,pace_s_per_mi,avg_hr,cadence,altitude_ft,grade_pct
```

Column meanings:

| Column | Meaning |
|---|---|
| `activity_id` | Garmin activity identifier. |
| `date` | Activity date. |
| `segment_start_mi` | Inclusive start distance in miles. |
| `segment_end_mi` | End distance in miles. |
| `elapsed_s` | Elapsed seconds represented by the segment. |
| `pace_s_per_mi` | Segment pace in seconds per mile. |
| `avg_hr` | Average heart rate, if available. |
| `cadence` | Segment cadence, if available. |
| `altitude_ft` | Segment altitude value or defined segment altitude summary in feet. |
| `grade_pct` | Segment grade percentage, if derivable. |

Requirements:

- Produce one row per 0.1-mile segment where the FIT data supports that resolution.
- Preserve precision sufficient for breakdown analysis to 0.01 mile.
- Leave unsupported fields blank or explicitly unavailable.
- Do not invent values.
- Keep measured, derived, estimated and unavailable status in application data or companion metadata because the fixed CSV schema has no `data_quality` column.
- Historical runs without adequate raw data retain estimated or unavailable status.
- Do not silently relabel lap-based estimates as measured.
- Repeated generation from the same source files must be deterministic.
- The generated file must remain usable by the laptop analysis flow.

The current analysis used audited activity-table lap splits because segment-level export was unavailable.

## Integrations and accounts needed (with source URLs)

### Garmin Personal API

Requirement: MUST.

Aurora must use a supported Garmin access path and must not rely on private Garmin Connect endpoints.

For the athlete's own data, the researched Personal API path requires the athlete to:

1. Log in to Garmin Connect Web.
2. Create a personal API key.
3. Choose an expiration period.
4. Save the key because it is displayed once.
5. Exchange the key for an access token.
6. Generate and refresh tokens according to Garmin's instructions.

The public overview identifies:

- Activity data in JSON and FIT.
- Health data in JSON.
- Pull-only delivery.

Automatic Garmin synchronization must not be claimed until a supported acquisition path is implemented and tested. Manual FIT-file import remains a fallback.

UNVERIFIED:

- Exact API request and response schemas.
- Exact quotas.
- Exact token-refresh behavior from the supplied material.
- Whether a single-user local-first application qualifies for business Starter access.
- Exact approval criteria and commercial terms.

Source URLs:

- https://developer.garmin.com/gc-developer-program
- https://developer.garmin.com/gc-developer-program/personal/
- https://developer.garmin.com/gc-developer-program/enterprise/program-faq/
- https://developer.garmin.com/gc-developer-program/enterprise/activity-api/
- https://developer.garmin.com/gc-developer-program/enterprise/health-api/

### Health Connect

Requirement: MUST.

Aurora must:

- Use the native Health Connect SDK or an appropriate Capacitor integration.
- Declare only required permissions.
- Check granted permissions before every read or write.
- Handle permission revocation.
- Provide the required privacy-policy rationale activity or activity alias.
- Request background-read and historical-read permissions separately when needed.
- Read only records that another installed source has written.

Potentially relevant data categories include:

- Sleep.
- Resting heart rate.
- Heart rate.
- HRV RMSSD.
- Weight.
- Hydration.
- Nutrition.
- Exercise sessions and workouts.
- Calories.
- Distance.
- Elevation.

The app must distinguish:

```text
permission not granted
no source data
not recorded
record imported
```

Health Connect does not guarantee that original Garmin FIT trackpoints are available.

Starting with Android 14, Health Connect is part of the Android framework. On Android 13 and lower, the athlete must install the Health Connect app from Google Play where required.

The exact minimum Android API level supported by the selected SDK and plugin is UNVERIFIED.

Source URLs:

- https://developer.android.com/health-and-fitness/health-connect/get-started
- https://developer.android.com/health-and-fitness/health-connect/data-types
- https://developer.android.com/health-and-fitness/health-connect/ui/permissions
- https://developer.android.com/codelabs/health-connect
- https://developer.android.com/health-and-fitness/health-connect/publish

### Capacitor Health Connect integration

Requirement: SHOULD if the existing web flow remains the base.

Use `@capacitor/health-fitness` where its data model is sufficient. If it does not expose required records or change-token behavior, use a custom Capacitor Android plugin backed directly by `androidx.health.connect`.

Source URLs:

- https://capacitorjs.com/docs/apis/health-fitness
- https://github.com/ubie-oss/capacitor-health-connect/
- https://github.com/devmaxime/capacitor-health-connect

### WorkManager

Requirement: MUST.

Use WorkManager for durable, retryable work. It supports:

- One-time work.
- Periodic work.
- Network constraints.
- Charging constraints.
- Retry and backoff.
- Chained work.
- Work status inspection.

The athlete should avoid placing Aurora in the Restricted battery state, permit network access and avoid force-stopping the app when background synchronization is expected.

Source URLs:

- https://developer.android.com/develop/background-work/background-tasks
- https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started/define-work
- https://developer.android.com/develop/background-work/background-tasks/data-transfer-options
- https://developer.android.com/topic/performance/power/power-details
- https://developer.android.com/develop/background-work/background-tasks/optimize-battery

### Capacitor background bridge

Requirement: MUST if Capacitor is used for the local queue, but only as a bridge.

`@capacitor/background-runner` may handle short JavaScript-facing work, local notifications and notification actions. It must not be the durable queue mechanism.

Known limits:

- Android background tasks have a maximum of 10 minutes.
- Cross-platform work should generally be limited to about 30 seconds.
- Repeating tasks have a minimum interval of at least 15 minutes.
- Requested intervals are not exact.
- The runner is not persistent.
- State is not maintained automatically.
- The operating system can force-kill the runner.

Source URL:

- https://capacitorjs.com/docs/apis/background-runner

### Firebase Cloud Messaging

Requirement: MUST only if remote push is needed.

FCM requires:

- A Firebase project.
- A registered Android application.
- `google-services.json`.
- Firebase Messaging SDK or Capacitor push support.
- A trusted server or relay.
- Google Play services or Google APIs.
- Notification permission on Android 13 and later.

Prefer local notifications for the laptop-local deployment.

Source URLs:

- https://firebase.google.com/docs/cloud-messaging/android/get-started
- https://firebase.google.com/docs/cloud-messaging/android/first-message
- https://firebase.google.com/docs/cloud-messaging/customize-messages/set-message-type
- https://firebase.google.com/docs/cloud-messaging/android/message-priority
- https://firebase.google.com/docs/cloud-messaging/throttling-and-quotas
- https://capacitorjs.com/docs/apis/push-notifications

### Direct APK distribution

Requirement: NOT PERMITTED for this athlete.

The athlete has explicitly rejected sideloading: apps are installed only from
the Play Store or an equivalent store. Direct APK distribution must not be
offered as an option in any plan, install guide or brief. This section is kept
as a record of the rejected path, not as an instruction.

For the record, direct distribution would require receiving a signed APK,
enabling installation from an unknown source, approving the install warning,
granting runtime permissions, and preserving the release signing key for future
updates. It also provides no automatic updates. None of that is acceptable
here.

The accepted distribution path is Google Play. If Play review is not viable for
a feature, the fallback is a browser-based flow (the dashboard's own web UI or a
store-installed bridge such as HC Webhook), never a sideloaded build.

Source URLs:

- https://developer.android.com/studio/publish
- https://developer.android.com/distribute/marketing-tools/alternative-distribution
- https://developer.android.com/guide/app-bundle/faq
- https://developer.android.com/developer-verification/guides
- https://developer.android.com/developer-verification/guides/android-developer-console
- https://developer.android.com/developer-verification/guides/limited-distribution

### Google Play Health Apps declaration

Requirement: MUST if distributed through Google Play.

If Aurora is published through Google Play and uses Health Connect, the developer must complete applicable health-app, Data Safety and data-use declarations. The requested Health Connect permissions must match the declared user-facing features.

The current membership fee is UNVERIFIED and must not be assumed.

Source URLs:

- https://developer.android.com/health-and-fitness/health-connect/publish
- https://developer.android.com/privacy-and-security/declare-data-use
- https://developer.android.com/developer-verification/guides/google-play-console

### Garmin Connect IQ

Requirement: SHOULD/LATER for a future Garmin watch feature.

A Connect IQ watch app is separate from Garmin cloud activity acquisition and is not required for the first phone release.

Source URLs:

- https://developer.garmin.com/connect-iq/
- https://developer.garmin.com/connect-iq/sdk
- https://developer.garmin.com/connect-iq/articles/connect-iq-basics/App_Types.html
- https://developer.garmin.com/downloads/connect-iq/sdks/agreement.html

### CalTrak CSV

Requirement: SHOULD.

The athlete must provide one representative CalTrak CSV before the parser is finalized. The app should retain the original file, validate columns, report malformed rows, detect duplicates and queue accepted records for laptop import.

The exact CalTrak CSV format is UNVERIFIED.

## Roadmap (slugs in order)

1. `build-fit-segment-export`
2. `app-shell-capacitor-android`
3. `app-local-store-and-sync`
4. `laptop-sync-protocol`
5. `health-connect-ingestion`
6. `push-notifications-fcm`
7. `hydration-and-fuel-quicklog`
8. `garmin-auto-sync`
9. `fit-file-intake-and-upload`
10. `nutrition-and-lifting-context`
11. `android-activity-review`
12. `caltrak-share-import`
13. `android-notification-actions-and-widgets`
14. `watch-quicklog`
15. `data-export-and-recovery`

### `build-fit-segment-export`

Create the laptop-authoritative `garmin_segments.csv` export before building the Android ingestion path.

Acceptance checks:

- Required CSV columns exist.
- Rows represent 0.1-mile segments where supported.
- Breakdown references can be measured to 0.01 mile.
- Missing fields are not invented.
- Historical estimates remain estimated or unavailable.
- Repeated runs are deterministic.

Athlete action: none for available source files. The athlete may need to provide original FIT files for historical runs.

### `app-shell-capacitor-android`

Create the Android-only Capacitor shell around `flow_outputs/aurora_dashboard.html`.

Acceptance checks:

- Debug build succeeds.
- Dashboard opens in the Android app.
- No additional native platform project is created.
- Existing laptop behavior is not removed.
- Build tool versions are documented.
- Release signing is configured without committing keys or passwords.

Athlete action: install the Play build, or test the web UI on the phone. USB debugging and direct APK installation are out of scope.

### `app-local-store-and-sync`

Create encrypted SQLite storage and the durable queue.

Acceptance checks:

- Offline nutrition, hydration, fuel and lifting capture works.
- Records have stable identifiers.
- Queue entries have idempotency keys and retry state.
- Failed delivery does not delete records.
- The three known browser keys migrate without data loss.
- SQLite becomes the source of truth.
- Export or recovery exists.
- Sync states are visible.

Athlete action: approve encrypted storage and recovery behavior.

### `laptop-sync-protocol`

Implement phone-to-laptop delivery and acknowledgements.

Acceptance checks:

- Queued records reach `garmin_server.py`.
- FIT files reach the laptop.
- Duplicate requests are safe.
- Retryable errors remain queued.
- Non-retryable errors remain visible.
- Sync events record request and acknowledgement details.
- The laptop is not exposed as an unauthenticated public endpoint.

Athlete action: configure the laptop address or local pairing method.

### `health-connect-ingestion`

Read permitted Health Connect records and reconcile incrementally.

Acceptance checks:

- Required permissions are requested only when needed.
- Revoked permissions are detected.
- Permission, source-data and not-recorded states are distinct.
- Provenance is retained.
- Change tokens or an equivalent cursor are stored when supported.
- Records can be queued to `POST /api/health`.

Athlete action: install or enable Health Connect and grant selected permissions.

### `push-notifications-fcm`

Add remote push only if local notifications are insufficient.

Acceptance checks:

- FCM is not claimed until Firebase and a trusted sender exist.
- Notification permission is requested.
- Channels exist for analysis and sync failure.
- Payloads contain no unnecessary health or nutrition values.
- Local notifications still work without FCM.

Athlete action: approve remote push and grant notification permission if enabled.

### `hydration-and-fuel-quicklog`

Add fast offline phone capture for hydration and fuel.

Acceptance checks:

- Both event types work offline.
- Timestamp, amount, unit, source and optional activity ID are retained.
- Missing values remain missing.
- Events survive process death and restart.
- Duplicate delivery is prevented.
- Local-save versus laptop-delivered status is visible.

Athlete action: approve units and quick-log defaults.

### `garmin-auto-sync`

Implement the supported Garmin Personal API path while retaining manual FIT import.

Acceptance checks:

- Credentials and tokens are stored securely.
- Failure categories are visible.
- New supported activities enter the local queue.
- Original FIT data is preserved where supplied.
- Duplicate activities do not duplicate records.
- Pull-only behavior is represented accurately.
- Automatic sync is not claimed before testing.

Athlete action: create and securely authorize a Garmin Personal API key, or choose manual FIT import.

### `fit-file-intake-and-upload`

Implement Android file selection and share-sheet FIT intake.

Acceptance checks:

- FIT files can be selected or shared.
- Original files are retained.
- Hash and activity identifiers are recorded where available.
- Duplicates and malformed files are reported.
- Files remain until laptop acknowledgement.
- Upload retries work.

Athlete action: provide a FIT file for end-to-end testing.

### `nutrition-and-lifting-context`

Capture nutrition, lifting and bodyweight context.

Acceptance checks:

- Calories, carbohydrate and protein can be recorded.
- Lifting sessions and optional bodyweight can be recorded.
- Partial records remain partial.
- Existing nutrition data is migrated after inspection.
- Records are delivered idempotently.
- The app does not claim these fields are causal explanations.

Athlete action: select practical fields and preferred bodyweight units.

### `android-activity-review`

Show cached activities, sync status, missing context and segment data quality.

Acceptance checks:

- Cached activities work offline.
- Sync failures are visible.
- Segment states are measured, derived, estimated or unavailable.
- Estimates are not labeled measured.
- Missing context is not invented.
- Laptop-generated segments appear when available.

Athlete action: review one imported run and confirm labels are understandable.

### `caltrak-share-import`

Receive and validate CalTrak CSV files.

Acceptance checks:

- Shared CSV files are retained.
- Actual supplied columns are validated.
- Malformed rows and duplicates are reported.
- Accepted records queue offline.
- Laptop import is traceable.
- Parser assumptions are not finalized before a real CSV is supplied.

Athlete action: provide one representative CalTrak CSV.

### `android-notification-actions-and-widgets`

Add notification actions and widgets after the queue is reliable.

Acceptance checks:

- Hydration and fuel actions create durable records.
- Widget state shows sync or pending-upload status.
- Duplicate taps do not duplicate records.
- Android notification permission behavior is handled.

Athlete action: grant notification permission and add the widget.

### `watch-quicklog`

Later scope for a watch quick-log surface.

Acceptance checks:

- Watch events reach the phone without loss.
- Events retain timestamps and provenance.
- Offline handoff and duplicate protection work.
- Events can be associated with the correct run.
- Actual target watch compatibility is tested.

Athlete action: select the target watch platform and provide the model.

### `data-export-and-recovery`

Provide recovery export for FIT files, health records, context records and pending queue items.

Acceptance checks:

- The athlete can export captured records and pending files.
- Provenance and sync state are included.
- Encryption keys are not exported.
- Interrupted export reports failure.
- Exported data can be retained for recovery.

Athlete action: choose export storage and retention.

## Athlete actions

Before installation:

- Have an Android phone available.
- Confirm the phone can install the app from the Play Store (no sideloading).
- Enable or install Health Connect as required by the Android version.
- Configure the laptop server.
- Test a network route to the laptop.
- Review Android battery restrictions.
- Decide whether Garmin Personal API access will be authorized.

After installation:

1. Open Aurora.
2. Grant notification permission where required.
3. Grant selected Health Connect permissions.
4. Configure the laptop endpoint or local pairing.
5. Test an offline nutrition record.
6. Test an offline hydration record.
7. Test a FIT-file import.
8. Reconnect to the laptop.
9. Confirm queue acknowledgement.
10. Confirm the activity appears in the activity endpoint.
11. Confirm segments appear after `garmin_segments.csv` is generated.
12. Confirm a failed request appears in sync history.
13. Keep Aurora out of the Restricted battery state if background synchronization is expected.
14. Keep the release signing key safe for future updates.

Garmin-specific action:

- Create a Garmin Connect Personal API key.
- Save it when displayed because it is shown once.
- Approve secure storage and use of the resulting credential.
- Enable supported pull-based acquisition, or select manual FIT import instead.

Health Connect-specific action:

- Ensure the relevant source application writes records to Health Connect.
- Grant background-read or historical-read permissions only if approved.
- Regrant permissions if they are revoked.

## Open questions

- What is the exact current FIT-file layout and parser behavior?
- What is the exact current response schema of `garmin_server.py`?
- What are the exact JSON shapes of `aurora_nutrition`, `aurora_sync_queue` and `aurora_last_api`?
- What is the exact FIT upload endpoint?
- What is the exact local pairing or authorization mechanism?
- What transport should be used when the phone is away from the home network?
- Which SQLite package and encryption implementation will be selected?
- Which FIT parser library will be selected?
- What Android minimum API level is supported by the selected Health Connect SDK and plugin?
- Will local notifications be sufficient, or is FCM required?
- What exact CalTrak CSV format will the athlete provide?
- Which quick-log units and defaults should be used?
- Which target watch platform and model should be supported later?
- What retention period should apply to original FIT files and exports?
- What Garmin Personal API request, token and refresh details must be implemented?
- What is the exact Google Play Console fee, if distribution through Google Play is later chosen? UNVERIFIED
- What authentication or local pairing mechanism should be used? Authentication remains LATER and is not required for the first single-athlete local deployment.
