-- 001: canonical activity record.
-- One row per real-world activity. The primary key is ours and stable; Garmin's
-- own id is kept in source_activity_id so a re-export can be matched back.
-- start_local is nullable on purpose: when only UTC is known, the local date is
-- unknown and NULL says that. It is never backfilled with a guess.

CREATE TABLE IF NOT EXISTS activities (
    activity_id           TEXT PRIMARY KEY,
    source_system         TEXT NOT NULL,
    source_activity_id    TEXT,
    sport                 TEXT NOT NULL,
    title                 TEXT NOT NULL DEFAULT '',
    start_utc             TEXT NOT NULL,
    start_local           TEXT,
    timezone_source       TEXT NOT NULL,
    distance_mi           REAL,
    moving_time_s         INTEGER,
    elapsed_time_s        INTEGER,
    calories              INTEGER,
    avg_hr                INTEGER,
    max_hr                INTEGER,
    avg_cadence           INTEGER,
    max_cadence           INTEGER,
    avg_pace_s_per_mi     REAL,
    best_pace_s_per_mi    REAL,
    total_ascent_ft       INTEGER,
    total_descent_ft      INTEGER,
    training_stress_score INTEGER,
    value_state           TEXT NOT NULL,
    confidence            TEXT NOT NULL,
    confirmation          TEXT NOT NULL,
    review_state          TEXT NOT NULL,
    notes                 TEXT,
    first_seen_utc        TEXT NOT NULL,
    last_updated_utc      TEXT NOT NULL
);

-- NULL source_activity_id must stay repeatable, and SQLite treats NULLs as
-- distinct in a unique index, so this constrains only identified activities.
CREATE UNIQUE INDEX IF NOT EXISTS ux_activities_source
    ON activities (source_system, source_activity_id);

CREATE INDEX IF NOT EXISTS ix_activities_start ON activities (start_utc);
CREATE INDEX IF NOT EXISTS ix_activities_review ON activities (review_state);
