#!/usr/bin/env python3
"""
garmin_server.py - minimal, locked-down static server for Coach Dashboard.

Serves only the dashboard HTML, the two Garmin CSV exports, and runs' FIT
files to ONE local browser session. It is intentionally paranoid:

  * binds 127.0.0.1 only (never a reachable network IP),
  * a per-launch random token must be supplied in the X-Dash-Token header
    (opened page receives it as ?tk=... in its URL),
  * Host header must be exactly 127.0.0.1:<port> or localhost:<port>,
    which defeats DNS-rebinding attacks from hostile web pages,
  * never lists directories, serves only known filenames,
  * sends nosniff + same-origin headers and zero CORS headers,
  * exits on its own after ~20 minutes with no requests, so nothing
    lingers in the background.

Usage:
    python garmin_server.py [--port PORT] [--token TOKEN] [--open]
"""

import argparse
import datetime
import io
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import paths  # noqa: E402

# The dashboard now lives in the repository under dashboard/. Athlete data stays
# in the local data directory: this server must not read from the public repo for
# sleep, HR or FIT, and those files are not committed.
DASH_DIR = os.path.join(ROOT, "dashboard")
DATA_DIR = paths.data_dir()
HTML_FILE = os.path.join(DASH_DIR, "index.html")

def resolve_dashboard_html():
    """Return the dashboard HTML to serve.

    The path used to be bound once at import time, so any server process that
    was already running kept serving the previous build forever and a stale
    window could never pick up a new one. Resolving per request removes that
    failure mode: a long-long-lived process always serves the newest dashboard.

    Prefers a numbered build (Coach Dashboard vX.Y.html) when one is present so
    an in-progress build can be compared against the committed index.html.
    """
    best_name, best_rank = None, -1
    try:
        for fn in os.listdir(DASH_DIR):
            m = re.match(r"^Coach Dashboard v(\d+)\.(\d+)\.html$", fn)
            if not m:
                continue
            rank = int(m.group(1)) * 1000 + int(m.group(2))
            if rank > best_rank:
                best_rank, best_name = rank, fn
    except OSError:
        pass
    if best_name:
        return os.path.join(DASH_DIR, best_name)
    return HTML_FILE if os.path.exists(HTML_FILE) else os.path.join(ROOT, "index.html")
SLEEP_CSV = os.path.join(DATA_DIR, "garmin_sleep.csv")
HR_CSV = os.path.join(DATA_DIR, "garmin_hr.csv")
FIT_DIR = paths.fit_dir()
IDLE_TIMEOUT = 1200

TOKEN = ""
PORT = 0

# ---------------------------------------------------------------------------
# JSON API over the existing data layer.
#
# These routes are the dashboard's only authoritative source for activities,
# load and coaching. They read the migration-backed database and call
# loadcalc/recommend directly; nothing is recomputed here, so the browser and
# the CLI can never disagree about a number.
#
# Two rules shape the code below:
#
#   1. Counts, versions and states are QUERIED, never written down. A hardcoded
#      count goes stale the moment a run is imported, and a stale count in a
#      coaching surface is worse than no number at all.
#   2. null, unavailable and refused are preserved as themselves. None of them
#      is zero, and none of them is a normal result.
#
# Each builder is a pure function of (conn, hr_max) returning a JSON-safe dict,
# so the tests exercise real logic without binding a socket.
# ---------------------------------------------------------------------------

API_PREFIX = "/api/"


def _rows(conn, sql, args=()):
    """Fetch rows as dicts. Row factory is set per-connection in trainingdb."""
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def _open_reviews(conn, activity_id):
    return _rows(
        conn,
        "SELECT reason, detail, opened_utc FROM review_items "
        "WHERE activity_id = ? AND state = 'open' ORDER BY reason",
        (activity_id,),
    )


def _review_summary(conn):
    """Open review counts by reason, queried. Includes activity_gap rows, whose
    activity_id is null because no activity exists for the gap."""
    by_reason = {r["reason"]: r["c"] for r in _rows(
        conn,
        "SELECT reason, COUNT(*) c FROM review_items WHERE state = 'open' "
        "GROUP BY reason ORDER BY reason",
    )}
    total = sum(by_reason.values())
    return {
        "open_reviews": total,
        "by_reason": by_reason,
        "timezone_uncertain": by_reason.get("timezone_uncertain", 0),
        "activity_gap": by_reason.get("activity_gap", 0),
    }


def _source_files(conn):
    """activity_id -> raw FIT filename, so the dashboard can keep its existing
    raw FIT detail view reachable without a second lookup convention."""
    return {r["activity_id"]: r["source_file"] for r in _rows(
        conn,
        "SELECT activity_id, source_file FROM activity_raw_refs",
    )}


def api_activities(conn):
    """GET /api/activities - canonical activities with review state preserved."""
    src = _source_files(conn)
    out = []
    for r in _rows(conn, "SELECT * FROM activities ORDER BY start_utc DESC"):
        aid = r["activity_id"]
        reviews = _open_reviews(conn, aid)
        out.append({
            # Stable identity. Never the array index, never the FIT filename.
            "activity_id": aid,
            "source_activity_id": r["source_activity_id"],
            "source_file": src.get(aid),
            "sport": r["sport"],
            "start_utc": r["start_utc"],
            "start_local": r["start_local"],
            # start_local is a filename-derived guess until the offset is
            # confirmed. Say so rather than presenting it as local time.
            "timezone_source": r["timezone_source"],
            "distance_mi": r["distance_mi"],
            "moving_time_s": r["moving_time_s"],
            "elapsed_time_s": r["elapsed_time_s"],
            "avg_hr": r["avg_hr"],
            "max_hr": r["max_hr"],
            "total_ascent_ft": r["total_ascent_ft"],
            "total_descent_ft": r["total_descent_ft"],
            "value_state": r["value_state"],
            "confidence": r["confidence"],
            "confirmation": r["confirmation"],
            "review_state": r["review_state"],
            "reviews": reviews,
            "has_open_review": bool(reviews) or r["review_state"] == "open",
        })
    summary = _review_summary(conn)
    return {
        "activities": out,
        "count": len(out),
        "review_summary": summary,
        # Provenance of the snapshot itself, so a stale panel is detectable.
        "data_version": {
            "last_activity_update_utc": conn.execute(
                "SELECT MAX(last_updated_utc) v FROM activities"
            ).fetchone()["v"],
            "activities_table": "activities",
            "source": "trainloop.db",
        },
    }


def _window_payload(w, days, as_of_utc):
    """One load window. start/end are the actual bounds, so the number is
    interpretable without re-deriving the window server-side.

    window_bounds returns datetimes; they are converted here so the payload is
    JSON-native rather than relying on a default=str fallback at send time.
    """
    start, end = loadcalc.window_bounds(as_of_utc, days)
    start = start.isoformat() if hasattr(start, "isoformat") else str(start)
    end = end.isoformat() if hasattr(end, "isoformat") else str(end)
    return {
        "days": days,
        "value": w["run_load"],
        "combined_load": w["combined_load"],
        "start": start,
        "end": end,
        "run_confidence": w["run_confidence"],
        "strength_confidence": w["strength_confidence"],
        "runs_included": len(w["run_days"]),
        "strength_sessions_included": len(w["strength_days"]),
        # Why a component is missing, verbatim from loadcalc. Empty means the
        # component was simply absent, not that it was withheld.
        "unavailable": w["unavailable"],
        "included_activity_ids": w["included_run_ids"],
    }


def api_load(conn, hr_max, as_of=None):
    """GET /api/load - 7/14/28-day load straight from loadcalc."""
    result = loadcalc.compute(conn, as_of=as_of, hr_max=hr_max)
    windows = {}
    for key in ("7", "14", "28"):
        w = result["windows"][key]
        windows["%sd" % key] = _window_payload(w, w["days"], result["as_of_utc"])

    hr_note = None
    if hr_max is None:
        # loadcalc still returns numbers without a max by falling back, so the
        # dashboard must be able to say the input was never supplied.
        hr_note = ("hr_max not supplied; run load falls back to the "
                   "loadcalc unverified path")

    return {
        "algorithm": result["version"],
        "as_of_utc": result["as_of_utc"],
        "windows": windows,
        # null here means "no confirmed strength sessions exist". It must never
        # be rendered as 0, which would read as "you trained and did nothing".
        "strength_load": result["windows"]["28"]["strength_load"],
        "strength_state": result["windows"]["28"]["strength_confidence"],
        "assumptions": result["assumptions"],
        "hr_max_supplied": hr_max,
        "hr_max_note": hr_note,
    }


def api_coaching(conn, hr_max, as_of=None):
    """GET /api/coaching - refusal-first result straight from recommend."""
    result = recommend.recommend(conn, as_of=as_of, hr_max=hr_max)
    state = result["state"]
    advisory = result.get("advisory", True)
    return {
        "state": state,
        # A refusal is not a weak recommendation. The dashboard keys its
        # rendering off this flag, so a refusal can never be styled as advice.
        "refused": not advisory,
        "advisory": advisory,
        "blocking_conditions": list(result.get("reasons", [])),
        "rationale": list(result.get("reasons", [])),
        "limitation": result.get("limitation"),
        "evidence": result.get("evidence", {}),
        "disclaimers": result.get("disclaimers", []),
        "available_states": recommend.available_states(),
        "review_summary": _review_summary(conn),
        "version": loadcalc.LOAD_VERSION,
    }


API_ROUTES = {
    "/api/activities": lambda conn, hr, at: api_activities(conn),
    "/api/load": lambda conn, hr, at: api_load(conn, hr, as_of=at),
    "/api/coaching": lambda conn, hr, at: api_coaching(conn, hr, as_of=at),
}

TOKEN = ""
PORT = 0
last_request: float = time.time()
SYNC_SCRIPT = os.path.join(ROOT, "garmin_sync.py")
_sync_lock = threading.Lock()
MEGACMD = ""
MEGACMD_REMOTE = "/CoachDashboard"

# Imported for the JSON API. These are the canonical implementations; the
# server must not grow a second parser, a second load formula or a second
# coaching rule, or the dashboard and the CLI would drift apart.
import activities          # noqa: E402
import loadcalc            # noqa: E402
import recommend           # noqa: E402
import trainingdb          # noqa: E402
import trainloop           # noqa: E402


def _run_sync():
    if not os.path.isfile(SYNC_SCRIPT):
        return {"ok": False, "exit": None,
                "output": "garmin_sync.py not found next to garmin_server.py."}
    try:
        proc = subprocess.run([sys.executable, SYNC_SCRIPT], capture_output=True,
                              text=True, stdin=subprocess.DEVNULL, cwd=ROOT, timeout=300)
        lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
        out = "\n".join(lines[-25:])
        if proc.returncode != 0:
            out += "\n[exit code %d]" % proc.returncode
        return {"ok": proc.returncode == 0, "exit": proc.returncode, "output": out[-4000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit": None,
                "output": "Garmin sync ran longer than 300s and was stopped."}
    except Exception as exc:
        return {"ok": False, "exit": None,
                "output": "Could not start Garmin sync: %r" % (exc,)}


def fit_names():
    if not os.path.isdir(FIT_DIR):
        return []
    return sorted(
        n for n in os.listdir(FIT_DIR)
        if n.lower().endswith(".fit") and os.path.isfile(os.path.join(FIT_DIR, n))
    )


def _build_cloud_zip(env):
    """Bundle backup.json + dashboard + FIT/CSV + scripts into one offline zip.
    Only fixed, known local files are included; the access token and the
    .garmin_tokens folder are never written into the bundle.
    """
    buf = io.BytesIO()
    name = "coach-dashboard-cloud-%s.zip" % time.strftime("%Y-%m-%d")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("backup.json", json.dumps(env, indent=2))
        for rel in ("garmin_server.py", "garmin_sync.py", "paths.py",
                    "Coach Dashboard.cmd"):
            p = os.path.join(ROOT, rel)
            if os.path.isfile(p):
                zf.write(p, rel)
        dash = resolve_dashboard_html()
        if os.path.isfile(dash):
            zf.write(dash, "Coach Dashboard v1.1 RESTORED.html")
    # Sleep and HR exports live in the local data directory, not the repo.
    for rel in (SLEEP_CSV, HR_CSV):
        if os.path.isfile(rel):
            zf.write(rel, os.path.basename(rel))
    if os.path.isdir(FIT_DIR):
        for n in fit_names():
            zf.write(os.path.join(FIT_DIR, n), "garmin_fit/" + n)
    return buf.getvalue(), name


def _find_megacmd():
    if MEGACMD:
        return _mega_argv(MEGACMD)
    for name in ("mega-put.exe", "mega-put.cmd", "mega-put"):
        found = shutil.which(name)
        if found:
            return [found]
    bases = [os.environ.get("ProgramFiles(x86)", ""),
             os.environ.get("ProgramFiles", ""),
             os.environ.get("LocalAppData", "")]
    for base in bases:
        if not base:
            continue
        for rel in ("MEGAcmd", os.path.join("Programs", "MEGAcmd")):
            d = os.path.join(base, rel)
            if not os.path.isdir(d):
                continue
            for name in ("mega-put.exe", "MEGAclient.exe"):
                cand = os.path.join(d, name)
                if os.path.isfile(cand):
                    return [cand] if name != "MEGAclient.exe" else [cand, "put"]
    return None


def _mega_argv(exe):
    if "\\" in exe or " " not in exe:
        return [exe]
    try:
        parts = shlex.split(exe)
        if parts:
            return parts
    except Exception:
        pass
    return [exe]


def _is_megaclient(argv):
    return len(argv) >= 1 and os.path.basename(argv[0]).lower() == "megaclient.exe"


def _mc(argv, sub):
    if _is_megaclient(argv):
        return argv[:1] + [sub]
    return None


def _run_mega_put(zip_path, argv):
    try:
        proc = subprocess.run(argv + ["-c", zip_path, MEGACMD_REMOTE],
                              capture_output=True, text=True, timeout=120)
    except Exception as exc:
        return {"ok": False, "detail": "could not start MEGAcmd: %r" % (exc,)}
    tail = ""
    for txt in ((proc.stdout or "").replace("\x00", ""),
                (proc.stderr or "").replace("\x00", "")):
        for ln in txt.splitlines():
            if ln.strip():
                tail = ln.strip()
    return {"ok": proc.returncode == 0, "detail": tail[:300] or "no output"}


class Handler(BaseHTTPRequestHandler):
    server_version = ""
    sys_version = ""

    def _deny(self, code, reason):
        try:
            payload = reason.encode("utf-8", "replace")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
        except Exception:
            pass

    def _send(self, code, body, ctype):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass

    def _send_json(self, code, payload):
        """Send a JSON body with the same hardening as _send.

        Errors go through here too, so an API failure is always parseable JSON
        rather than a traceback or an HTML error page.
        """
        try:
            body = json.dumps(payload, default=str).encode("utf-8")
        except (TypeError, ValueError):
            body = json.dumps(
                {"error": "unserializable response"}).encode("utf-8")
            code = 500
        return self._send(code, body, "application/json; charset=utf-8")

    def _api(self, path, query):
        """Dispatch one /api/ route.

        Opens the database per request and closes it in a finally, so a browser
        hitting refresh in a loop cannot leak handles.
        """
        route = API_ROUTES.get(path)
        if route is None:
            return self._send_json(404, {
                "error": "unknown endpoint",
                "path": path,
                "available": sorted(API_ROUTES),
            })
        # Reject unknown query parameters rather than ignoring a typo, which
        # would otherwise look like a filter that silently did nothing.
        for key in query:
            if key not in ("as_of",):
                return self._send_json(400, {
                    "error": "unsupported query parameter",
                    "parameter": key,
                    "supported": ["as_of"],
                })
        as_of = query.get("as_of")
        if as_of is not None:
            try:
                datetime.datetime.strptime(as_of, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                return self._send_json(400, {
                    "error": "as_of must be UTC ISO-8601, e.g. "
                             "2026-10-04T00:00:00Z",
                    "as_of": as_of,
                })

        conn = None
        try:
            conn = trainingdb.connect()
            hr_max = trainloop._hr_max()
            payload = route(conn, hr_max, as_of)
        except Exception as exc:
            # Log locally, return nothing identifying. A traceback or a
            # filesystem path in a browser is an information leak.
            sys.stderr.write("api %s failed: %s: %s\n"
                             % (path, type(exc).__name__, exc))
            return self._send_json(500, {
                "error": "internal error",
                "endpoint": path,
            })
        finally:
            if conn is not None:
                conn.close()
        return self._send_json(200, payload)

    def _send_zip(self, payload, filename):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Disposition",
                             'attachment; filename="%s"' % filename)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
        except Exception:
            pass

    def do_GET(self):
        global last_request
        last_request = time.time()
        host = self.headers.get("Host", "").lower()
        if host not in ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT):
            return self._deny(403, "forbidden host")
        parts = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parts.path)
        if path == "/ping":
            return self._send(200, b"coach-dashboard", "text/plain; charset=utf-8")
        if path in ("/", "/index.html", "/favicon.ico"):
            try:
                with open(resolve_dashboard_html(), "rb") as fh:
                    return self._send(200, fh.read(), "text/html; charset=utf-8")
            except OSError:
                return self._deny(404, "dashboard html not found")
        if self.headers.get("X-Dash-Token", None) != TOKEN:
            return self._deny(403, "missing or wrong token")
        if path == "/garmin_sleep.csv":
            try:
                with open(SLEEP_CSV, "rb") as fh:
                    return self._send(200, fh.read(), "text/csv; charset=utf-8")
            except OSError:
                return self._deny(404, "no sleep csv yet")
        if path == "/garmin_hr.csv":
            try:
                with open(HR_CSV, "rb") as fh:
                    return self._send(200, fh.read(), "text/csv; charset=utf-8")
            except OSError:
                return self._deny(404, "no hr csv yet")
        if path == "/fit-list":
            return self._send(200, json.dumps(fit_names()).encode("utf-8"), "application/json")
        if path == "/cloud-check":
            return self._send(200, json.dumps({"megacmd": _find_megacmd() is not None}).encode("utf-8"),
                              "application/json; charset=utf-8")
        if path.startswith(API_PREFIX):
            # Behind the token check above, same as every other data route.
            # Same-origin only; no CORS headers are ever sent.
            # parse_qs yields lists; take the first value so a duplicated
            # parameter cannot smuggle a second value past the checks below.
            raw = urllib.parse.parse_qs(parts.query)
            query = {k: v[0] for k, v in raw.items() if v}
            return self._api(path, query)
        if path.startswith("/fit/"):
            name = path[len("/fit/"):].replace("/", "")
            if name not in fit_names():
                return self._deny(404, "no such fit file")
            fit_path = os.path.join(FIT_DIR, name)
            try:
                with open(fit_path, "rb") as fh:
                    return self._send(200, fh.read(), "application/octet-stream")
            except OSError:
                return self._deny(404, "no such fit file")
        return self._deny(404, "not found")

    def do_POST(self):
        global last_request
        last_request = time.time()
        host = self.headers.get("Host", "").lower()
        if host not in ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT):
            return self._deny(403, "forbidden host")
        if self.headers.get("X-Dash-Token", None) != TOKEN:
            return self._deny(403, "missing or wrong token")
        parts = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parts.path)
        if path == "/sync":
            if not _sync_lock.acquire(False):
                body = json.dumps({"ok": False, "busy": True,
                                   "output": "A sync is already running."})
                return self._send(200, body.encode("utf-8"), "application/json; charset=utf-8")
            try:
                res = _run_sync()
            finally:
                _sync_lock.release()
            return self._send(200, json.dumps(res).encode("utf-8"),
                              "application/json; charset=utf-8")
        if path == "/cloud-backup":
            raw_len = self.headers.get("Content-Length") or "0"
            try:
                raw_len = int(raw_len)
            except ValueError:
                raw_len = 0
            if raw_len < 1 or raw_len > 10 * 1024 * 1024:
                return self._deny(413, "backup payload too large")
            body = self.rfile.read(raw_len)
            try:
                env = json.loads(body.decode("utf-8")).get("backup")
            except Exception:
                env = None
            if not env or not isinstance(env, dict):
                return self._deny(400, 'expected JSON body {"backup": {...}}')
            try:
                payload, name = _build_cloud_zip(env)
            except OSError as exc:
                return self._deny(500, "could not build cloud zip: %r" % (exc,))
            mega = _find_megacmd()
            if mega:
                mdir = _mc(mega, "mkdir")
                if mdir:
                    try:
                        subprocess.run(mdir + ["-p", MEGACMD_REMOTE],
                                       capture_output=True, timeout=60)
                    except Exception:
                        pass
                tmp = tempfile.mkdtemp(prefix="ca-cloud-")
                zpath = os.path.join(tmp, name)
                with open(zpath, "wb") as fh:
                    fh.write(payload)
                try:
                    res = _run_mega_put(zpath, mega)
                finally:
                    try:
                        os.remove(zpath)
                        os.rmdir(tmp)
                    except OSError:
                        pass
                return self._send(200, json.dumps(res).encode("utf-8"),
                                  "application/json; charset=utf-8")
            return self._send_zip(payload, name)
        return self._deny(404, "not found")

    def log_message(self, fmt, *args):
        pass


def idle_watchdog(server):
    while True:
        time.sleep(15)
        if time.time() - last_request > IDLE_TIMEOUT:
            try:
                print("Idle for %ds - shutting down." % IDLE_TIMEOUT)
                server.shutdown()
                return
            except Exception:
                return


TOKEN_FILE = os.path.join(DATA_DIR, ".coach_dash_token")
FIXED_PORT = 24567


def load_or_make_token():
    """Reuse one token across launches.

    localStorage is scoped per origin, and the origin includes the port. A
    random port per launch therefore handed the browser a brand-new, empty
    store every time, silently discarding logged runs, notes and imports.
    """
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as fh:
            t = fh.read().strip()
            if t:
                return t
    except OSError:
        pass
    t = secrets.token_urlsafe(18)
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as fh:
            fh.write(t)
    except OSError:
        pass
    return t


def probe_existing_instance(port):
    """Return the dashboard URL if a healthy instance already owns this port."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/ping" % port, timeout=2) as r:
            if r.status == 200 and b"coach-dashboard" in r.read():
                return "http://127.0.0.1:%d/?tk=%s" % (port, TOKEN)
    except Exception:
        pass
    return None


def main():
    global TOKEN, PORT, MEGACMD
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=FIXED_PORT)
    ap.add_argument("--token", default="")
    ap.add_argument("--megacmd", default="",
                    help="optional path (or command) for mega-put, e.g. "
                         '"C:\\Program Files (x86)\\MEGAcmd\\mega-put.exe"')
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    PORT = args.port
    TOKEN = args.token if args.token else load_or_make_token()
    MEGACMD = args.megacmd
    url = "http://127.0.0.1:%d/?tk=%s" % (PORT, TOKEN)
    # Probe BEFORE binding. On Windows SO_REUSEADDR lets a second bind to the
    # same port succeed, which would silently start a rival server instead of
    # reusing this one - and the two would fight over the same origin.
    existing = probe_existing_instance(PORT)
    if existing:
        print("Coach Dashboard is already running: %s" % existing)
        print("(reused - saved runs, notes and imports stay intact.)")
        if args.open:
            _t2 = threading.Timer(0.3, lambda: webbrowser.open(existing))
            _t2.daemon = True
            _t2.start()
        return
    if args.open:
        _t = threading.Timer(0.6, lambda: webbrowser.open(url))
        _t.daemon = True
        _t.start()
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as exc:
        print("Could not bind 127.0.0.1:%d: %s" % (PORT, exc))
        sys.exit(1)
    print("Coach Dashboard local server: %s" % url)
    threading.Thread(target=idle_watchdog, args=(httpd,), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()