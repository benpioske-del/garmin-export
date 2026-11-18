"""Manual run entries typed into the dashboard's quick-log form.

A typed entry is not a Garmin activity: there is no FIT file, no device summary
and no lap splits. Putting it in the canonical ``activities`` table would make
``loadcalc`` count it as if the watch had recorded it, so it lives in a local
JSON sidecar next to the other athlete data and is merged into
``/api/activities`` for display only. Every merged row carries
``source_system = "manual"`` so a caller can tell the difference.

The quick-log form promises that a Garmin sync replaces the typed copy. That is
enforced here: a manual entry is hidden while a device activity exists on the
same local date, so a later sync cannot double-count the run.

The file is local-only (``paths.data_dir()``), listed in ``paths.DATA_FILES``
and bundled by ``backup_data.py``. It is never committed.
"""

import datetime
import json
import os
import re
import tempfile

import paths
import terms

STORE_FILE = (os.environ.get("GARMIN_MANUAL_RUNS_FILE")
              or os.path.join(paths.data_dir(), "manual_runs.json"))

# A quick-log body is tiny. Refusing anything larger keeps a stray upload from
# growing the store without bound.
MAX_BODY = 64 * 1024
MAX_ENTRIES = 5000
MAX_DISTANCE_MI = 200.0
MAX_SECONDS = 24 * 3600

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ManualRunError(ValueError):
    """A quick-log payload that cannot be stored honestly."""


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def parse_duration(text):
    """Seconds from ``H:MM:SS``, ``MM:SS``, ``SS`` or a bare number.

    Returns ``None`` when the value is absent or not a positive duration.
    """
    if text is None or text == "":
        return None
    if isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        seconds = float(text)
    else:
        raw = str(text).strip()
        if not raw:
            return None
        parts = raw.split(":")
        if len(parts) > 3:
            return None
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            return None
        seconds = 0.0
        for part in nums:
            seconds = seconds * 60 + part
    if not (seconds > 0):
        return None
    return int(round(seconds))


def _optional_int(value, low, high, label):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ManualRunError("%s must be a number" % label)
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        raise ManualRunError("%s must be a number" % label)
    if not (low <= number <= high):
        raise ManualRunError("%s must be between %d and %d"
                             % (label, low, high))
    return number


def normalize(payload):
    """Validate one quick-log payload and return the record to store.

    Raises ``ManualRunError`` for anything that would be stored as a guess:
    an impossible date, a zero distance, an unparseable duration.
    """
    if not isinstance(payload, dict):
        raise ManualRunError("payload must be a JSON object")

    date = str(payload.get("date") or "").strip()
    if not _DATE.match(date):
        raise ManualRunError("date must be YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise ManualRunError("date is not a real calendar day")

    raw_distance = payload.get("distance")
    if raw_distance in (None, ""):
        raw_distance = payload.get("distance_mi")
    try:
        distance = float(raw_distance)
    except (TypeError, ValueError):
        raise ManualRunError("distance must be a number")
    if not (0 < distance <= MAX_DISTANCE_MI):
        raise ManualRunError("distance must be between 0 and %g miles"
                             % MAX_DISTANCE_MI)

    raw_time = payload.get("seconds")
    if raw_time in (None, ""):
        raw_time = payload.get("time")
    seconds = parse_duration(raw_time)
    if seconds is None:
        raise ManualRunError("time must look like 45:00 or 1:02:03")
    if seconds > MAX_SECONDS:
        raise ManualRunError("time is longer than 24 hours")

    avg_hr = _optional_int(payload.get("hr", payload.get("avg_hr")),
                           30, 250, "average heart rate")
    rpe = _optional_int(payload.get("rpe"), 1, 10, "RPE")

    return {
        # Date is the identity: re-logging the same day replaces the entry
        # instead of stacking two runs the athlete only ran once.
        "activity_id": "manual:" + date,
        "date": date,
        "distance_mi": round(distance, 2),
        "moving_time_s": seconds,
        "avg_hr": avg_hr,
        "rpe": rpe,
        "avg_pace_s_per_mi": int(round(seconds / distance)),
        "logged_utc": _now_utc(),
    }


def load(path=None):
    """Stored entries, oldest first. A missing or corrupt file reads as []."""
    path = path or STORE_FILE
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    rows = data.get("runs") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if isinstance(row, dict) and _DATE.match(str(row.get("date") or "")):
            out.append(row)
    out.sort(key=lambda r: str(r.get("date")))
    return out


def save(rows, path=None):
    """Write the store atomically so a crash cannot leave half a JSON file."""
    path = path or STORE_FILE
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    payload = {"version": 1, "runs": list(rows)[-MAX_ENTRIES:]}
    fd, tmp = tempfile.mkstemp(prefix=".manual-runs-", suffix=".json",
                               dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return path


def upsert(payload, path=None):
    """Validate, store and return one entry, replacing the same date."""
    row = normalize(payload)
    rows = load(path)
    for index, existing in enumerate(rows):
        if existing.get("date") == row["date"]:
            rows[index] = row
            break
    else:
        rows.append(row)
    rows.sort(key=lambda r: str(r.get("date")))
    save(rows, path)
    return row


def activity_rows(existing_dates, path=None):
    """Manual entries as ``/api/activities`` rows, minus synced dates.

    ``existing_dates`` holds the local dates already covered by a device
    activity. Those entries are hidden rather than deleted, so the typed copy
    is still there if the Garmin import is ever removed.
    """
    out = []
    for row in load(path):
        date = str(row.get("date"))
        if date in existing_dates:
            continue
        distance = float(row.get("distance_mi") or 0)
        seconds = int(row.get("moving_time_s") or 0)
        pace = row.get("avg_pace_s_per_mi")
        if pace is None and distance > 0:
            pace = int(round(seconds / distance))
        out.append({
            "activity_id": row.get("activity_id") or ("manual:" + date),
            "source_system": "manual",
            "source_activity_id": None,
            "source_file": "manual entry",
            "sport": "Running",
            "title": "Manual run",
            "start_utc": date + "T00:00:00Z",
            "start_local": date,
            "timezone_source": "manual",
            "distance_mi": distance,
            "moving_time_s": seconds,
            "elapsed_time_s": seconds,
            "avg_hr": row.get("avg_hr"),
            "max_hr": None,
            "avg_cadence": None,
            "max_cadence": None,
            "avg_pace_s_per_mi": pace,
            "best_pace_s_per_mi": None,
            "calories": None,
            "training_stress_score": None,
            "total_ascent_ft": None,
            "total_descent_ft": None,
            # No FIT file means no lap splits. An empty list would read as
            # "the watch recorded zero laps", so it stays null.
            "splits": None,
            "best_5k_s": None,
            "laps": None,
            "rpe": row.get("rpe"),
            "value_state": terms.ATHLETE_REPORTED,
            "confidence": terms.MEDIUM,
            "confirmation": terms.CONFIRMATION_NOT_REQUIRED,
            "review_state": "manual",
            "reviews": [],
            "has_open_review": False,
            "manual": True,
        })
    return out


def merge(payload, path=None):
    """Add manual rows to an ``/api/activities`` payload.

    Pure enough for a request handler: the input dict is updated in place and
    returned, so the route lambda stays a one-liner.
    """
    if not isinstance(payload, dict):
        return payload
    activities = payload.get("activities")
    if not isinstance(activities, list):
        return payload

    existing_dates = set()
    base = []
    for row in activities:
        if not isinstance(row, dict):
            continue
        if row.get("source_system") == "manual":
            # Re-merging an already-merged payload must not duplicate rows.
            continue
        base.append(row)
        date = str(row.get("start_local") or row.get("start_utc") or "")[:10]
        if date:
            existing_dates.add(date)

    added = activity_rows(existing_dates, path)
    payload["manual_count"] = len(added)
    if not added:
        payload["activities"] = base
        payload["count"] = len(base)
        return payload

    merged = base + added
    merged.sort(key=lambda r: str(r.get("start_utc") or ""), reverse=True)
    payload["activities"] = merged
    payload["count"] = len(merged)
    return payload
