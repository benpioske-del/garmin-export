# Restoring the coach dashboard on a new laptop

Written for the case where the laptop is gone: stolen, dead disk, or Windows
reinstalled. It assumes nothing from the old machine except your Garmin login
and the most recent `coach-data-*.zip`.

## What survives without a backup

The repository is on GitHub, so a `git clone` returns the whole pipeline: code,
tests, migrations, docs, the dashboard template, the vendored Chart.js, and
`garmin_export.csv` with the published run summaries.

That is not enough to run. Everything below is deliberately kept out of git and
lives only in the local data directory and the backup zip:

| Asset | In git? | Rebuildable? |
| --- | --- | --- |
| `garmin_fit/*.fit` (the corpus) | no | yes, re-download from Garmin |
| `trainloop.db` | no | yes, `trainloop.cmd bootstrap` |
| `nutrition_log.csv` | no | **no** |
| `nutrition_log.records.json` | no | **no** |
| `dashboard/index.html` (`/classic`) | no | **no** |
| `garmin_sleep.csv`, `garmin_hr.csv` | no | partly, 14-day window |
| `.coach_dash_token`, `.coach_dash_auth` | no | yes, regenerated |
| `nutrition_log.hook-token` | no | yes, regenerated |
| `.garmin_tokens/` | no | yes, re-login |

The nutrition files and `dashboard/index.html` are the data that cannot be
recreated. That is the whole reason the backup exists. Aurora at `/` comes from
the committed template, so the dashboard is usable even if the classic page is
gone.

## Before you start

- Windows 10 or 11, PowerShell.
- Python 3.12 or newer (`py --version`).
- Git for Windows.
- Your Garmin account password, and access to the MFA method on it.
- The newest `coach-data-*.zip` from `OneDrive\CoachDashboardBackups`.

## Restore in order

### 1. Install Python and Git

Install Python 3.12+ and tick **Add python.exe to PATH**. Install Git for
Windows. Confirm both:

```powershell
py --version
git --version
```

### 2. Clone the repository

```powershell
cd $env:USERPROFILE
git clone https://github.com/benpioske-del/garmin-export.git
cd garmin-export
```

### 3. Install the dependencies

```powershell
py -m pip install -e ".[dev]"
```

`garminconnect` and `fitparse` come from this step. If it fails on a corporate
proxy, fix the proxy before continuing; nothing else works without them.

### 4. Choose the data directory

The default is `%USERPROFILE%\Downloads`, which mixes athlete data with
installers. Prefer a dedicated folder:

```powershell
$env:GARMIN_DATA_DIR = "$env:USERPROFILE\Documents\coach-data"
New-Item -ItemType Directory -Force $env:GARMIN_DATA_DIR | Out-Null
```

Set it permanently so every new shell and scheduled task sees it:

```powershell
setx GARMIN_DATA_DIR "$env:USERPROFILE\Documents\coach-data"
```

Reopen PowerShell after `setx`.

### 5. Restore the backup

```powershell
$zip = Get-ChildItem "$env:OneDrive\CoachDashboardBackups\coach-data-*.zip" |
       Sort-Object Name | Select-Object -Last 1
Expand-Archive -Path $zip.FullName -DestinationPath $env:GARMIN_DATA_DIR -Force
Get-ChildItem $env:GARMIN_DATA_DIR
```

Expected: `garmin_fit\`, `garmin_sleep.csv`, `garmin_hr.csv`,
`garmin_last_sync.json`, `trainloop.db`, `dashboard\`, `MANIFEST.txt`.
`nutrition_log.csv` and `nutrition_log.records.json` appear in the zip once
nutrition has been ingested; before that they are legitimately absent.

Two files belong in the **repository**, not the data directory:

```powershell
if (Test-Path "$env:GARMIN_DATA_DIR\trainloop.db") {
    Move-Item "$env:GARMIN_DATA_DIR\trainloop.db" . -Force
}
if (Test-Path "$env:GARMIN_DATA_DIR\dashboard\index.html") {
    New-Item -ItemType Directory -Force dashboard | Out-Null
    Move-Item "$env:GARMIN_DATA_DIR\dashboard\index.html" dashboard -Force
    Remove-Item "$env:GARMIN_DATA_DIR\dashboard" -Recurse -Force
}
```

`dashboard/index.html` is the old `/classic` page. It is gitignored because it
holds hand-entered athlete data and nothing regenerates it, so the backup is the
only copy. Aurora at `/` does not need it.

Read `MANIFEST.txt` before moving on. It records the code commit the backup was
taken from; if the current `git log -1` is much newer, expect schema migrations
and let step 6 apply them.

### 6. Rebuild or verify the database

If the zip carried `trainloop.db`, verify it first:

```powershell
.\trainloop.cmd status
```

If the counts are wrong, or there was no database in the zip, rebuild from the
FIT corpus:

```powershell
.\trainloop.cmd bootstrap
```

Safe to re-run: a second run reports files as unchanged and inserts nothing.

### 7. Re-download any missing runs

If the FIT corpus was lost, or the backup is older than your last few runs,
Garmin still has every activity:

```powershell
py garmin_sync.py
.\trainloop.cmd bootstrap
.\trainloop.cmd publish
```

The first run prompts for Garmin credentials and MFA. The sync is marker-based,
so it downloads everything newer than `garmin_last_sync.json` - a year of gap
fills in one pass.

### 8. Start the dashboard

```powershell
py garmin_server.py --idle-timeout 0
```

Open `http://127.0.0.1:24567`. The first page sets the dashboard password.

For the phone link, recreate the launcher (`start-dashboard.cmd` in
`%USERPROFILE%\coach-dashboard`) or run ngrok directly:

```powershell
ngrok http 127.0.0.1:24567 --url=https://foam-tackiness-header.ngrok-free.dev `
      --traffic-policy-file="$env:USERPROFILE\coach-dashboard\host-header-policy.yml"
```

## Re-create credentials

Nothing secret is in the backup. Each one regenerates on demand:

| Credential | How |
| --- | --- |
| Dashboard password | first page load sets it; hash lands in `%GARMIN_DATA_DIR%\.coach_dash_auth` |
| Dashboard token | `garmin_server.py` creates `.coach_dash_token` on first start |
| Nutrition hook token | delete `%GARMIN_DATA_DIR%\nutrition_log.hook-token`, then reload the Fuel page |
| Garmin session | `py garmin_sync.py` and complete MFA |

If the phone bridge was already configured, it must be given the **new** hook
token. The Fuel page shows the current value under **Automatic upload**.

## Verify the restore

Run these in order. Each one should be boring.

```powershell
.\trainloop.cmd doctor          # Python, sqlite3, fitparse, FIT dir, gitignore
.\trainloop.cmd status          # FIT files on disk == activities in database
py -m pytest                    # expect 622 passed, 1 skipped on a full corpus
py backup_data.py --dry-run     # lists what a new backup would contain
```

Then in the browser: Home shows run totals, Analysis renders charts, Fuel shows
your nutrition days, and **Sync Garmin now** completes in 15-90 seconds.

## What cannot be restored

- **Nutrition history older than the newest backup.** Health Connect keeps a
  limited window and the logging app keeps its own. If the backup is a month old
  and the app has since discarded the raw records, that month is gone.
- **Anything logged only in a browser.** The "Log a run" and lift-session forms
  currently write to `localStorage`, which is not part of this backup and does
  not leave the browser that created it.
- **Weather enrichment**, which is fetched per run and can be refetched.

## Keeping the backup running

```powershell
py backup_data.py
```

Defaults: writes to `%OneDrive%\CoachDashboardBackups`, keeps the newest 14
copies, excludes all credentials. `--dry-run` lists contents without writing.

Register it daily, and let Windows catch up after a missed wake:

```powershell
schtasks /Create /TN "Coach Data Backup" /SC DAILY /ST 12:00 /F `
  /TR "\"$env:LOCALAPPDATA\Programs\Python\Python313\python.exe\" \"$env:USERPROFILE\garmin-export\backup_data.py\""
```

Then make the task resilient:

```powershell
$t = Get-ScheduledTask -TaskName "Coach Data Backup"
$t.Settings.StartWhenAvailable = $true
$t.Settings.ExecutionTimeLimit = "PT15M"
Set-ScheduledTask -TaskName "Coach Data Backup" -Settings $t.Settings
```

Verify it actually ran, not just that it exists:

```powershell
Get-ScheduledTaskInfo -TaskName "Coach Data Backup" | Select LastRunTime, LastTaskResult
Get-ChildItem "$env:OneDrive\CoachDashboardBackups" | Sort-Object Name | Select-Object -Last 3
```

`LastTaskResult` of `0` is success. `0x41301` means still running.

To remove it: `Unregister-ScheduledTask -TaskName "Coach Data Backup" -Confirm:$false`

## Preventing the next incident

- Confirm OneDrive is actually syncing the backup folder (cloud icon, no red
  X). A backup in a folder that never uploads is not a backup.
- Once a month, open the newest zip, read `MANIFEST.txt`, and confirm the files
  listed there are present. `nutrition_log.records.json` appears once nutrition
  has been ingested; before that it is legitimately absent.
- Keep the data directory out of `Downloads`. That folder is the first thing
  anyone clears when disk space runs low.
