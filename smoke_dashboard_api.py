"""Local smoke test: serve the real dashboard and hit the real API.

Runs garmin_server's own Handler against the athlete's actual trainloop.db, so
this exercises the whole path -- HTTP, token gate, database, loadcalc, recommend
-- rather than a fixture. Nothing is written and nothing is pushed.

Not part of pytest: it binds a port and reads the live database. Run directly:

    python smoke_dashboard_api.py
"""

import json
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import garmin_server as G

TOKEN = "smoke-token"


def fetch(base, path):
    req = urllib.request.Request(base + path)
    req.add_header("X-Dash-Token", TOKEN)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, r.headers.get("Content-Type"), json.loads(
            r.read().decode("utf-8"))


def main():
    G.TOKEN = TOKEN
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), G.Handler)
    port = httpd.server_address[1]
    G.PORT = port
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % port

    failures = []
    try:
        status, ctype, page = None, None, None
        req = urllib.request.Request(base + "/")
        with urllib.request.urlopen(req, timeout=15) as r:
            status, page = r.status, r.read().decode("utf-8", "replace")
        print("GET /                    %s  html=%d bytes" % (status, len(page)))
        for needle in ("id=\"apiPanel\"", "api/activities", "api/load",
                       "api/coaching", "window.refreshApiPanel"):
            ok = needle in page
            print("   panel contains %-24s %s" % (needle, "yes" if ok else "NO"))
            if not ok:
                failures.append("panel missing " + needle)

        for path in ("/api/activities", "/api/load", "/api/coaching"):
            status, ctype, body = fetch(base, path)
            print("GET %-22s %s  %s" % (path, status, ctype))
            if status != 200 or "application/json" not in ctype:
                failures.append(path + " bad status/content-type")

        _, _, act = fetch(base, "/api/activities")
        rs = act["review_summary"]
        print()
        print("   activities=%d  open_reviews=%d  timezone_uncertain=%d  activity_gap=%d"
              % (act["count"], rs["open_reviews"], rs["timezone_uncertain"],
                 rs["activity_gap"]))
        # The real invariant: one open timezone review per activity, plus any
        # gap reviews that have no activity to attach to.
        other = rs["open_reviews"] - rs["timezone_uncertain"] - rs["activity_gap"]
        if rs["timezone_uncertain"] != act["count"] or other != 0:
            failures.append(
                "review shape unexpected: %d tz / %d activities / %d other"
                % (rs["timezone_uncertain"], act["count"], other))
        newest = act["activities"][0]
        print("   newest: %s  %s  %s mi  source_file=%s"
              % (newest["activity_id"], newest["start_local"],
                 newest["distance_mi"], newest["source_file"]))
        if newest["source_file"]:
            print("   raw FIT still reachable via the existing /fit route")
        else:
            print("   note: newest activity has no raw ref row")

        _, _, load = fetch(base, "/api/load")
        print("   load algorithm=%s  strength_load=%r"
              % (load["algorithm"], load["strength_load"]))
        for k in ("7d", "14d", "28d"):
            w = load["windows"][k]
            print("      %-4s %-9s runs=%-3d conf=%s"
                  % (k, w["value"], w["runs_included"], w["run_confidence"]))
        if load["strength_load"] is None:
            print("      strength_load is null (correct: no confirmed sessions)")
        else:
            failures.append("strength_load should be null")

        _, _, co = fetch(base, "/api/coaching")
        print("   coaching state=%s refused=%s" % (co["state"], co["refused"]))
        for b in co["blocking_conditions"]:
            print("      blocked by: %s" % b)
        if not co["refused"]:
            failures.append("expected a refusal while reviews are open")

        # The dashboard must not quietly render a zero for an unknown value.
        with open("dashboard/index.html", encoding="utf-8") as fh:
            js = fh.read()
        for needle, why in (
                ("Loading from the local API", "status copy"),
                ("no confirmed strength sessions recorded", "strength null note"),
                ("rather than a stale or cached one", "no-stale-fallback copy")):
            if needle not in js:
                failures.append("dashboard missing " + why)
        print()
        print("   dashboard: strength-null note present, no stale-fallback path")
    finally:
        httpd.shutdown()
        httpd.server_close()

    print()
    if failures:
        print("SMOKE FAILED")
        for f in failures:
            print("  - %s" % f)
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())