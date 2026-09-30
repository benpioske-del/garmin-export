"""Canonical activity records: stable identity, provenance, review and audit.

Everything the pipeline imports lands here first, so the CSV export is a
published view of these rows rather than the system of record.

Design rules that the rest of the brief depends on:

  * Identity is ours and stable. Garmin's id is kept alongside it, never used
    as the key, because a re-export must map onto the same record.
  * Absence is NULL. A missing field is never written as 0, and a gap in the
    data becomes a review question, never an invented session.
  * Re-import is idempotent. Importing identical bytes twice changes nothing
    and writes no audit rows, so re-running is safe and quiet.
  * Every write is auditable, and the audit table has no foreign key, so the
    history of a record outlives the record.

Local-date handling follows garmin_fit_reader: UTC is observed, the local date
comes from the filename, and until the athlete confirms an offset the local
date carries TZ_FILENAME_DATE and a review item.
"""

import datetime
import hashlib
import json
import os
import sys

import terms
import trainingdb
from garmin_fit_reader import FILENAME_DATE, hms_sec, pace_min

SOURCE_SYSTEM = "garmin"

# (column, reader key, kind, value_state, confidence)
# Calories, ascent and training stress are device-computed summaries rather
# than direct observations, so they are device_derived at medium confidence.
FIELD_SPECS = (
    ("distance_mi",           "Distance",              "float",   terms.DEVICE_DERIVED, terms.HIGH),
    ("moving_time_s",         "Moving Time",           "duration", terms.DEVICE_DERIVED, terms.HIGH),
    ("elapsed_time_s",        "Elapsed Time",          "duration", terms.DEVICE_DERIVED, terms.HIGH),
    ("calories",              "Calories",              "int",     terms.DEVICE_DERIVED, terms.MEDIUM),
    ("avg_hr",                "Avg HR",                "int",     terms.DEVICE_DERIVED, terms.HIGH),
    ("max_hr",                "Max HR",                "int",     terms.DEVICE_DERIVED, terms.HIGH),
    ("avg_cadence",           "Avg Run Cadence",       "int",     terms.DEVICE_DERIVED, terms.HIGH),
    ("max_cadence",           "Max Run Cadence",       "int",     terms.DEVICE_DERIVED, terms.HIGH),
    ("avg_pace_s_per_mi",     "Avg Pace",              "pace",    terms.ALGORITHMIC,     terms.MEDIUM),
    ("best_pace_s_per_mi",    "Best Pace",             "pace",    terms.ALGORITHMIC,     terms.MEDIUM),
    ("total_ascent_ft",       "Total Ascent",          "int",     terms.DEVICE_DERIVED, terms.MEDIUM),
    ("total_descent_ft",      "Total Descent",         "int",     terms.DEVICE_DERIVED, terms.MEDIUM),
    ("training_stress_score", "Training Stress Score", "int",     terms.DEVICE_DERIVED, terms.MEDIUM),
)

TRACKED_COLUMNS = tuple(spec[0] for spec in FIELD_SPECS)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def source_activity_id(source_file):
    """Pull Garmin's own activity id out of YYYY-MM-DD_<id>.fit."""
    if not source_file:
        return None
    m = FILENAME_DATE.match(os.path.basename(source_file))
    if m and "_" in os.path.basename(source_file):
        tail = os.path.basename(source_file).split("_", 1)[1]
        return os.path.splitext(tail)[0] or None
    return None


def canonical_id(source_system, native_id, start_utc, sport):
    """Stable id for an activity.

    Preferred form is source + native id. Where no native id exists, fall back
    to a digest of the identifying tuple, so the same activity still resolves
    to the same id on a later import instead of accumulating duplicates.
    """
    if native_id:
        return "%s:%s" % (source_system, native_id)
    seed = "|".join([source_system, start_utc or "", (sport or "").lower()])
    return "%s:%s" % (source_system, hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16])


def _num(value, kind):
    """Convert a reader string to a typed value. Blank becomes None, not 0."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if kind == "float" else int(value)
    text = str(value).strip()
    if not text:
        return None
    if kind == "duration":
        return hms_sec(text)
    if kind == "pace":
        return round(pace_min(text) * 60.0, 2)
    try:
        return float(text) if kind == "float" else int(float(text))
    except ValueError:
        return None


def _iso_utc(value):
    """Normalise a reader timestamp to an ISO-8601 Z string."""
    if not value:
        return None
    text = str(value).strip().replace(" ", "T")
    if text.endswith("Z"):
        return text
    return text + "Z"


def _naive(value):
    return str(value).strip().replace(" ", "T") if value else None


def _completeness(value, confidence):
    """Map a stored value plus its confidence onto a completeness state."""
    if value is None:
        return terms.UNAVAILABLE_FROM_SOURCE
    if confidence == terms.UNVERIFIED:
        return terms.PRESENT_LOW_CONFIDENCE
    if confidence == terms.LOW:
        return terms.AWAITING_CONFIRMATION
    return terms.COMPLETE


def _audit(conn, activity_id, event, actor="system", field=None,
           old_value=None, new_value=None, reason=None):
    conn.execute(
        """INSERT INTO activity_import_audit
           (activity_id, event_utc, event, actor, field, old_value, new_value, reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (activity_id, now_utc(), event, actor, field,
         _text(old_value), _text(new_value), reason),
    )


def _text(value):
    return None if value is None else str(value)


def upsert_activity(conn, row, source_dir=None, raw_hash=None, raw_size=None,
                    parser="garmin_fit_reader", actor="system"):
    """Insert or update one activity from a reader row.

    Returns (activity_id, event) where event is inserted, updated or unchanged.
    """
    source_file = row.get("_source_file")
    native = source_activity_id(source_file)
    start_utc = _iso_utc(row.get("Date (UTC)"))
    sport = (row.get("Activity Type") or "").strip()
    activity_id = canonical_id(SOURCE_SYSTEM, native, start_utc, sport)

    values = {}
    provenance = {}
    for column, key, kind, state, confidence in FIELD_SPECS:
        raw = row.get(key)
        value = _num(raw, kind)
        # A blank on a numeric field means the source had no such value.
        if value is None:
            state, confidence = terms.MISSING, terms.UNVERIFIED
        values[column] = value
        provenance[column] = (state, confidence, terms.CONFIRMATION_NOT_REQUIRED)

    # The local date is a filename assumption, never an observation, and it is
    # the one field that is routinely wrong near midnight.
    start_local = _naive(row.get("Date"))
    tz_source = terms.TZ_FILENAME_DATE if start_local else terms.TZ_UTC_ONLY
    provenance["start_local"] = (
        terms.ASSUMED, terms.LOW, terms.CONFIRMATION_REQUIRED
    )
    provenance["start_utc"] = (terms.OBSERVED, terms.HIGH, terms.CONFIRMATION_NOT_REQUIRED)

    existing = conn.execute(
        "SELECT * FROM activities WHERE activity_id = ?", (activity_id,)
    ).fetchone()

    aggregate = terms.worst(p[1] for p in provenance.values())
    confirmation = terms.CONFIRMATION_REQUIRED if tz_source != terms.TZ_CONFIRMED_OFFSET \
        else terms.CONFIRMATION_NOT_REQUIRED
    review_state = terms.OPEN if terms.needs_review(confirmation) else terms.CLOSED
    stamp = now_utc()

    if existing is None:
        conn.execute(
            """INSERT INTO activities (
                activity_id, source_system, source_activity_id, sport, title,
                start_utc, start_local, timezone_source, value_state, confidence,
                confirmation, review_state, first_seen_utc, last_updated_utc,
                %s) VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, %s)"""
            % (", ".join(TRACKED_COLUMNS),
               ", ".join("?" * len(TRACKED_COLUMNS))),
            (activity_id, SOURCE_SYSTEM, native, sport, start_utc, start_local,
             tz_source, terms.DEVICE_DERIVED, aggregate, confirmation,
             review_state, stamp, stamp) + tuple(values[c] for c in TRACKED_COLUMNS),
        )
        _audit(conn, activity_id, "inserted", actor, reason="import")
        event = "inserted"
    else:
        changed = [c for c in TRACKED_COLUMNS if existing[c] != values[c]]
        for col, keep, new in (("start_local", start_local, start_local),
                               ("timezone_source", tz_source, tz_source),
                               ("sport", sport, sport)):
            if keep != new:
                changed.append(col)
        if not changed:
            _record_provenance(conn, activity_id, provenance, source_file, stamp)
            return activity_id, "unchanged"
        sets = ", ".join("%s = ?" % c for c in changed)
        conn.execute(
            "UPDATE activities SET %s, last_updated_utc = ? WHERE activity_id = ?" % sets,
            tuple(_new_for(c, values, sport, start_local, tz_source) for c in changed)
            + (stamp, activity_id),
        )
        for col in changed:
            _audit(conn, activity_id, "updated", actor, field=col,
                   old_value=existing[col], new_value=_new_for(col, values, sport, start_local, tz_source),
                   reason="reimport")
        event = "updated"

    _record_provenance(conn, activity_id, provenance, source_file, stamp)

    if source_file and raw_hash:
        conn.execute(
            """INSERT INTO activity_raw_refs
               (activity_id, source_file, sha256, byte_size, file_mtime_utc,
                parser, parser_version, imported_utc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(activity_id, source_file) DO UPDATE SET
                   sha256=excluded.sha256, imported_utc=excluded.imported_utc""",
            (activity_id, source_file, raw_hash, raw_size, None, parser,
             _parser_version(parser), stamp),
        )

    if terms.needs_review(confirmation):
        open_review(conn, activity_id, terms.REVIEW_TIMEZONE,
                    detail="local date derived from filename: %s" % start_local,
                    actor=actor)
    return activity_id, event


def _new_for(column, values, sport, start_local, tz_source):
    if column == "sport":
        return sport
    if column == "start_local":
        return start_local
    if column == "timezone_source":
        return tz_source
    return values[column]


def _parser_version(parser):
    """Version of the parser that produced a value, when it declares one."""
    if parser != "garmin_fit_reader":
        return None
    import garmin_fit_reader
    return getattr(garmin_fit_reader, "__version__", None)


def _record_provenance(conn, activity_id, provenance, source_file, stamp):
    for field, (state, confidence, confirmation) in provenance.items():
        conn.execute(
            """INSERT INTO activity_field_provenance
               (activity_id, field_name, value_state, confidence, confirmation,
                source_file, source_field, updated_utc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(activity_id, field_name) DO UPDATE SET
                   value_state=excluded.value_state, confidence=excluded.confidence,
                   confirmation=excluded.confirmation, updated_utc=excluded.updated_utc""",
            (activity_id, field, state, confidence, confirmation,
             source_file, field, stamp),
        )


def open_review(conn, activity_id, reason, detail=None, actor="system"):
    """Raise a review question. Idempotent: does not stack duplicates."""
    existing = conn.execute(
        """SELECT review_id FROM review_items
           WHERE activity_id IS ? AND reason = ? AND state = ?""",
        (activity_id, reason, terms.OPEN),
    ).fetchone()
    if existing:
        return existing["review_id"]
    cur = conn.execute(
        """INSERT INTO review_items (activity_id, reason, state, detail, opened_utc)
           VALUES (?, ?, ?, ?, ?)""",
        (activity_id, reason, terms.OPEN, detail, now_utc()),
    )
    return cur.lastrowid


def resolve_review(conn, review_id, state, actor, note=None):
    state = state.upper()
    if state == "CONFIRMATION_REQUIRED":
        raise ValueError("cannot resolve into a non-terminal state")
    conn.execute(
        """UPDATE review_items
           SET state = ?, resolved_utc = ?, resolved_by = ?, resolution_note = ?
           WHERE review_id = ?""",
        (state, now_utc(), actor, note, review_id),
    )
    _audit(conn, None, "review_" + state.lower(), actor,
           reason="review_id=%s" % review_id)


def detect_duplicates(conn, window_s=300, tol=0.01):
    """Flag activities that look like the same real session recorded twice.

    Same sport, near-identical start and near-identical distance. Returns the
    ids of the later record in each pair; the earlier one is left alone.
    """
    rows = conn.execute(
        """SELECT activity_id, sport, start_utc, distance_mi
           FROM activities WHERE start_utc IS NOT NULL
           ORDER BY start_utc"""
    ).fetchall()
    flagged = []
    for i, a in enumerate(rows):
        ta = _parse(a["start_utc"])
        for b in rows[i + 1:]:
            tb = _parse(b["start_utc"])
            if ta is None or tb is None:
                continue
            if (tb - ta).total_seconds() > window_s:
                break
            if a["sport"].lower() != b["sport"].lower():
                continue
            da, db = a["distance_mi"], b["distance_mi"]
            if not da or not db:
                continue
            if abs(da - db) / max(da, db) <= tol:
                flagged.append(b["activity_id"])
                open_review(conn, b["activity_id"], terms.REVIEW_DUPLICATE,
                            detail="within %ds of %s" % (window_s, a["activity_id"]))
    return flagged


def detect_date_gaps(conn, gap_days=7):
    """Open a review item for stretches of missing days.

    A gap is reported, never filled. Nothing in this function creates a
    placeholder activity.
    """
    rows = conn.execute(
        "SELECT DISTINCT substr(start_utc, 1, 10) AS d FROM activities "
        "WHERE start_utc IS NOT NULL ORDER BY d"
    ).fetchall()
    dates = [datetime.date.fromisoformat(r["d"]) for r in rows]
    opened = []
    for a, b in zip(dates, dates[1:]):
        gap = (b - a).days
        if gap > gap_days:
            rid = open_review(conn, None, terms.REVIEW_DATE_GAP,
                              detail="no activity %s..%s (%d days)" % (a, b, gap - 1))
            opened.append(rid)
    return opened


def confirm_timezone(conn, activity_id, offset_hours, actor="athlete"):
    """Apply an athlete-confirmed UTC offset to an activity's local date.

    This is the only path that upgrades a local date from assumed to confirmed.
    """
    if offset_hours is None:
        raise ValueError("offset_hours required")
    row = conn.execute(
        "SELECT start_utc FROM activities WHERE activity_id = ?", (activity_id,)
    ).fetchone()
    if row is None:
        raise KeyError(activity_id)
    start = _parse(row["start_utc"])
    local = (start + datetime.timedelta(hours=offset_hours)).replace(tzinfo=None)
    stamp = now_utc()
    conn.execute(
        """UPDATE activities SET start_local = ?, timezone_source = ?,
           confirmation = ?, review_state = ?, last_updated_utc = ?
           WHERE activity_id = ?""",
        (local.strftime("%Y-%m-%dT%H:%M:%S"), terms.TZ_CONFIRMED_OFFSET,
         terms.CONFIRMATION_NOT_REQUIRED, terms.CLOSED, stamp, activity_id),
    )
    conn.execute(
        """UPDATE activity_field_provenance
           SET value_state = ?, confidence = ?, confirmation = ?, updated_utc = ?
           WHERE activity_id = ? AND field_name = 'start_local'""",
        (terms.ATHLETE_REPORTED, terms.HIGH, terms.CONFIRMATION_NOT_REQUIRED,
         stamp, activity_id),
    )
    conn.execute(
        """UPDATE review_items SET state = ?, resolved_utc = ?, resolved_by = ?,
           resolution_note = ? WHERE activity_id = ? AND reason = ? AND state = ?""",
        (terms.RESOLVED, stamp, actor, "offset %+dh" % offset_hours,
         activity_id, terms.REVIEW_TIMEZONE, terms.OPEN),
    )
    _audit(conn, activity_id, "timezone_confirmed", actor,
           field="timezone_source", old_value=terms.TZ_FILENAME_DATE,
           new_value=terms.TZ_CONFIRMED_OFFSET, reason="offset %+dh" % offset_hours)


def _parse(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def history(conn, activity_id):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM activity_import_audit WHERE activity_id = ? ORDER BY audit_id",
        (activity_id,))]


def completeness(conn):
    """Per-field completeness rollup across the whole record set."""
    out = {}
    for row in conn.execute(
        """SELECT field_name, value_state, confidence FROM activity_field_provenance"""
    ):
        bucket = out.setdefault(row["field_name"], {})
        state = _completeness(None if row["value_state"] == terms.MISSING else 1,
                              row["confidence"])
        bucket[state] = bucket.get(state, 0) + 1
    return out


def summary(conn):
    total = conn.execute("SELECT COUNT(*) c FROM activities").fetchone()["c"]
    open_reviews = conn.execute(
        "SELECT COUNT(*) c FROM review_items WHERE state = ?", (terms.OPEN,)
    ).fetchone()["c"]
    return {"activities": total, "open_reviews": open_reviews}


def import_dir(pattern, db=None):
    """Import every FIT under a glob. Returns a per-file event tally.

    Only closes the connection when it opened it, so a caller can keep querying
    afterwards.
    """
    import glob
    import garmin_fit_reader

    own = db is None
    conn = db or trainingdb.connect()
    trainingdb.migrate(conn, verbose=False)
    tally = {"inserted": 0, "updated": 0, "unchanged": 0, "unreadable": 0}
    for path in sorted(glob.glob(pattern)):
        try:
            row = garmin_fit_reader.read_fit(path)
            if not row:
                tally["unreadable"] += 1
                continue
            size = os.path.getsize(path)
            _, event = upsert_activity(conn, row, raw_hash=sha256_file(path),
                                       raw_size=size)
            tally[event] += 1
        except Exception:
            tally["unreadable"] += 1
    detect_duplicates(conn)
    detect_date_gaps(conn)
    conn.commit()
    if own:
        conn.close()
    return tally


def _main(argv):
    db = trainingdb.connect()
    trainingdb.migrate(db, verbose=False)
    verb = argv[0] if argv else "summary"
    if verb == "import":
        pattern = argv[1] if len(argv) > 1 else r"C:\Users\benpi\Downloads\garmin_fit\*.fit"
        print(json.dumps(import_dir(pattern, db), indent=2))
    elif verb == "duplicates":
        print(json.dumps(detect_duplicates(db)))
    elif verb == "gaps":
        print(json.dumps(detect_date_gaps(db)))
    else:
        print(json.dumps(summary(db), indent=2))
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
