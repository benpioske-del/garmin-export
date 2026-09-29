"""Tests for fit_audit: GPS presence, validity, and failure handling.

Supervisor brief Task 4 requires coverage of a file with GPS, one without GPS,
and malformed input. Of the three, only "with GPS" is available as a real
fixture, so the other two are synthesised.
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
    """Parse the whole corpus once. Inspecting 56 files is slow, and four
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
    assert sum(r["points"] for r in results) > 0
    assert sum(r["out_of_range"] for r in results) == 0
    assert sum(r["null_island"] for r in results) == 0


@requires_real_fit
def test_real_files_have_laps_and_no_timezone(real_report):
    _, results, _ = real_report
    assert all(r["laps"] > 0 for r in results)
    # No FIT file exposes a time zone, which is why the export has to record an
    # explicit unknown timezone status rather than deriving one.
    assert sum(r["tz_fields"] for r in results) == 0


@requires_real_fit
def test_coordinates_land_in_the_expected_region(real_report):
    _, results, _ = real_report
    lats = [r["lat_min"] for r in results if r["lat_min"] is not None]
    lats += [r["lat_max"] for r in results if r["lat_max"] is not None]
    assert 44.0 < min(lats) and max(lats) < 45.5


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
    assert out["points"] == 0
    assert out["lat_min"] is None and out["lon_max"] is None


def test_file_with_gps_converts_semicircles(monkeypatch, tmp_path):
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
    assert out["points"] == 1
    assert out["lat_min"] == pytest.approx(44.95, abs=0.01)
    assert out["lon_max"] == pytest.approx(-93.16, abs=0.01)
    assert out["out_of_range"] == 0
    assert out["null_island"] == 0


def test_partial_gps_pair_is_not_counted(monkeypatch, tmp_path):
    """A latitude with no longitude is unusable and must not become a point."""
    p = tmp_path / "half.fit"
    p.write_bytes(b"stub")
    rec = FakeMessage([("position_lat", to_semicircles(44.95))])
    monkeypatch.setattr(fit_audit.fitparse, "FitFile",
                        lambda _p: FakeFitFile(records=[rec]))
    out = fit_audit.inspect_file(str(p))
    assert out["points"] == 0
    assert out["has_gps"] is False


def test_null_island_is_flagged(monkeypatch, tmp_path):
    p = tmp_path / "zero.fit"
    p.write_bytes(b"stub")
    rec = FakeMessage([("position_lat", 0), ("position_long", 0)])
    monkeypatch.setattr(fit_audit.fitparse, "FitFile",
                        lambda _p: FakeFitFile(records=[rec]))
    out = fit_audit.inspect_file(str(p))
    assert out["null_island"] == 1


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
