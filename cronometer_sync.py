"""Nightly Cronometer -> Aurora nutrition pull.

Cronometer has no public API. This module drives the same private web export
the site uses, the flow documented by the open-source ``gocronometer`` and
``crono-export-cli`` clients:

  1. GET /login/ for the anti-CSRF token and session cookie.
  2. POST /login with the athlete's credentials.
  3. GWT-RPC authenticate -> user id + session auth token.
  4. GWT-RPC generateAuthorizationToken -> one-shot export nonce.
  5. GET /export?generate=dailySummary -> the Daily Nutrition CSV.

That CSV is the exact format ``nutrition.parse_export`` already handles, so
there is no second nutrition parser. Credentials come only from
CRONOMETER_USERNAME / CRONOMETER_PASSWORD. No credential, auth token or nonce
is ever printed, returned or written to disk. Failures are reported with a
sanitised message so a log cannot leak a session secret.

The GWT permutation is a deploy-time value that Cronometer rotates. Override
it with CRONOMETER_GWT_PERMUTATION without a code release if a sync starts
failing with an authentication error.
"""

import datetime
import http.cookiejar
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

import nutrition
import paths

BASE_URL = os.environ.get("CRONOMETER_BASE_URL", "https://cronometer.com")
GWT_MODULE_BASE = "https://cronometer.com/cronometer/"
GWT_SERVICE = "com.cronometer.shared.rpc.CronometerService"
GWT_CONTENT_TYPE = "text/x-gwt-rpc; charset=UTF-8"
DEFAULT_PERMUTATION = "7B121DC5483BF272B1BC1916DA9FA963"
USER_AGENT = "aurora-cronometer-sync/1.0 (personal data export)"

CSRF_RE = re.compile(r'name="anticsrf"\s+value="([^"]+)"')
USER_ID_RE = re.compile(r"^//OK\[(\d+),")
HEX32_RE = re.compile(r'"([0-9a-fA-F]{32})"')
NONCE_RE = re.compile(r'\[\s*"([0-9a-fA-F]{32})"\s*\]')


class CronometerError(Exception):
    """A step of the pull failed, with a message safe to log."""


def status_path():
    """Local-only status file. Never published or committed."""
    return (os.environ.get("CRONOMETER_SYNC_STATUS")
            or os.path.join(paths.data_dir(), "nutrition_sync_status.json"))


def _stamp():
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_status(state, path=None, **fields):
    """Atomically record the last attempt without any secret material."""
    target = path or status_path()
    record = {"state": state, "last_attempt": _stamp(),
              "ok": state == "ok", "error": None}
    record.update(fields)
    parent = os.path.dirname(os.path.abspath(target))
    os.makedirs(parent, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=parent, prefix=".nutri-sync-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(record, fh, sort_keys=True, indent=2)
            fh.write("\n")
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return record


def read_status(path=None):
    target = path or status_path()
    try:
        with open(target, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"state": "missing", "ok": False, "error": None}


def _utc_offset_minutes():
    """Offset Cronometer should use when interpreting the login handshake."""
    override = os.environ.get("CRONOMETER_UTC_OFFSET_MINUTES")
    if override is not None:
        try:
            return int(override)
        except ValueError:
            raise CronometerError("CRONOMETER_UTC_OFFSET_MINUTES is not an integer")
    offset = datetime.datetime.now().astimezone().utcoffset()
    return int(offset.total_seconds() // 60) if offset else 0


def authenticate_body(permutation, offset_minutes):
    return ("7|0|5|%s|%s|%s|authenticate|java.lang.Integer/3438268394|"
            "1|2|3|4|1|5|5|%d|" % (GWT_MODULE_BASE, permutation,
                                    GWT_SERVICE, offset_minutes))


def authorization_token_body(permutation, auth_token, user_id, ttl=3600):
    return ("7|0|8|%s|%s|%s|generateAuthorizationToken|"
            "java.lang.String/2004016611|I|"
            "com.cronometer.shared.user.AuthScope/2065601159|%s|"
            "1|2|3|4|4|5|6|6|7|8|%d|%d|7|2|"
            % (GWT_MODULE_BASE, permutation, GWT_SERVICE, auth_token,
               user_id, ttl))


class CronometerClient:
    """A single authenticated Cronometer web session."""

    def __init__(self, base_url=None, permutation=None, opener=None,
                 timeout=60):
        self.base_url = (base_url or BASE_URL).rstrip("/")
        self.permutation = (permutation
                            or os.environ.get("CRONOMETER_GWT_PERMUTATION")
                            or DEFAULT_PERMUTATION)
        self.timeout = timeout
        if opener is None:
            jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(jar))
        self.opener = opener
        self.user_id = None
        self.auth_token = None

    def _request(self, path, data=None, headers=None, label="request"):
        url = self.base_url + path
        req = urllib.request.Request(url, data=data, headers=headers or {})
        req.add_header("User-Agent", USER_AGENT)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            # The URL can carry an export nonce, so never echo it.
            raise CronometerError("%s: HTTP %d" % (label, exc.code)) from None
        except urllib.error.URLError:
            raise CronometerError("%s: could not reach Cronometer" % label) from None
        except OSError:
            raise CronometerError("%s: could not reach Cronometer" % label) from None

    def _gwt(self, body):
        headers = {
            "Content-Type": GWT_CONTENT_TYPE,
            "X-Gwt-Module-Base": GWT_MODULE_BASE,
            "X-Gwt-Permutation": self.permutation,
        }
        return self._request("/cronometer/app", data=body.encode("utf-8"),
                             headers=headers, label="GWT request")

    def login(self, username, password):
        if not username or not password:
            raise CronometerError("username and password are required")
        html = self._request("/login/", label="login page")
        match = CSRF_RE.search(html)
        if not match:
            raise CronometerError("login page had no anti-CSRF token")
        form = urllib.parse.urlencode({
            "anticsrf": match.group(1),
            "password": password,
            "username": username,
        }).encode("utf-8")
        body = self._request(
            "/login", data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            label="login")
        # Cronometer's error body is deliberately not surfaced: it can echo
        # parts of the submitted form.
        if '"error"' in body:
            raise CronometerError("login was rejected by Cronometer")
        reply = self._gwt(authenticate_body(self.permutation,
                                            _utc_offset_minutes()))
        user = USER_ID_RE.match(reply)
        tokens = HEX32_RE.findall(reply)
        if not reply.startswith("//OK[") or not user or not tokens:
            raise CronometerError("GWT authentication response not understood")
        self.user_id = int(user.group(1))
        self.auth_token = tokens[-1]
        return self.user_id

    def _export_nonce(self):
        if not self.auth_token or self.user_id is None:
            raise CronometerError("not logged in")
        reply = self._gwt(authorization_token_body(
            self.permutation, self.auth_token, self.user_id))
        match = NONCE_RE.search(reply) if reply.startswith("//OK[") else None
        if not match:
            raise CronometerError("export authorization was not understood")
        return match.group(1)

    def daily_nutrition_csv(self, start, end):
        """Return the verbatim Daily Nutrition CSV for an inclusive date range."""
        query = urllib.parse.urlencode({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "generate": "dailySummary",
            "nonce": self._export_nonce(),
        })
        return self._request("/export?" + query,
                             label="daily nutrition export")


def sync(days=7, client=None, status_file=None):
    """Pull Cronometer's recent daily totals into the canonical nutrition log.

    ``days`` includes today, so a short window catches days missed by a failed
    nightly run. Re-running is safe: upsert_days keys on the local ISO date.
    """
    if days < 1:
        raise ValueError("days must be at least 1")
    target = status_file or status_path()
    username = os.environ.get("CRONOMETER_USERNAME")
    password = os.environ.get("CRONOMETER_PASSWORD")
    if not username or not password:
        write_status("not_configured", target, days_requested=days)
        return {"ok": True, "skipped": True, "status": "not_configured"}

    end = datetime.date.today()
    start = end - datetime.timedelta(days=days - 1)
    try:
        session = client or CronometerClient()
        if not session.auth_token:
            session.login(username, password)
        csv_text = session.daily_nutrition_csv(start, end)
        parsed = nutrition.parse_export(csv_text)
        result = nutrition.upsert_days(parsed)
    except CronometerError as exc:
        message = str(exc)
        write_status("failed", target, days_requested=days, error=message)
        return {"ok": False, "skipped": False, "error": message}
    except nutrition.NutritionError as exc:
        message = "export could not be parsed: %s" % exc
        write_status("failed", target, days_requested=days, error=message)
        return {"ok": False, "skipped": False, "error": message}
    except OSError:
        message = "could not write the nutrition log"
        write_status("failed", target, days_requested=days, error=message)
        return {"ok": False, "skipped": False, "error": message}

    write_status("ok", target, days_requested=days,
                 last_success=_stamp(), **result)
    return {"ok": True, "skipped": False, **result}


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if "--status" in args:
        print(json.dumps(read_status(), sort_keys=True, indent=2))
        return 0
    if "--check" in args:
        ready = bool(os.environ.get("CRONOMETER_USERNAME")
                     and os.environ.get("CRONOMETER_PASSWORD"))
        print("Cronometer credentials: %s"
              % ("configured" if ready else "not configured"))
        return 0 if ready else 1
    days = 7
    if "--days" in args:
        index = args.index("--days")
        try:
            days = int(args[index + 1])
        except (IndexError, ValueError):
            print("--days needs a positive integer", file=sys.stderr)
            return 2
    result = sync(days)
    if result.get("skipped"):
        print("Cronometer sync skipped: credentials not configured")
    elif not result["ok"]:
        print("Cronometer sync failed: %s" % result["error"])
    else:
        print("Cronometer sync: accepted %s day(s), upserted %s, total %s"
              % (result["accepted"], result["upserted"], result["total_days"]))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
