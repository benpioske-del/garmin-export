-- 006: weather observations, coarse location only.
-- No latitude or longitude columns exist in this table and none may be added.
-- location_key is a deliberately rounded grid cell, which is enough to match
-- runs to conditions and far too coarse to reconstruct a route from.

CREATE TABLE IF NOT EXISTS weather_observations (
    observation_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_utc        TEXT NOT NULL,
    location_key        TEXT NOT NULL,
    location_granularity TEXT NOT NULL,
    temperature_c       REAL,
    humidity_pct        REAL,
    precipitation_mm    REAL,
    wind_kph            REAL,
    source              TEXT NOT NULL,
    created_utc         TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_weather_obs
    ON weather_observations (observed_utc, location_key, source);

CREATE INDEX IF NOT EXISTS ix_weather_match
    ON weather_observations (location_key, observed_utc);

-- Matched-run pairing. This is what a personalised weather claim would be built
-- from, so it is gated by run count rather than merely gated by consent.
CREATE TABLE IF NOT EXISTS weather_run_matches (
    match_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id  TEXT NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
    observation_id INTEGER NOT NULL REFERENCES weather_observations(observation_id) ON DELETE CASCADE,
    matched_utc  TEXT NOT NULL,
    distance_km  REAL,
    created_utc  TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_weather_match_activity
    ON weather_run_matches (activity_id);
