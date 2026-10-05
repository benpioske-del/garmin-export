"""Deterministic scenario fixtures for coaching rationales.

The point of this module is that a coaching rationale should be reviewable as a
concrete artefact rather than trusted as a string a function happens to build.
Every scenario here pins a known database shape to a known control state, so a
change in loadcalc or recommend shows up as a diff against a recorded answer
that a human agreed to.

Determinism
-----------
Two things would otherwise make these unstable. Both are pinned:

* the clock. `recommend()` accepts `as_of`, and every scenario uses
  `FIXED_AS_OF`. Without it the 7-day window slides and a rationale recorded in
  October fails in November for no reason connected to the code.
* `hr_max`. Taken from the profile rather than inferred, so the intensity
  multiplier is pinned rather than dependent on the athlete's data.

Isolation
---------
Every scenario builds its database at an explicit path via
`trainingdb.connect(path=...)` and migrates it. The environment variable is
never touched. An earlier draft of this harness guessed the variable name
(`GARMIN_DB` instead of `TRAINLOOP_DB`), silently wrote to the athlete's live
database, and inserted ten junk activities before the mistake was caught. Using
the explicit path makes that failure mode impossible rather than merely
unlikely.

Coverage
--------
The scenarios are chosen to cover the distinctions the system claims to make,
not merely to produce green tests: a refusal, an unavailable input, a missing
input, a value that is null rather than zero, and the advisory states. Two
states in `terms.CONTROL_STATES` turn out to be unreachable from any input --
see `test_recommend_snapshots.py::TestStateReachability`, which fails if that
ever changes in either direction.
"""

import datetime
import os
import tempfile

import recommend
import terms
import trainingdb

# 2026-10-04T12:00:00Z. Midday UTC, away from a window boundary, so a change in
# window arithmetic cannot be masked by a boundary case.
FIXED_AS_OF = "2026-10-04T12:00:00Z"

# hr_max as recorded in profile.json. Not inferred from age: the athlete's
# observed peaks contradict the age formulas, and the profile documents that.
HR_MAX = 198

_RUN_COLUMNS = (
    "activity_id", "source_system", "sport", "title", "start_utc",
    "start_local", "timezone_source", "distance_mi", "moving_time_s",
    "avg_hr", "value_state", "confidence", "confirmation", "review_state",
    "first_seen_utc", "last_updated_utc",
)


class Scenario(object):
    """One pinned database shape and the state it must produce."""

    def __init__(self, name, expected_state, days_ago=(), covers=(),
                 hr_max=HR_MAX, avg_hr=150, moving_time_s=3600,
                 review_state="resolved", minutes_per_run=60,
                 extra_runs=(), description="", expect_advisory=None):
        self.name = name
        self.expected_state = expected_state
        self.days_ago = tuple(days_ago)
        self.covers = tuple(covers)
        self.hr_max = hr_max
        self.avg_hr = avg_hr
        self.moving_time_s = moving_time_s
        self.review_state = review_state
        self.minutes_per_run = minutes_per_run
        self.extra_runs = tuple(extra_runs)
        self.description = description
        self.expect_advisory = expect_advisory

    def build(self, path):
        """Create and migrate a database at `path`, then populate it."""
        conn = trainingdb.connect(path=path)
        trainingdb.migrate(conn, verbose=False)
        end = datetime.datetime.fromisoformat(FIXED_AS_OF.replace("Z", "+00:00"))

        rows = [(d, self.avg_hr, self.moving_time_s, self.review_state)
                for d in self.days_ago]
        rows.extend(self.extra_runs)

        for i, (ago, avg_hr, moving, review) in enumerate(rows):
            t = end - datetime.timedelta(days=ago)
            z = t.strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "INSERT INTO activities (%s) VALUES (%s)"
                % (", ".join(_RUN_COLUMNS), ", ".join("?" * len(_RUN_COLUMNS))),
                ("run-%03d" % i, "fixture", "running", "Fixture run", z, z,
                 "device_local", 6.0, moving, avg_hr, "present", "medium",
                 "confirmed", review, z, z),
            )
        conn.commit()
        return conn

    def recommend(self, conn):
        return recommend.recommend(conn, as_of=FIXED_AS_OF, hr_max=self.hr_max)


def _scenario_db(scenario, tmpdir):
    path = os.path.join(tmpdir, scenario.name + ".db")
    return scenario.build(path)


# Layouts, chosen to walk the decision tree rather than to produce tidy numbers.
# `days_ago` counts back from FIXED_AS_OF.
RECENT = (1, 2, 3, 4)
OLDER = (10, 13, 16, 19, 22, 25)
BOTH = RECENT + OLDER

SCENARIOS = (
    Scenario(
        "empty-database",
        terms.STATE_DATA_INSUFFICIENT,
        covers=("missing", "refused"),
        description="No activities at all. Every count is zero and the answer "
                    "must still be an explicit refusal, not an empty success.",
    ),
    Scenario(
        "confirmation-required",
        terms.STATE_CONFIRMATION_REQUIRED,
        days_ago=BOTH,
        review_state="open",
        covers=("refused", "provisional"),
        description="Enough history to advise, but records await confirmation. "
                    "Unconfirmed data outranks the load figures by policy.",
    ),
    Scenario(
        "insufficient-chronic-history",
        terms.STATE_DATA_INSUFFICIENT,
        days_ago=(1, 5, 9, 13, 17, 21),
        covers=("missing", "refused"),
        description="Six runs in 28 days against a floor of eight. The chronic "
                    "window is not established, so no build is authorised.",
    ),
    Scenario(
        "insufficient-acute-history",
        terms.STATE_DATA_INSUFFICIENT,
        days_ago=(1, 2, 10, 13, 16, 19, 22, 25),
        covers=("missing", "refused"),
        description="Eight runs in 28 days but only two in the acute window. "
                    "The ratio would be computed from a two-session numerator.",
    ),
    Scenario(
        "run-load-unavailable-no-hr-max",
        terms.STATE_DATA_INSUFFICIENT,
        days_ago=BOTH,
        hr_max=None,
        covers=("unavailable", "refused"),
        description="History is sufficient but no max heart rate is supplied. "
                    "Running load is unavailable rather than zero. KNOWN "
                    "DEFECT: the refusal currently reports 'only 0 runs in 28 "
                    "days', because runs with no computable load are dropped "
                    "before they are counted as days. The true cause is the "
                    "missing hr_max and the rationale does not say so.",
    ),
    Scenario(
        "run-load-unavailable-no-avg-hr",
        terms.STATE_DATA_INSUFFICIENT,
        days_ago=BOTH,
        avg_hr=None,
        covers=("unavailable", "refused"),
        description="Runs recorded without average heart rate. Same KNOWN "
                    "DEFECT as above: the missing input is not named.",
    ),
    Scenario(
        "zero-chronic-load-is-not-a-ratio",
        terms.STATE_DATA_INSUFFICIENT,
        days_ago=RECENT,
        covers=("null-not-zero", "refused"),
        description="Only four counted days, so the chronic floor rejects the "
                    "window before a ratio is ever considered. Retained to pin "
                    "the null-not-zero distinction: with no established chronic "
                    "window the ratio stays null rather than defaulting to 1.0.",
    ),
    Scenario(
        "build-band",
        terms.STATE_BUILD,
        days_ago=(1, 2, 3, 8, 10, 12, 14, 16, 18, 20, 22),
        covers=("available",),
        description="Three acute days against a chronic block of eight on a "
                    "two-day stride. Three of eleven training days lands the "
                    "ratio at 1.09, inside the build band. Note the gates count "
                    "distinct DAYS, not sessions, so two runs on one day collapse "
                    "to one entry.",
    ),
    Scenario(
        "caution-band-spike",
        terms.STATE_MAINTAIN,
        days_ago=(1, 2, 3, 4, 8, 10, 12, 14, 16, 18, 20, 22),
        covers=("available",),
        description="One more acute day puts the ratio at 1.33, inside the "
                    "1.30-1.50 caution band. Holds current volume and adds "
                    "nothing. This band was unreachable while the ratio compared "
                    "two window sums.",
    ),
    Scenario(
        "deload-band-concentration",
        terms.STATE_DELOAD,
        days_ago=(1, 2, 3, 4, 5, 8, 10, 12, 14, 16, 18, 20, 22),
        covers=("available",),
        description="Five acute days against the same chronic block puts the "
                    "ratio at 1.54, at or above the high bound, so the state is "
                    "deload. The old sum-based ratio read this shape as 0.65 and "
                    "called it 'build'; recommending progression during a spike "
                    "is the defect this scenario pins.",
    ),
    Scenario(
        "recover-after-gap",
        terms.STATE_RECOVER,
        days_ago=(8, 10, 12, 14, 16, 18, 20, 22),
        covers=("available",),
        description="Eight chronic days and nothing in the acute window, so the "
                    "last run was eight days ago. Without the gap branch this "
                    "fell through to the thin-window refusal, which reported the "
                    "arithmetic instead of the situation. recover was advertised "
                    "by available_states() with no branch that could return it.",
    ),
    Scenario(
        "maintain-low-ratio",
        terms.STATE_MAINTAIN,
        days_ago=(1, 2, 3, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
                  22, 23, 24, 25, 26, 27),
        covers=("available",),
        description="Three acute days against eighteen chronic days, ratio 0.57. "
                    "A low ratio is not on its own a reason to add volume, so "
                    "this maintains.",
    ),
)

SCENARIOS_BY_NAME = {s.name: s for s in SCENARIOS}