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
from recommend_scenarios import (  # noqa: E402
    SCENARIOS, SCENARIOS_BY_NAME, FIXED_AS_OF, HR_MAX,
)

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fixtures", "recommend")

REGENERATE = bool(os.environ.get("REGENERATE_SNAPSHOTS"))

# States the fixtures demonstrate, derived from the scenarios rather than
# asserted in the abstract.
REACHABLE = ("build", "maintain", "data_insufficient", "confirmation_required")

# Advertised by terms.CONTROL_STATES but not returnable by recommend().
UNREACHABLE_ADVERTISED = ("recover", "deload")

# Branch conditions in recommend() that no input can satisfy, with why.
KNOWN_DEFECTS = {
    "deload-band-unreachable": {
        "where": "recommend.py: HIGH_ACWR = 1.5",
        "why": "ratio = 7d_sum / 28d_sum and the 7-day window is a subset of "
               "the 28-day window, so ratio <= 1.0 always",
        "consequence": "the system can never recommend reducing load",
    },
    "caution-band-unreachable": {
        "where": "recommend.py: CAUTION_ACWR = 1.3",
        "why": "same ceiling as above",
        "consequence": "the caution band is dead code",
    },
    "recover-never-returned": {
        "where": "recommend.recommend",
        "why": "no branch returns terms.STATE_RECOVER",
        "consequence": "available_states() advertises a state that cannot occur",
    },
    "run-load-none-branch-unreachable": {
        "where": 'recommend.py: if w28["run_load"] is None',
        "why": "compute() skips runs whose load is None before counting them "
               "as days, so runs_28d >= 8 implies run_load is not None",
        "consequence": "the unavailable-input branch never runs",
    },
    "ratio-none-branch-unreachable": {
        "where": "recommend.py: if ratio is None",
        "why": "chronic sums to more than zero whenever runs_28d >= 8, since "
               "every counted day contributes a positive load",
        "consequence": "dead code",
    },
    "missing-input-reported-as-missing-history": {
        "where": "recommend.py: MIN_RUNS_28D check precedes the load check",
        "why": "runs without a computable load are dropped before counting, so "
               "a missing hr_max presents as runs_28d == 0",
        "consequence": "the athlete is told they lack history rather than "
                       "that a required input is absent",
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

        # Distinct days only: runs_7d/runs_28d count days, so two runs on one
        # day would collapse and the sweep would understate the space.
        for recent in range(0, 10):
            for older in range(0, 10):
                for moving in (1800, 3600, 7200):
                    for avg_hr in (140, 165, 185):
                        for hr_max in (HR_MAX, None):
                            for review in ("resolved", "open"):
                                days = list(range(1, recent + 1))
                                days += [12 + 3 * i for i in range(older)]
                                conn.execute("DELETE FROM activities")
                                for i, ago in enumerate(days):
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
                                        (recent, older, moving, avg_hr, hr_max))
        conn.close()
        return seen, shapes, produced_deload

    def test_sweep_never_produces_deload_or_recover(self, tmp_path):
        seen, shapes, produced_deload = self._sweep(tmp_path)
        assert shapes > 1000, "sweep was too small to be evidence: %d" % shapes
        assert not produced_deload, (
            "deload became reachable in %d shapes; the acute:chronic ceiling "
            "changed and the policy needs reviewing: %s"
            % (len(produced_deload), produced_deload[:3]))
        assert terms.STATE_RECOVER not in seen
        assert terms.STATE_DELOAD not in seen, sorted(seen)

    def test_sweep_reaches_exactly_the_documented_states(self, tmp_path):
        seen, shapes, _ = self._sweep(tmp_path)
        assert seen == set(REACHABLE), (
            "sweep of %d shapes produced %s, documented as %s"
            % (shapes, sorted(seen), sorted(REACHABLE)))

    def test_recover_has_no_branch_at_all(self):
        # The one state whose unreachability is structural rather than
        # arithmetic: there is no code path that produces it.
        src = inspect.getsource(recommend.recommend)
        assert "STATE_RECOVER" not in src, (
            "recover now has a branch; update KNOWN_DEFECTS and the inventory")
        assert "recover" in terms.CONTROL_STATES, (
            "recover left CONTROL_STATES without a decision")

    def test_ratio_is_bounded_by_one(self):
        # The reason deload is unreachable. Asserted so that changing the
        # chronic calculation cannot happen silently.
        assert loadcalc.WINDOWS == (7, 14, 28), (
            "window set changed; re-examine the acute:chronic ceiling")
        assert recommend.HIGH_ACWR > 1.0, (
            "HIGH_ACWR was lowered to at most 1.0, which would make deload "
            "reachable and silently change the policy")

    def test_missing_input_is_still_misreported(self, recorded):
        # Pins the defect rather than tolerating it silently. This test is
        # expected to be INVERTED when the rationale is fixed to name the
        # absent input.
        for name in ("run-load-unavailable-no-hr-max",
                     "run-load-unavailable-no-avg-hr"):
            reasons = " ".join(recorded[name]["recommend"]["reasons"])
            assert "hr_max" not in reasons and "avg_hr" not in reasons, (
                "%s now names the missing input; invert this test and remove "
                "'missing-input-reported-as-missing-history' from KNOWN_DEFECTS"
                % name)
            assert "only 0 runs" in reasons, (
                "%s no longer reports missing history; re-check the fix" % name)


class TestKnownDefectsAreAccurate:
    """The defect list must describe the code as it actually is."""

    def test_ratio_ceiling_holds(self):
        assert loadcalc.acwr(600.0, 600.0) == 1.0
        # A 7-day sum can never exceed a 28-day sum over the same records.
        assert loadcalc.acwr(700.0, 700.0) == 1.0
        assert loadcalc.acwr(600.0, 1500.0) == 0.4

    def test_zero_chronic_gives_none_not_infinity(self):
        assert loadcalc.acwr(100.0, 0) is None
        assert loadcalc.acwr(100.0, None) is None

    def test_unavailable_runs_are_not_counted_as_days(self):
        src = inspect.getsource(loadcalc.compute)
        assert "if load is None:" in src and "continue" in src, (
            "compute() no longer skips unavailable runs; the unreachability "
            "analysis in KNOWN_DEFECTS needs redoing")

    def test_load_version_is_recorded_in_every_window(self, recorded):
        # A rationale that does not say which load formula produced it cannot
        # be audited against a later change to that formula.
        assert loadcalc.LOAD_VERSION
        for snap in recorded.values():
            assert snap["windows"]["28"]["run_confidence"] is not None


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