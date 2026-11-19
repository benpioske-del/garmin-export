#!/usr/bin/env bash
# Install the Coach Dashboard on a fresh Ubuntu 24.04 VM.
#
# Run as root from a clone of the public repository:
#   git clone https://github.com/benpioske-del/garmin-export.git
#   sudo bash garmin-export/deploy/cloud/install.sh
#
# Safe to re-run: it updates the checkout, refreshes the virtualenv and
# reinstalls the units. Athlete data lives in /srv/coach-dashboard/data and is
# never touched by an upgrade.
#
# Nothing is exposed to the internet except through the outbound ngrok tunnel.
# The server binds 127.0.0.1, so the VM needs no inbound firewall rule at all.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/benpioske-del/garmin-export.git}"
APP_DIR=/opt/coach-dashboard/app
VENV=/opt/coach-dashboard/venv
DATA_DIR=/srv/coach-dashboard/data
SERVICE_USER=coach
UNIT_DIR=/etc/systemd/system
CONF_DIR=/etc/coach-dashboard

say() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run this with sudo"
command -v apt-get >/dev/null 2>&1 || die "this installer targets Ubuntu/Debian"

say "== packages =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl ca-certificates tar

say "== service user =="
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --create-home --home-dir /srv/coach-dashboard \
            --shell /bin/bash "$SERVICE_USER"
fi
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" /srv/coach-dashboard
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" "$DATA_DIR"
install -d /opt/coach-dashboard
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" "$APP_DIR"

say "== code =="
if [ -d "$APP_DIR/.git" ]; then
    sudo -u "$SERVICE_USER" git -C "$APP_DIR" fetch --depth 1 origin main
    sudo -u "$SERVICE_USER" git -C "$APP_DIR" reset --hard FETCH_HEAD
else
    sudo -u "$SERVICE_USER" git clone --depth 1 "$REPO_URL" "$APP_DIR"
fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

say "== python environment =="
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -e "$APP_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

# A 1 GB free-tier VM can run out of memory while pip builds a wheel. One
# gigabyte of swap is enough and costs nothing when it is unused.
if [ ! -f /swapfile ]; then
    mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
    if [ "${mem_kb:-0}" -lt 1900000 ]; then
        say "== swap (small VM) =="
        fallocate -l 1G /swapfile 2>/dev/null || \
            dd if=/dev/zero of=/swapfile bs=1M count=1024 status=none
        chmod 600 /swapfile
        mkswap /swapfile >/dev/null
        swapon /swapfile || true
        grep -q '^/swapfile ' /etc/fstab || \
            printf '/swapfile none swap sw 0 0\n' >> /etc/fstab
    fi
fi

say "== ngrok agent =="
if ! command -v ngrok >/dev/null 2>&1; then
    curl -fsSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
        | tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
    printf 'deb https://ngrok-agent.s3.amazonaws.com buster main\n' \
        > /etc/apt/sources.list.d/ngrok.list
    apt-get update -qq
    apt-get install -y -qq ngrok
fi

say "== configuration and units =="
install -d -m 0755 "$CONF_DIR"
install -m 0644 "$APP_DIR/deploy/cloud/host-header-policy.yml" \
    "$CONF_DIR/host-header-policy.yml"
install -m 0644 "$APP_DIR/deploy/cloud/coach-dashboard.service" "$UNIT_DIR/"
install -m 0644 "$APP_DIR/deploy/cloud/coach-dashboard-tunnel.service" "$UNIT_DIR/"
install -m 0644 "$APP_DIR/deploy/cloud/coach-dashboard-sync.service" "$UNIT_DIR/"
install -m 0644 "$APP_DIR/deploy/cloud/coach-dashboard-sync.timer" "$UNIT_DIR/"
chmod 0755 "$APP_DIR/deploy/cloud/"*.sh
systemctl daemon-reload

say "== services =="
systemctl enable coach-dashboard.service >/dev/null
systemctl restart coach-dashboard.service || true
systemctl enable --now coach-dashboard-sync.timer >/dev/null

tunnel_state="NOT enabled"
if [ -s "$CONF_DIR/ngrok.env" ]; then
    chown root:"$SERVICE_USER" "$CONF_DIR/ngrok.env"
    chmod 0640 "$CONF_DIR/ngrok.env"
    systemctl enable coach-dashboard-tunnel.service >/dev/null
    systemctl restart coach-dashboard-tunnel.service || true
    tunnel_state="enabled"
fi

sleep 1
if systemctl is-active --quiet coach-dashboard.service; then
    server_state="active"
else
    server_state="FAILED - run: journalctl -u coach-dashboard -n 50"
fi

cat <<EOF

== installed ==

  server       : $server_state on 127.0.0.1:24567 (loopback only)
  nightly sync : enabled, 04:30 +/- 15 min
  public tunnel: $tunnel_state

EOF

if [ ! -f "$DATA_DIR/.coach_dash_auth" ]; then
    cat <<EOF
WARNING: there is no dashboard password on this host yet. If you enable the
tunnel first, the public URL is open to anyone who finds it. Copy the laptop's
data first (deploy/cloud/migrate-to-cloud.ps1), or set a password:

  sudo -u $SERVICE_USER $VENV/bin/python $APP_DIR/garmin_server.py --password 'choose-one'
  # it prints the local URL, then press Ctrl-C; the hash is saved

EOF
fi

if [ "$tunnel_state" = "NOT enabled" ]; then
    cat <<EOF
To turn on the public link, paste your ngrok authtoken once:

  sudo install -m 0640 -o root -g $SERVICE_USER /dev/null $CONF_DIR/ngrok.env
  echo 'NGROK_AUTHTOKEN=<paste-your-token>' | sudo tee $CONF_DIR/ngrok.env >/dev/null
  sudo systemctl enable --now coach-dashboard-tunnel.service

The token is read from that file by systemd; it is never on a command line and
must never be committed. The permanent address is
https://foam-tackiness-header.ngrok-free.dev

EOF
fi
