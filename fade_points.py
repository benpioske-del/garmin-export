"""Per-run fade points intersected with intake and temperature.

Why this exists
---------------
``run_fuel.fade()`` already measures a per-run fade, but it only surfaces when
that run also has a fuel entry. Most runs have splits and no intake record, so
the worst fades in the corpus were invisible to the analysis. This module builds
one *fade point* for every run with at least four usable splits, whether or not
anyone logged what the athlete drank or ate.

Each point carries the canonical fade, the recorded intake (with ``None`` kept
distinct from an explicit zero), and a conservative temperature read from the
athlete's own journal note. ``intersections()`` then groups those points by
hydration, fuel, electrolyte and temperature status. It is deliberately
*descriptive*: heat, hills, distance and effort all move fade, so a group median
is a prompt to look closer, never evidence that one thing caused another. Small
groups are suppressed rather than shown as a shaky average.

Nothing here is a training-load input and nothing here makes a weather claim.
The weather gate in ``weather.py`` stays the authority for provider-backed
conditions; this module only reads words the athlete already wrote down.
"""

import re
import statistics

import run_fuel

# A group smaller than this is an anecdote, not an intersection. Six is a
# common floor for a median, but three is enough to show a range on this corpus
# without pretending the difference means anything.
MIN_GROUP = 3

# Feels-like has to be read first and masked out of the note. "Feels-like 100F"
# is an apparent temperature, not an air temperature, and must never land in
# the air-temperature column.
_FEELS = re.compile(
    r"\bfeels?\s*[- ]?\s*like\s*(\d{2,3})\s*(?:°\s*)?F?\b"
    r"|\bfeels\s*[- ]?\s*(\d{2,3})\s*(?:°\s*)?F?\b", re.I)
_TEMP_RANGE = re.compile(r"\b(\d{2,3})\s*[-–]\s*(\d{2,3})\s*(?:°\s*)?F\b", re.I)
_TEMP_EXPLICIT = re.compile(r"\b(\d{2,3})\s*(?:°\s*)?F\b", re.I)
_DECADE_MOD = re.compile(r"\b(low|mid|high)\s*[- ]\s*(\d{2})s\b", re.I)
_DECADE = re.compile(r"\b(\d{2})s\b", re.I)

_DECADE_OFFSET = {"low": 2.0, "mid": 5.0, "high": 8.0}


def _band(value):
    """The decade a temperature belongs to: 84 -> '80s', 101 -> '100s'."""
    if value is None:
        return None
    return "%ds" % (int(value) // 10 * 10)


def _plausible(value):
    return value is not None and 40 <= value <= 115


def temperature(note=None, temp_f=None):
    """Read a conservative temperature signal from a note or a recorded value.

    Returns ``None`` when there is nothing explicit. A bare word like "heat"
    or "hot" is never enough: the athlete writes "heat-driven" about runs whose
    temperature is unknown. Feels-like values stay in their own field so an
    apparent temperature is not silently passed off as the air temperature.
    """
    text = str(note or "")

    feels = None
    feels_raw = None
    match = _FEELS.search(text)
    if match:
        value = match.group(1) or match.group(2)
        try:
            candidate = float(value)
        except (TypeError, ValueError):
            candidate = None
        if _plausible(candidate):
            feels = candidate
            feels_raw = match.group(0).strip()
            # Blank out the matched span. Otherwise "feels-like 100F" would
            # also be picked up by the plain ``100F`` pattern below.
            text = text[:match.start()] + " " * (match.end() - match.start()) \
                + text[match.end():]

    actual = None
    source = None
    confidence = None
    raw = None

    if isinstance(temp_f, (int, float)) and not isinstance(temp_f, bool):
        candidate = float(temp_f)
        if _plausible(candidate):
            actual = candidate
            source = "recorded"
            confidence = "high"
            raw = "tempF=%s" % temp_f

    if actual is None:
        match = _TEMP_RANGE.search(text)
        if match:
            low, high = int(match.group(1)), int(match.group(2))
            if _plausible(low) and _plausible(high):
                actual = (low + high) / 2.0
                source = "note_range"
                confidence = "medium"
                raw = match.group(0).strip()

    if actual is None:
        match = _TEMP_EXPLICIT.search(text)
        if match and _plausible(float(match.group(1))):
            actual = float(match.group(1))
            source = "note_explicit"
            confidence = "high"
            raw = match.group(0).strip()

    if actual is None:
        match = _DECADE_MOD.search(text)
        if match:
            base = int(match.group(2))
            candidate = base + _DECADE_OFFSET[match.group(1).lower()]
            if _plausible(candidate):
                actual = candidate
                source = "note_decade"
                confidence = "low"
                raw = match.group(0).strip()

    if actual is None:
        match = _DECADE.search(text)
        if match:
            candidate = int(match.group(1)) + 5.0
            if _plausible(candidate):
                actual = candidate
                source = "note_decade"
                confidence = "low"
                raw = match.group(0).strip()

    if actual is None and feels is None:
        return None

    return {
        "temp_f": actual,
        "feels_like_f": feels,
        # Bands come from air temperature only. Mixing an apparent temperature
        # into an "80s" bucket would make the grouping misleading.
        "band": _band(actual),
        "feels_like_band": _band(feels),
        "feels_like_only": actual is None and feels is not None,
        "source": source,
        "confidence": confidence,
        "raw": raw,
        "feels_raw": feels_raw,
    }


def _status(events, kind, fields):
    """recorded > none > unmeasured > not recorded, for one intake kind.

    ``none`` is a logged zero (a real observation). ``unmeasured`` means the
    athlete logged that they took something but no amount. ``not recorded``
    means there is no event at all. The three are never collapsed: "0 oz" and
    "no entry" are different facts and must stay different groups.
    """
    group = [event for event in events if event.get("kind") == kind]
    if not group:
        return "not recorded"
    values = []
    for event in group:
        for field in fields:
            value = event.get(field)
            if value is not None:
                values.append(value)
    if any(value > 0 for value in values):
        return "recorded"
    if any(value == 0 for value in values):
        return "none"
    return "unmeasured"


def point(row, notes=None):
    """Build one fade point from an ``/api/activities`` row, or None.

    ``notes`` is an optional ``{date: {note, temp_f}}`` map from the classic
    journal. It is read-only context; the fade still comes from the canonical
    ``run_fuel.fade()`` and an unlogged intake stays unknown.
    """
    if not isinstance(row, dict):
        return None
    measured = run_fuel.fade(row.get("splits"))
    if measured is None:
        return None

    fuel = row.get("fuel") if isinstance(row.get("fuel"), dict) else {}
    events = fuel.get("items") if isinstance(fuel.get("items"), list) else []
    totals = fuel.get("totals") if isinstance(fuel.get("totals"), dict) else {}
    rates = fuel.get("rates") if isinstance(fuel.get("rates"), dict) else {}
    date = str(row.get("start_local") or row.get("start_utc") or "")[:10]
    journal = (notes or {}).get(date) or {}
    note = fuel.get("note") or journal.get("note") or ""

    return {
        "date": date,
        "activity_id": row.get("activity_id"),
        "distance_mi": row.get("distance_mi"),
        "duration_h": fuel.get("duration_h"),
        "splits_used": measured["splits_used"],
        "first_half_s_per_mi": measured["first_half_s_per_mi"],
        "second_half_s_per_mi": measured["second_half_s_per_mi"],
        "fade_s_per_mi": measured["fade_s_per_mi"],
        "fade_pct": measured["fade_pct"],
        # Estimated onset of the fade, in distance, elapsed time and split.
        # It is a descriptive composite of the same splits, never a cause.
        "fade_onset": run_fuel.fade_onset(row.get("splits"), measured),
        "intake": {
            "water_oz": totals.get("oz"),
            "kcal": totals.get("kcal"),
            "carbs_g": totals.get("carbs_g"),
            "sodium_mg": totals.get("sodium_mg"),
            "water_oz_per_h": rates.get("oz_per_h"),
            "kcal_per_h": rates.get("kcal_per_h"),
            "carbs_g_per_h": rates.get("carbs_g_per_h"),
            "sodium_mg_per_h": rates.get("sodium_mg_per_h"),
        },
        "hydration": _status(events, "water", ("oz",)),
        "fuel_status": _status(events, "fuel", ("kcal", "carbs_g")),
        "electrolytes": _status(events, "electrolyte", ("sodium_mg",)),
        "temperature": temperature(note, journal.get("temp_f")),
        "needs_review": bool(fuel.get("needs_review")),
    }


# (key, label, field on a point). The field is a scalar status or a band.
DIMENSIONS = (
    ("hydration", "Hydration", "hydration"),
    ("fuel", "Fuel", "fuel_status"),
    ("electrolytes", "Electrolytes", "electrolytes"),
    ("temperature", "Temperature band", "_temperature_band"),
)

CAVEAT = (
    "Descriptive only, not a cause-and-effect result. Fade is also moved by "
    "distance, hills, effort and heat, and most runs have no intake record. "
    "Groups with fewer than %d runs are hidden. 'none' is a logged zero; "
    "'not recorded' means nothing was logged; 'unmeasured' means an item was "
    "logged without an amount. Temperature comes only from words in the "
    "athlete's notes, never from a weather estimate." % MIN_GROUP
)


def _point_field(item, field):
    if field == "_temperature_band":
        temp = item.get("temperature")
        return temp.get("band") if isinstance(temp, dict) else None
    return item.get(field)


def intersections(points):
    """Group fade percentages by each dimension, suppressing tiny groups."""
    dimensions = []
    for key, label, field in DIMENSIONS:
        buckets = {}
        for item in points:
            value = _point_field(item, field) or "not recorded"
            buckets.setdefault(value, []).append(item["fade_pct"])

        groups = []
        suppressed = []
        for name, values in sorted(buckets.items()):
            if len(values) < MIN_GROUP:
                suppressed.append({"key": name, "n": len(values)})
                continue
            groups.append({
                "key": name,
                "n": len(values),
                "median_fade_pct": round(statistics.median(values), 1),
                "mean_fade_pct": round(sum(values) / len(values), 1),
                "min_fade_pct": round(min(values), 1),
                "max_fade_pct": round(max(values), 1),
            })
        dimensions.append({
            "key": key,
            "label": label,
            "groups": groups,
            "suppressed": suppressed,
        })

    return {
        "count": len(points),
        "min_group": MIN_GROUP,
        "caveat": CAVEAT,
        "dimensions": dimensions,
    }


def attach(payload, notes=None):
    """Add ``fade_points`` and ``fade_analysis`` to an activities payload.

    Idempotent: calling it twice replaces the two keys instead of stacking
    them. Runs without four usable splits are skipped, not given a fake point,
    and an unlogged intake stays ``None`` rather than becoming a zero.
    """
    if not isinstance(payload, dict):
        return payload
    activities = payload.get("activities")
    if not isinstance(activities, list):
        return payload

    if notes is None:
        notes = run_fuel.journal_notes()

    points = []
    for row in activities:
        if not isinstance(row, dict):
            continue
        item = point(row, notes)
        if item is None:
            continue
        points.append(item)
        # The per-row copy is what the live Aurora layer maps into each run.
        # The top-level list is the same data for the analysis view and for
        # anyone reading the payload without walking every activity.
        row["fadePoint"] = item
    points.sort(key=lambda item: (item.get("date") or "", item.get("activity_id") or ""))

    payload["fade_points"] = points
    payload["fade_analysis"] = intersections(points)
    return payload


def main(argv=None):
    """Local inspection helper: print the fade points from the live store."""
    import argparse
    import json

    import garmin_server

    parser = argparse.ArgumentParser(
        description="Fade points intersected with intake and journal temperature.")
    parser.add_argument("--json", action="store_true", help="print the full payload")
    args = parser.parse_args(argv)

    conn = garmin_server.trainingdb.connect()
    try:
        payload = garmin_server.run_fuel.attach(
            garmin_server.manual_runs.merge(garmin_server.api_activities(conn)))
    finally:
        conn.close()
    attach(payload)
    if args.json:
        print(json.dumps({"fade_points": payload["fade_points"],
                          "fade_analysis": payload["fade_analysis"]}, indent=2))
        return 0
    analysis = payload["fade_analysis"]
    print("fade points: %d (groups of %d or more only)" %
          (analysis["count"], analysis["min_group"]))
    for dimension in analysis["dimensions"]:
        print("\n" + dimension["label"])
        for group in dimension["groups"]:
            print("  %-14s n=%2d  median %+5.1f%%  mean %+5.1f%%" %
                  (group["key"], group["n"], group["median_fade_pct"],
                   group["mean_fade_pct"]))
        for hidden in dimension["suppressed"]:
            print("  %-14s n=%2d  (hidden)" % (hidden["key"], hidden["n"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
