-- 005: consent records and consented health inputs.
-- A health value with no live, matching consent is unreadable by construction;
-- the service layer enforces that, and access attempts are logged either way.

CREATE TABLE IF NOT EXISTS consents (
    consent_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    subject     TEXT NOT NULL,
    scope       TEXT NOT NULL,
    purpose     TEXT NOT NULL,
    status      TEXT NOT NULL,          -- active | revoked
    granted_utc TEXT NOT NULL,
    revoked_utc TEXT,
    source      TEXT NOT NULL,
    note        TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_consent
    ON consents (subject, scope, purpose);

CREATE TABLE IF NOT EXISTS health_inputs (
    input_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    subject       TEXT NOT NULL,
    observed_date TEXT NOT NULL,
    metric        TEXT NOT NULL,
    value         REAL,
    unit          TEXT,
    value_state   TEXT NOT NULL,
    confidence    TEXT NOT NULL,
    confirmation  TEXT NOT NULL,
    source        TEXT NOT NULL,
    consent_id    INTEGER REFERENCES consents(consent_id),
    recorded_utc  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_health_subject ON health_inputs (subject, observed_date);
