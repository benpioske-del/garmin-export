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

import terms
from loadcalc import acwr, compute

# Minimum sessions before a window supports a control state at all.
MIN_RUNS_7D = 3
MIN_RUNS_28D = 8
MIN_STRENGTH_28D = 2

# Acute:chronic bounds for training control. These are conventional operating
# bounds, quoted to keep the decision auditable, not thresholds for anything
# clinical. There is no lower bound that authorises "more": being undertrained
# is not a reason to add volume, so the floor only ever allows a build when the
# 28-day history is itself established.
HIGH_ACWR = 1.5
LOW_ACWR = 0.8
CAUTION_ACWR = 1.3


def recommend(conn, as_of=None, hr_max=None):
    """Return a control state with evidence. Never raises for missing data."""
    result = compute(conn, as_of=as_of, hr_max=hr_max)
    w7 = result["windows"]["7"]
    w28 = result["windows"]["28"]

    evidence = {
        "runs_7d": len(w7["run_days"]),
        "runs_28d": len(w28["run_days"]),
        "strength_28d": len(w28["strength_days"]),
        "run_load_28d": w28["run_load"],
        "strength_load_28d": w28["strength_load"],
        "run_unavailable": w28["unavailable"]["run"],
        "strength_unavailable": w28["unavailable"]["strength"],
    }

    # Unconfirmed records near the window make every number derived from them
    # provisional, so they outrank the load figures. SQLite does the date
    # arithmetic so the caller does not have to trust a hand-rolled offset.
    pending = conn.execute(
        "SELECT COUNT(*) c FROM activities WHERE review_state = 'open' "
        "AND substr(start_utc, 1, 10) >= date(?, '-28 days')",
        (result["as_of_utc"][:10],),
    ).fetchone()["c"]
    if pending:
        return _result(
            terms.STATE_CONFIRMATION_REQUIRED, evidence,
            ["%d recent activities are awaiting confirmation" % pending],
            "Resolve the open review items before acting on this state.")

    if evidence["runs_28d"] < MIN_RUNS_28D:
        return _result(
            terms.STATE_DATA_INSUFFICIENT, evidence,
            ["only %d runs in 28 days, need %d" % (evidence["runs_28d"], MIN_RUNS_28D)],
            "Not enough recorded history to judge load.")

    if w28["run_load"] is None:
        return _result(
            terms.STATE_DATA_INSUFFICIENT, evidence,
            ["running load unavailable: %s" % (
                w28["unavailable"]["run"][:3] or "no data")],
            "Running load needs average heart rate and a max estimate.")

    if evidence["runs_7d"] < MIN_RUNS_7D:
        return _result(
            terms.STATE_DATA_INSUFFICIENT, evidence,
            ["only %d runs in 7 days, need %d" % (evidence["runs_7d"], MIN_RUNS_7D)],
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
