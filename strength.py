"""Strength sessions: many exercises per session, many sets per exercise.

Reuses the same audit table as activities rather than standing up a second
history system, so "what changed and who decided" is answerable for strength
the same way it is for runs.

The brief's safety constraints are enforced here, not left to the caller:

  * rest between sets defaults to at least 2.0 minutes, and a shorter
    recorded rest is flagged rather than silently accepted
  * warmup sets are tracked separately and excluded from volume and from
    progression, so they cannot inflate load
  * progression is conservative: it holds unless every working set was
    completed at or under the effort ceiling, and it never proposes more than
    a single small increment at a time

A set with no load is bodyweight and keeps load_kg NULL. Zero is never used to
mean "no weight", because a genuine zero-kilogram set is meaningless and the
distinction matters to volume.
"""

import datetime

import terms

MIN_REST_S = 120          # 2.0 minutes, per the brief
LOAD_INCREMENT_KG = 1.25  # 2.5 lb, the smallest plate change most gyms stock
MAX_PROGRESSION_PCT = 5.0
RPE_CEILING = 8.0         # at or above this, hold rather than add load
RIR_FLOOR = 2             # too close to failure to add load


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit(conn, session_id, event, actor="system", field=None,
           old_value=None, new_value=None, reason=None):
    """Strength history lands in the shared audit table, with a namespaced field."""
    conn.execute(
        """INSERT INTO activity_import_audit
           (activity_id, event_utc, event, actor, field, old_value, new_value, reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, _now(), "strength_" + event, actor,
         field and "strength." + field,
         None if old_value is None else str(old_value),
         None if new_value is None else str(new_value),
         reason),
    )


def add_exercise(conn, name, muscle_group=None, equipment=None, is_bodyweight=False):
    """Register an exercise, or return the existing one with that name+equipment.

    No conflict target is given: exercise_id is derived from the name, so a
    repeat insert collides on the primary key first and a target naming only
    the (name, equipment) unique index would not catch it.
    """
    conn.execute(
        """INSERT INTO strength_exercises (exercise_id, name, muscle_group, equipment, is_bodyweight)
           VALUES (lower(trim(?)), trim(?), ?, ?, ?)
           ON CONFLICT DO NOTHING""",
        (name, name, muscle_group, equipment, int(bool(is_bodyweight))),
    )
    row = conn.execute(
        "SELECT * FROM strength_exercises WHERE exercise_id = ?",
        (name.strip().lower(),),
    ).fetchone()
    return row["exercise_id"] if row else None


def start_session(conn, start_utc, start_local=None,
                  timezone_source=terms.TZ_UNKNOWN, notes=None,
                  value_state=terms.MANUAL, confidence=terms.MEDIUM,
                  confirmation=terms.CONFIRMATION_NOT_REQUIRED,
                  source_system=None, source_activity_id=None):
    session_id = "strength:%s" % (source_activity_id or start_utc)
    conn.execute(
        """INSERT INTO strength_sessions
           (session_id, start_utc, start_local, timezone_source, notes, value_state,
            confidence, confirmation, review_state, source_system,
            source_activity_id, created_utc, updated_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(session_id) DO NOTHING""",
        (session_id, start_utc, start_local, timezone_source, notes, value_state,
         confidence, confirmation, terms.CLOSED, source_system,
         source_activity_id, _now(), _now()),
    )
    return session_id


def record_set(conn, session_id, exercise_name, set_number, reps,
               load_kg=None, load_display=None, rir=None, rpe=None,
               is_warmup=False, tempo=None, rest_s=None, distance_m=None,
               duration_s=None, notes=None, value_state=terms.MANUAL,
               confidence=terms.MEDIUM, equipment=None, actor="athlete"):
    """Record one set. Raises ValueError on contradictory input."""
    if reps is not None and reps < 0:
        raise ValueError("reps cannot be negative")
    if load_kg is not None and load_kg < 0:
        raise ValueError("load_kg cannot be negative")
    if is_warmup and reps is None:
        raise ValueError("warmup set needs reps")
    # Bodyweight and loaded are mutually exclusive unless the athlete supplied
    # both text and a number, which happens with plates-added bodyweight work.
    if load_kg is None and not load_display:
        pass  # genuine bodyweight, load stays NULL

    if rest_s is None:
        rest_s = MIN_REST_S
    elif rest_s < MIN_REST_S:
        _flag(conn, session_id,
              "rest below %.1f min (%ds)" % (MIN_REST_S / 60.0, rest_s))

    exercise_id = add_exercise(conn, exercise_name, equipment=equipment,
                               is_bodyweight=load_kg is None and not load_display)
    conn.execute(
        """INSERT INTO strength_session_exercises (session_id, exercise_id, ordinal)
           VALUES (?, ?, COALESCE((SELECT MAX(ordinal) + 1 FROM strength_session_exercises
                                   WHERE session_id = ?), 1))
           ON CONFLICT(session_id, exercise_id) DO NOTHING""",
        (session_id, exercise_id, session_id),
    )
    se = conn.execute(
        "SELECT session_exercise_id FROM strength_session_exercises WHERE session_id = ? AND exercise_id = ?",
        (session_id, exercise_id),
    ).fetchone()

    existing = conn.execute(
        "SELECT * FROM strength_sets WHERE session_exercise_id = ? AND set_number = ?",
        (se["session_exercise_id"], set_number),
    ).fetchone()

    conn.execute(
        """INSERT INTO strength_sets
           (session_exercise_id, set_number, reps, load_kg, load_display, rir, rpe,
            is_warmup, tempo, rest_s, distance_m, duration_s, notes, value_state, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(session_exercise_id, set_number) DO UPDATE SET
               reps=excluded.reps, load_kg=excluded.load_kg,
               load_display=excluded.load_display, rir=excluded.rir, rpe=excluded.rpe,
               is_warmup=excluded.is_warmup, tempo=excluded.tempo, rest_s=excluded.rest_s,
               distance_m=excluded.distance_m, duration_s=excluded.duration_s,
               notes=excluded.notes, value_state=excluded.value_state,
               confidence=excluded.confidence""",
        (se["session_exercise_id"], set_number, reps, load_kg, load_display, rir,
         rpe, int(bool(is_warmup)), tempo, rest_s, distance_m, duration_s, notes,
         value_state, confidence),
    )
    _audit(conn, session_id, "set_recorded", actor, field="%s#%d" % (exercise_name, set_number),
           old_value=None if existing is None else existing["reps"],
           new_value=reps, reason="value_state=%s" % value_state)
    return se["session_exercise_id"]


def _flag(conn, session_id, detail):
    conn.execute(
        """INSERT INTO review_items (activity_id, reason, state, detail, opened_utc)
           VALUES (?, 'strength_safety', 'open', ?, ?)""",
        (session_id, detail, _now()),
    )


def session_sets(conn, session_id, include_warmups=False):
    return [dict(r) for r in conn.execute(
        """SELECT s.*, e.name AS exercise, e.is_bodyweight, e.muscle_group
           FROM strength_sets s
           JOIN strength_session_exercises se USING (session_exercise_id)
           JOIN strength_exercises e USING (exercise_id)
           JOIN strength_sessions ss USING (session_id)
           WHERE ss.session_id = ?
             AND (? = 1 OR s.is_warmup = 0)
           ORDER BY se.ordinal, s.set_number""",
        (session_id, 1 if include_warmups else 0))]


def session_volume(conn, session_id):
    """Working-set volume in kg-reps. Warmups excluded.

    Returns a breakdown rather than one number, because a single total hides
    whether the work was legs or arms.
    """
    totals = {}
    for row in session_sets(conn, session_id):
        if row["is_warmup"] or not row["reps"]:
            continue
        name = row["exercise"]
        load = row["load_kg"] or 0.0
        totals[name] = totals.get(name, 0.0) + load * row["reps"]
    return {
        "by_exercise": {k: round(v, 1) for k, v in sorted(totals.items())},
        "total_kg_reps": round(sum(totals.values()), 1),
    }


def suggest_progression(conn, exercise_name, equipment=None, athlete_kg=None):
    """Conservative next-load suggestion for one exercise.

    Holds unless the last session's working sets were all completed with
    RPE at or under the ceiling and RIR above the floor. Returns a decision
    with its reasoning rather than a bare number.
    """
    row = conn.execute(
        """SELECT ss.session_id, ss.start_utc
           FROM strength_sessions ss
           JOIN strength_session_exercises se USING (session_id)
           JOIN strength_exercises e USING (exercise_id)
           WHERE e.name = ? AND (? IS NULL OR e.equipment IS ?)
           ORDER BY ss.start_utc DESC LIMIT 1""",
        (exercise_name, equipment, equipment),
    ).fetchone()
    if row is None:
        return {"decision": "no_history", "load_kg": None,
                "reason": "no recorded sets for %s" % exercise_name,
                "confidence": terms.UNVERIFIED}

    sets = [s for s in session_sets(conn, row["session_id"]) if not s["is_warmup"]]
    if not sets:
        return {"decision": "no_history", "load_kg": None,
                "reason": "last session had only warmup sets",
                "confidence": terms.UNVERIFIED}

    bodyweight = all(s["load_kg"] is None for s in sets)
    reps = [s["reps"] for s in sets if s["reps"]]
    rpes = [s["rpe"] for s in sets if s["rpe"] is not None]
    rirs = [s["rir"] for s in sets if s["rir"] is not None]

    target = max(reps) if reps else None
    short = [s for s in sets if target and s["reps"] and s["reps"] < target]
    hard = [s for s in sets if s["rpe"] is not None and s["rpe"] > RPE_CEILING]
    close = [s for s in sets if s["rir"] is not None and s["rir"] < RIR_FLOOR]

    if short:
        return {"decision": "hold", "load_kg": sets[-1]["load_kg"],
                "reason": "%d of %d sets fell short of %d reps" % (
                    len(short), len(sets), target),
                "confidence": terms.MEDIUM}
    if hard:
        return {"decision": "hold", "load_kg": sets[-1]["load_kg"],
                "reason": "RPE %s exceeds the %.0f ceiling" % (
                    max(rpes), RPE_CEILING),
                "confidence": terms.MEDIUM}
    if close:
        return {"decision": "hold", "load_kg": sets[-1]["load_kg"],
                "reason": "RIR %s is below %d" % (min(rirs), RIR_FLOOR),
                "confidence": terms.MEDIUM}

    if bodyweight:
        return {"decision": "add_reps", "load_kg": None, "add_reps": 1,
                "reason": "bodyweight: all working sets completed cleanly",
                "confidence": terms.MEDIUM}

    last = sets[-1]["load_kg"]
    step = LOAD_INCREMENT_KG
    if athlete_kg and last / athlete_kg < 0.5:
        step = 0.5                      # lighter lift, smaller jump
    proposed = last + step
    if last and (proposed - last) / last * 100.0 > MAX_PROGRESSION_PCT:
        proposed = last
    return {
        "decision": "increase",
        "load_kg": round(proposed, 2),
        "increment_kg": round(proposed - last, 2),
        "reason": "all %d working sets completed, RPE within ceiling" % len(sets),
        "confidence": terms.MEDIUM,
        "disclaimer": terms.NON_MEDICAL,
    }


def safety_flags(conn, session_id):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM review_items WHERE activity_id = ? AND state = 'open'",
        (session_id,))]
