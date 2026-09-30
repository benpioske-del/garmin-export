"""Versioned training-load calculation, with running and strength kept apart.

The brief is explicit that these must not be fused into one untraceable number,
so this module never returns a bare total. Every result carries its components,
the window, the exact days and activities that fed it, and the formula version
that produced it.

Running load uses a heart-rate intensity bucket (TRIMP-like) scaled by duration.
When heart rate or a max estimate is unavailable the running component is None
and marked unavailable, rather than falling back to a distance proxy that would
quietly measure something else.

Strength load uses the session-RPE method: volume in kg-reps times session RPE
over 100. When RPE is unrecorded the result is marked low confidence, because an
assumed RPE is an assumption, not a measurement.

Assumptions are collected in ASSUMPTIONS so a reader can disagree with a number
without reading the code.
"""

import datetime
import json

import terms
import trainingdb

LOAD_VERSION = "load-1.0.0"
WINDOWS = (7, 14, 28)

ASSUMPTIONS = {
    "hr_buckets": "intensity ratio hr_avg/hr_max -> multiplier",
    "hr_buckets_values": ((0.50, 1.0), (0.65, 1.5), (0.80, 2.5), (0.90, 4.0)),
    "hr_buckets_above_0.90": 5.0,
    "hr_max": "supplied by caller; never estimated silently",
    "strength": "kg-reps * session_rpe / 100",
    "strength_default_rpe": 5.0,
    "windows_days": WINDOWS,
}


def _parse(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _intensity_multiplier(hr_avg, hr_max):
    if not hr_avg or not hr_max or hr_max <= 0:
        return None
    ratio = hr_avg / hr_max
    for ceiling, mult in ASSUMPTIONS["hr_buckets_values"]:
        if ratio <= ceiling:
            return mult
    return ASSUMPTIONS["hr_buckets_above_0.90"]


def run_session_load(row, hr_max):
    """Load for one run, or None when the inputs do not support one.

    Returns (load, confidence, note) so the caller can say why rather than
    storing a silent zero.
    """
    if row["start_utc"] is None:
        return None, terms.UNVERIFIED, "no start_utc"
    start = _parse(row["start_utc"])
    if start is None:
        return None, terms.UNVERIFIED, "unparseable start_utc"

    days = (start - datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)).days
    if row["avg_hr"] is None:
        return None, terms.UNVERIFIED, "no avg_hr in source"
    mult = _intensity_multiplier(row["avg_hr"], hr_max)
    if mult is None:
        return None, terms.UNVERIFIED, "no hr_max supplied"
    minutes = (row["moving_time_s"] or 0) / 60.0
    if minutes <= 0:
        return None, terms.UNVERIFIED, "no moving_time_s"
    return round(minutes * mult, 1), terms.MEDIUM, "hr %.0f/%.0f x%.1f" % (
        row["avg_hr"], hr_max or 0, mult)


def strength_session_load(conn, session_id, default_rpe=None):
    import strength

    sets = [s for s in strength.session_sets(conn, session_id) if not s["is_warmup"]]
    if not sets:
        return None, terms.UNVERIFIED, "no working sets"
    rpes = [s["rpe"] for s in sets if s["rpe"] is not None]
    if rpes:
        session_rpe = sum(rpes) / len(rpes)
        confidence = terms.HIGH if len(rpes) == len(sets) else terms.MEDIUM
    else:
        session_rpe = default_rpe or ASSUMPTIONS["strength_default_rpe"]
        confidence = terms.LOW
    volume = sum((s["load_kg"] or 0.0) * (s["reps"] or 0) for s in sets)
    if volume <= 0:
        return None, terms.UNVERIFIED, "no loaded volume"
    return round(volume * session_rpe / 100.0, 1), confidence, "volume %.0f kg-reps @ RPE %.1f" % (
        volume, session_rpe)


def window_bounds(as_of, days):
    end = _parse(as_of)
    if end is None:
        end = datetime.datetime.now(datetime.timezone.utc)
    return end - datetime.timedelta(days=days), end


def compute(conn, as_of=None, hr_max=None, default_rpe=None):
    """Load for every supported window.

    Returns a dict keyed by window with run/strength/combined always separate.
    combined is only populated when at least one component is real, and is
    accompanied by the components it was built from.
    """
    as_of = as_of or datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    out = {"version": LOAD_VERSION, "as_of_utc": as_of,
           "assumptions": {k: str(v) for k, v in ASSUMPTIONS.items()}, "windows": {}}

    runs = [dict(r) for r in conn.execute(
        "SELECT * FROM activities WHERE start_utc IS NOT NULL ORDER BY start_utc")]
    sessions = [dict(r) for r in conn.execute(
        "SELECT * FROM strength_sessions ORDER BY start_utc")]

    for days in WINDOWS:
        start, end = window_bounds(as_of, days)
        run_days, run_total, run_conf, run_notes = set(), 0.0, [], []
        run_ids = []
        for row in runs:
            t = _parse(row["start_utc"])
            if t is None or not (start <= t <= end):
                continue
            load, conf, note = run_session_load(row, hr_max)
            if load is None:
                run_notes.append({"activity_id": row["activity_id"], "reason": note})
                continue
            run_total += load
            run_days.add(t.date().isoformat())
            run_conf.append(conf)
            run_ids.append(row["activity_id"])

        str_days, str_total, str_conf, str_notes = set(), 0.0, [], []
        str_ids = []
        for row in sessions:
            t = _parse(row["start_utc"])
            if t is None or not (start <= t <= end):
                continue
            load, conf, note = strength_session_load(conn, row["session_id"], default_rpe)
            if load is None:
                str_notes.append({"session_id": row["session_id"], "reason": note})
                continue
            str_total += load
            str_days.add(t.date().isoformat())
            str_conf.append(conf)
            str_ids.append(row["session_id"])

        run_component = round(run_total, 1) if run_days else None
        str_component = round(str_total, 1) if str_days else None
        if run_component is None and str_component is None:
            combined = None
        else:
            combined = round((run_component or 0.0) + (str_component or 0.0), 1)

        out["windows"][str(days)] = {
            "days": days,
            "run_load": run_component,
            "strength_load": str_component,
            "combined_load": combined,
            "run_confidence": terms.worst(run_conf) if run_conf else terms.UNVERIFIED,
            "strength_confidence": terms.worst(str_conf) if str_conf else terms.UNVERIFIED,
            "run_days": sorted(run_days),
            "strength_days": sorted(str_days),
            "included_run_ids": run_ids,
            "included_session_ids": str_ids,
            "unavailable": {"run": run_notes, "strength": str_notes},
        }
    return out


def acwr(acute, chronic):
    """Acute:chronic workload ratio.

    A monitoring signal only. Not an injury probability or a risk score, and
    not a clinical measure of anything.
    """
    if chronic in (None, 0) or acute is None:
        return None
    return round(acute / chronic, 2)


def save_snapshot(conn, result, state, confidence, confirmation):
    """Persist a computed result so a quoted number survives a formula change."""
    acute = result["windows"].get("7", {}).get("combined_load")
    chronic = result["windows"].get("28", {}).get("combined_load")
    row = result["windows"].get("28", {})
    conn.execute(
        """INSERT INTO load_snapshots
           (as_of_utc, version, window_days, run_load, strength_load, combined_load,
            acute_load, chronic_load, acwr, state, confidence, confirmation,
            inputs_json, created_utc)
           VALUES (?, ?, 28, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (result["as_of_utc"], result["version"], row.get("run_load"),
         row.get("strength_load"), row.get("combined_load"), acute, chronic,
         acwr(acute, chronic), state, confidence, confirmation,
         json.dumps({"windows": result["windows"], "assumptions": result["assumptions"]}),
         datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    return conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]


def _main(argv):
    conn = trainingdb.connect()
    trainingdb.migrate(conn, verbose=False)
    result = compute(conn)
    print(json.dumps(result, indent=2, default=str))
    conn.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv[1:]))
