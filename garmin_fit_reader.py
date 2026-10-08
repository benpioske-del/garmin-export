"""Read Garmin .FIT activity files into the same flat schema as the Garmin CSV export.

Deliberately never reads or emits any position field. The session records carry
start_position_lat/long, nec_lat/long and swc_lat/long; those are dropped here and
the module asserts they never reach the output.
"""

import datetime
import glob
import os
import re

import fitparse

M_TO_MI = 1.0 / 1609.344
M_TO_FT = 1.0 / 0.3048

# Bump when the derived fields below change meaning, not just for bug fixes.
# Recorded by fit_audit so a result can name the code that produced it.
__version__ = "1.1.0"

# Elevation is the one field in a FIT file that is never measured, only derived.
# These files carry no barometer_pressure samples, so altitude comes from GPS at
# roughly 6-second intervals carrying several feet of positional noise. Summing
# every upward step therefore counts that noise as climbing: on a real 5-mile
# run the raw sum was 596 ft while ~300 ft of it was noise.
#
# `total_ascent` stays the device's own figure because it is the most defensible
# number available and inventing a different one would be worse. The smoothed
# recomputation is carried beside it so the uncertainty is visible instead of
# silent. Neither is a measurement, and neither should drive a load decision.
ELEV_SMOOTH_SAMPLES = 5


def _smooth(values, window):
    """Centred moving average with ragged edges clamped, not shortened."""
    if window < 2 or len(values) < 2:
        return list(values)
    half = window // 2
    out = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def _ascent_ft(alt_m):
    """Total climb in feet from a metre altitude series, or None.

    Sums only positive steps. A smoothed series is supplied by the caller; this
    function does not smooth so a caller can compare both and expose the spread.
    """
    if len(alt_m) < 2:
        return None
    return sum(max(0.0, alt_m[i] - alt_m[i - 1]) for i in range(1, len(alt_m))) * M_TO_FT

# Garmin names downloaded activities YYYY-MM-DD_<activity id>.fit, using the
# device's local date. That filename is the only local-date signal we have,
# because no FIT file carries a timezone offset.
FILENAME_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})_")

# Values for the Timezone Status column. See docs/PROVENANCE.md.
TZ_ASSUMED_UTC = "assumed_utc; local date from filename"


def split_start(start, path):
    """Return (local_naive, utc_aware) for a FIT session start_time.

    The FIT spec defines start_time as UTC, but fitparse returns a *naive*
    datetime, so the value carries no offset marker of its own. Attaching UTC
    makes the assumption explicit rather than implicit.

    The athlete's own local date is taken from the filename when available. It
    genuinely differs from the UTC date for evening runs that cross midnight
    UTC, which is why the two are reported separately instead of one column
    being silently labelled the other.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=datetime.timezone.utc)
    m = FILENAME_DATE.match(os.path.basename(path))
    if not m:
        return start.replace(tzinfo=None), start
    try:
        local_date = datetime.datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return start.replace(tzinfo=None), start
    local = datetime.datetime.combine(
        local_date, start.astimezone(datetime.timezone.utc).timetz().replace(tzinfo=None)
    )
    return local, start


# Fields that must never be exported. Guarded by assert_no_gps() below.
FORBIDDEN = (
    "position_lat", "position_long", "position_latitude", "position_longitude",
    "start_position_lat", "start_position_long", "end_position_lat",
    "end_position_long", "nec_lat", "nec_long", "swc_lat", "swc_long",
)


def hms(seconds):
    """Seconds -> H:MM:SS, matching how Garmin writes times in its CSV."""
    seconds = int(round(seconds or 0))
    if seconds <= 0:
        return ""
    return "%d:%02d:%02d" % (seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def pace_str(min_per_mile):
    """Minutes per mile -> M:SS (or H:MM:SS past an hour)."""
    if not min_per_mile or min_per_mile <= 0:
        return ""
    total = int(round(min_per_mile * 60))
    if total >= 3600:
        return hms(total)
    return "%d:%02d" % (total // 60, total % 60)


def _best_5k_seconds(fit, start):
    """Elapsed seconds at the first record whose cumulative distance >= 5000 m.

    Only distance and timestamps are read. Position fields are never touched;
    the row-level GPS guard in assert_no_gps covers the columns, and this
    routine never looks at latitude/longitude fields by name or value.
    """
    if not start:
        return None
    for rec in fit.get_messages("record"):
        d = {f.name: f.value for f in rec}
        dist = d.get("distance")
        ts = d.get("timestamp")
        if not dist or dist < 5000.0 or not ts:
            continue
        try:
            delta = (ts - start).total_seconds()
        except Exception:  # a fixture or file with a non-datetime timestamp
            continue
        if delta <= 0:
            continue
        return delta
    return None


def _mile_splits(fit, start):
    """Per-mile split times from the distance curve, as M:SS strings.

    Same curve-only discipline as _best_5k_seconds: cumulative distance and
    timestamps only, position fields never touched. Used as a fallback when a
    file carries no lap messages, so a run is still published with its split
    column populated. One split per mile boundary, with each split the time
    from the previous boundary; like a watch, the final partial mile is not
    emitted as its own split.
    """
    if not start:
        return []
    splits = []
    prev_t = 0.0
    next_mile = 1609.344
    for rec in fit.get_messages("record"):
        d = {f.name: f.value for f in rec}
        dist = d.get("distance")
        ts = d.get("timestamp")
        if not dist or not ts:
            continue
        try:
            t = (ts - start).total_seconds()
        except Exception:  # a fixture or file with a non-datetime timestamp
            continue
        if t <= 0:
            continue
        if dist >= next_mile:
            splits.append(pace_str((t - prev_t) / 60.0))
            prev_t = t
            next_mile += 1609.344
    return splits


def pace_from_speed(mps):
    # Pace is time per mile, so this DIVIDES by speed. 1609.344 m per mile,
    # then seconds -> minutes. (Multiplying here inverts the ranking and makes
    # the slowest lap look like the fastest.)
    if not mps or mps <= 0.5 or mps > 12:
        return ""
    return pace_str(1609.344 / mps / 60.0)


def _sport_label(sport):
    if not sport:
        return "Running"
    return str(sport).replace("_", " ").title()


def assert_no_gps(row):
    for k in row:
        if any(bad in k.lower() for bad in ("lat", "lon", "position", "gps")):
            raise AssertionError("GPS field leaked into export: %s" % k)
    return row


def read_fit(path):
    """Return one activity dict, or None if the file has no usable session."""
    fit = fitparse.FitFile(path)

    sessions = list(fit.get_messages("session"))
    if not sessions:
        return None
    sess = sessions[-1]
    s = {f.name: f.value for f in sess}

    start = s.get("start_time")
    if not start:
        return None

    dist_mi = (s.get("total_distance") or 0.0) * M_TO_MI
    timer_s = s.get("total_timer_time") or 0.0
    elapsed_s = s.get("total_elapsed_time") or 0.0

    if dist_mi <= 0.05 or timer_s <= 0:
        return None

    # Laps drive best pace / best lap time. Ignore the trailing partial lap
    # (Garmin emits a final sub-metre lap on stop).
    laps = []
    for m in fit.get_messages("lap"):
        lap = {f.name: f.value for f in m}
        d = (lap.get("total_distance") or 0.0) * M_TO_MI
        t = lap.get("total_timer_time") or 0.0
        if d >= 0.95 and t > 0:
            laps.append((d, t, lap))

    best_pace = ""
    best_lap = ""
    for d, t, lap in laps:
        p = pace_from_speed(lap.get("avg_speed"))
        if p and (not best_pace or pace_min(p) < pace_min(best_pace)):
            best_pace = p
        lt = hms(t)
        if lt and (not best_lap or t < hms_sec(best_lap)):
            best_lap = lt

    # Measured 5 km crossing: the clock time at which the distance curve reaches
    # 5000 m, from per-record cumulative distance and timestamps. Not an average
    # pace projection. Includes any stops before the crossing, so it is recorded
    # as a measurement, not as a "PR" - see docs/SPLITS_AUDIT.md.
    _five_k_seconds = _best_5k_seconds(fit, start)
    five_k = pace_str(_five_k_seconds / 60.0) if _five_k_seconds else ""

    # Splits the device cut, in "M:SS" each (d >= 0.95 mi already filtered).
    # A file with no lap messages still has mile boundaries in its distance
    # curve, so the column is populated from the curve rather than left empty.
    lap_splits = ", ".join(pace_str(t / 60.0) for d, t, lap in laps)
    if not lap_splits:
        lap_splits = ", ".join(_mile_splits(fit, start))

    # One altitude sample per record. Previously this appended both
    # enhanced_altitude and altitude when a record carried both, interleaving two
    # series into a single list; they happen to be identical on current firmware
    # so min/max were unaffected, but on firmware where they diverge it would
    # have produced a min and max from different series. enhanced_altitude is
    # preferred because it is the device's corrected altitude.
    elev = []
    for rec in fit.get_messages("record"):
        d = {f.name: f.value for f in rec}
        alt = d.get("enhanced_altitude")
        if alt is None:
            alt = d.get("altitude")
        if alt is not None:
            elev.append(alt)
    lo = round(min(elev) * M_TO_FT) if elev else ""
    hi = round(max(elev) * M_TO_FT) if elev else ""
    # Recomputed climb, carried so the GPS-noise band around the device figure is
    # visible. Not a replacement: see the note above ELEV_SMOOTH_SAMPLES.
    elev_smooth = _smooth(elev, ELEV_SMOOTH_SAMPLES)
    smooth_ascent = _ascent_ft(elev_smooth)
    raw_ascent = _ascent_ft(elev)
    elev_range = (max(elev) - min(elev)) * M_TO_FT if elev else 0.0

    local_start, start_utc = split_start(start, path)

    row = {
        "Activity Type": _sport_label(s.get("sport")),
        "Date": local_start.strftime("%Y-%m-%d %H:%M:%S"),
        "Date (UTC)": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Timezone Status": TZ_ASSUMED_UTC,
        "Source": "Garmin FIT",
        "Favorite": "false",
        # Title is intentionally blank. Garmin titles can name a city or route.
        "Title": "",
        "Distance": round(dist_mi, 2),
        "Calories": s.get("total_calories") if s.get("total_calories") is not None else "",
        "Time": hms(timer_s),
        "Avg HR": s.get("avg_heart_rate") or "",
        "Max HR": s.get("max_heart_rate") or "",
        "Avg Run Cadence": s.get("avg_running_cadence") or "",
        "Max Run Cadence": s.get("max_running_cadence") or "",
        "Avg Pace": pace_str((timer_s / 60.0) / dist_mi),
        "Best Pace": best_pace,
        "Best 5K Time": five_k,
        "Lap Splits": lap_splits,
        "Total Ascent": round((s.get("total_ascent") or 0) * M_TO_FT),
        "Total Descent": round((s.get("total_descent") or 0) * M_TO_FT),
        "Avg Stride Length": (round(s["avg_step_length"] * M_TO_FT)
                              if s.get("avg_step_length") else ""),
        "Training Stress Score": (s.get("training_stress_score")
                                  if s.get("training_stress_score") is not None else ""),
        "Steps": "",
        "Decompression": "",
        "Best Lap Time": best_lap,
        "Number of Laps": s.get("num_laps") or len(laps),
        "Moving Time": hms(timer_s),
        "Elapsed Time": hms(elapsed_s),
        "Min Elevation": lo,
        "Max Elevation": hi,
        # Underscore-prefixed: diagnostics, not part of the published CSV schema.
        # They expose the GPS-noise band around Total Ascent and let a consumer
        # sanity-check an implausible ratio without re-parsing the FIT file.
        "_elev_range_ft": round(elev_range),
        "_ascent_smoothed_ft": round(smooth_ascent) if smooth_ascent is not None else "",
        "_ascent_raw_ft": round(raw_ascent) if raw_ascent is not None else "",
        "_ascent_samples": len(elev),
        "_source_file": os.path.basename(path),
    }
    return assert_no_gps(row)


def pace_min(p):
    parts = [int(x) for x in p.split(":")]
    if len(parts) == 3:
        return parts[0] * 60 + parts[1] + parts[2] / 60.0
    return parts[0] + parts[1] / 60.0


def hms_sec(p):
    parts = [int(x) for x in p.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return parts[0] * 60 + parts[1]


def read_dir(pattern):
    """Read every .FIT under a glob, newest last. Skips unreadable files."""
    rows = []
    skipped = []
    for path in sorted(glob.glob(pattern)):
        try:
            row = read_fit(path)
        except Exception as e:
            skipped.append((os.path.basename(path), str(e)[:60]))
            continue
        if row:
            rows.append(row)
    rows.sort(key=lambda r: r["Date"])
    return rows, skipped
