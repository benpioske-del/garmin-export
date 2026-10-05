"""Tests for the supervisor brief consistency checker.

The brief's task table is prose from a process that cannot see gitignored files.
Three consecutive briefs asserted a dashboard state it had no way to observe, and
one claimed per-mile splits were unavailable when all 58 FIT files carry laps.

These tests pin the *known* gap so that a NEW unbacked row fails the suite, which
is the drift worth catching. When the brief legitimately changes, update
KNOWN_UNBACKED and say why in the commit.
"""

import os
import re

import pytest

import brief_consistency as B

# As of commit 0e88c33 (2026-10-04 21:13). Twelve rows, two task files.
KNOWN_UNBACKED = {
    "establish-authenticated-athlete-ownership",
    "complete-athlete-profile-and-timezone-provenance",
    "formalize-continuity-review-without-synthetic-activities",
    "capture-confirmed-strength-history",
    "implement-gated-weather-enrichment",
    "make-coaching-rationales-deterministic-and-auditable",
    "stabilize-running-load-before-progression",
    "build-long-run-pace-durability",
    "introduce-conservative-runner-strength",
    "harden-bridge-and-release-quality-gates",
    "document-conservative-training-signals",
    "connect-dashboard-to-data-layer",
}


def test_brief_rows_are_found():
    rows = B.brief_rows()
    assert len(rows) >= 10
    slugs = {slug for slug, _, _ in rows}
    assert "connect-dashboard-to-data-layer" in slugs


def test_every_row_has_a_slug_status_and_text():
    for slug, status, text in B.brief_rows():
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]{6,}", slug), slug
        assert status and status == status.upper(), status
        assert len(text) > 10, slug


def test_the_queue_is_the_real_queue():
    """tasks/ holds two files; the brief table is not the queue."""
    assert B.queued_slugs() == {"001-example-task", "002-log-a-5k-pr"}


def test_unbacked_rows_are_pinned_so_new_phantoms_fail():
    found = {slug for slug, _, _ in B.unbacked_rows()}
    assert found == KNOWN_UNBACKED, (
        "the brief's task table changed: %s"
        % (found ^ KNOWN_UNBACKED))


def test_the_dashboard_claim_is_refutable():
    """The TOP PRIORITY row says the dashboard is disconnected. It is not.

    If a task is ever raised from that row, this is the evidence that it is
    already done.
    """
    html = os.path.join(B.REPO, "dashboard", "index.html")
    if not os.path.isfile(html):
        pytest.skip("private dashboard not present")
    text = open(html, encoding="utf-8", errors="replace").read()
    assert "window.DASHBOARD_SOURCES" in text
    for endpoint in ("/api/activities", "/api/load", "/api/coaching"):
        assert endpoint in text, endpoint


def test_checker_reports_the_gap_and_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["brief_consistency.py"])
    assert B.main() == 1
    assert "unbacked rows" in capsys.readouterr().out


def test_checker_quiet_mode_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["brief_consistency.py", "--quiet"])
    assert B.main() == 0


def test_lap_coverage_on_a_sample_proves_splits_exist():
    """The brief claims splits are unavailable. Sample two files and disprove it."""
    cov = B.lap_coverage(limit=2)
    if cov is None:
        pytest.skip("fitparse not installed")
    have, seen = cov
    assert seen == 2
    assert have == 2, "FIT files have no lap records; splits would be unavailable"


def test_lap_coverage_handles_no_fit_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(B.paths, "data_dir", lambda: str(tmp_path))
    assert B.lap_coverage() == (0, 0)


def test_missing_brief_yields_no_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(B, "BRIEF", str(tmp_path / "nope.md"))
    assert B.brief_rows() == []
    assert B.unbacked_rows() == []