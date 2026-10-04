"""HTTP-level tests for the dashboard JSON API.

test_dashboard_api.py covers what the routes compute. This file covers the wire:
status codes, content types, the token gate, structured errors that do not leak
tracebacks, and proof that the pre-existing raw FIT routes still work.

A real server is bound on an ephemeral loopback port. Nothing here reaches the
network; PORT is a module global that do_GET validates the Host header against,
so the test sets it before serving.
"""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import garmin_server as G

TOKEN = "test-token-abc123"


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(G, "TOKEN", TOKEN)
    # An empty fit dir keeps these tests off the athlete's real files.
    monkeypatch.setattr(G, "FIT_DIR", "")
    monkeypatch.setattr(G, "fit_names", lambda: ["2026-10-01_111.fit"])

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), G.Handler)
    port = httpd.server_address[1]
    # do_GET rejects any Host that is not 127.0.0.1:<PORT> or localhost:<PORT>.
    monkeypatch.setattr(G, "PORT", port)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield "http://127.0.0.1:%d" % port
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(base, path, token=TOKEN, host=None):
    req = urllib.request.Request(base + path)
    if token is not None:
        req.add_header("X-Dash-Token", token)
    if host is not None:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()


def _json(base, path, **kw):
    status, ctype, body = _get(base, path, **kw)
    return status, ctype, json.loads(body.decode("utf-8"))


# --------------------------------------------------------------- happy paths

@pytest.mark.parametrize("path", ["/api/activities", "/api/load", "/api/coaching"])
def test_every_route_answers_200_json(server, path):
    status, ctype, payload = _json(server, path)
    assert status == 200
    assert ctype == "application/json; charset=utf-8"
    assert isinstance(payload, dict)


def test_success_responses_are_not_cached(server):
    """A cached coaching panel is a stale coaching panel."""
    req = urllib.request.Request(server + "/api/coaching")
    req.add_header("X-Dash-Token", TOKEN)
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.headers.get("Cache-Control") == "no-store"
        assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_no_cors_headers_are_ever_sent(server):
    req = urllib.request.Request(server + "/api/load")
    req.add_header("X-Dash-Token", TOKEN)
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.headers.get("Access-Control-Allow-Origin") is None


# ------------------------------------------------------------------- the gate

@pytest.mark.parametrize("path", ["/api/activities", "/api/load", "/api/coaching"])
def test_api_requires_the_dash_token(server, path):
    status, _, _ = _get(server, path, token=None)
    assert status == 403


def test_api_rejects_a_wrong_token(server):
    status, _, _ = _get(server, "/api/load", token="not-the-token")
    assert status == 403


def test_api_rejects_a_foreign_host_header(server):
    """DNS-rebinding defence. The Host must be the loopback port we bound."""
    req = urllib.request.Request(server + "/api/load")
    req.add_header("X-Dash-Token", TOKEN)
    req.add_header("Host", "evil.example.com")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            pytest.fail("a foreign Host header was served: %s" % r.status)
    except urllib.error.HTTPError as e:
        assert e.code == 403


# ------------------------------------------------------------- error handling

def test_unknown_api_endpoint_is_a_json_404(server):
    status, ctype, payload = _json(server, "/api/nope")
    assert status == 404
    assert ctype == "application/json; charset=utf-8"
    assert payload["error"] == "unknown endpoint"
    assert "/api/load" in payload["available"]


def test_unsupported_query_parameter_is_a_json_400(server):
    status, _, payload = _json(server, "/api/activities?limitt=5")
    assert status == 400
    assert payload["error"] == "unsupported query parameter"
    assert payload["parameter"] == "limitt"


def test_malformed_as_of_is_a_json_400(server):
    status, _, payload = _json(server, "/api/load?as_of=yesterday")
    assert status == 400
    assert "ISO-8601" in payload["error"]


def test_valid_as_of_is_accepted(server):
    status, _, payload = _json(server, "/api/load?as_of=2026-10-04T00:00:00Z")
    assert status == 200
    assert payload["as_of_utc"].startswith("2026-10-04")


def test_a_duplicated_parameter_cannot_smuggle_a_second_value(server):
    """parse_qs yields a list per key; taking the first is deliberate."""
    status, _, payload = _json(server, "/api/load?as_of=2026-10-04T00:00:00Z"
                                      "&as_of=not-a-date")
    assert status == 200, "the first value must win, and it must be validated"


def test_route_failure_is_a_json_500_without_a_traceback(server, monkeypatch):
    """A stack trace or a filesystem path in a browser response is an
    information leak. The detail goes to stderr only."""
    def boom(conn, hr, at):
        raise RuntimeError("secret path C:\\Users\\benpi\\private.db")
    monkeypatch.setitem(G.API_ROUTES, "/api/load", boom)

    status, ctype, body = _get(server, "/api/load")
    assert status == 500
    assert ctype == "application/json; charset=utf-8"
    text = body.decode("utf-8")
    assert "Traceback" not in text
    assert "RuntimeError" not in text
    assert "benpi" not in text
    assert "private.db" not in text
    assert json.loads(text)["error"] == "internal error"


def test_error_body_is_still_valid_json_when_the_payload_is_unserialisable(
        server, monkeypatch):
    def weird(conn, hr, at):
        return {"bad": object()}
    monkeypatch.setitem(G.API_ROUTES, "/api/load", weird)
    status, ctype, body = _get(server, "/api/load")
    # default=str copes, so this must succeed rather than 500.
    assert status == 200
    assert json.loads(body.decode("utf-8"))["bad"]


# ------------------------------------------------- pre-existing routes intact

def test_ping_still_works_without_a_token(server):
    status, _, body = _get(server, "/ping", token=None)
    assert status == 200
    assert body == b"coach-dashboard"


def test_fit_list_route_is_unchanged(server):
    status, ctype, body = _get(server, "/fit-list")
    assert status == 200
    assert json.loads(body.decode("utf-8")) == ["2026-10-01_111.fit"]


def test_raw_fit_route_still_rejects_an_unknown_file(server):
    status, _, _ = _get(server, "/fit/not-a-real-file.fit")
    assert status == 404


def test_raw_fit_route_still_rejects_a_path_traversal(server):
    """The route strips separators; traversal must not escape FIT_DIR."""
    status, _, _ = _get(server, "/fit/..%2f..%2fetc%2fpasswd")
    assert status in (403, 404)


def test_unknown_non_api_route_is_still_plain_text_404(server):
    status, _, _ = _get(server, "/not-a-thing")
    assert status == 404