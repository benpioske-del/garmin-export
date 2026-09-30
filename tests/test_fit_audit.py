"""Tests for fit_audit: GPS presence, validity, reproducibility, failure handling.

Supervisor brief Task 3 requires coverage of a file with GPS, one without GPS,
and malformed input, plus file hashes and parser versions. Of the three file
shapes, only "with GPS" is available as a real fixture, so the other two are
synthesised.

The previous version of this file asserted that the athlete's coordinates fall
inside a particular region. That assertion both hardcoded the location into a
tracked test file and depended on the audit reporting coordinates at all. The
audit no longer reports coordinates, so the test is inverted: it now asserts
that no coordinate value appears anywhere in the output. See
docs/PRIVACY_INCIDENT.md.
"""

import os

import pytest

import fit_audit
from conftest import FakeFitFile, FakeMessage, REAL_FIT, requires_real_fit

SEMI = fit_audit.SEMICIRCLE


def to_semicircles(deg):
    return int(round(deg / SEMI))


# --- the real corpus -------------------------------------------------------

@pytest.fixture(scope="module")
def real_report():
    """Parse the whole corpus once. Inspecting 56 files is slow, and several
    separate tests each re-reading them dominated the run time."""
    return fit_audit.report()


@requires_real_fit
def test_real_files_parse_without_failure(real_report):
    _, results, failures = real_report
    assert failures == [], "every real FIT file should parse: %s" % failures
    assert results


@requires_real_fit
def test_real_files_have_gps_and_valid_coordinates(real_report):
    _, results, _ = real_report
    assert all(r["has_gps"] for r in results), "expected GPS in every file"
    assert sum(r["position_points"] for r in results) > 0
    assert sum(r["out_of_range"] for r in results) == 0
    assert sum(r["null_island"] for r in results) == 0


@requires_real_fit
def test_real_files_have_laps_and_no_timezone(real_report):
    _, results, _ = real_report
    assert all(r["laps"] > 0 for r in results)
    # No FIT file exposes a time zone, which is why the export has to record an
    # explicit assumed-UTC status rather than deriving one.
    assert sum(r["tz_fields"] for r in results) == 0


@requires_real_fit
def test_every_real_file_has_a_hash_and_usable_timestamp(real_report):
    _, results, _ = real_report
    for r in results:
        assert r["sha256"] and len(r["sha256"]) == 64
        assert r["byte_size"] > 0
        assert r["has_timestamp"] is True
        assert r["start_utc"].endswith("Z")


@requires_real_fit
def test_audit_output_contains_no_coordinates(real_report):
    """Regression guard: the audit must reduce positions to counts."""
    text, results, _ = real_report
    blob = text + repr(results)
    # Any decoded degree value would show up as a bare decimal in this range.
    for suspect in ("lat_min", "lat_max", "lon_min", "lon_max", "semicircle"):
        assert suspect not in blob
    for row in results:
        for key, value in row.items():
            assert "lat" not in key.lower() and "lon" not in key.lower(), key
            assert not isinstance(value, float) or value >= 0, key


# --- a file without GPS ----------------------------------------------------

def test_file_without_gps_is_detected_not_assumed(monkeypatch, tmp_path):
    """A file with no position fields must be reported as lacking GPS.

    This is the case the brief cares about: the absence must be recorded, never
    filled in with a default route.
    """
    p = tmp_path / "nogps.fit"
    p.write_bytes(b"not really a fit file")
    monkeypatch.setattr(fit_audit.fitparse, "FitFile",
                        lambda _p: FakeFitFile())
    out = fit_audit.inspect_file(str(p))
    assert out["has_gps"] is False
    assert out["position_points"] == 0
    assert out["readable"] is True


def test_file_with_gps_is_counted_without_decoding(monkeypatch, tmp_path):
    p = tmp_path / "gps.fit"
    p.write_bytes(b"stub")
    rec = FakeMessage([
        ("position_lat", to_semicircles(44.95)),
        ("position_long", to_semicircles(-93.16)),
    ])
    monkeypatch.setattr(fit_audit.fitparse, "FitFile",
                        lambda _p: FakeFitFile(records=[rec]))
    out = fit_audit.inspect_file(str(p))
    assert out["has_gps"] is True
    assert out["position_points"] == 1
    assert out["out_of_range"] == 0
    assert out["null_island"] == 0
    # The decoded degrees exist nowhere in the result.
    assert "44.95" not in repr(out)
    assert "-93.16" not in repr(out)


def test_partial_gps_pair_is_not_counted(monkeypatch, tmp_path):
    """A latitude with no longitude is unusable and must not become a point."""
    p = tmp_path / "half.fit"
    p.write_bytes(b"stub")
    rec = FakeMessage([("position_lat", to_semicircles(44.95))])
    monkeypatch.setattr(fit_audit.fitparse, "FitFile",
                        lambda _p: FakeFitFile(records=[rec]))
    out = fit_audit.inspect_file(str(p))
    assert out["position_points"] == 0
    assert out["has_gps"] is False


def test_null_island_is_flagged(monkeypatch, tmp_path):
    p = tmp_path / "zero.fit"
    p.write_bytes(b"stub")
    rec = FakeMessage([("position_lat", 0), ("position_long", 0)])
    monkeypatch.setattr(fit_audit.fitparse, "FitFile",
                        lambda _p: FakeFitFile(records=[rec]))
    out = fit_audit.inspect_file(str(p))
    assert out["null_island"] == 1


def test_missing_session_fields_are_reported(monkeypatch, tmp_path):
    """A field the reader needs but the file lacks must show up, not go blank."""
    p = tmp_path / "thin.fit"
    p.write_bytes(b"stub")
    monkeypatch.setattr(fit_audit.fitparse, "FitFile",
                        lambda _p: FakeFitFile(
                            sessions=[FakeMessage([("sport", "running")])]))
    out = fit_audit.inspect_file(str(p))
    assert "avg_heart_rate" in out["fields_missing"]
    assert any("missing session fields" in w for w in out["warnings"])


# --- hashes and versions ---------------------------------------------------

def test_hash_is_recorded_and_stable(monkeypatch, tmp_path):
    p = tmp_path / "h.fit"
    p.write_bytes(b"deterministic bytes")
    monkeypatch.setattr(fit_audit.fitparse, "FitFile", lambda _p: FakeFitFile())
    first = fit_audit.inspect_file(str(p))
    second = fit_audit.inspect_file(str(p))
    assert first["sha256"] == second["sha256"]
    assert first["byte_size"] == 19


def test_parser_version_is_reported():
    versions = fit_audit.parser_versions()
    assert versions.get("fitparse")


def test_report_states_the_parser_version(monkeypatch, tmp_path):
    p = tmp_path / "v.fit"
    p.write_bytes(b"stub")
    monkeypatch.setattr(fit_audit.fitparse, "FitFile", lambda _p: FakeFitFile())
    text, _, _ = fit_audit.report(str(tmp_path))
    assert "fitparse=" in text


def test_rollup_counts_are_consistent(monkeypatch, tmp_path):
    p = tmp_path / "r.fit"
    p.write_bytes(b"stub")
    monkeypatch.setattr(fit_audit.fitparse, "FitFile", lambda _p: FakeFitFile())
    _, results, failures = fit_audit.report(str(tmp_path))
    roll = fit_audit.rollup(results, failures)
    assert roll["files_inspected"] == 1
    assert roll["files_with_gps"] + roll["files_without_gps"] == len(results)


# --- malformed input -------------------------------------------------------

@requires_real_fit
def test_truncated_real_file_is_reported_as_a_failure(tmp_path):
    """A corrupt file must be named and counted, not skipped silently."""
    src = REAL_FIT[0]
    bad = tmp_path / "truncated.fit"
    with open(src, "rb") as fh:
        head = fh.read(200)
    bad.write_bytes(head)
    results, failures = fit_audit.summarise([str(bad)])
    assert len(failures) == 1
    assert failures[0]["name"] == "truncated.fit"
    assert failures[0]["error"]
    assert results == []


def test_summary_survives_a_mixed_corpus(monkeypatch, tmp_path):
    """One bad file must not abort the run over the good ones."""
    good = tmp_path / "good.fit"
    bad = tmp_path / "bad.fit"
    good.write_bytes(b"stub")
    bad.write_bytes(b"stub")

    def fake(p):
        if "bad" in os.path.basename(p):
            raise ValueError("corrupt")
        return FakeFitFile()

    monkeypatch.setattr(fit_audit.fitparse, "FitFile", fake)
    results, failures = fit_audit.summarise([str(good), str(bad)])
    assert len(results) == 1
    assert len(failures) == 1
    assert failures[0]["error"] == "ValueError"
