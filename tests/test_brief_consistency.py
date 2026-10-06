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

def test_write_facts_produces_a_readable_document(tmp_path):
    out = tmp_path / "brief_facts.json"
    doc = B.write_facts(path=str(out), commit="abc1234", visibility="private")
    assert doc["commit"] == "abc1234"
    assert doc["repo_visibility"] == "private"
    assert json.loads(out.read_text(encoding="utf-8"))["corpus"] == doc["corpus"]


def test_facts_document_carries_the_numbers_a_brief_gets_wrong(tmp_path):
    doc = B.write_facts(path=str(tmp_path / "f.json"))
    facts = B.measured_facts()
    assert doc["corpus"]["fit_files"] == facts["fit_files"]
    assert doc["corpus"]["activities"] == facts["activities"]
    assert doc["reviews"]["open"] == facts["open_reviews"]
    assert doc["reviews"]["open"] == sum(doc["reviews"]["by_reason"].values())
    assert doc["tests"]["passed"] == facts["tests_passed"]


def test_facts_document_states_the_dashboard_is_wired(tmp_path):
    doc = B.write_facts(path=str(tmp_path / "f.json"))
    if not doc["dashboard"]:
        pytest.skip("server or dashboard absent")
    assert len(doc["dashboard"]["dashboard_calls"]) == 3
    assert len(doc["dashboard"]["server_routes"]) == 3


def test_facts_document_records_a_refusal_as_a_refusal(tmp_path):
    """A refusal is the honest answer and must not be laundered into a state."""
    doc = B.write_facts(path=str(tmp_path / "f.json"))
    coaching = doc["coaching"]
    assert "state" in coaching
    if coaching["state"] in ("confirmation_required", "data_insufficient"):
        assert coaching["advisory"] is False
        assert coaching["reasons"]


def test_facts_document_carries_no_gps_or_activity_identifiers(tmp_path):
    """This file is published. It must hold counts and states, nothing else."""
    import re as _re
    raw = (tmp_path / "f.json").as_posix()
    B.write_facts(path=raw)
    text = open(raw, encoding="utf-8").read()
    for banned in ("position_lat", "position_long", "latitude", "longitude",
                   "start_local", "garmin_fit", ".fit", "weight", "body_fat"):
        assert banned not in text, banned
    assert not _re.search(r"\b17\d{8}\b", text), "an activity id leaked"


def test_facts_file_is_not_itself_a_source_of_staleness(tmp_path):
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


def test_written_facts_carry_the_digest_they_were_measured_by(tmp_path):
    doc = B.write_facts(path=str(tmp_path / "f.json"))
    assert doc["facts_sha"] == B.facts_digest(doc)


def test_two_generations_of_the_same_state_agree(tmp_path):
    a = B.write_facts(path=str(tmp_path / "a.json"))
    b = B.write_facts(path=str(tmp_path / "b.json"))
    assert a["facts_sha"] == b["facts_sha"], (
        "regenerating facts must be idempotent, or the publisher commits on "
        "every scheduled run no matter what changed")
    assert a["generated_utc"] != b["generated_utc"]


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
