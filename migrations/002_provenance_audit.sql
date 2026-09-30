-- 002: provenance, immutable raw references, import audit and review queue.
-- These exist so that "where did this number come from" and "what changed, and
-- who decided" are answerable after the fact rather than reconstructed.

-- Field-level provenance: one row per field per activity.
CREATE TABLE IF NOT EXISTS activity_field_provenance (
    activity_id  TEXT NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
    field_name   TEXT NOT NULL,
    value_state  TEXT NOT NULL,
    confidence   TEXT NOT NULL,
    confirmation TEXT NOT NULL,
    source_file  TEXT,
    source_field TEXT,
    note         TEXT,
    updated_utc  TEXT NOT NULL,
    PRIMARY KEY (activity_id, field_name)
);

-- Hash of every source file that fed an activity, so a later file change is
-- detectable and a re-import can be shown to have read identical bytes.
CREATE TABLE IF NOT EXISTS activity_raw_refs (
    activity_id    TEXT NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
    source_file    TEXT NOT NULL,
    sha256         TEXT NOT NULL,
    byte_size      INTEGER,
    file_mtime_utc TEXT,
    parser         TEXT,
    parser_version TEXT,
    imported_utc   TEXT NOT NULL,
    PRIMARY KEY (activity_id, source_file)
);

-- Append-only. Deliberately has no foreign key and no cascade: the history of
-- what happened to a record must outlive the record itself.
CREATE TABLE IF NOT EXISTS activity_import_audit (
    audit_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id TEXT,
    event_utc   TEXT NOT NULL,
    event       TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'system',
    field       TEXT,
    old_value   TEXT,
    new_value   TEXT,
    reason      TEXT
);

CREATE INDEX IF NOT EXISTS ix_audit_activity ON activity_import_audit (activity_id);
CREATE INDEX IF NOT EXISTS ix_audit_event ON activity_import_audit (event_utc);

-- Questions for the athlete. A gap becomes a question here; it never becomes
-- an invented session. See docs/DATA_QUALITY_TERMINOLOGY.md.
--
-- subject is deliberately not a foreign key: the review queue is shared between
-- activities and strength sessions, and a "strength:"-prefixed session id is not
-- a row in activities. Enforcing the reference here would mean every strength
-- safety flag had to invent an activity row to exist.
CREATE TABLE IF NOT EXISTS review_items (
    review_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id    TEXT,
    reason         TEXT NOT NULL,
    state          TEXT NOT NULL,
    detail         TEXT,
    opened_utc     TEXT NOT NULL,
    resolved_utc   TEXT,
    resolved_by    TEXT,
    resolution_note TEXT
);

CREATE INDEX IF NOT EXISTS ix_review_state ON review_items (state, reason);
