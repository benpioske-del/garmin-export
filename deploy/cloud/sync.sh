#!/usr/bin/env bash
# Nightly Garmin sync for the cloud host.
#
# Three steps, and a failure in one does not skip the others:
#   1. garmin_sync.py downloads new .FIT files into the data directory.
#   2. trainloop.py bootstrap imports them into the SQLite database.
#   3. refresh_export.py rebuilds garmin_export.csv, which is where the
#      dashboard gets per-mile splits and best-5K times.
#
# No GitHub credential is used here. The CSV is rebuilt locally for the
# dashboard; publishing it is a separate, optional step described in README.md.
set -uo pipefail

APP_DIR=/opt/coach-dashboard/app
VENV=/opt/coach-dashboard/venv

export GARMIN_DATA_DIR=/srv/coach-dashboard/data
export TRAINLOOP_DB="$GARMIN_DATA_DIR/trainloop.db"
export GARMINTOKENS="$GARMIN_DATA_DIR/.garmin_tokens"
export GARMIN_REPO="$APP_DIR"
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

cd "$APP_DIR" || exit 1

rc=0

echo "== Garmin sync =="
"$VENV/bin/python" garmin_sync.py || rc=1

echo "== Database import =="
"$VENV/bin/python" trainloop.py bootstrap || rc=1

echo "== Export refresh =="
"$VENV/bin/python" deploy/cloud/refresh_export.py || rc=1

exit "$rc"
