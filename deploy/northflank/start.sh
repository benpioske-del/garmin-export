#!/usr/bin/env bash
# Start the Coach Dashboard and its ngrok tunnel inside the Northflank service.
# All athlete data and credentials live on the persistent volume mounted at /data.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$APP_DIR"

export GARMIN_DATA_DIR="${GARMIN_DATA_DIR:-/data}"
export TRAINLOOP_DB="${TRAINLOOP_DB:-/data/trainloop.db}"
export PYTHONUNBUFFERED=1
# Set START_TUNNEL=1 only when the laptop tunnel has been stopped. ngrok allows
# one agent per static domain, so starting it here while the laptop is still up
# would bounce the phone between two origins.
START_TUNNEL="${START_TUNNEL:-0}"
mkdir -p "$GARMIN_DATA_DIR"

# The classic page is local-only (gitignored). The migration uploads it to the
# volume; copy it into the checkout on every boot so /classic keeps working.
if [ -f "$GARMIN_DATA_DIR/dashboard/index.html" ]; then
    mkdir -p "$APP_DIR/dashboard"
    cp "$GARMIN_DATA_DIR/dashboard/index.html" "$APP_DIR/dashboard/index.html"
fi

PY="$(command -v python3 || command -v python)"

NGROK_BIN="$HOME/ngrok/ngrok"
if [ "$START_TUNNEL" = "1" ]; then
    # The buildpack image has no ngrok agent. Fetch the stable v3 Linux binary
    # into the writable home directory at boot; the download is verified by HTTPS.
    if [ ! -x "$NGROK_BIN" ]; then
        mkdir -p "$HOME/ngrok"
        "$PY" - <<'PY'
import os
import urllib.request
import zipfile

url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.zip"
zip_path = os.path.expanduser("~/ngrok/ngrok.zip")
urllib.request.urlretrieve(url, zip_path)
with zipfile.ZipFile(zip_path) as archive:
    archive.extract("ngrok", os.path.dirname(zip_path))
os.chmod(os.path.expanduser("~/ngrok/ngrok"), 0o755)
PY
    fi
    if [ -z "${NGROK_AUTHTOKEN:-}" ]; then
        echo "START_TUNNEL=1 but NGROK_AUTHTOKEN is not set." >&2
        exit 1
    fi
    "$NGROK_BIN" config add-authtoken "$NGROK_AUTHTOKEN" >/dev/null
fi

# Nightly Garmin refresh, equivalent to deploy/cloud's sync timer. The server
# keeps serving the data it already has if a sync fails.
(
    while true; do
        now="$(date -u +%s)"
        target="$(date -u -d '04:30' +%s)"
        if [ "$target" -le "$now" ]; then
            target="$(date -u -d 'tomorrow 04:30' +%s)"
        fi
        sleep $((target - now))
        "$PY" "$APP_DIR/garmin_sync.py" || true
        # Bare trainloop.py only prints help; new FITs would never reach the DB.
        "$PY" "$APP_DIR/trainloop.py" bootstrap || true
        # The CSV carries the per-mile splits for runs the DB cannot store.
        "$PY" "$APP_DIR/deploy/cloud/refresh_export.py" || true
        # Weather is archived at build time, never looked up by the page. Rebuild
        # the baked context after the CSV so phone-synced runs get weather and
        # splits too; a failed fetch leaves the previous context serving.
        "$PY" "$APP_DIR/build_run_context.py" || true
    done
) &

# Loopback only: ngrok runs in this same container and rewrites Host to
# 127.0.0.1:24567 via the committed traffic policy.
"$PY" "$APP_DIR/garmin_server.py" --port 24567 --idle-timeout 0 &
SERVER_PID=$!
PIDS=("$SERVER_PID")

if [ "$START_TUNNEL" = "1" ]; then
    "$NGROK_BIN" http 127.0.0.1:24567 \
        --url=https://foam-tackiness-header.ngrok-free.dev \
        --traffic-policy-file="$APP_DIR/deploy/cloud/host-header-policy.yml" &
    TUNNEL_PID=$!
    PIDS+=("$TUNNEL_PID")
fi

# If any foreground process dies, the container exits and Northflank restarts it.
wait -n "${PIDS[@]}" || true
