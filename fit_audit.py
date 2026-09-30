"""Task 3: deterministic, reproducible audit of every raw .FIT file.

Read-only. Nothing here writes to a FIT file or to the data directory.

What changed from the previous version of this script:

  * exact latitude and longitude are no longer computed or printed. The old
    script reported a lat/lon range, which is a route fingerprint and was the
    same class of leak as the incident recorded in docs/PRIVACY_INCIDENT.md.
    Position data is now reduced to counts.
  * every file gets a SHA-256, so a later audit can prove it read identical
    bytes and a changed file is detectable.
  * the parser version is recorded alongside the hash, because a result that
    cannot name the code that produced it is not reproducible.
  * per-field presence is reported, so a field the reader needs but the file
    lacks shows up as a warning instead of a blank cell.

Run directly:

    python fit_audit.py [--dir PATH] [--json OUT]
"""

import argparse
import glob
import hashlib
import json
import os
import sys

import fitparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

# FIT stores semicircles: degrees * (2**31 / 180). Used only to sanity-check
# a point's validity; the decoded value is never stored or printed.
SEMICIRCLE = 180.0 / (2 ** 31)

# Fields the export reader depends on. Absence of any of these degrades the
# canonical record, so absence is reported rather than tolerated silently.
EXPECTED_SESSION_FIELDS = (
    "sport", "start_time", "total_distance", "total_timer_time",
    "total_elapsed_time", "total_calories", "avg_heart_rate",
    "max_heart_rate", "avg_running_cadence", "max_running_cadence",
    "total_ascent", "total_descent", "num_laps",
)

# Position fields are counted, never decoded into output.
POSITION_FIELDS = ("position_lat", "position_long")


def parser_versions():
    import garmin_fit_reader
    return {
        "fitparse": getattr(fitparse, "__version__", None),
        "garmin_fit_reader": getattr(garmin_fit_reader, "__version__", None),
    }


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _blank(path):
    return {
        "name": os.path.basename(path),
        "sha256": None,
        "byte_size": 0,
        "readable": False,
        "position_points": 0,
        "null_island": 0,
        "out_of_range": 0,
        "has_gps": False,
        "has_timestamp": False,
        "start_utc": None,
        "records": 0,
        "sessions": 0,
        "laps": 0,
        "tz_fields": 0,
        "fields_present": [],
        "fields_missing": [],
        "warnings": [],
        "out_of_range": 0,
        "error": None,
    }


def _val(message, name):
    """Raw value of a field, or None.

    fitparse's .get() returns a FieldData wrapper rather than the value, and
    that wrapper is truthy even when the underlying value is None, so .value
    has to be read explicitly or a present-but-null position field gets counted
    as a real point. Test doubles hand back the bare value, so accept both.
    """
    field = message.get(name)
    if field is None:
        return None
    return getattr(field, "value", field)


def inspect_file(path):
    """Return a summary dict for one FIT file.

    Raises on an unparseable file so the caller records the failure rather
    than counting a broken file as clean.
    """
    out = _blank(path)
    out["name"] = os.path.basename(path)
    out["byte_size"] = os.path.getsize(path)
    out["sha256"] = sha256_file(path)

    fit = fitparse.FitFile(path)

    records = list(fit.get_messages("record"))
    out["records"] = len(records)
    for rec in records:
        lat, lon = _val(rec, "position_lat"), _val(rec, "position_long")
        if lat is None or lon is None:
            continue
        out["position_points"] += 1
        # Range and null-island are counted, never the decoded degrees.
        if not (-90 <= lat * SEMICIRCLE <= 90 and -180 <= lon * SEMICIRCLE <= 180):
            out["out_of_range"] += 1
        if lat == 0 and lon == 0:
            out["null_island"] += 1

    sessions = list(fit.get_messages("session"))
    out["sessions"] = len(sessions)
    if sessions:
        fields = {f.name for f in sessions[-1]}
        out["fields_present"] = sorted(fields & set(EXPECTED_SESSION_FIELDS))
        out["fields_missing"] = sorted(set(EXPECTED_SESSION_FIELDS) - fields)
        start = _val(sessions[-1], "start_time")
        if start is not None:
            out["has_timestamp"] = True
            out["start_utc"] = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        if len(sessions) > 1:
            out["warnings"].append(
                "multiple sessions in one file: %d" % len(sessions))

    out["laps"] = len(list(fit.get_messages("lap")))
    out["has_gps"] = out["position_points"] > 0

    # Counted so the report can state that no file carries a usable timezone,
    # which is the evidence behind the assumed-UTC provenance label.
    for sess in fit.get_messages("session"):
        for f in sess:
            if "time_zone" in f.name or "utc_offset" in f.name:
                out["tz_fields"] += 1

    if not sessions:
        out["warnings"].append("no session message: not importable")
    elif not out["has_timestamp"]:
        out["warnings"].append("session has no start_time")
    if out["fields_missing"]:
        out["warnings"].append("missing session fields: %s" % ", ".join(out["fields_missing"]))
    if out["sessions"] and not out["laps"]:
        out["warnings"].append("session present but no lap records")
    if out["has_gps"] and not out["records"]:
        out["warnings"].append("gps flag set but no record messages")
    if out["out_of_range"]:
        out["warnings"].append(
            "%d position points outside valid range" % out["out_of_range"])
    if out["null_island"]:
        out["warnings"].append(
            "%d position points at 0,0" % out["null_island"])

    out["readable"] = True
    return out


def summarise(paths_list):
    """Inspect files, collecting successes and failures separately."""
    results, failures = [], []
    for p in paths_list:
        try:
            results.append(inspect_file(p))
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
            failure = _blank(p)
            failure["name"] = os.path.basename(p)
            failure["byte_size"] = os.path.getsize(p) if os.path.exists(p) else 0
            failure["error"] = type(exc).__name__
            failure["warnings"].append("unparseable: %s" % type(exc).__name__)
            failures.append(failure)
    return results, failures


def rollup(results, failures):
    counts = {}
    for r in list(results) + list(failures):
        for w in r["warnings"]:
            counts[w] = counts.get(w, 0) + 1
    return {
        "files_inspected": len(results) + len(failures),
        "parse_failures": len(failures),
        "files_readable": len(results),
        "files_with_gps": sum(1 for r in results if r["has_gps"]),
        "files_without_gps": sum(1 for r in results if not r["has_gps"]),
        "files_with_timestamp": sum(1 for r in results if r["has_timestamp"]),
        "files_without_timestamp": sum(1 for r in results if not r["has_timestamp"]),
        "total_laps": sum(r["laps"] for r in results),
        "total_sessions": sum(r["sessions"] for r in results),
        "total_records": sum(r["records"] for r in results),
        "total_position_points": sum(r["position_points"] for r in results),
        "position_points_out_of_range": sum(r["out_of_range"] for r in results),
        "files_with_missing_fields": sum(1 for r in results if r["fields_missing"]),
        "warning_counts": dict(sorted(counts.items())),
    }


def render(results, failures, roll=None):
    """Deterministic text report. Counts only, never coordinates."""
    roll = roll or rollup(results, failures)
    versions = parser_versions()
    lines = [
        "FIT data audit",
        "parser: fitparse=%s reader=%s"
        % (versions.get("fitparse"), versions.get("garmin_fit_reader")),
        "",
        "files inspected           : %d" % roll["files_inspected"],
        "parse failures            : %d" % roll["parse_failures"],
        "files readable            : %d" % roll["files_readable"],
        "files with GPS            : %d" % roll["files_with_gps"],
        "files without GPS         : %d" % roll["files_without_gps"],
        "files with usable timestamp: %d" % roll["files_with_timestamp"],
        "files without timestamp   : %d" % roll["files_without_timestamp"],
        "session messages          : %d" % roll["total_sessions"],
        "lap messages              : %d" % roll["total_laps"],
        "record messages           : %d" % roll["total_records"],
        "position points (counted) : %d" % roll["total_position_points"],
        "files missing fields      : %d" % roll["files_with_missing_fields"],
        "",
        "warnings:",
    ]
    if roll["warning_counts"]:
        for w, n in roll["warning_counts"].items():
            lines.append("   %-52s %d" % (w[:52], n))
    else:
        lines.append("   none")
    lines += ["", "per-file manifest (sha256 truncated to 16):"]
    for r in sorted(list(results) + list(failures), key=lambda x: x["name"]):
        lines.append(
            "   %-34s %s  gps=%-5s ts=%-5s laps=%-3s missing=%d%s"
            % (r["name"], (r["sha256"] or "")[:16], r["has_gps"], r["has_timestamp"],
               r["laps"], len(r["fields_missing"]),
               "  ERROR %s" % r["error"] if r["error"] else "")
        )
    return "\n".join(lines)


def report(fit_dir=None):
    files = sorted(glob.glob(os.path.join(fit_dir or paths.fit_dir(), "*.fit")))
    results, failures = summarise(files)
    roll = rollup(results, failures)
    return render(results, failures, roll), results, failures


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=None, help="directory of .FIT files")
    ap.add_argument("--json", default=None, help="write machine-readable manifest here")
    args = ap.parse_args(argv)
    text, results, failures = report(args.dir)
    print(text)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"versions": parser_versions(),
                       "rollup": rollup(results, failures),
                       "files": sorted(list(results) + list(failures),
                                       key=lambda x: x["name"])},
                      fh, indent=2, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
