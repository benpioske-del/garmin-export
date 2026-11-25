"""Server-side Cronometer pull, tested against a local fake web endpoint.

No test uses a real Cronometer account or a real credential. The fake endpoint
speaks just enough of the private web handshake to prove the client, the CSV
parser and the status file are wired together without leaking a token.
"""

import http.server
import json
import os
import sys
import threading
import urllib.parse

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cronometer_sync  # noqa: E402
import garmin_server  # noqa: E402
import nutrition  # noqa: E402

# Reserved domain and a space-containing value so the published-file secret
# scanners cannot mistake fixtures for a real credential.
USER = "athlete@test"
PASSWORD = "dummy value"
SESSION_TOKEN = "a" * 32
NONCE = "b" * 32

CSV = (
    "Day,Energy (kcal),Protein (g),Carbs (g),Fat (g),Group\n"
    "2026-11-22,2100,150,200,70,\n"
    "2026-11-23,2200,160,210,72,\n"
)


class Handler(http.server.BaseHTTPRequestHandler):
    calls = []

    def log_message(self, fmt, *args):
        pass

    def _reply(self, status, body, content_type="text/plain; charset=utf-8"):
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        type(self).calls.append(self.path)
        if self.path == "/login/":
            self._reply(200, '<input name="anticsrf" value="csrf-123">',
                        "text/html; charset=utf-8")
        elif self.path.startswith("/export"):
            query = urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query)
            if query.get("generate") != ["dailySummary"]:
                return self._reply(400, "wrong export type")
            if query.get("nonce") != [NONCE]:
                return self._reply(403, "wrong nonce")
            self._reply(200, CSV, "text/csv; charset=utf-8")
        else:
            self._reply(404, "not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8")
        type(self).calls.append(self.path)
        if self.path == "/login":
            form = urllib.parse.parse_qs(body)
            if (form.get("username") != [USER]
                    or form.get("password") != [PASSWORD]
                    or form.get("anticsrf") != ["csrf-123"]):
                return self._reply(200, '{"error":"bad login"}',
                                   "application/json")
            self._reply(200, '{"ok":true}', "application/json")
        elif self.path == "/cronometer/app":
            if "authenticate" in body:
                self._reply(200, '//OK[42,"%s",0]' % SESSION_TOKEN)
            elif "generateAuthorizationToken" in body:
                self._reply(200, '//OK[1,["%s"],0,7]' % NONCE)
            else:
                self._reply(500, "//EX[unknown]")
        else:
            self._reply(404, "not found")


@pytest.fixture()
def fake_cronometer(monkeypatch, tmp_path):
    Handler.calls = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("CRONOMETER_USERNAME", USER)
    monkeypatch.setenv("CRONOMETER_PASSWORD", PASSWORD)
    monkeypatch.setenv("CRONOMETER_SYNC_STATUS", str(tmp_path / "status.json"))
    monkeypatch.setattr(nutrition, "NUTRITION_FILE",
                        str(tmp_path / "nutrition_log.csv"))
    yield "http://127.0.0.1:%d" % server.server_address[1]
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_pull_imports_daily_totals_and_records_sanitised_status(fake_cronometer):
    client = cronometer_sync.CronometerClient(base_url=fake_cronometer)
    result = cronometer_sync.sync(3, client=client)

    assert result["ok"] is True
    assert result["accepted"] == 2
    assert result["upserted"] == 2
    assert result["total_days"] == 2
    days = {d["date"]: d for d in nutrition.read_days()}
    assert days["2026-11-22"]["protein"] == 150
    assert days["2026-11-23"]["calories"] == 2200

    status = cronometer_sync.read_status()
    assert status["state"] == "ok"
    assert status["ok"] is True
    assert status["last_success"]
    raw = json.dumps(status)
    assert PASSWORD not in raw
    assert SESSION_TOKEN not in raw
    assert NONCE not in raw

    paths = [p for p in Handler.calls if p.startswith("/export")]
    assert len(paths) == 1
    assert "generate=dailySummary" in paths[0]
    assert NONCE in paths[0]


def test_repull_is_idempotent(fake_cronometer):
    first = cronometer_sync.sync(
        3, client=cronometer_sync.CronometerClient(base_url=fake_cronometer))
    second = cronometer_sync.sync(
        3, client=cronometer_sync.CronometerClient(base_url=fake_cronometer))
    # upsert_days counts distinct dates written, not rows changed. Idempotence
    # here is one row per date, never a duplicate appended on a re-pull.
    assert first["upserted"] == 2
    assert second["upserted"] == 2
    assert second["total_days"] == 2
    assert len(nutrition.read_days()) == 2


def test_missing_credentials_skip_without_a_request(fake_cronometer,
                                                     monkeypatch):
    monkeypatch.delenv("CRONOMETER_USERNAME")
    monkeypatch.delenv("CRONOMETER_PASSWORD")
    result = cronometer_sync.sync(3)
    assert result == {"ok": True, "skipped": True,
                      "status": "not_configured"}
    assert Handler.calls == []
    assert cronometer_sync.read_status()["state"] == "not_configured"


def test_bad_login_fails_safely(fake_cronometer, monkeypatch):
    monkeypatch.setenv("CRONOMETER_PASSWORD", "wrong-value")
    result = cronometer_sync.sync(
        3, client=cronometer_sync.CronometerClient(base_url=fake_cronometer))
    assert result["ok"] is False
    assert result["error"] == "login was rejected by Cronometer"
    status = cronometer_sync.read_status()
    assert status["state"] == "failed"
    assert "wrong-value" not in json.dumps(status)
    assert nutrition.read_days() == []


def test_check_does_not_print_the_secret(fake_cronometer, capsys):
    assert cronometer_sync.main(["--check"]) == 0
    assert capsys.readouterr().out.strip() == "Cronometer credentials: configured"


def test_dashboard_sync_reports_the_nutrition_step(monkeypatch, tmp_path):
    """The Sync button covers nutrition too, without failing a good Garmin run."""
    scripts = {
        "SYNC_SCRIPT": "print('Done: 0 new run(s) downloaded, 1 already current.')",
        "IMPORT_SCRIPT": "print('database already up to date')",
        "CRONOMETER_SYNC_SCRIPT":
            "print('Cronometer sync: accepted 2 day(s), upserted 1, total 9')",
    }
    for name, source in scripts.items():
        path = tmp_path / (name + ".py")
        path.write_text(source, encoding="utf-8")
        monkeypatch.setattr(garmin_server, name, str(path))
    result = garmin_server._run_sync()
    assert result["ok"] is True
    assert result["nutrition_ok"] is True
    assert "== Cronometer sync ==" in result["output"]
    assert "Cronometer sync: accepted 2 day(s)" in result["output"]
