# Run the Coach Dashboard on a free cloud VM

This directory makes the dashboard independent of the laptop. The same Python
server that runs on Windows runs on a small Ubuntu VM, pulls Garmin data from
Garmin's cloud on a nightly timer, and keeps the permanent ngrok address alive
while the laptop is off, asleep or broken.

```
 phone / browser
       |
       | https://foam-tackiness-header.ngrok-free.dev
       v
   ngrok edge  --->  ngrok agent on the VM (outbound only)
                          |
                          v
                 127.0.0.1:24567  garmin_server.py
                          |
             +------------+-------------+
             |                          |
   /srv/coach-dashboard/data     /opt/coach-dashboard/app
   FIT files, SQLite, tokens     git checkout, venv
```

Nothing listens on a public port. The VM needs no inbound firewall rule, no
public DNS name and no static IP. The only inbound service is SSH, which the
provider enables by default.

## What you need

- A free cloud account. Both options below need a card for identity
  verification; neither charges the always-free shapes used here.
- An SSH key pair. The provider creates one during setup, or you upload your
  existing public key.
- Your ngrok authtoken (from <https://dashboard.ngrok.com/get-started/your-authtoken>).
  It is a secret: paste it only into `/etc/coach-dashboard/ngrok.env` on the VM.
- About 20 minutes.

The data is small: roughly 5 MB of FIT files plus a sub-megabyte SQLite
database. Any free shape is enough.

## 1. Create the VM

### Option A - Oracle Cloud Always Free (recommended)

1. Sign up at <https://www.oracle.com/cloud/free/> and choose a home region.
2. **Compute > Instances > Create instance**.
3. Image: **Canonical Ubuntu 24.04**. Shape: **VM.Standard.E2.1.Micro**
   (Always Free, 1 GB RAM). The Ampere A1 shape also works and is faster, but
   free capacity comes and goes.
4. Under **Add SSH keys**, upload your public key (or let Oracle generate a
   key pair and download the private key).
5. Leave the default VCN and security list. Do **not** add HTTP or HTTPS
   ingress rules; none are needed.
6. Create the instance and note its public IP.

The public IP may change if the instance is stopped and started. That does not
matter: ngrok connects outbound, so the dashboard address never changes.

### Option B - Google Cloud e2-micro

1. Sign up at <https://cloud.google.com/free>.
2. **Compute Engine > VM instances > Create instance**.
3. Region: `us-central1`, `us-west1` or `us-east1` (the Always Free regions).
   Machine type: **e2-micro**. Boot disk: **Ubuntu 24.04 LTS**, 30 GB standard.
4. Allow the default SSH firewall rule. Do not enable HTTP/HTTPS traffic.
5. Create the instance and note its external IP.

## 2. Install the server

SSH in with the key from step 1, then:

```bash
sudo apt-get update -qq
sudo apt-get install -y -qq git
git clone https://github.com/benpioske-del/garmin-export.git
sudo bash garmin-export/deploy/cloud/install.sh
```

The installer is idempotent. It:

- installs Python, a virtualenv and the ngrok agent,
- creates the `coach` service user,
- clones the public repository into `/opt/coach-dashboard/app`,
- creates `/srv/coach-dashboard/data` for athlete data and tokens,
- installs and starts `coach-dashboard.service` on `127.0.0.1:24567`,
- installs the nightly sync timer,
- enables the tunnel **only** when an ngrok token is already configured,
- adds 1 GB of swap on a 1 GB VM so pip cannot run out of memory.

Check it:

```bash
systemctl status coach-dashboard --no-pager
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:24567/
```

`302`, `303` or `200` all mean the server is up. A `303` is the login redirect,
which is expected once a password exists.

## 3. Move the data from the laptop

Run this **on the laptop**, from the repository checkout:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\cloud\migrate-to-cloud.ps1 `
    -Target coach@203.0.113.10 `
    -Key $env:USERPROFILE\.ssh\oracle.key
```

It copies:

| From | To on the VM |
| --- | --- |
| `%GARMIN_DATA_DIR%\garmin_fit\` | `/srv/coach-dashboard/data/garmin_fit/` |
| `%GARMIN_DATA_DIR%\.garmin_tokens\` | `/srv/coach-dashboard/data/.garmin_tokens/` |
| `.coach_dash_auth`, `.coach_dash_sessionkey`, `.coach_dash_token` | `/srv/coach-dashboard/data/` |
| `nutrition_log.csv`, `nutrition_log.records.json`, `manual_runs.json` | `/srv/coach-dashboard/data/` |
| `garmin_last_sync.json`, `garmin_sleep.csv`, `garmin_hr.csv` | `/srv/coach-dashboard/data/` |
| `trainloop.db` (from the checkout) | `/srv/coach-dashboard/data/trainloop.db` |
| `dashboard\index.html` (gitignored, local only) | `/opt/coach-dashboard/app/dashboard/` |

The archive exists only in `%TEMP%` for the duration of the copy, and it is
deleted on success and on failure. Secrets are chmod 600 and owned by `coach`.

Copying `.coach_dash_auth` keeps your existing dashboard password, so the same
password works on the VM. If that file is missing, the script warns you: set a
password before exposing the tunnel.

Then refresh the CSV the dashboard reads for splits:

```bash
sudo -u coach /opt/coach-dashboard/venv/bin/python \
    /opt/coach-dashboard/app/deploy/cloud/refresh_export.py
```

## 4. Turn on the public link

On the VM:

```bash
sudo install -m 0640 -o root -g coach /dev/null /etc/coach-dashboard/ngrok.env
echo 'NGROK_AUTHTOKEN=<paste-your-token>' | sudo tee /etc/coach-dashboard/ngrok.env >/dev/null
sudo systemctl enable --now coach-dashboard-tunnel.service
```

Before that command, stop the laptop's tunnel. The free ngrok plan allows one
agent per static domain, so two hosts fighting over
`foam-tackiness-header.ngrok-free.dev` make the address flap:

```powershell
C:\Users\benpi\coach-dashboard\stop-dashboard.cmd
```

Also remove the Startup shortcut so it does not come back at the next sign-in:

```powershell
Remove-Item "$([Environment]::GetFolderPath('Startup'))\Coach Dashboard.lnk"
```

Verify from the laptop:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://foam-tackiness-header.ngrok-free.dev/
```

`303` is the login redirect and is the expected answer. On a phone, open the
address, tap **Visit Site** once if ngrok shows its notice, and sign in with the
existing dashboard password. If the home-screen icon was created from a
`192.168.x.x` address, delete it and add it again from the tunnel URL.

## 5. Day-to-day

| What | How |
| --- | --- |
| Dashboard | `https://foam-tackiness-header.ngrok-free.dev` |
| Server status | `systemctl status coach-dashboard` |
| Tunnel status | `systemctl status coach-dashboard-tunnel` |
| Server log | `journalctl -u coach-dashboard -n 100 --no-pager` |
| Tunnel log | `journalctl -u coach-dashboard-tunnel -n 100 --no-pager` |
| Sync log | `tail -50 /srv/coach-dashboard/data/garmin_sync.log` |
| Run a sync now | `sudo systemctl start coach-dashboard-sync` |
| Sync timer | `systemctl list-timers coach-dashboard-sync.timer` |

The sync timer runs at **04:30 local time plus up to 15 minutes**, with
`Persistent=true`, so a run missed while the VM was down happens once at the
next boot. A sync downloads new FIT files, imports them into SQLite and rebuilds
`garmin_export.csv` locally. The dashboard's **Sync Garmin** button still works
too and runs the same two scripts.

### Garmin re-authentication

The Garmin refresh tokens copied from the laptop usually last months. When they
expire, the nightly sync fails and the dashboard keeps serving the data it
already has. Re-authenticate once, interactively:

```bash
sudo -u coach -H bash -c '
  cd /opt/coach-dashboard/app &&
  GARMIN_DATA_DIR=/srv/coach-dashboard/data \
  TRAINLOOP_DB=/srv/coach-dashboard/data/trainloop.db \
  /opt/coach-dashboard/venv/bin/python garmin_sync.py'
```

It prompts for the Garmin password and the 6-digit MFA code. The new tokens are
written to `/srv/coach-dashboard/data/.garmin_tokens` and later timer runs use
them without prompting. The sync unit deliberately has no stdin, so an expired
token fails fast instead of hanging the timer.

## 6. Updating the code

```bash
sudo bash /opt/coach-dashboard/app/deploy/cloud/install.sh
```

That fetches `origin/main`, resets the checkout, reinstalls dependencies and
restarts the server. It does not touch `/srv/coach-dashboard/data`. The local
`garmin_export.csv` is reset to the committed copy; the next sync rebuilds it
from the VM's FIT files.

## 7. Optional: keep the public CSV current

The cloud host refreshes `garmin_export.csv` **locally** so the dashboard has
splits. It does not push to GitHub, because that would require a repository
token on the VM.

If you also want the public file at
`https://raw.githubusercontent.com/benpioske-del/garmin-export/main/garmin_export.csv`
to keep moving after the laptop is retired, you can add a fine-grained GitHub
token with `Contents: Read and write` on that one repository. Treat it as a
credential: store it in a root-only file, never in the repository, and never in
a systemd `ExecStart` line. This is optional; nothing the dashboard shows
depends on it.

## 8. Backups

The VM is now the only copy of hand-entered data (manual runs, nutrition,
notes). Garmin history can always be downloaded again; those cannot.

```bash
sudo -u coach /opt/coach-dashboard/venv/bin/python \
    /opt/coach-dashboard/app/backup_data.py \
    --dest /srv/coach-dashboard/backups --include-secrets
```

`--include-secrets` bundles the Garmin tokens and dashboard password hash, so
keep the resulting zip private. Pull one copy off the VM now and then:

```powershell
scp coach@203.0.113.10:/srv/coach-dashboard/backups/*.zip $env:USERPROFILE\Downloads\
```

`docs/RESTORE.md` covers restoring a backup on a new machine.

## 9. Decommissioning the laptop

1. Stop the laptop watchdog and tunnel: `stop-dashboard.cmd`.
2. Delete the Startup shortcut (command in step 4).
3. Confirm the VM's tunnel is the only agent on the domain.
4. Keep the laptop's data directory and OneDrive backups; they are the fallback
   if the VM is lost.

Once the VM is verified, the laptop is just a browser. Nothing on it is required
for the dashboard to work.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `303` to `/login`, password rejected | `.coach_dash_auth` was not migrated | copy it again with `migrate-to-cloud.ps1`, then `systemctl restart coach-dashboard` |
| ngrok `ERR_NGROK_3200` or the URL flaps | a second agent uses the same domain | stop the laptop's tunnel; one agent per domain on the free plan |
| `502` from the tunnel | server is down | `systemctl status coach-dashboard`; check the journal |
| `403` on `/api/*` after opening the page | the `dash_local` cookie was not set | load `/` first; do not bookmark an `/api` URL |
| nightly sync exits 1, log says MFA or login | tokens expired | run the interactive re-auth command above |
| new runs have no splits | `refresh_export.py` did not run | `sudo systemctl start coach-dashboard-sync`, then check the log |
| out of memory during install | 1 GB VM without swap | the installer adds swap; re-run it |

## What this does not do

- It cannot wake a dead VM. If the provider has an outage or you stop the
  instance, the link is down until it is back.
- It does not remove the dashboard password requirement. The URL is public; the
  password gates every route.
- It does not make Cronometer uploads automatic. The Cronometer app still
  exports through Health Connect, or you still upload a `dailysummary.csv`
  export; the cloud host only receives it.
