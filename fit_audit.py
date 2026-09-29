"""Task 4: inspect FIT files for GPS, timestamps and laps. Read-only.

Refactored so the per-file logic is importable and testable. Nothing here
writes to a FIT file or to the data directory.

Run directly to print a report:

    python fit_audit.py
"""

import glob
import os
import sys
from collections import Counter

import fitparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

# FIT stores semicircles: degrees * (2**31 / 180)
SEMICIRCLE = 180.0 / (2 ** 31)


def inspect_file(path):
    """Return a summary dict for one FIT file.

    Raises on an unparseable file so the caller can record the failure rather
    than silently counting the file as clean.
    """
    out = {
        "name": os.path.basename(path),
        "points": 0,
        "records": 0,
        "has_gps": False,
        "laps": 0,
        "tz_fields": 0,
        "out_of_range": 0,
        "null_island": 0,
        "lat_min": None,
        "lat_max": None,
        "lon_min": None,
        "lon_max": None,
    }
    for rec in fitparse.FitFile(path).get_messages("record"):
        out["records"] += 1
        raw_lat = raw_lon = None
        for f in rec:
            if f.name == "position_lat":
                raw_lat = f.value
            elif f.name == "position_long":
                raw_lon = f.value
        if raw_lat is None or raw_lon is None:
            continue
        out["points"] += 1
        out["has_gps"] = True
        lat, lon = raw_lat * SEMICIRCLE, raw_lon * SEMICIRCLE
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            out["out_of_range"] += 1
        if abs(lat) < 1e-6 and abs(lon) < 1e-6:
            out["null_island"] += 1
        out["lat_min"] = lat if out["lat_min"] is None else min(out["lat_min"], lat)
        out["lat_max"] = lat if out["lat_max"] is None else max(out["lat_max"], lat)
        out["lon_min"] = lon if out["lon_min"] is None else min(out["lon_min"], lon)
        out["lon_max"] = lon if out["lon_max"] is None else max(out["lon_max"], lon)
    out["laps"] = len(list(fitparse.FitFile(path).get_messages("lap")))
    for sess in fitparse.FitFile(path).get_messages("session"):
        for f in sess:
            if "time_zone" in f.name or "utc_offset" in f.name:
                out["tz_fields"] += 1
    return out


def summarise(paths_list):
    """Inspect a list of FIT files, collecting successes and failures."""
    results, failures = [], []
    for p in paths_list:
        try:
            results.append(inspect_file(p))
        except Exception as exc:  # noqa: BLE001 - a bad file must not stop the run
            failures.append({"name": os.path.basename(p),
                             "error": type(exc).__name__})
    return results, failures


def report(fit_dir=None):
    files = sorted(glob.glob(os.path.join(fit_dir or paths.fit_dir(), "*.fit")))
    results, failures = summarise(files)
    gps = [r for r in results if r["has_gps"]]
    laps = [r for r in results if r["laps"]]
    tz = [r for r in results if r["tz_fields"]]
    points = sum(r["points"] for r in results)

    lines = [
        "files inspected        : %d" % len(files),
        "parse failures         : %d" % len(failures),
    ]
    for f in failures:
        lines.append("   FAIL %s -> %s" % (f["name"], f["error"]))
    lines += [
        "files WITH GPS         : %d" % len(gps),
        "files WITHOUT GPS      : %d" % (len(results) - len(gps)),
        "files with lap records : %d" % len(laps),
        "files w/ session tz    : %d" % len(tz),
        "position points        : %d" % points,
        "points out of range    : %d" % sum(r["out_of_range"] for r in results),
        "points at null island  : %d" % sum(r["null_island"] for r in results),
    ]
    lats = [r["lat_min"] for r in results if r["lat_min"] is not None]
    lats += [r["lat_max"] for r in results if r["lat_max"] is not None]
    lons = [r["lon_min"] for r in results if r["lon_min"] is not None]
    lons += [r["lon_max"] for r in results if r["lon_max"] is not None]
    if lats:
        lines += ["lat range              : %.4f to %.4f" % (min(lats), max(lats)),
                  "lon range              : %.4f to %.4f" % (min(lons), max(lons))]
    return "\n".join(lines), results, failures


if __name__ == "__main__":
    text, _, _ = report()
    print(text)
