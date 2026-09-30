-- 003: strength sessions, exercises and sets.
-- A session holds many exercises and an exercise holds many sets, so a
-- leg press with four sets and a calf raise with three are both representable
-- without inventing a flat "strength session = one number" row.

CREATE TABLE IF NOT EXISTS strength_exercises (
    exercise_id    TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    muscle_group   TEXT,
    equipment      TEXT,
    is_bodyweight  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (name, equipment)
);

CREATE TABLE IF NOT EXISTS strength_sessions (
    session_id         TEXT PRIMARY KEY,
    start_utc          TEXT NOT NULL,
    start_local        TEXT,
    timezone_source    TEXT NOT NULL,
    notes              TEXT,
    value_state        TEXT NOT NULL,
    confidence         TEXT NOT NULL,
    confirmation       TEXT NOT NULL,
    review_state       TEXT NOT NULL,
    source_system      TEXT,
    source_activity_id TEXT,
    created_utc        TEXT NOT NULL,
    updated_utc        TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_strength_source
    ON strength_sessions (source_system, source_activity_id);

CREATE INDEX IF NOT EXISTS ix_strength_start ON strength_sessions (start_utc);

CREATE TABLE IF NOT EXISTS strength_session_exercises (
    session_exercise_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL REFERENCES strength_sessions(session_id) ON DELETE CASCADE,
    exercise_id         TEXT NOT NULL REFERENCES strength_exercises(exercise_id),
    ordinal             INTEGER NOT NULL DEFAULT 1,
    UNIQUE (session_id, exercise_id)
);

-- load_kg is NULL for bodyweight work rather than 0, and load_display keeps the
-- exact text the athlete entered ("135", "2 plates", "bodyweight") so nothing
-- is lost when a number is not cleanly parseable.
-- value_state/confidence carry the manual-vs-imported distinction the brief
-- asks for. These migrations have never shipped, so 003 is amended in place
-- rather than adding a 007 that only patches itself.
CREATE TABLE IF NOT EXISTS strength_sets (
    set_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_exercise_id INTEGER NOT NULL REFERENCES strength_session_exercises(session_exercise_id) ON DELETE CASCADE,
    set_number         INTEGER NOT NULL,
    reps               INTEGER,
    load_kg            REAL,
    load_display       TEXT,
    rir                INTEGER,
    rpe                REAL,
    is_warmup          INTEGER NOT NULL DEFAULT 0,
    tempo              TEXT,
    rest_s             INTEGER,
    distance_m         REAL,
    duration_s         INTEGER,
    notes              TEXT,
    value_state        TEXT NOT NULL,
    confidence         TEXT NOT NULL,
    UNIQUE (session_exercise_id, set_number)
);
