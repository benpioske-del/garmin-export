"""Consent-gated health inputs.

The repo has no authentication, so this is a single-subject boundary rather
than a multi-user permission system, and it is described that way rather than
being dressed up as one. What it does provide is real: a stored health value
carries a consent reference, reads are refused without a live matching consent,
and every attempt is logged whether it was allowed or not.

No fitness-for-return decision, injury risk score, or diagnosis is derived here.
The output is the athlete's own numbers, with their provenance, or nothing.
"""

import datetime

import terms

SCOPE_RECOVERY = "recovery"
PURPOSE_TRAINING = "training_context"

ACTIVE = "active"
REVOKED = "revoked"

# Metrics this module is willing to hold. Kept narrow on purpose.
ALLOWED_METRICS = frozenset({
    "sleep_hours", "rhr", "hrv", "resting_hr", "soreness", "fatigue",
    "stress", "motivation", "illness_flag",
})


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def grant(conn, subject, scope=SCOPE_RECOVERY, purpose=PURPOSE_TRAINING,
          source="athlete", note=None):
    conn.execute(
        """INSERT INTO consents (subject, scope, purpose, status, granted_utc, source, note)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(subject, scope, purpose) DO UPDATE SET
               status = 'active', granted_utc = excluded.granted_utc,
               revoked_utc = NULL, note = excluded.note""",
        (subject, scope, purpose, ACTIVE, _now(), source, note),
    )
    return _find(conn, subject, scope, purpose)


def revoke(conn, subject, scope=SCOPE_RECOVERY, purpose=PURPOSE_TRAINING, source="athlete"):
    conn.execute(
        "UPDATE consents SET status = ?, revoked_utc = ? WHERE subject = ? AND scope = ? AND purpose = ?",
        (REVOKED, _now(), subject, scope, purpose),
    )


def _find(conn, subject, scope, purpose):
    return conn.execute(
        "SELECT * FROM consents WHERE subject = ? AND scope = ? AND purpose = ?",
        (subject, scope, purpose),
    ).fetchone()


def has_consent(conn, subject, scope=SCOPE_RECOVERY, purpose=PURPOSE_TRAINING):
    row = _find(conn, subject, scope, purpose)
    return bool(row and row["status"] == ACTIVE)


def record(conn, subject, observed_date, metric, value, unit=None,
           source="athlete", value_state=terms.ATHLETE_REPORTED,
           confidence=terms.MEDIUM, confirmation=terms.CONFIRMATION_NOT_REQUIRED):
    """Store one health input. Refuses without a live consent."""
    if metric not in ALLOWED_METRICS:
        raise ValueError("metric %r not accepted" % metric)
    consent = _find(conn, subject, SCOPE_RECOVERY, PURPOSE_TRAINING)
    if not consent or consent["status"] != ACTIVE:
        _log(conn, subject, "record", False, SCOPE_RECOVERY,
             None if consent is None else consent["consent_id"],
             "no active consent for scope")
        raise PermissionError(
            "recording %s requires an active %s consent" % (metric, SCOPE_RECOVERY))
    _log(conn, subject, "record", True, SCOPE_RECOVERY, consent["consent_id"], None)
    conn.execute(
        """INSERT INTO health_inputs
           (subject, observed_date, metric, value, unit, value_state, confidence,
            confirmation, source, consent_id, recorded_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (subject, observed_date, metric, value, unit, value_state, confidence,
         confirmation, source, consent["consent_id"], _now()),
    )


def read(conn, subject, since_date=None, scope=SCOPE_RECOVERY,
         purpose=PURPOSE_TRAINING):
    """Read consented inputs. Returns [] rather than raising when not consented."""
    consent = _find(conn, subject, scope, purpose)
    if not consent or consent["status"] != ACTIVE:
        _log(conn, subject, "read", False, scope,
             None if consent is None else consent["consent_id"],
             "no active consent for scope")
        return []
    _log(conn, subject, "read", True, scope, consent["consent_id"], None)
    if since_date:
        rows = conn.execute(
            """SELECT * FROM health_inputs
               WHERE subject = ? AND observed_date >= ?
                 AND consent_id = ?
               ORDER BY observed_date""",
            (subject, since_date, consent["consent_id"]),
        )
    else:
        rows = conn.execute(
            "SELECT * FROM health_inputs WHERE subject = ? AND consent_id = ? ORDER BY observed_date",
            (subject, consent["consent_id"]),
        )
    return [dict(r) for r in rows]


def access_log(conn, subject=None):
    if subject:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM health_access_log WHERE subject = ? ORDER BY access_id", (subject,))]
    return [dict(r) for r in conn.execute("SELECT * FROM health_access_log ORDER BY access_id")]


def _log(conn, subject, action, granted, scope, consent_id, reason):
    conn.execute(
        """INSERT INTO health_access_log (subject, action, granted, scope, consent_id, reason, at_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (subject, action, int(bool(granted)), scope, consent_id, reason, _now()),
    )
