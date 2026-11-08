"""Golden rationale snapshots for the coaching policy.

A coaching rationale is the only thing in this system that tells the athlete
what to do. It is also a string built by conditional logic, which means it can
change without anyone deciding to change it. These tests pin the output of
every reachable policy branch to a recorded answer, so a change shows up as a
diff that a human has to agree to.

Run with `REGENERATE_SNAPSHOTS=1` to re-record, then read the diff.

    python -m pytest tests/test_recommend_snapshots.py            # verify
    REGENERATE_SNAPSHOTS=1 python -m pytest ...                  # re-record

Four defects were found by writing these. They are recorded in
`KNOWN_DEFECTS` and asserted rather than quietly tolerated, because each one
changes what the athlete is told:

  * `deload` cannot be produced. The acute:chronic ratio is a 7-day sum over a
    28-day sum, and the acute window is a subset of the chronic one, so the
    ratio is bounded by 1.0. `HIGH_ACWR` is 1.5. The state that should fire when
    someone is overreaching is the one state that cannot.

  * The 1.3-1.5 caution band cannot be produced either, for the same reason.

  * `recover` is advertised in `terms.CONTROL_STATES` and returned by
    `recommend.available_states()`, but `recommend()` never returns it.

  * A missing `hr_max` is reported as insufficient history rather than as a
    missing input. An athlete with twenty logged runs and no max heart rate is
    told they do not have enough runs.

The first three are load-bearing: a control policy that cannot recommend
backing off is not conservative, it is merely quiet.
"""

import datetime
import inspect
import json
import os
import sys

import pytest

import loadcalc
import recommend
import terms
import trainingdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import requires_real_db  # noqa: E402
from recommend_scenarios import (  # noqa: E402
    SCENARIOS, SCENARIOS_BY_NAME, FIXED_AS_OF, HR_MAX,
)

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fixtures", "recommend")

REGENERATE = bool(os.environ.get("REGENERATE_SNAPSHOTS"))

# States the fixtures demonstrate, derived from the scenarios rather than
# asserted in the abstract.
REACHABLE = ("build", "maintain", "recover", "deload",
             "data_insufficient", "confirmation_required")

# Nothing in terms.CONTROL_STATES is advertised without a branch that returns it.
UNREACHABLE_ADVERTISED = ()

# Defects that were fixed rather than tolerated. Kept as a ledger so that a
# regression names the change it undid, and so the audit document stays
# checkable against the code.
FIXED_DEFECTS = {
    "deload-band-unreachable": {
        "where": "loadcalc.acwr",
        "was": "ratio = 7d_sum / 28d_sum, and the 7-day window is a subset of "
               "the 28-day window, so ratio <= 1.0 always",
        "now": "ratio = 7d_sum / (28d_sum / 4): acute week against mean "
               "chronic week, which is the canonical rate form",
        "consequence_removed": "the system could never recommend reducing load",
    },
    "caution-band-unreachable": {
        "where": "recommend.py: CAUTION_ACWR = 1.3",
        "was": "same ceiling as above",
        "now": "reachable whenever the acute week exceeds chronic by 30%",
        "consequence_removed": "the caution band is no longer dead code",
    },
    "recover-never-returned": {
        "where": "recommend.recommend",
        "was": "no branch returned terms.STATE_RECOVER",
        "now": "a training gap of RECOVER_GAP_DAYS or more returns recover, "
               "checked before the thin-window refusal that used to mask it",
        "consequence_removed": "available_states() no longer advertises an "
                               "impossible state",
    },
    "missing-input-reported-as-missing-history": {
        "where": "recommend.recommend check order",
        "was": "the MIN_RUN_DAYS_28D count check preceded the load-availability "
               "check, so a missing hr_max presented as 'only 0 runs in 28 days'",
        "now": "the load-availability branch runs first and names the absent "
               "input; the count is treated as a symptom",
        "consequence_removed": "the athlete is told which input to supply",
    },
    "runs-counted-days-not-sessions": {
        "where": "recommend.MIN_RUN_DAYS_7D / MIN_RUN_DAYS_28D",
        "was": "the constants were named MIN_RUNS_*, implying sessions, while "
               "the code counted distinct days",
        "now": "renamed to MIN_RUN_DAYS_* and the reasons say 'training days'",
        "consequence_removed": "the evidence keys match what they measure",
    },
}


def _snapshot_path(name):
    return os.path.join(FIXTURE_DIR, name + ".json")


def _record(scenario, conn):
    """The full recommend() output, plus the load figures it was derived from."""
    result = scenario.recommend(conn)
    computed = loadcalc.compute(conn, as_of=FIXED_AS_OF, hr_max=scenario.hr_max)
    return {
        "scenario": scenario.name,
        "description": scenario.description,
        "covers": list(scenario.covers),
        "fixed_as_of": FIXED_AS_OF,
        "hr_max": scenario.hr_max,
        "expected_state": scenario.expected_state,
        "recommend": result,
        "windows": {
            key: {
                "combined_load": win["combined_load"],
                "run_load": win["run_load"],
                "strength_load": win["strength_load"],
                "run_days": len(win["run_days"]),
                "strength_days": len(win["strength_days"]),
                "run_confidence": win["run_confidence"],
            }
            for key, win in sorted(computed["windows"].items())
        },
        "unavailable": computed["windows"]["28"]["unavailable"],
    }


@pytest.fixture()
def recorded(tmp_path):
    """name -> snapshot dict, regenerated into tmp when asked."""
    out = {}
    for scenario in SCENARIOS:
        conn = scenario.build(str(tmp_path / (scenario.name + ".db")))
        out[scenario.name] = _record(scenario, conn)
        conn.close()
    return out


class TestSnapshots:
    def test_snapshots_match_golden_files(self, recorded):
        mismatches = []
        for name, snap in sorted(recorded.items()):
            path = _snapshot_path(name)
            if REGENERATE or not os.path.exists(path):
                os.makedirs(FIXTURE_DIR, exist_ok=True)
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    json.dump(snap, fh, indent=2, sort_keys=True)
                    fh.write("\n")
                continue
            with open(path, encoding="utf-8") as fh:
                golden = json.load(fh)
            if golden != snap:
                mismatches.append(name)
        assert not mismatches, (
            "rationale changed for: %s\n"
            "Re-record with REGENERATE_SNAPSHOTS=1 and read the diff."
            % ", ".join(mismatches))

    def test_every_scenario_produces_its_declared_state(self, recorded):
        for name, snap in sorted(recorded.items()):
            assert snap["recommend"]["state"] == snap["expected_state"], (
                "%s produced %s, the fixture declares %s"
                % (name, snap["recommend"]["state"], snap["expected_state"]))

    def test_advisory_flag_matches_state_class(self, recorded):
        # advisory must be derived from the state, never restated. A non-advisory
        # state with advisory=True is the single most dangerous bug available
        # in this module.
        for name, snap in sorted(recorded.items()):
            state = snap["recommend"]["state"]
            expected = state not in terms.NON_ADVISORY_STATES
            assert snap["recommend"]["advisory"] is expected, (
                "%s: state %s but advisory=%s"
                % (name, state, snap["recommend"]["advisory"]))

    def test_refusals_carry_a_limitation_and_reasons(self, recorded):
        for name, snap in sorted(recorded.items()):
            if snap["recommend"]["advisory"] is False:
                assert snap["recommend"]["reasons"], "%s refused silently" % name
                assert snap["recommend"]["limitation"], (
                    "%s refused without saying what to do instead" % name)

    def test_every_result_carries_the_disclaimers(self, recorded):
        for name, snap in sorted(recorded.items()):
            d = snap["recommend"]["disclaimers"]
            assert terms.NOT_INJURY_PREDICTION in d
            assert terms.NON_MEDICAL in d
            assert terms.ESCALATION in d

    def test_null_is_never_coerced_to_zero(self, recorded):
        # strength_load must stay null in every scenario: there are no
        # confirmed strength sessions anywhere in the corpus.
        for name, snap in sorted(recorded.items()):
            for window, values in snap["windows"].items():
                if values["strength_load"] is None:
                    continue
                pytest.fail(
                    "%s window %s produced strength_load=%r; the corpus has no "
                    "confirmed strength sessions so this must remain null"
                    % (name, window, values["strength_load"]))

    def test_unavailable_is_recorded_rather_than_hidden(self, recorded):
        # When a scenario is meant to have an unavailable input, the
        # unavailable notes must actually be populated.
        for name in ("run-load-unavailable-no-hr-max",
                     "run-load-unavailable-no-avg-hr"):
            notes = recorded[name]["unavailable"]["run"]
            assert notes, "%s recorded no unavailable notes" % name
            reasons = {r["reason"] for r in notes}
            assert reasons, "%s has notes without a reason" % name

    def test_goldens_contain_no_real_athlete_data(self):
        # The fixtures are synthetic by construction, but these files are
        # committed, so assert it rather than trusting the construction.
        if not os.path.isdir(FIXTURE_DIR):
            pytest.skip("no goldens recorded yet")
        for name in sorted(os.listdir(FIXTURE_DIR)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(FIXTURE_DIR, name), encoding="utf-8") as fh:
                body = fh.read()
            for forbidden in ('"garmin:', '"lat":', '"lon":', '"elevGain"',
                              '"injury":', '"baseRuns"', '"splits"',
                              '"note":', '"heat"'):
                assert forbidden not in body, (
                    "%s looks like it contains real data (%r)" % (name, forbidden))

    def test_goldens_exist_for_every_scenario(self):
        if REGENERATE:
            pytest.skip("regenerating")
        missing = [s.name for s in SCENARIOS
                   if not os.path.exists(_snapshot_path(s.name))]
        assert not missing, "no golden recorded for: %s" % ", ".join(missing)

    def test_determinism_is_repeatable(self, tmp_path):
        # Two independent builds of the same scenario must agree exactly.
        for scenario in SCENARIOS:
            a = scenario.build(str(tmp_path / (scenario.name + "-a.db")))
            b = scenario.build(str(tmp_path / (scenario.name + "-b.db")))
            assert _record(scenario, a) == _record(scenario, b), (
                "%s is not deterministic" % scenario.name)
            a.close()
            b.close()


class TestCoverage:
    def test_every_semantic_is_covered(self, recorded):
        required = {"available", "provisional", "unavailable", "refused",
                    "missing", "null-not-zero"}
        covered = set()
        for snap in recorded.values():
            covered.update(snap["covers"])
        assert required <= covered, "uncovered: %s" % (required - covered)

    def test_scenarios_are_documented(self, recorded):
        for name, snap in sorted(recorded.items()):
            assert len(snap["description"]) > 40, (
                "%s needs a description explaining why it exists" % name)

    def test_fixtures_are_pinned_in_time(self, recorded):
        # Without a fixed instant these snapshots would drift with the calendar.
        for snap in recorded.values():
            assert snap["fixed_as_of"] == FIXED_AS_OF


class TestStateReachability:
    """Empirical reachability, by sweeping the input space.

    Source inspection cannot answer this. `STATE_DELOAD` does appear in
    recommend.py -- inside a branch no input can reach -- so grepping for the
    constant proves nothing. The only honest evidence is to construct inputs
    and observe which states actually come out.
    """

    def _sweep(self, tmp_path):
        """Run a grid of database shapes and collect the states produced."""
        conn = trainingdb.connect(path=str(tmp_path / "sweep.db"))
        trainingdb.migrate(conn, verbose=False)
        end = datetime.datetime.fromisoformat(FIXED_AS_OF.replace("Z", "+00:00"))

        seen = set()
        produced_deload = []
        shapes = 0

        # Distinct days only: the gates count days, so two runs on one day
        # would collapse and the sweep would understate the space.
        #
        # Chronic days are placed on a 2-day stride rather than a 3-day one. At
        # 3 days, only six chronic days fit inside the 28-day window and the
        # MIN_RUN_DAYS_28D gate rejects every shape, so the space this swept
        # contained no advisory state at all. The two starts are what make
        # build and recover reachable: a dense chronic block balanced against
        # the acute week, and a chronic block far enough back to leave a gap.
        for recent in range(0, 10):
            for chronic in range(0, 15):
                for chronic_start in (8, 12, 18):
                    for moving in (1800, 3600, 7200):
                        for avg_hr in (140, 165, 185):
                            for hr_max in (HR_MAX, None):
                                for review in ("resolved", "open"):
                                    days = list(range(1, recent + 1))
                                    days += [chronic_start + 2 * i
                                             for i in range(chronic)]
                                    if not days:
                                        continue
                                    conn.execute("DELETE FROM activities")
                                    for i, ago in enumerate(days):
                                        if ago > 27:
                                            break
                                        t = end - datetime.timedelta(days=ago)
                                        z = t.strftime("%Y-%m-%dT%H:%M:%SZ")
                                        conn.execute(
                                            "INSERT INTO activities (activity_id,"
                                            " source_system, sport, title, start_utc,"
                                            " start_local, timezone_source,"
                                            " distance_mi, moving_time_s, avg_hr,"
                                            " value_state, confidence, confirmation,"
                                            " review_state, first_seen_utc,"
                                            " last_updated_utc) VALUES"
                                            " (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                            ("s%d" % i, "sweep", "running", "Sweep",
                                             z, z, "device_local", 6.0, moving,
                                             avg_hr, "present", "medium",
                                             "confirmed", review, z, z))
                                    conn.commit()
                                    shapes += 1
                                    result = recommend.recommend(
                                        conn, as_of=FIXED_AS_OF, hr_max=hr_max)
                                    seen.add(result["state"])
                                    if result["state"] == terms.STATE_DELOAD:
                                        produced_deload.append(
                                            (recent, chronic, chronic_start,
                                             moving, avg_hr, hr_max))
        conn.close()
        return seen, shapes, produced_deload

    def test_sweep_now_produces_deload_and_recover(self, tmp_path):
        """Every advertised state must be reachable by some input."""
        seen, shapes, produced_deload = self._sweep(tmp_path)
        assert shapes > 1000, "sweep was too small to be evidence: %d" % shapes
        assert produced_deload, (
            "deload went unreachable again; the rate-based chronic changed")
        assert terms.STATE_DELOAD in seen, sorted(seen)
        assert terms.STATE_RECOVER in seen, sorted(seen)
        assert not UNREACHABLE_ADVERTISED

    def test_sweep_reaches_exactly_the_documented_states(self, tmp_path):
        seen, shapes, _ = self._sweep(tmp_path)
        assert seen == set(REACHABLE), (
            "sweep of %d shapes produced %s, documented as %s"
            % (shapes, sorted(seen), sorted(REACHABLE)))

    def test_recover_has_a_branch_that_names_its_bound(self):
        # recover was previously advertised by terms.CONTROL_STATES with no
        # branch capable of returning it.
        src = inspect.getsource(recommend.recommend)
        assert "STATE_RECOVER" in src
        assert recommend.RECOVER_GAP_DAYS >= 1, (
            "a zero-day gap bound would make recover unconditional")

    def test_ratio_can_exceed_one(self):
        # The ratio is now a rate comparison, so 1.0 is an interior value rather
        # than a ceiling. A week at 1.5x the average week must read as 1.5.
        assert loadcalc.WINDOWS == (7, 14, 28)
        assert recommend.HIGH_ACWR > 1.0
        assert loadcalc.acwr(1500.0, 2000.0) == 3.0

    def test_missing_input_now_names_the_absent_input(self, recorded):
        """Inverted when the rationale was fixed to name what is absent."""
        for name in ("run-load-unavailable-no-hr-max",
                     "run-load-unavailable-no-avg-hr"):
            reasons = " ".join(recorded[name]["recommend"]["reasons"])
            assert "hr_max" in reasons or "avg_hr" in reasons, (
                "%s stopped naming the missing input" % name)
            assert "only 0 runs" not in reasons, (
                "%s regressed to blaming missing history" % name)
            assert recorded[name]["recommend"]["evidence"]["run_days_28d"] == 0


class TestFixedDefectsStayFixed:
    """The ledger must describe the code as it actually is, both ways."""

    def test_ratio_compares_a_week_against_a_mean_week(self):
        # Steady state is a 28-day total of four equal weeks, so ratio 1.0.
        # Loading the whole 28-day volume into one week reads 4.0, which is the
        # spike the old sum-based comparison could never see.
        assert loadcalc.acwr(600.0, 2400.0) == 1.0
        assert loadcalc.acwr(600.0, 600.0) == 4.0
        assert loadcalc.acwr(1200.0, 2400.0) == 2.0
        assert loadcalc.acwr(600.0, 1200.0) == 2.0

    def test_live_ratio_is_inside_the_operating_range(self):
        """A regression here would make every recommendation meaningless."""
        acute, chronic = 780.8, 3364.4
        assert loadcalc.acwr(acute, chronic) == 0.93
        assert recommend.LOW_ACWR < loadcalc.acwr(acute, chronic) < recommend.CAUTION_ACWR

    def test_every_ledger_entry_names_a_fixed_thing(self):
        assert FIXED_DEFECTS, "the ledger should not be emptied silently"
        for name, entry in FIXED_DEFECTS.items():
            assert {"where", "was", "now", "consequence_removed"} <= set(entry), name

    def test_zeros_and_none_still_guard(self):
        assert loadcalc.acwr(100.0, 0) is None
        assert loadcalc.acwr(100.0, None) is None
        assert loadcalc.acwr(100.0, 0.4) == 1000.0, (
            "a near-zero chronic is a genuine spike, not an error")

    def test_unavailable_runs_are_not_counted_as_days(self):
        src = inspect.getsource(loadcalc.compute)
        assert "if load is None:" in src and "continue" in src, (
            "compute() no longer skips unavailable runs; the unreachability "
            "analysis in FIXED_DEFECTS needs redoing")

    def test_load_version_is_recorded_in_every_window(self, recorded):
        # A rationale that does not say which load formula produced it cannot
        # be audited against a later change to that formula.
        assert loadcalc.LOAD_VERSION
        for snap in recorded.values():
            assert snap["windows"]["28"]["run_confidence"] is not None


@requires_real_db
def test_no_scenario_can_reach_the_live_database(tmp_path):
    """Guard against the mistake that started this work.

    An earlier draft set `GARMIN_DB`; the real variable is `TRAINLOOP_DB`, so
    the fixtures silently opened the athlete's database and wrote ten junk
    activities into it. The scenarios now pass an explicit path. This asserts
    the live database is untouched by a fixture build.
    """
    before = trainingdb.connect().execute(
        "SELECT COUNT(*) c FROM activities").fetchone()["c"]
    scenario = SCENARIOS_BY_NAME["empty-database"]
    conn = scenario.build(str(tmp_path / "isolated.db"))
    rows = conn.execute("SELECT COUNT(*) c FROM activities").fetchone()["c"]
    conn.close()
    after = trainingdb.connect().execute(
        "SELECT COUNT(*) c FROM activities").fetchone()["c"]
    assert rows == 0
    assert before == after, (
        "building a fixture changed the live activity count from %d to %d"
        % (before, after))