-- 004: versioned load snapshots.
-- Stored rather than recomputed on read so a number quoted today can still be
-- explained after the formula changes. version records which formula produced
-- the row, and inputs_json keeps the evidence the numbers came from.

CREATE TABLE IF NOT EXISTS load_snapshots (
    snapshot_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of_utc    TEXT NOT NULL,
    version      TEXT NOT NULL,
    window_days  INTEGER NOT NULL,
    run_load     REAL,
    strength_load REAL,
    combined_load REAL,
    acute_load   REAL,
    chronic_load REAL,
    acwr         REAL,
    state        TEXT NOT NULL,
    confidence   TEXT NOT NULL,
    confirmation TEXT NOT NULL,
    inputs_json  TEXT,
    created_utc  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_load_as_of ON load_snapshots (as_of_utc);

-- Event log for the health boundary. Recording the access is the point: an
-- audit of "was a read permitted" must survive the row it read.
CREATE TABLE IF NOT EXISTS health_access_log (
    access_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    subject     TEXT NOT NULL,
    action      TEXT NOT NULL,
    granted     INTEGER NOT NULL,
    scope       TEXT,
    consent_id  INTEGER,
    reason      TEXT,
    at_utc      TEXT NOT NULL
);
