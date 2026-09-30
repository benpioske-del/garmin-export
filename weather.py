"""Weather enrichment gate.

The only thing that can leave this module is descriptive matched-observation
count. Personalised "you run 8% slower in heat" claims are not produced, and
the schema stores no latitude or longitude so a route cannot be reconstructed
from the table.

The athlete has not yet chosen a location policy, so the default is
conservative: with no recorded location the gate returns blocked_no_location
rather than falling back to the coordinates inside a FIT file. Those are exact
and route-revealing, and reading them for this purpose is precisely what the
brief forbids without a location policy.
"""

import datetime
import math

import terms

SCOPE_WEATHER = "weather"
PURPOSE_ENRICHMENT = "activity_context"

# Grid resolution for location_key. 0.25 degrees is roughly 25 km, which is far
# too coarse to infer a route and fine enough to group runs by general climate.
GRID_DEGREES = 0.25


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def location_key(lat, lon, grid=GRID_DEGREES):
    """Round to a coarse grid cell. Reduces precision rather than storing it.

    Accepting coordinates here is deliberate: a location policy may supply them
    at day resolution. What is stored is only the rounded cell.
    """
    return "%+.2f_%+.2f" % (round(lat / grid) * grid, round(lon / grid) * grid)


def gate(conn, subject, location=None, consent_check=None):
    """Decide whether weather may be used, and say why not when it may not.

    Returns one of terms.WEATHER_STATES plus a reason. No observation data is
    returned until the gate is WEATHER_MATCHED.
    """
    if consent_check is not None and not consent_check():
        return terms.WEATHER_BLOCKED_NO_CONSENT, "consent not recorded for weather enrichment"
    if not location:
        return terms.WEATHER_BLOCKED_NO_LOCATION, (
            "no location policy recorded; FIT coordinates are exact and were "
            "not used as a substitute")
    return terms.WEATHER_UNAVAILABLE, "location available; no provider configured"


def record_observation(conn, observed_utc, lat, lon, temperature_c=None,
                       humidity_pct=None, precipitation_mm=None, wind_kph=None,
                       source="manual"):
    """Store one observation. Only the rounded grid cell is persisted."""
    conn.execute(
        """INSERT INTO weather_observations
           (observed_utc, location_key, location_granularity, temperature_c,
            humidity_pct, precipitation_mm, wind_kph, source, created_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(observed_utc, location_key, source) DO UPDATE SET
               temperature_c = excluded.temperature_c,
               humidity_pct = excluded.humidity_pct,
               precipitation_mm = excluded.precipitation_mm,
               wind_kph = excluded.wind_kph""",
        (observed_utc, location_key(lat, lon), "grid_%.2f" % GRID_DEGREES,
         temperature_c, humidity_pct, precipitation_mm, wind_kph, source, _now()),
    )


def match_observations(conn, activity_id, start_utc, key, tolerance_s=3600):
    """Link a run to observations near its start time in the same grid cell."""
    start = datetime.datetime.fromisoformat(str(start_utc).replace("Z", "+00:00"))
    window = str(start - datetime.timedelta(seconds=tolerance_s))
    end = str(start + datetime.timedelta(seconds=tolerance_s))
    rows = list(conn.execute(
        """SELECT * FROM weather_observations
           WHERE location_key = ? AND observed_utc BETWEEN ? AND ?""",
        (key, window, end),
    ))
    for row in rows:
        conn.execute(
            """INSERT INTO weather_run_matches
               (activity_id, observation_id, matched_utc, created_utc)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(activity_id) DO NOTHING""",
            (activity_id, row["observation_id"], row["observed_utc"], _now()),
        )
    return len(rows)


def matched_run_count(conn, key):
    return conn.execute(
        "SELECT COUNT(*) c FROM weather_run_matches m "
        "JOIN weather_observations o USING (observation_id) WHERE o.location_key = ?",
        (key,),
    ).fetchone()["c"]


def personalised_claim_state(conn, key):
    """Whether a personalised weather-performance claim is supported at all.

    Even with consent and a location, the observation count has to be large
    enough for a per-condition split to mean anything. Below the floor the
    answer is that the claim is unsupported, not a weak version of it.
    """
    n = matched_run_count(conn, key)
    if n >= terms.WEATHER_RECOMMENDED_MATCHED_RUNS:
        return terms.WEATHER_MATCHED, n, (
            "%d matched runs; enough to describe conditions, still not a prediction" % n)
    if n >= terms.WEATHER_MIN_MATCHED_RUNS:
        return terms.WEATHER_MATCHED, n, (
            "%d matched runs; descriptive only, below the %d recommended for a split" % (
                n, terms.WEATHER_RECOMMENDED_MATCHED_RUNS))
    return terms.WEATHER_NO_MATCH, n, (
        "%d matched runs, need at least %d" % (n, terms.WEATHER_MIN_MATCHED_RUNS))


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 2)
