"""Tests for the cloud deployment kit in deploy/cloud/.

The kit is the only supported way to keep the dashboard alive when the laptop is
off. These tests pin the properties that make that safe rather than the exact
prose:

  * the server still binds loopback only; the tunnel is the only way in,
  * athlete data and tokens live outside the git checkout,
  * the nightly job runs the same scripts the laptop runs, and cannot hang on a
    Garmin MFA prompt,
  * no secret is committed, and the unattended publisher stages the kit,
  * the shell scripts are valid bash.

They are deliberately independent of the Windows laptop: everything they read is
in the repository, so a clean CI checkout runs them.
"""

import ast
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import export_publish

REPO = Path(export_publish.REPO)
KIT = REPO / "deploy" / "cloud"

SERVER = KIT / "coach-dashboard.service"
TUNNEL = KIT / "coach-dashboard-tunnel.service"
SYNC = KIT / "coach-dashboard-sync.service"
TIMER = KIT / "coach-dashboard-sync.timer"
INSTALL = KIT / "install.sh"
SYNC_SH = KIT / "sync.sh"
REFRESH = KIT / "refresh_export.py"
MIGRATE = KIT / "migrate-to-cloud.ps1"
APPLY = KIT / "migrate-apply.sh"
README = KIT / "README.md"
POLICY = KIT / "host-header-policy.yml"

EXPECTED = [SERVER, TUNNEL, SYNC, TIMER, INSTALL, SYNC_SH, REFRESH,
            MIGRATE, APPLY, README, POLICY]


def read(path):
    return path.read_text(encoding="utf-8")


def parse_unit(path):
    """Tiny systemd-unit reader.

    configparser rejects repeated keys such as several ``Environment=`` lines,
    and that repetition is exactly what this kit needs, so parse by hand.
    """
    sections = {}
    current = None
    for raw in read(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, {})
            continue
        if "=" in line and current is not None:
            key, value = line.split("=", 1)
            sections[current].setdefault(key.strip(), []).append(value.strip())
    return sections


def values(unit, section, key):
    return parse_unit(unit).get(section, {}).get(key, [])


def one(unit, section, key):
    found = values(unit, section, key)
    assert len(found) == 1, "%s [%s] %s: %r" % (unit.name, section, key, found)
    return found[0]


def kit_text():
    return {p.name: read(p) for p in KIT.rglob("*") if p.is_file()}


def test_the_kit_is_complete():
    for path in EXPECTED:
        assert path.is_file(), "missing %s" % path


def test_no_public_bind_and_no_browser_cors():
    """The VM must not open a port, and the page must stay same-origin."""
    for name, text in kit_text().items():
        low = text.lower()
        assert "0.0.0.0" not in text, "%s binds or documents a public bind" % name
        assert "--lan" not in text, "%s would bind all interfaces" % name
        assert "access-control-allow-origin" not in low, "%s adds CORS" % name


def test_server_binds_loopback_and_never_idles_out():
    assert one(SERVER, "Service", "User") == "coach"
    assert one(SERVER, "Service", "WorkingDirectory") == "/opt/coach-dashboard/app"
    exec_start = one(SERVER, "Service", "ExecStart")
    assert exec_start.endswith("garmin_server.py --idle-timeout 0")
    assert "/opt/coach-dashboard/venv/bin/python" in exec_start
    assert "--host" not in exec_start
    assert one(SERVER, "Service", "Restart") == "always"


def test_server_keeps_data_and_code_in_separate_places():
    env = values(SERVER, "Service", "Environment")
    assert "GARMIN_DATA_DIR=/srv/coach-dashboard/data" in env
    assert "TRAINLOOP_DB=/srv/coach-dashboard/data/trainloop.db" in env
    assert "GARMINTOKENS=/srv/coach-dashboard/data/.garmin_tokens" in env
    # The checkout may be reset by an upgrade; the data directory may not.
    writable = one(SERVER, "Service", "ReadWritePaths")
    assert "/srv/coach-dashboard/data" in writable
    assert one(SERVER, "Service", "ProtectSystem") == "strict"
    assert one(SERVER, "Service", "ProtectHome") == "yes"


def test_tunnel_is_the_only_way_in_and_rewrites_host():
    assert one(TUNNEL, "Unit", "Requires") == "coach-dashboard.service"
    assert one(TUNNEL, "Service", "EnvironmentFile") == \
        "/etc/coach-dashboard/ngrok.env"
    exec_start = one(TUNNEL, "Service", "ExecStart")
    assert "/usr/bin/ngrok http 127.0.0.1:24567" in exec_start
    assert "--url=https://foam-tackiness-header.ngrok-free.dev" in exec_start
    assert "--traffic-policy-file=/etc/coach-dashboard/host-header-policy.yml" \
        in exec_start
    # The token is read from a file, never written into the unit.
    assert "NGROK_AUTHTOKEN=" not in read(TUNNEL)


def test_traffic_policy_matches_the_server_host_check():
    text = read(POLICY)
    assert "add-headers" in text
    assert 'host: "127.0.0.1:24567"' in text


def test_nightly_timer_is_persistent_and_points_at_the_sync_unit():
    assert one(TIMER, "Timer", "Unit") == "coach-dashboard-sync.service"
    assert one(TIMER, "Timer", "Persistent") == "true"
    assert one(TIMER, "Timer", "OnCalendar").startswith("*-*-* ")
    assert "timers.target" in values(TIMER, "Install", "WantedBy")


def test_sync_unit_cannot_hang_on_an_mfa_prompt():
    assert one(SYNC, "Service", "Type") == "oneshot"
    assert one(SYNC, "Service", "StandardInput") == "null"
    exec_start = one(SYNC, "Service", "ExecStart")
    assert exec_start == \
        "/bin/bash /opt/coach-dashboard/app/deploy/cloud/sync.sh"
    assert one(SYNC, "Service", "User") == "coach"


def test_sync_script_runs_download_import_and_export_in_order():
    text = read(SYNC_SH)
    positions = [
        text.index("garmin_sync.py"),
        text.index("trainloop.py bootstrap"),
        text.index("refresh_export.py"),
    ]
    assert positions == sorted(positions)
    # A failure in one step must not skip the remaining steps, so the script
    # records the failure instead of exiting on the first error.
    assert "set -uo pipefail" in text
    assert "|| rc=1" in text
    assert "exit \"$rc\"" in text


def test_refresh_export_uses_the_same_builder_and_never_touches_git():
    text = read(REFRESH)
    tree = ast.parse(text)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert any(isinstance(c.func, ast.Attribute) and c.func.attr == "build_csv"
               for c in calls), "refresh_export.py must call build_csv()"
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert "subprocess" not in imported
    # The checkout is a git repository; this script must not run git commands.
    assert "git " not in text.lower()


def test_refresh_export_compiles():
    compile(read(REFRESH), str(REFRESH), "exec")


def test_shell_scripts_are_valid_bash():
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is not installed; CI runs this check")
    for path in (INSTALL, SYNC_SH, APPLY):
        proc = subprocess.run([bash, "-n", str(path)],
                              capture_output=True, text=True)
        assert proc.returncode == 0, "%s: %s" % (path.name, proc.stderr)


def test_installer_is_idempotent_and_gates_the_tunnel():
    text = read(INSTALL)
    assert "[ \"$(id -u)\" -eq 0 ]" in text
    assert "[ -d \"$APP_DIR/.git\" ]" in text
    assert "[ ! -x \"$VENV/bin/python\" ]" in text
    assert "useradd" in text
    assert "command -v ngrok" in text
    assert "[ -s \"$CONF_DIR/ngrok.env\" ]" in text
    # Every unit in the kit is installed.
    for unit in sorted(KIT.glob("*.service")) + sorted(KIT.glob("*.timer")):
        assert unit.name in text, "install.sh does not install %s" % unit.name
    # The password warning is the guard against an open public URL.
    assert ".coach_dash_auth" in text


def test_migration_sends_named_data_only_and_cleans_up():
    text = read(MIGRATE)
    for name in (".garmin_tokens", "garmin_fit", ".coach_dash_auth",
                 ".coach_dash_sessionkey", "nutrition_log.csv",
                 "manual_runs.json", "trainloop.db", "dashboard\\index.html"):
        assert name in text, "migration omits %s" % name
    assert "finally" in text
    assert "Remove-Item -Path $stage" in text
    assert "Remove-Item -Path $archive" in text
    # It must not print the contents of anything it copies.
    assert "Get-Content" not in text


def test_migration_apply_restricts_secret_permissions():
    text = read(APPLY)
    assert "chmod 700 \"$DATA_DIR\"" in text
    assert "chmod 600 \"$DATA_DIR/$f\"" in text
    assert "chown -R \"$SERVICE_USER:$SERVICE_USER\"" in text
    assert "/srv/coach-dashboard/data" in text
    assert "systemctl restart coach-dashboard.service" in text
    assert "set -euo pipefail" in text


def test_readme_documents_the_operational_contract():
    low = " ".join(read(README).lower().split())
    for needle in ("oracle", "e2-micro", "ubuntu 24.04",
                   "foam-tackiness-header.ngrok-free.dev",
                   "one agent per static domain", "mfa",
                   "stop-dashboard.cmd", "backup_data.py",
                   "docs/restore.md"):
        assert needle in low, "README does not mention %r" % needle
    # It must be honest that the VM is still a single point of failure.
    assert "cannot wake a dead vm" in low


def test_no_secret_shaped_text_is_committed():
    for name, text in kit_text().items():
        found = export_publish.scan_secrets(text)
        assert not found, "%s contains %s" % (name, found)


def test_gitattributes_keeps_shell_scripts_lf():
    text = read(REPO / ".gitattributes")
    assert "deploy/cloud/*.sh text eol=lf" in text
    assert "*.service text eol=lf" in text
    assert "*.timer text eol=lf" in text


def test_publisher_stages_the_kit(tmp_path, monkeypatch):
    """The unattended publisher must not silently leave deploy/ behind."""
    monkeypatch.setattr(export_publish, "REPO", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    for rel in ("deploy/cloud/sync.sh", "deploy/cloud/README.md",
                "deploy/cloud/coach-dashboard.service",
                "deploy/cloud/coach-dashboard-sync.timer",
                "deploy/cloud/refresh_export.py"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", encoding="utf-8")
    (tmp_path / "deploy/cloud/notes.bin").write_text("x", encoding="utf-8")

    staged = export_publish.code_paths()
    assert "deploy/cloud/sync.sh" in staged
    assert "deploy/cloud/README.md" in staged
    assert "deploy/cloud/coach-dashboard.service" in staged
    assert "deploy/cloud/coach-dashboard-sync.timer" in staged
    assert "deploy/cloud/refresh_export.py" in staged
    assert "deploy/cloud/notes.bin" not in staged

    scanned = export_publish.publishable_text_paths()
    assert "deploy/cloud/sync.sh" in scanned
    assert "deploy/cloud/coach-dashboard.service" in scanned


def test_units_reference_files_that_exist_in_the_checkout():
    """A unit must not point at a path the repository never provides."""
    assert (REPO / "garmin_server.py").is_file()
    assert (REPO / "deploy/cloud/sync.sh").is_file()
    assert (REPO / "deploy/cloud/refresh_export.py").is_file()
    assert os.path.basename(one(SERVER, "Service", "ExecStart").split()[0]) == \
        "python"
