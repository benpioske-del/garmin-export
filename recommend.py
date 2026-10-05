"""Training-control states: build, maintain, recover, deload, or say nothing.

Every recommendation returns a state, the evidence behind it, and its
limitations. There is no free-text advice path, so the output cannot drift into
"you should probably push through this".

Refusal is a first-class outcome. If the window has too few sessions, if the
inputs needed for load were unavailable, or if the record is still waiting on an
athlete confirmation, the state is data_insufficient or confirmation_required
and no control state is offered. An aggressive recommendation reached through a
rule that silently defaulted an input to zero is exactly the failure this
structure exists to prevent.

This is a training-control signal. It is not an injury prediction, not a
diagnosis, and not medical advice.
"""

import datetime

import terms
from loadcalc import acwr, compute

# Minimum *training days* before a window supports a control state at all.
# Counted as distinct calendar days with a run, not sessions: three sessions can
# land on three consecutive days and still be a compressed week, whereas three
# spread days are the readiness signal these gates are meant to express.
MIN_RUN_DAYS_7D = 3
MIN_RUN_DAYS_28D = 8
MIN_STRENGTH_28D = 2

# A training gap this long makes "recover" the honest state: the athlete is
# returning, not progressing. Below it, an absent acute window is just a thin one.
RECOVER_GAP_DAYS = 7

# Acute:chronic bounds for training control. These are conventional operating
# bounds for the canonical rate-based ratio, quoted to keep the decision
# auditable, not thresholds for anything clinical. There is no lower bound that
# authorises "more": being undertrained is not a reason to add volume, so the
# floor only ever allows a build when the 28-day history is itself established.
HIGH_ACWR = 1.5
LOW_ACWR = 0.8
CAUTION_ACWR = 1.3


def recommend(conn, as_of=None, hr_max=None):
    """Return a control state with evidence. Never raises for missing data."""
    result = compute(conn, as_of=as_of, hr_max=hr_max)
    w7 = result["windows"]["7"]
    w28 = result["windows"]["28"]

    # compute() passes as_of through untouched, so this is whatever the caller
    # supplied: a string, a date, or a datetime. Normalise it once here instead
    # of trusting each caller to pass the string form the SQL below assumes.
    as_of_day = _as_of_day(result.get("as_of_utc"))

    evidence = {
        "run_days_7d": len(w7["run_days"]),
        "run_days_28d": len(w28["run_days"]),
        "strength_days_28d": len(w28["strength_days"]),
        "run_load_28d": w28["run_load"],
        "strength_load_28d": w28["strength_load"],
        "run_unavailable": w28["unavailable"]["run"],
        "strength_unavailable": w28["unavailable"]["strength"],
    }

    # Days since the last confirmed run. SQLite does the date arithmetic so the
    # caller does not have to trust a hand-rolled offset.
    last_run = conn.execute(
        "SELECT MAX(substr(start_utc, 1, 10)) d FROM activities "
        "WHERE substr(start_utc, 1, 10) >= date(?, '-28 days')",
        (as_of_day,),
    ).fetchone()["d"]
    evidence["days_since_last_run"] = (
        None if not last_run
        else (_days_between(last_run, as_of_day))
    )

    # Unconfirmed records near the window make every number derived from them
    # provisional, so they outrank the load figures. SQLite does the date
    # arithmetic so the caller does not have to trust a hand-rolled offset.
    pending = conn.execute(
        "SELECT COUNT(*) c FROM activities WHERE review_state = 'open' "
        "AND substr(start_utc, 1, 10) >= date(?, '-28 days')",
        (as_of_day,),
    ).fetchone()["c"]
    if pending:
        return _result(
            terms.STATE_CONFIRMATION_REQUIRED, evidence,
            ["%d recent activities are awaiting confirmation" % pending],
            "Resolve the open review items before acting on this state.")

    # The unavailable-input diagnosis must come before the window-size
    # diagnosis. A missing heart-rate input produces no run_days either, so
    # checking the count first reported "0 runs in 28 days" and never named the
    # input the athlete actually needs to supply. The count is a symptom; the
    # missing input is the cause.
    if w28["run_load"] is None:
        return _result(
            terms.STATE_DATA_INSUFFICIENT, evidence,
            ["running load unavailable: %s" % (
                w28["unavailable"]["run"][:3] or "no data")],
            "Running load needs average heart rate and a max estimate.")

    if evidence["run_days_28d"] < MIN_RUN_DAYS_28D:
        return _result(
            terms.STATE_DATA_INSUFFICIENT, evidence,
            ["only %d training days with runs in 28 days, need %d" % (
                evidence["run_days_28d"], MIN_RUN_DAYS_28D)],
            "Not enough recorded history to judge load.")

    # A long gap is a state in its own right. Without this, an athlete three
    # weeks into a break has an empty acute window and falls through to the
    # thin-window refusal, which describes the arithmetic instead of the
    # situation. "recover" was previously advertised but unreachable.
    gap = evidence["days_since_last_run"]
    if gap is not None and gap >= RECOVER_GAP_DAYS:
        return _result(
            terms.STATE_RECOVER, evidence,
            ["%d days since the last run, at or above the %d-day gap bound" % (
                gap, RECOVER_GAP_DAYS)],
            "Return gradually over one to two weeks; do not resume at "
            "pre-break volume.")

    if evidence["run_days_7d"] < MIN_RUN_DAYS_7D:
        return _result(
            terms.STATE_DATA_INSUFFICIENT, evidence,
            ["only %d training days with runs in 7 days, need %d" % (
                evidence["run_days_7d"], MIN_RUN_DAYS_7D)],
            "The acute window is too thin to compare against the chronic one.")

    ratio = acwr(w7["combined_load"], w28["combined_load"])
    evidence["acwr"] = ratio
    if ratio is None:
        return _result(
            terms.STATE_DATA_INSUFFICIENT, evidence, ["acute:chronic unavailable"],
            "Chronic load is zero or missing.")

    if ratio >= HIGH_ACWR:
        return _result(
            terms.STATE_DELOAD, evidence,
            ["acute:chronic %.2f is at or above %.1f" % (ratio, HIGH_ACWR)],
            "Reduce volume; do not add intensity to compensate.")
    if ratio >= CAUTION_ACWR:
        return _result(
            terms.STATE_MAINTAIN, evidence,
            ["acute:chronic %.2f is in the %.1f-%.1f caution band" % (
                ratio, CAUTION_ACWR, HIGH_ACWR)],
            "Hold current volume and do not add load this week.")
    if ratio < LOW_ACWR:
        return _result(
            terms.STATE_MAINTAIN, evidence,
            ["acute:chronic %.2f is below %.1f" % (ratio, LOW_ACWR)],
            "A low ratio is not on its own a reason to add volume.")
    return _result(
        terms.STATE_BUILD, evidence,
        ["acute:chronic %.2f sits between %.1f and %.1f" % (
            ratio, LOW_ACWR, CAUTION_ACWR)],
        "Progression is optional; a repeat week is equally valid.")


def _as_of_day(value):
    """The YYYY-MM-DD string the SQL date arithmetic expects."""
    if value is None:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    if isinstance(value, str):
        return value[:10]
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, datetime.date):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def _days_between(earlier_iso, later_iso):
    """Whole days from one YYYY-MM-DD string to another. None if unparseable."""
    try:
        a = datetime.date.fromisoformat(earlier_iso)
        b = datetime.date.fromisoformat(later_iso)
    except (TypeError, ValueError):
        return None
    return (b - a).days


def _result(state, evidence, reasons, limitation):
    out = {
        "state": state,
        "evidence": evidence,
        "reasons": reasons,
        "limitation": limitation,
    }
    if state in terms.NON_ADVISORY_STATES:
        out["advisory"] = False
    else:
        out["advisory"] = True
    out["disclaimers"] = [terms.NOT_INJURY_PREDICTION, terms.NON_MEDICAL, terms.ESCALATION]
    return out


def available_states():
    return list(terms.CONTROL_STATES)
