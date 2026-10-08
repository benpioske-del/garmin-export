"""Tests for the supervisor brief consistency checker.

The brief is written by a process that cannot read this repository: `dashboard/`
is gitignored, the FIT files are local-only, and since the repo went private an
anonymous fetch of every file 404s. Four briefs in a row asserted numbers and
states the writer had no way to observe.

These tests pin the *known* gap so a NEW fabricated claim fails the suite, which
is the drift worth catching. When the brief legitimately changes, update
KNOWN_UNBACKED and KNOWN_CONFLICTS and say why in the commit.
"""

import json
import os
import re

import pytest

import brief_consistency as B

# As of commit 09b5a1a (2026-10-05). Eleven ranked backlog rows, two task files.
KNOWN_UNBACKED = {
    "complete-athlete-profile-and-timezone-provenance",
    "formalize-continuity-review-without-synthetic-activities",
    "capture-confirmed-strength-history",
    "implement-gated-weather-enrichment",
    "make-coaching-rationales-deterministic-and-auditable",
    "harden-bridge-and-release-quality-gates",
    "document-conservative-training-signals",
    "stabilize-running-load-before-progression",
    "build-long-run-pace-durability",
    "introduce-conservative-runner-strength",
    "establish-authenticated-athlete-ownership",
}

# (label, stated) pairs the fourth brief got wrong. Kept so that a brief which
# stops making them is a visible change rather than a silent improvement.
KNOWN_CONFLICTS = {
    ("FIT files", 57),
    ("activities", 57),
    ("open reviews", 58),
    ("tests passed", 207),
}
# The per-reason breakdown is checked separately by reason_conflicts().


def test_brief_rows_are_found():
    rows = B.brief_rows()
    assert len(rows) >= 10
    slugs = {slug for slug, _, _ in rows}
    assert slugs & KNOWN_UNBACKED


def test_every_row_has_a_slug_status_and_text():
    for slug, status, text in B.brief_rows():
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]{6,}", slug), slug
        assert status and status == status.upper(), status
        assert len(text) > 10, slug


def test_ranked_backlog_rows_are_counted():
    """The fourth brief carried only a prose backlog and a prose primary task."""
    statuses = {s for _, s, _ in B.brief_rows()}
    assert "RANKED" in statuses, "rank: N | slug | prose rows are not parsed"


def test_the_queue_is_the_real_queue():
    """tasks/ holds two files; the brief's table is not the queue."""
    assert B.queued_slugs() == {"001-example-task", "002-log-a-5k-pr"}


def test_unbacked_rows_are_pinned_so_new_phantoms_fail():
    found = {slug for slug, _, _ in B.unbacked_rows()}
    assert found == KNOWN_UNBACKED, (
        "the brief's task list changed: %s" % (found ^ KNOWN_UNBACKED))


# --- facts -------------------------------------------------------------------

def test_measured_facts_are_available():
    facts = B.measured_facts()
    for key in ("fit_files", "activities", "open_reviews"):
        assert isinstance(facts.get(key), int), key
    assert facts["open_reviews"] == sum(
        (facts.get("review_breakdown") or {}).values())


def test_conflicting_claims_are_pinned():
    """Every number the writer could not read, and its correct value."""
    found = {(label, stated) for label, stated, _, _ in B.claim_conflicts()}
    for label, stated in KNOWN_CONFLICTS:
        assert (label, stated) in found, (
            "the brief no longer states %s = %d; if that is deliberate, drop it "
            "from KNOWN_CONFLICTS and say why" % (label, stated))


def test_reason_breakdown_conflicts_are_pinned():
    found = {(label, stated) for label, stated, _, _ in B.reason_conflicts()}
    assert ("timezone_uncertain", 57) in found


def test_a_brief_matching_reality_reports_no_conflicts(tmp_path, monkeypatch):
    """The checker must not cry wolf. Feed it a brief that agrees with the data."""
    facts = B.measured_facts()
    monkeypatch.setattr(B, "BRIEF", str(tmp_path / "b.md"))
    good = (
        "standing-corpus | accepted | %d FIT files and %d activities are the "
        "accepted corpus.\n"
        "open-review-state | accepted | %d open reviews.\n"
        "test-state | accepted | %d passed and %d skipped.\n"
% (facts["fit_files"], facts["activities"], facts["open_reviews"],
           facts["tests_passed"], facts["tests_skipped"])
    )
    open(B.BRIEF, "w", encoding="utf-8").write(good)
    assert B.claim_conflicts(facts) == []
    assert B.reason_conflicts(facts) == []


def test_conflict_checkers_check_text_as_well_as_the_file(tmp_path, monkeypatch):
    """The merge gate passes an incoming brief; the file-based calls stay whole."""
    facts = B.measured_facts()
    monkeypatch.setattr(B, "BRIEF", str(tmp_path / "b.md"))
    open(B.BRIEF, "w", encoding="utf-8").write(
        "%d activities and %d open reviews\n"
        % (facts["activities"], facts["open_reviews"]))
    assert B.claim_conflicts(facts) == []
    wrong = "%d activities\n" % (facts["activities"] + 1)
    found = B.claim_conflicts(facts, text=wrong)
    assert found and found[0][0] == "activities"
    assert found[0][1] == facts["activities"] + 1
    assert found[0][2] == facts["activities"]


def test_numeric_conflicts_aggregates_and_dedupes(tmp_path, monkeypatch):
    facts = B.measured_facts()
    monkeypatch.setattr(B, "BRIEF", str(tmp_path / "b.md"))
    wrong = "%d activities\n%d activities again\n%d open reviews\n" % (
        facts["activities"] + 1, facts["activities"] + 1,
        facts["open_reviews"] + 1)
    open(B.BRIEF, "w", encoding="utf-8").write("nothing numeric")
    out = B.numeric_conflicts(text=wrong)
    labels = [item[0] for item in out]
    assert labels.count("activities") == 1, out
    assert "open reviews" in labels, out
    assert B.numeric_conflicts(
        text="%d activities and %d open reviews\n"
             % (facts["activities"], facts["open_reviews"])) == []
    assert B.numeric_conflicts(text="all prose, no claims") == []


def test_numeric_conflicts_includes_the_dashboard_claim(tmp_path, monkeypatch):
    if B.dashboard_wiring() is None:
        pytest.skip("server or dashboard absent")
    monkeypatch.setattr(B, "BRIEF", str(tmp_path / "b.md"))
    out = B.numeric_conflicts(text="The dashboard is not connected yet.")
    assert any(item[0] == "dashboard" for item in out), out


def test_dashboard_wiring_is_measured_not_assumed():
    wiring = B.dashboard_wiring()
    if wiring is None:
        pytest.skip("server or dashboard absent")
    assert len(wiring["server_routes"]) == 3, wiring
    assert len(wiring["dashboard_calls"]) == 3, wiring


def test_dashboard_conflict_detects_the_prose_claim():
    """Four briefs in a row wrote this as prose, never as a table row."""
    conflict = B.dashboard_conflict()
    if B.dashboard_wiring() is None:
        pytest.skip("server or dashboard absent")
    assert conflict is not None, "the dashboard claim went unnoticed"
    label, stated, actual, _ = conflict
    assert label == "dashboard"
    assert "disconnected" in stated or "no references" in stated
    assert actual.startswith("consumes")


def test_dashboard_conflict_is_silent_once_the_claim_is_gone(tmp_path,
                                                             monkeypatch):
    monkeypatch.setattr(B, "BRIEF", str(tmp_path / "b.md"))
    open(B.BRIEF, "w", encoding="utf-8").write(
        "## SUPERVISOR DECISIONS\n"
        "- The dashboard consumes the canonical API. This is done.\n")
    assert B.dashboard_conflict() is None


# --- the regression this module shipped with --------------------------------

def test_no_rows_is_a_failure_not_a_clean_bill(monkeypatch, tmp_path, capsys):
    """Losing the task table must not pass.

    The first version exited 0 when it parsed no rows, which is exactly the
    silent regression the checker exists to prevent.
    """
    monkeypatch.setattr(B, "BRIEF", str(tmp_path / "empty.md"))
    open(B.BRIEF, "w", encoding="utf-8").write(
        "# Supervisor Brief\n\nno recognisable task rows here\n")
    monkeypatch.setattr("sys.argv", ["brief_consistency.py"])
    assert B.main() == 1
    assert "NO TASK ROWS PARSED" in capsys.readouterr().out


def test_a_clean_brief_exits_zero(monkeypatch, tmp_path, capsys):
    """A brief whose only task is genuinely queued, with correct numbers."""
    facts = B.measured_facts()
    queued = sorted(B.queued_slugs())[0]
    monkeypatch.setattr(B, "BRIEF", str(tmp_path / "ok.md"))
    open(B.BRIEF, "w", encoding="utf-8").write(
        "%s | IN PROGRESS | the one task that really exists\n"
        "test-state | accepted | %d passed and %d skipped.\n"
        % (queued, facts["tests_passed"], facts["tests_skipped"]))
    monkeypatch.setattr("sys.argv", ["brief_consistency.py"])
    assert B.main() == 0, capsys.readouterr().out


def test_missing_brief_yields_no_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(B, "BRIEF", str(tmp_path / "nope.md"))
    assert B.brief_rows() == []
    assert B.unbacked_rows() == []


# --- brief_facts.json --------------------------------------------------------

@pytest.fixture
def fast_facts(monkeypatch):
    """Structural tests don't need the recommender to run on the real DB or
    every FIT file to be parsed; the two live-corpus tests below exercise that.
    Stubbing keeps a dozen write_facts() calls in minutes instead of an hour.
    """
    monkeypatch.setattr(B, "lap_coverage", lambda limit=None: (0, 0))
    monkeypatch.setattr(
        B, "_coaching_facts",
        lambda: {"state": "data_insufficient", "advisory": False,
                 "reasons": ["timezone unresolved"], "date": None})


def test_write_facts_produces_a_readable_document(tmp_path, fast_facts):
    out = tmp_path / "brief_facts.json"
    doc = B.write_facts(path=str(out), commit="abc1234", visibility="private")
    assert doc["commit"] == "abc1234"
    assert doc["repo_visibility"] == "private"
    assert json.loads(out.read_text(encoding="utf-8"))["corpus"] == doc["corpus"]


def test_facts_document_carries_the_numbers_a_brief_gets_wrong(tmp_path, fast_facts):
    doc = B.write_facts(path=str(tmp_path / "f.json"))
    facts = B.measured_facts()
    assert doc["corpus"]["fit_files"] == facts["fit_files"]
    assert doc["corpus"]["activities"] == facts["activities"]
    assert doc["reviews"]["open"] == facts["open_reviews"]
    assert doc["reviews"]["open"] == sum(doc["reviews"]["by_reason"].values())
    assert doc["tests"]["passed"] == facts["tests_passed"]


def test_facts_document_states_the_dashboard_is_wired(tmp_path, fast_facts):
    doc = B.write_facts(path=str(tmp_path / "f.json"))
    if not doc["dashboard"]:
        pytest.skip("server or dashboard absent")
    assert len(doc["dashboard"]["dashboard_calls"]) == 3
    assert len(doc["dashboard"]["server_routes"]) == 3


def test_facts_document_records_a_refusal_as_a_refusal(tmp_path, fast_facts):
    """A refusal is the honest answer and must not be laundered into a state."""
    doc = B.write_facts(path=str(tmp_path / "f.json"))
    coaching = doc["coaching"]
    assert "state" in coaching
    if coaching["state"] in ("confirmation_required", "data_insufficient"):
        assert coaching["advisory"] is False
        assert coaching["reasons"]


def test_facts_document_carries_no_gps_or_activity_identifiers(tmp_path, fast_facts):
    """This file is published. It must hold counts and states, nothing else."""
    import re as _re
    raw = (tmp_path / "f.json").as_posix()
    B.write_facts(path=raw)
    text = open(raw, encoding="utf-8").read()
    for banned in ("position_lat", "position_long", "latitude", "longitude",
                   "start_local", "garmin_fit", ".fit", "weight", "body_fat"):
        assert banned not in text, banned
    assert not _re.search(r"\b17\d{8}\b", text), "an activity id leaked"


def test_facts_file_is_not_itself_a_source_of_staleness(tmp_path, fast_facts):
    """It records the commit it describes, so a stale copy is recognisable."""
    doc = B.write_facts(path=str(tmp_path / "f.json"), commit="deadbee")
    assert doc["generated_utc"].endswith("Z")
    assert doc["commit"] == "deadbee"

def test_facts_digest_ignores_the_timestamp():
    """A fresh stamp on identical figures is not a change.

    The publisher decides whether to commit by comparing facts_sha. If the
    digest covered generated_utc, every scheduled run would look like new data
    and commit twice a day forever, which is the exact churn the early-return
    exists to prevent.
    """
    d1 = {"generated_utc": "2026-10-05T00:00:00Z", "corpus": {"fit_files": 58}}
    d2 = {"generated_utc": "2026-10-06T00:00:00Z", "corpus": {"fit_files": 58}}
    assert B.facts_digest(d1) == B.facts_digest(d2)


def test_facts_digest_notices_a_real_change():
    d1 = {"generated_utc": "2026-10-05T00:00:00Z", "corpus": {"fit_files": 58}}
    d2 = {"generated_utc": "2026-10-05T00:00:00Z", "corpus": {"fit_files": 59}}
    assert B.facts_digest(d1) != B.facts_digest(d2)


def test_written_facts_carry_the_digest_they_were_measured_by(tmp_path, fast_facts):
    doc = B.write_facts(path=str(tmp_path / "f.json"))
    assert doc["facts_sha"] == B.facts_digest(doc)


def test_two_generations_of_the_same_state_agree(tmp_path, fast_facts):
    a = B.write_facts(path=str(tmp_path / "a.json"))
    b = B.write_facts(path=str(tmp_path / "b.json"))
    assert a["facts_sha"] == b["facts_sha"], (
        "regenerating facts must be idempotent, or the publisher commits on "
        "every scheduled run no matter what changed")


def test_facts_digest_excludes_the_commit_it_describes():
    """The loop this prevents: commit is HEAD, committing moves HEAD.

    If commit were inside the digest, publishing would rewrite the facts with
    the HEAD it is committing onto, that commit would move HEAD, and the next
    scheduled run would differ again - committing forever with no change in the
    underlying data. Verified live before this test existed.
    """
    base = {"corpus": {"fit_files": 58}, "generated_utc": "x"}
    assert B.facts_digest(dict(base, commit="aaaaaaa")) == \
        B.facts_digest(dict(base, commit="bbbbbbb"))


def test_facts_digest_still_tracks_visibility():
    """Excluding volatile fields must not blind it to a real change."""
    base = {"corpus": {"fit_files": 58}}
    assert B.facts_digest(dict(base, repo_visibility="public")) != \
        B.facts_digest(dict(base, repo_visibility="private"))


# --- measured splits ---------------------------------------------------------

def test_best_5k_from_csv_measures_the_fastest_crossing(tmp_path, monkeypatch):
    csvf = tmp_path / "garmin_export.csv"
    csvf.write_text(
        "Date,Distance,Best 5K Time,Lap Splits\n"
        "2026-05-21 07:00:00,6.52,27:35,8:40\n"
        "2026-06-16 19:26:37,4.89,24:42,7:11\n",
        encoding="utf-8")
    monkeypatch.setattr(B, "CANON", str(csvf))
    best = B._best_5k_from_csv()
    assert best["time"] == "24:42"
    assert best["date"] == "2026-06-16"
    assert best["distance_mi"] == 4.89


def test_best_5k_from_csv_is_absent_without_the_column(tmp_path, monkeypatch):
    csvf = tmp_path / "garmin_export.csv"
    csvf.write_text("Date,Distance\n2026-06-16 07:00:00,4.89\n", encoding="utf-8")
    monkeypatch.setattr(B, "CANON", str(csvf))
    assert B._best_5k_from_csv() is None
    assert B._csv_has_split_columns() is False


def test_csv_split_columns_are_detected(tmp_path, monkeypatch):
    csvf = tmp_path / "garmin_export.csv"
    csvf.write_text("Date,Best 5K Time,Lap Splits\n2026-06-16,24:42,7:11\n",
                    encoding="utf-8")
    monkeypatch.setattr(B, "CANON", str(csvf))
    assert B._csv_has_split_columns() is True


def test_csv_split_completeness_counts_every_cell(tmp_path, monkeypatch):
    csvf = tmp_path / "garmin_export.csv"
    csvf.write_text(
        "Date,Best 5K Time,Lap Splits\n"
        "2026-06-16 19:26:37,24:42,7:11\n"
        "2026-07-01 08:00:00,25:10,8:00, 8:05\n"
        "2026-07-02 08:00:00,,8:30\n"
        "2026-07-03 08:00:00,27:00,\n",
        encoding="utf-8")
    monkeypatch.setattr(B, "CANON", str(csvf))
    rows, both, miss_5k, miss_laps = B._csv_split_completeness()
    assert (rows, both, miss_5k, miss_laps) == (4, 2, 1, 1)


def test_csv_split_completeness_is_absent_without_the_columns(tmp_path,
                                                              monkeypatch):
    csvf = tmp_path / "garmin_export.csv"
    csvf.write_text("Date,Distance\n2026-06-16,4.89\n", encoding="utf-8")
    monkeypatch.setattr(B, "CANON", str(csvf))
    assert B._csv_split_completeness() == (0, 0, None, None)


def test_facts_document_carries_the_measured_5k(tmp_path, fast_facts, monkeypatch):
    csvf = tmp_path / "garmin_export.csv"
    csvf.write_text("Date,Distance,Best 5K Time,Lap Splits\n"
"2026-06-16 19:26:37,4.89,24:42,7:11\n", encoding="utf-8")
    monkeypatch.setattr(B, "CANON", str(csvf))
    doc = B.write_facts(path=str(tmp_path / "f.json"))
    assert doc["best_5k"]["time"] == "24:42"
    assert doc["best_5k"]["date"] == "2026-06-16"
    assert doc["splits"]["published"] is True
    assert doc["splits"]["rows_published"] == 1
    assert doc["splits"]["rows_with_splits"] == 1

