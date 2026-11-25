# Cronometer -> Aurora server-side sync

This is the Garmin-style path: the always-on container pulls data on a schedule,
not the phone. `cronometer_sync.py` signs in to cronometer.com, downloads the
same **Daily Nutrition** CSV the website's Export Data button produces, and
upserts it into the local nutrition log that Aurora already reads.

Cronometer has no public API. This uses the private endpoints its own web app
calls (the same flow used by the open-source `gocronometer` and
`crono-export-cli` clients). It is an unofficial integration and can break when
Cronometer ships a web update; a failure is recorded in a status file and the
last good nutrition data keeps serving. No data is invented.

## 1. Add the credentials as Northflank secrets

Do this **yourself**, in the Northflank dashboard, so the values never enter
chat, shell history, the repository, a commit, or a URL.

1. Open <https://app.northflank.com/> and select project **default**.
2. Open service **running-data**, then the **Secrets** tab.
3. Add two secrets to the secret group the service uses (the same one that
   already holds `START_TUNNEL` and `NGROK_AUTHTOKEN`):
   - Name: `CRONOMETER_USERNAME` — value: the email you use for cronometer.com.
   - Name: `CRONOMETER_PASSWORD` — value: your Cronometer password.
4. Save. Do not paste either value into this chat or a terminal command.

The container reads them from its environment. Nothing is written to `/data`
except a sanitised status file. `--check` prints only `configured` or `not
configured`; it never echoes a value.

If a value is ever pasted somewhere it should not have been, change the
Cronometer password first, then update the secret.

## 2. Apply and verify

After the secrets are saved, restart the service so the new environment is
picked up:

```powershell
$env:Path = "C:\Program Files\nodejs;$env:APPDATA\npm;" + $env:Path
& "$env:APPDATA\npm\northflank.cmd" restart service --projectId default --serviceId running-data
```

Then verify inside the running container (values are never printed):

```sh
cd /workspace
# A manual exec session does not inherit the server's exported GARMIN_DATA_DIR.
# Set it explicitly so checks read and write the same persistent volume as the
# nightly loop and the dashboard's Sync button.
export GARMIN_DATA_DIR=/data
python3 cronometer_sync.py --check      # Cronometer credentials: configured
python3 cronometer_sync.py              # Cronometer sync: accepted N day(s), upserted N, total N
python3 cronometer_sync.py --status     # state, last_success, counts; no secrets
python3 cronometer_sync.py --show-days 2  # date + macros only, no credentials
```

`--diagnose-env` prints the resolved `data_dir` and `status_path` as well as
shape booleans, so a future check can confirm it is using `/data`.

The dashboard's **Sync** button also runs this pull alongside the Garmin sync.
Its result includes a `nutrition_ok` flag; a missing credential does not turn a
successful Garmin sync into a failure.

## 3. Schedule

`deploy/northflank/start.sh` runs the pull after the 04:30 UTC nightly Garmin
refresh. The default window is the last 7 days including today, so a missed
night is caught on the next run. Re-importing a date updates that day's row
instead of appending a duplicate.

## 4. Troubleshooting

- **`credentials rejected by Cronometer`** — the two values reached the
  container but Cronometer did not accept them. Confirm you used the email and
  password for the Cronometer website, not the app-only login or the dashboard
  password. Run `python3 cronometer_sync.py --diagnose-env` for a shape-only
  report: it prints booleans and length buckets, never the values. If
  `username_equals_key` or `password_equals_key` is true, you typed the variable
  name into the Value field. Cronometer's own error text is never echoed.
- **`anti-CSRF token rejected`** — the login page changed or the session cookie
  was not returned. Retry once; if it persists, Cronometer changed its login
  flow.
- **`GWT authentication response not understood`** — Cronometer rotated its
  GWT permutation. In Chrome DevTools, open cronometer.com, trigger an export,
  open a `/cronometer/app` request in the Network tab, copy the
  `X-Gwt-Permutation` header value, and add it as a new secret named
  `CRONOMETER_GWT_PERMUTATION`. Restart the service.
- **`credentials not configured`** — a secret is missing or the service was not
  restarted after adding it.
- **`export could not be parsed`** — Cronometer changed the CSV column names.
  The previous nutrition log is left untouched.

The status file is `/data/nutrition_sync_status.json` on the volume. It is
local-only, gitignored, and excluded from the publisher. It never contains a
password, token or nonce.

## 5. Optional phone path

The existing Health Connect bridge remains available as redundancy: install
**HC Webhook** from the Play Store ($14.99, one-time), enable Nutrition at Daily
resolution and Local time, and paste the URL and header value from Aurora's
**Set up automatic upload** card. Cronometer Android must be allowed to write
Food to Health Connect. This path has not received a live payload yet, so the
server-side pull is the primary.
