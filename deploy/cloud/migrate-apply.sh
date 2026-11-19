#!/usr/bin/env bash
# Apply a data bundle uploaded by migrate-to-cloud.ps1.
#
# Runs as root on the VM, from a staging directory that contains:
#   data/       athlete data, tokens and trainloop.db
#   dashboard/  the local-only classic page (optional)
#
# It never prints file contents, so a token cannot end up in the SSH log.
set -euo pipefail

STAGE=/tmp/coach-migrate
DATA_DIR=/srv/coach-dashboard/data
APP_DIR=/opt/coach-dashboard/app
SERVICE_USER=coach

[ -d "$STAGE/data" ] || { echo "no staged data directory" >&2; exit 1; }

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" "$DATA_DIR"
cp -a "$STAGE/data/." "$DATA_DIR/"

if [ -d "$STAGE/dashboard" ] && [ -n "$(ls -A "$STAGE/dashboard" 2>/dev/null)" ]; then
    install -d -o "$SERVICE_USER" -g "$SERVICE_USER" "$APP_DIR/dashboard"
    cp -a "$STAGE/dashboard/." "$APP_DIR/dashboard/"
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR" "$APP_DIR/dashboard" 2>/dev/null || true

# Secrets are readable by the service user only. The server runs as that user.
chmod 700 "$DATA_DIR"
for f in .coach_dash_auth .coach_dash_sessionkey .coach_dash_token \
         nutrition_log.hook-token garmin_tokens.json; do
    if [ -f "$DATA_DIR/$f" ]; then
        chmod 600 "$DATA_DIR/$f"
    fi
done
if [ -d "$DATA_DIR/.garmin_tokens" ]; then
    chmod 700 "$DATA_DIR/.garmin_tokens"
    find "$DATA_DIR/.garmin_tokens" -type f -name '*.json' -exec chmod 600 {} + 2>/dev/null || true
fi

rm -rf "$STAGE" /tmp/coach-dashboard-migrate.tar.gz

systemctl restart coach-dashboard.service || true

echo "data copied to $DATA_DIR"
echo "dashboard password file: $([ -f "$DATA_DIR/.coach_dash_auth" ] && echo present || echo MISSING)"
