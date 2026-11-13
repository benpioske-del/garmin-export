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
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import garmin_server as G

TOKEN = "test-token-abc123"


@pytest.fixture
def dashboard_html(monkeypatch, tmp_path):
    """A minimal page, so these wire tests do not depend on the gitignored
    dashboard/index.html being present (it never is on a clean checkout)."""
    html = tmp_path / "index.html"
    html.write_text(
        "<!doctype html><html><head><title>x</title></head>"
        "<body>hi</body></html>", encoding="utf-8")
    monkeypatch.setattr(G, "resolve_dashboard_html", lambda: str(html))
    return html


@pytest.fixture
def server(monkeypatch, migrated_db, dashboard_html):
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


# ------------------------------------------------------- mobile (PWA) extras

def test_manifest_is_served_without_a_token(server):
    """The browser fetches the manifest itself; it never carries our header."""
    status, ctype, body = _get(server, "/manifest.webmanifest", token=None)
    assert status == 200
    assert ctype == "application/manifest+json; charset=utf-8"
    m = json.loads(body.decode("utf-8"))
    assert m["short_name"]
    assert m["start_url"] == "/"
    assert m["display"] == "standalone"


def test_service_worker_is_served_without_a_token(server):
    status, ctype, body = _get(server, "/sw.js", token=None)
    assert status == 200
    assert ctype == "text/javascript; charset=utf-8"
    assert b"service worker" in body.lower()


def test_service_worker_caches_the_page_and_data_for_offline(server):
    """Offline fallback: the worker keeps the shell + API data on the device."""
    _, _, body = _get(server, "/sw.js", token=None)
    text = body.decode("utf-8")
    assert "caches.open" in text
    assert G.SW_CACHE in text
    # Only the real dashboard is cached as the shell, never the login page.
    assert G.PWA_MARK in text
    assert "'/api/'" in text


def test_service_worker_falls_back_to_the_cache_on_an_origin_outage(server):
    """A dead tunnel returns 5xx, which is not a network error - use the cache."""
    _, _, body = _get(server, "/sw.js", token=None)
    text = body.decode("utf-8")
    assert "502" in text and "503" in text and "504" in text
    assert "cache.match(req)" in text
    assert "cache.match(SHELL)" in text
    # POSTs (e.g. /login, /sync) are never touched.
    assert "req.method !== 'GET'" in text


def test_classic_dashboard_receives_the_pwa_tags(server, monkeypatch, tmp_path):
    html = tmp_path / "index.html"
    html.write_text("<!doctype html><html><head><title>x</title></head>"
                    "<body>hi</body></html>", encoding="utf-8")
    monkeypatch.setattr(G, "resolve_dashboard_html", lambda: str(html))
    status, _, body = _get(server, "/classic")
    text = body.decode("utf-8")
    assert status == 200
    assert '<link rel="manifest" href="/manifest.webmanifest">' in text
    assert "serviceWorker.register('/sw.js')" in text
    assert 'name="apple-mobile-web-app-capable"' in text
    # injected once, not once per request
    assert text.count(G.PWA_MARK) == 1


def test_pwa_injection_is_idempotent_and_never_corrupts_non_html():
    page = b"<!doctype html><html><head></head><body></body></html>"
    once = G.inject_pwa(page)
    assert once.count(G.PWA_MARK.encode("utf-8")) == 1
    assert G.inject_pwa(once) == once
    raw = b"\xff\xfe\x00\x01"
    assert G.inject_pwa(raw) == raw


# --------------------------------------------------- network (LAN) exposure

def test_a_lan_host_is_answered_only_when_it_is_allowed(server, monkeypatch):
    port = int(server.rsplit(":", 1)[1])
    lan = "192.168.1.50"

    monkeypatch.setattr(G, "ALLOWED_HOSTS", {"127.0.0.1", "localhost"})
    status, _, _ = _get(server, "/api/load", host="%s:%d" % (lan, port))
    assert status == 403, "an unlisted LAN host must be refused"

    monkeypatch.setattr(G, "ALLOWED_HOSTS",
                        {"127.0.0.1", "localhost", lan})
    status, _, payload = _json(server, "/api/load", host="%s:%d" % (lan, port))
    assert status == 200
    assert isinstance(payload, dict)


def test_host_must_carry_our_port_even_for_a_known_name(server, monkeypatch):
    """A right name on the wrong port is still a rebinding attempt."""
    monkeypatch.setattr(G, "PORT", 1)  # no real server has this
    status, _, _ = _get(server, "/api/load", host="127.0.0.1:9")
    assert status == 403


# ------------------------------------------------------- password (login) gate

PASSWORD = "s3cret-pass"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface 3xx as an HTTPError so a test can inspect Location/Set-Cookie."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT = urllib.request.build_opener(_NoRedirect)


def _call(opener, base, path, data=None, headers=None):
    req = urllib.request.Request(base + path)
    if data is not None:
        req.data = urllib.parse.urlencode(data).encode("utf-8")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    for key, val in (headers or {}).items():
        req.add_header(key, val)
    try:
        with opener.open(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


@pytest.fixture
def secured_server(monkeypatch, migrated_db, dashboard_html):
    monkeypatch.setattr(G, "TOKEN", TOKEN)
    monkeypatch.setattr(G, "FIT_DIR", "")
    monkeypatch.setattr(G, "fit_names", lambda: ["2026-10-01_111.fit"])
    monkeypatch.setattr(G, "SESSION_KEY", "unit-test-session-key")
    monkeypatch.setattr(G, "PASSWORD_HASH", G.hash_password(PASSWORD))
    monkeypatch.setattr(G, "REQUIRE_LOGIN", True)
    monkeypatch.setattr(G, "_login_failures", 0)
    monkeypatch.setattr(G, "_login_lock_until", 0.0)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), G.Handler)
    port = httpd.server_address[1]
    monkeypatch.setattr(G, "PORT", port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield "http://127.0.0.1:%d" % port
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_page_redirects_to_login_without_a_session(secured_server):
    status, headers, _ = _call(_NO_REDIRECT, secured_server, "/")
    assert status == 303
    assert headers.get("Location") == "/login"


def test_login_page_renders_a_form(secured_server):
    status, _, body = _call(_NO_REDIRECT, secured_server, "/login")
    assert status == 200
    assert b"Sign in" in body
    assert b'name="password"' in body


def test_wrong_password_is_rejected(secured_server):
    status, headers, body = _call(_NO_REDIRECT, secured_server, "/login",
                                  data={"password": "nope"})
    assert status == 401
    assert b"Wrong password" in body
    assert "dash_session" not in headers.get("Set-Cookie", "")


def test_correct_password_sets_a_cookie_and_unlocks_the_page(secured_server):
    status, headers, _ = _call(_NO_REDIRECT, secured_server, "/login",
                               data={"password": PASSWORD})
    assert status == 303
    assert headers.get("Location") == "/"
    cookie = headers.get("Set-Cookie", "")
    assert cookie.startswith("dash_session=")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie

    sid = cookie.split(";", 1)[0]
    status, _, body = _call(_NO_REDIRECT, secured_server, "/",
                            headers={"Cookie": sid})
    assert status == 200
    assert G.PWA_MARK.encode("utf-8") in body


def test_cookie_alone_authorises_a_data_route(secured_server):
    _, headers, _ = _call(_NO_REDIRECT, secured_server, "/login",
                          data={"password": PASSWORD})
    sid = headers["Set-Cookie"].split(";", 1)[0]
    status, _, payload = _call(urllib.request.build_opener(), secured_server,
                               "/api/load", headers={"Cookie": sid})
    assert status == 200
    assert isinstance(json.loads(payload.decode("utf-8")), dict)


def test_data_route_needs_a_session_when_login_is_on(secured_server):
    status, _, _ = _call(_NO_REDIRECT, secured_server, "/api/load")
    assert status == 403


def test_a_forged_cookie_is_refused(secured_server):
    status, _, _ = _call(_NO_REDIRECT, secured_server, "/api/load",
                         headers={"Cookie": "dash_session=9999999999.deadbeef"})
    assert status == 403


def test_the_local_token_still_works_when_login_is_on(secured_server):
    """Desktop keeps using ?tk= / the header; the login is additive."""
    status, _, _ = _call(_NO_REDIRECT, secured_server, "/api/load",
                         headers={"X-Dash-Token": TOKEN})
    assert status == 200


def test_logout_clears_the_cookie(secured_server):
    status, headers, _ = _call(_NO_REDIRECT, secured_server, "/logout")
    assert status == 303
    assert headers.get("Location") == "/login"
    assert headers.get("Set-Cookie", "").endswith("Max-Age=0")


def test_secure_flag_is_set_only_behind_https(secured_server):
    _, plain, _ = _call(_NO_REDIRECT, secured_server, "/login",
                        data={"password": PASSWORD})
    assert "Secure" not in plain.get("Set-Cookie", "")
    _, tls, _ = _call(_NO_REDIRECT, secured_server, "/login",
                      data={"password": PASSWORD},
                      headers={"X-Forwarded-Proto": "https"})
    assert "Secure" in tls.get("Set-Cookie", "")


def test_session_cookie_is_signed_and_expires(monkeypatch):
    monkeypatch.setattr(G, "SESSION_KEY", "k")
    good = G.make_session(now=1000.0)
    assert G.session_valid(good, now=1000.0)
    assert not G.session_valid(good, now=1000.0 + G.SESSION_TTL + 1)
    assert not G.session_valid(good[:-1] + ("0" if good[-1] != "0" else "1"),
                               now=1000.0)
    assert not G.session_valid("not-a-token", now=1000.0)


def test_login_is_skipped_when_no_password_is_set(server):
    """The default (unsecured) server must behave exactly as before."""
    status, _, body = _call(_NO_REDIRECT, server, "/")
    assert status == 200
    assert b"Sign in" not in body


# --------------------------------------------------------- aurora preview

@pytest.fixture
def aurora_html(monkeypatch, tmp_path):
    """A minimal stand-in for the committed flow output."""
    html = tmp_path / "aurora_dashboard.html"
    html.write_text(
        '<!doctype html><html><head><title>aurora</title></head>'
        '<body><main id="app"></main>'
        '<script>const RUNS=[];const SUMMARY={};</script></body></html>',
        encoding="utf-8")
    monkeypatch.setattr(G, "resolve_aurora_html", lambda: str(html))
    return html


def test_root_serves_aurora_with_the_live_bootstrap(server, aurora_html):
    """Aurora is the dashboard now, so `/` must carry the live layer."""
    status, ctype, body = _get(server, "/")
    assert status == 200
    assert ctype == "text/html; charset=utf-8"
    text = body.decode("utf-8")
    assert G.AURORA_LIVE_MARK in text
    assert "/api/activities" in text
    assert "/api/load" in text
    assert "/api/coaching" in text
    assert G.PWA_MARK in text


def test_aurora_address_remains_an_alias(server, aurora_html):
    """Old bookmarks and the previous PWA start_url still work."""
    status, _, body = _get(server, "/aurora")
    assert status == 200
    assert G.AURORA_LIVE_MARK in body.decode("utf-8")


def test_classic_serves_the_local_dashboard(server, monkeypatch, tmp_path):
    html = tmp_path / "index.html"
    html.write_text("<!doctype html><html><body>classic-page</body></html>",
                    encoding="utf-8")
    monkeypatch.setattr(G, "resolve_dashboard_html", lambda: str(html))
    status, _, body = _get(server, "/classic")
    assert status == 200
    assert b"classic-page" in body


def test_root_falls_back_to_the_local_dashboard_without_aurora(
        server, monkeypatch, tmp_path):
    """A clean checkout without the committed app still opens a real page."""
    html = tmp_path / "index.html"
    html.write_text("<!doctype html><html><body>fallback-page</body></html>",
                    encoding="utf-8")
    monkeypatch.setattr(G, "resolve_aurora_html", lambda: None)
    monkeypatch.setattr(G, "resolve_dashboard_html", lambda: str(html))
    status, _, body = _get(server, "/")
    assert status == 200
    assert b"fallback-page" in body


def test_aurora_preview_requires_the_dash_token(server, aurora_html):
    status, _, _ = _get(server, "/aurora", token=None)
    assert status == 403


def test_aurora_preview_accepts_the_token_in_the_query(server, aurora_html):
    status, ctype, body = _get(server, "/aurora?tk=" + TOKEN, token=None)
    assert status == 200
    assert ctype == "text/html; charset=utf-8"
    assert G.AURORA_LIVE_MARK in body.decode("utf-8")


def test_aurora_preview_is_404_when_the_file_is_absent(server, monkeypatch):
    monkeypatch.setattr(G, "resolve_aurora_html", lambda: None)
    status, _, _ = _get(server, "/aurora")
    assert status == 404


def test_inject_aurora_live_is_idempotent():
    html = b"<html><body>x</body></html>"
    once = G.inject_aurora_live(html)
    twice = G.inject_aurora_live(once)
    assert once == twice
    assert once.decode("utf-8").count(G.AURORA_LIVE_MARK) == 1


def test_launch_url_opens_the_dashboard_at_root(aurora_html):
    """`/` is the dashboard, so --open lands there."""
    assert G.launch_url(8765, "tok") == \
        "http://127.0.0.1:8765/?tk=tok"


def test_launch_url_falls_back_to_the_local_dashboard(monkeypatch):
    """A clean checkout without the committed app still opens a real page."""
    monkeypatch.setattr(G, "resolve_aurora_html", lambda: None)
    assert G.launch_url(8765, "tok") == "http://127.0.0.1:8765/?tk=tok"


def test_launch_url_carries_the_run_port_and_token(aurora_html):
    url = G.launch_url(9999, "abc123")
    assert ":9999/" in url
    assert url.endswith("?tk=abc123")


def test_aurora_rewrites_the_chart_cdn_to_the_vendored_file(
        server, tmp_path, monkeypatch):
    """Charts must not depend on cdn.jsdelivr.net: the server swaps the CDN URL
    for the committed copy so the app works offline and behind a blocked CDN."""
    html = tmp_path / "aurora_dashboard.html"
    html.write_text(
        '<!doctype html><html><head><script src="%s"></script></head>'
        '<body>x</body></html>' % G.CHART_CDN,
        encoding="utf-8")
    vendor = tmp_path / "chart.umd.min.js"
    vendor.write_text("/* chart */", encoding="utf-8")
    monkeypatch.setattr(G, "resolve_aurora_html", lambda: str(html))
    monkeypatch.setattr(G, "CHART_FILE", str(vendor))
    _, _, body = _get(server, "/aurora")
    text = body.decode("utf-8")
    assert "/vendor/chart.umd.min.js" in text
    assert G.CHART_CDN not in text


def test_vendored_chart_js_is_served_without_the_token(
        server, tmp_path, monkeypatch):
    vendor = tmp_path / "chart.umd.min.js"
    vendor.write_text("/* chart */", encoding="utf-8")
    monkeypatch.setattr(G, "CHART_FILE", str(vendor))
    status, ctype, body = _get(server, "/vendor/chart.umd.min.js", token=None)
    assert status == 200
    assert ctype == "text/javascript; charset=utf-8"
    assert body == b"/* chart */"


def test_aurora_gets_the_pwa_tags(server, aurora_html):
    """Mobile install/offline is injected into /aurora, not only /."""
    _, _, body = _get(server, "/aurora")
    text = body.decode("utf-8")
    assert G.PWA_MARK in text
    assert "/manifest.webmanifest" in text
    assert "/sw.js" in text


# --------------------------------------------------------- nutrition routes

@pytest.fixture
def nutrition_file(monkeypatch, tmp_path):
    """Point the module at a temp log so the athlete's real log is untouched."""
    import nutrition
    path = tmp_path / "nutrition_log.csv"
    monkeypatch.setattr(nutrition, "NUTRITION_FILE", str(path))
    return path


def _post_json(base, path, payload, token=TOKEN, raw=None, headers=None):
    body = raw if raw is not None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base + path, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if token is not None:
        req.add_header("X-Dash-Token", token)
    for key, value in (headers or {}).items():
        req.add_header(key, value)

    def parsed(data):
        try:
            return json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            # The gate denies with plain text, not JSON.
            return {"raw": data.decode("utf-8", "replace")}

    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers.get("Content-Type"), parsed(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), parsed(e.read())


def test_nutrition_get_starts_empty(server, nutrition_file):
    status, ctype, payload = _json(server, "/api/nutrition")
    assert status == 200
    assert ctype == "application/json; charset=utf-8"
    assert payload["days"] == []
    assert payload["count"] == 0
    assert payload["fields"] == ["date", "calories", "protein", "carbs", "fat"]
    assert "local" in payload["storage"]


def test_nutrition_get_requires_the_dash_token(server, nutrition_file):
    status, _, _ = _get(server, "/api/nutrition", token=None)
    assert status == 403


def test_nutrition_get_rejects_unknown_query_parameters(server, nutrition_file):
    status, _, payload = _json(server, "/api/nutrition?from=2026-11-01")
    assert status == 400
    assert payload["error"] == "unsupported query parameter"


def test_nutrition_post_upserts_and_get_reflects_it(server, nutrition_file):
    status, _, result = _post_json(server, "/api/nutrition", {
        "days": [{"date": "2026-11-10", "calories": 500, "protein": 30,
                  "carbs": 60, "fat": 15}]})
    assert status == 200
    assert result == {"accepted": 1, "upserted": 1, "total_days": 1}
    status, _, payload = _json(server, "/api/nutrition")
    assert payload["count"] == 1
    assert payload["days"][0]["calories"] == 500


def test_nutrition_post_repeat_date_updates_one_row(server, nutrition_file):
    day = {"date": "2026-11-10", "calories": 500}
    _post_json(server, "/api/nutrition", {"days": [day]})
    _, _, result = _post_json(server, "/api/nutrition", {
        "days": [{"date": "2026-11-10", "calories": 600}]})
    assert result["total_days"] == 1
    _, _, payload = _json(server, "/api/nutrition")
    assert payload["count"] == 1
    assert payload["days"][0]["calories"] == 600


def test_nutrition_post_accepts_a_raw_caltrak_csv(server, nutrition_file):
    text = ("date,calories,protein,carbs,fat\n"
            "2026-11-10,300,20,30,10\n"
            "2026-11-10,200,10,20,5\n")
    status, _, result = _post_json(server, "/api/nutrition", {"csv": text})
    assert status == 200
    assert result["upserted"] == 1
    _, _, payload = _json(server, "/api/nutrition")
    assert payload["days"][0]["calories"] == 500
    assert payload["days"][0]["protein"] == 30


def test_nutrition_post_requires_the_dash_token(server, nutrition_file):
    status, _, _ = _post_json(server, "/api/nutrition",
                              {"days": []}, token=None)
    assert status == 403


def test_nutrition_post_rejects_a_malformed_payload(server, nutrition_file):
    status, _, payload = _post_json(server, "/api/nutrition",
                                    {"days": [{"date": "nope"}]})
    assert status == 400
    assert payload["error"] == "invalid nutrition payload"


def test_nutrition_post_rejects_non_json(server, nutrition_file):
    status, _, payload = _post_json(server, "/api/nutrition", None,
                                    raw=b"not json")
    assert status == 400
    assert payload["error"] == "body must be JSON"


def test_nutrition_post_rejects_a_non_object_body(server, nutrition_file):
    status, _, payload = _post_json(server, "/api/nutrition", [1, 2, 3])
    assert status == 400
    assert payload["error"] == "body must be a JSON object"


def test_nutrition_route_sends_no_cors_headers(server, nutrition_file):
    req = urllib.request.Request(server + "/api/nutrition")
    req.add_header("X-Dash-Token", TOKEN)
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.headers.get("Access-Control-Allow-Origin") is None


def test_aurora_bootstrap_wires_the_nutrition_route(server, aurora_html):
    _, _, body = _get(server, "/aurora")
    text = body.decode("utf-8")
    assert "/api/nutrition" in text
    assert "loadNutrition" in text
    # The committed FUEL view reads `kcal`; the API schema is `calories`.
    assert "kcal:" in text

# ------------------------------------------------ Android share target (PWA)

def test_manifest_declares_the_caltrak_share_target(server):
    _, _, body = _get(server, "/manifest.webmanifest", token=None)
    m = json.loads(body.decode("utf-8"))
    st = m["share_target"]
    assert st["action"] == "/share-target"
    assert st["method"] == "POST"
    assert st["enctype"] == "multipart/form-data"
    assert st["params"]["files"][0]["name"] == "log"


def test_multipart_file_text_parses_a_file_part():
    boundary = "----x"
    body = (
        ("--%s\r\n" % boundary).encode("utf-8")
        + b'Content-Disposition: form-data; name="log"; filename="caltrak.csv"\r\n'
        + b"Content-Type: text/csv\r\n\r\n"
        + b"date,calories\n2026-11-10,500\n"
        + ("\r\n--%s--\r\n" % boundary).encode("utf-8")
    )
    text = G.multipart_file_text(
        body, "multipart/form-data; boundary=%s" % boundary)
    assert text == "date,calories\n2026-11-10,500\n"


def test_multipart_file_text_ignores_a_plain_field():
    boundary = "----x"
    body = (
        ("--%s\r\n" % boundary).encode("utf-8")
        + b'Content-Disposition: form-data; name="note"\r\n\r\n'
        + b"hello\r\n"
        + ("--%s--\r\n" % boundary).encode("utf-8")
    )
    assert G.multipart_file_text(
        body, "multipart/form-data; boundary=%s" % boundary) is None


def test_multipart_file_text_rejects_a_missing_boundary():
    assert G.multipart_file_text(b"whatever", "multipart/form-data") is None


def _post_multipart(base, path, content, token=TOKEN):
    boundary = "----testboundary"
    body = (
        ("--%s\r\n" % boundary).encode("utf-8")
        + b'Content-Disposition: form-data; name="log"; filename="caltrak.csv"\r\n'
        + b"Content-Type: text/csv\r\n\r\n"
        + content.encode("utf-8")
        + ("\r\n--%s--\r\n" % boundary).encode("utf-8")
    )
    req = urllib.request.Request(base + path, data=body, method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=%s" % boundary)
    if token is not None:
        req.add_header("X-Dash-Token", token)
    try:
        with _NO_REDIRECT.open(req, timeout=10) as r:
            return r.status, r.headers.get("Location"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location"), e.read()


def test_share_target_ingests_the_caltrak_csv_and_redirects(server,
                                                           nutrition_file):
    csv_text = ("date,calories,protein,carbs,fat\n"
                "2026-11-10,300,20,30,10\n"
                "2026-11-10,200,10,20,5\n")
    status, location, _ = _post_multipart(server, "/share-target", csv_text)
    assert status == 303
    assert location == "/?shared=ok"
    _, _, payload = _json(server, "/api/nutrition")
    assert payload["days"][0]["calories"] == 500
    assert payload["days"][0]["protein"] == 30


def test_share_target_reports_an_unreadable_file(server, nutrition_file):
    status, location, _ = _post_multipart(server, "/share-target", "not a csv")
    assert status == 303
    assert location == "/?shared=error"


def test_share_target_requires_the_dash_token(server, nutrition_file):
    status, location, _ = _post_multipart(
        server, "/share-target", "date,calories\n2026-11-10,1\n", token=None)
    # The gate redirects an unauthenticated browser to the login page.
    assert status == 303
    assert location == "/login"


def test_aurora_bootstrap_exposes_reload_hooks_and_tss_fields(server,
                                                              aurora_html):
    _, _, body = _get(server, "/")
    text = body.decode("utf-8")
    assert "window.auroraReloadAll" in text
    assert "window.auroraReloadNutrition" in text
    assert "maxCadence" in text
    assert "training_stress_score" in text


# --------------------------------------- phone webhook (Health Connect bridge)

def _hook_token(server):
    status, _, info = _json(server, "/api/nutrition/hook-info")
    assert status == 200
    return info["token"]


def _hc_raw(record_id, date, calories, protein=0, carbs=0, fat=0):
    return {
        "start_time": date + "T08:00:00-08:00",
        "end_time": date + "T08:05:00-08:00",
        "calories": calories,
        "protein_grams": protein,
        "carbs_grams": carbs,
        "fat_grams": fat,
        "metadata": {"id": record_id},
    }


def test_hook_info_requires_the_dash_token(server, nutrition_file):
    status, _, _ = _get(server, "/api/nutrition/hook-info", token=None)
    assert status == 403


def test_hook_info_returns_the_header_and_a_stable_token(server, nutrition_file):
    _, _, first = _json(server, "/api/nutrition/hook-info")
    _, _, second = _json(server, "/api/nutrition/hook-info")
    assert first["path"] == "/api/nutrition/hook"
    assert first["header"] == "X-Nutrition-Token"
    assert first["token"]
    assert first["token"] == second["token"]


def test_hook_accepts_the_phone_token_without_a_browser_session(server,
                                                                nutrition_file):
    token = _hook_token(server)
    status, ctype, result = _post_json(
        server, "/api/nutrition/hook",
        {"nutrition": [_hc_raw("a", "2026-11-10", 300, 20, 30, 10)]},
        token=None, headers={"X-Nutrition-Token": token})
    assert status == 200
    assert ctype == "application/json; charset=utf-8"
    assert result["ok"] is True
    assert result["accepted"] == 1
    assert result["source"] == "health-connect"
    _, _, payload = _json(server, "/api/nutrition")
    assert payload["days"][0]["calories"] == 300


def test_hook_accepts_bearer_auth(server, nutrition_file):
    token = _hook_token(server)
    status, _, result = _post_json(
        server, "/api/nutrition/hook",
        {"nutrition": [_hc_raw("a", "2026-11-10", 300)]},
        token=None, headers={"Authorization": "Bearer " + token})
    assert status == 200
    assert result["accepted"] == 1


def test_hook_rejects_a_missing_token(server, nutrition_file):
    status, _, payload = _post_json(
        server, "/api/nutrition/hook",
        {"nutrition": [_hc_raw("a", "2026-11-10", 300)]}, token=None)
    assert status == 401
    assert "nutrition token" in payload["error"]


def test_hook_rejects_a_wrong_token(server, nutrition_file):
    status, _, _ = _post_json(
        server, "/api/nutrition/hook",
        {"nutrition": [_hc_raw("a", "2026-11-10", 300)]},
        token=None, headers={"X-Nutrition-Token": "not-the-hook-token"})
    assert status == 401


def test_hook_rejects_the_dashboard_token_as_the_hook_token(server,
                                                            nutrition_file):
    """The two secrets are separate; the login token must not work here."""
    status, _, _ = _post_json(
        server, "/api/nutrition/hook",
        {"nutrition": [_hc_raw("a", "2026-11-10", 300)]},
        token=None, headers={"X-Nutrition-Token": TOKEN})
    assert status == 401


def test_hook_rejects_a_non_object_payload(server, nutrition_file):
    token = _hook_token(server)
    status, _, payload = _post_json(
        server, "/api/nutrition/hook", [1, 2, 3],
        token=None, headers={"X-Nutrition-Token": token})
    assert status == 400
    assert payload["error"] == "invalid health connect payload"


def test_hook_incremental_records_keep_the_whole_day(server, nutrition_file):
    token = _hook_token(server)
    headers = {"X-Nutrition-Token": token}
    _post_json(server, "/api/nutrition/hook",
               {"nutrition": [_hc_raw("a", "2026-11-10", 300, 20, 30, 10)]},
               token=None, headers=headers)
    _post_json(server, "/api/nutrition/hook",
               {"nutrition": [_hc_raw("b", "2026-11-10", 250, 15, 40, 8)]},
               token=None, headers=headers)
    _, _, payload = _json(server, "/api/nutrition")
    assert payload["days"][0]["calories"] == 550
    assert payload["days"][0]["protein"] == 35


def test_hook_applies_a_deletion(server, nutrition_file):
    token = _hook_token(server)
    headers = {"X-Nutrition-Token": token}
    _post_json(server, "/api/nutrition/hook",
               {"nutrition": [_hc_raw("a", "2026-11-10", 300),
                              _hc_raw("b", "2026-11-10", 250)]},
               token=None, headers=headers)
    status, _, result = _post_json(
        server, "/api/nutrition/hook",
        {"nutrition": [], "deleted": [{"type": "nutrition", "id": "a"}]},
        token=None, headers=headers)
    assert status == 200
    assert result["accepted"] == 0
    _, _, payload = _json(server, "/api/nutrition")
    assert payload["days"][0]["calories"] == 250


def test_hook_accepts_a_daily_resolution_record(server, nutrition_file):
    token = _hook_token(server)
    status, _, result = _post_json(
        server, "/api/nutrition/hook",
        {"nutrition": [{
            "start_time": "2026-11-10T00:00:00-08:00",
            "end_time": "2026-11-11T00:00:00-08:00",
            "calories": 2100,
            "protein_grams": 140,
            "carbs_grams": 220,
            "fat_grams": 70,
        }]},
        token=None, headers={"X-Nutrition-Token": token})
    assert status == 200
    assert result["upserted"] == 1
    _, _, payload = _json(server, "/api/nutrition")
    assert payload["days"][0]["calories"] == 2100


def test_hook_sends_no_cors_headers(server, nutrition_file):
    token = _hook_token(server)
    body = json.dumps(
        {"nutrition": [_hc_raw("a", "2026-11-10", 300)]}).encode("utf-8")
    req = urllib.request.Request(server + "/api/nutrition/hook", data=body,
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Nutrition-Token", token)
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.headers.get("Access-Control-Allow-Origin") is None


# ------------------------------------------------- JSON CalTrak backups

def test_nutrition_post_accepts_a_json_backup(server, nutrition_file):
    status, _, result = _post_json(server, "/api/nutrition", {
        "json": {"days": [{"date": "2026-11-10", "calories": 700}]}})
    assert status == 200
    assert result["upserted"] == 1
    _, _, payload = _json(server, "/api/nutrition")
    assert payload["days"][0]["calories"] == 700


def test_nutrition_post_accepts_a_raw_backup_object(server, nutrition_file):
    status, _, result = _post_json(server, "/api/nutrition", {
        "version": 1,
        "food_log": [{
            "logged_at": "2026-11-10T08:00:00Z",
            "food": {"calories": 300, "protein": 20, "carbs": 30, "fat": 10},
        }],
    })
    assert status == 200
    assert result["upserted"] == 1
    _, _, payload = _json(server, "/api/nutrition")
    assert payload["days"][0]["calories"] == 300


def test_share_target_accepts_a_json_backup(server, nutrition_file):
    text = json.dumps({"days": [{"date": "2026-11-10", "calories": 500}]})
    status, location, _ = _post_multipart(server, "/share-target", text)
    assert status == 303
    assert location == "/?shared=ok"
    _, _, payload = _json(server, "/api/nutrition")
    assert payload["days"][0]["calories"] == 500
