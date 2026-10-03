"""Tests for the elevation fields in garmin_fit_reader.

Elevation is the only field in a FIT file that is derived rather than measured:
these files carry no barometer_pressure, so altitude is GPS-derived and carries
several feet of noise per sample. Summing every upward step counts that noise as
climbing, which is why the reader publishes the device's own total_ascent but
also carries a recomputation and the elevation range beside it.

These tests pin the arithmetic and the honesty of the diagnostics. They do not
pin a specific device figure, because the whole point is that the figure is
uncertain.
"""

import datetime

import pytest

import garmin_fit_reader as R
from conftest import FakeFitFile, FakeMessage, REAL_FIT, requires_real_fit

M = 1.0 / 0.3048  # one metre in feet, to build fixtures

# fitparse returns start_time as a naive datetime, and split_start relies on
# that, so synthetic sessions must not pass an integer epoch.
START = datetime.datetime(2026, 9, 29, 12, 0, 0)


def session(extra=()):
    """A minimal usable session: 1 mile in 600 s passes read_fit's guards."""
    return FakeMessage([("start_time", START),
                        ("total_distance", 16093.44),
                        ("total_timer_time", 600.0),
                        ("sport", "running")] + list(extra))


def smooth(values, window):
    return R._smooth(values, window)


# ----------------------------------------------------------------- _smooth

def test_smooth_returns_input_unchanged_for_a_window_below_two():
    assert R._smooth([1.0, 2.0, 3.0], 1) == [1.0, 2.0, 3.0]


def test_smooth_returns_input_unchanged_when_too_short_to_mean_anything():
    assert R._smooth([5.0], 5) == [5.0]


def test_smooth_averages_the_neighbourhood_in_the_middle():
    assert smooth([0.0, 0.0, 3.0, 0.0, 0.0], 3) == pytest.approx([0.0, 1.0, 1.0, 1.0, 0.0])


def test_smooth_clamps_rather_than_shortening_the_series():
    """The output length must match the input; a shorter series would silently
    drop the first and last samples, which are the ends of the run."""
    out = R._smooth([0.0, 0.0, 0.0, 0.0, 0.0], 3)
    assert len(out) == 5
    assert out[0] == pytest.approx(0.0)


def test_smooth_removes_a_single_spike():
    """The property the diagnostics depend on: one noisy sample must not move
    the recomputed climb much."""
    steady = [100.0] * 12
    spiked = list(steady)
    spiked[6] += 3.0
    assert R._ascent_ft(R._smooth(steady, 5)) == 0.0
    assert R._ascent_ft(R._smooth(spiked, 5)) < 1.0 * M


def test_smooth_preserves_a_real_climb():
    """A sustained rise is terrain, not noise, and must survive smoothing.

    Not an exact figure: clamping the edges pulls the first and last smoothed
    samples toward the interior, so a short ramp loses a little rise at each end.
    What matters is that a genuine climb is retained rather than smoothed away,
    which is the failure mode the diagnostics depend on.
    """
    ramp = [100.0 + i * 1.0 for i in range(12)]
    true_rise_ft = 11.0 * M
    got = R._ascent_ft(R._smooth(ramp, 5))
    assert got > 0.7 * true_rise_ft
    assert got <= true_rise_ft


# --------------------------------------------------------------- _ascent_ft

def test_ascent_sums_only_upward_steps():
    up_then_down = [0.0, 10.0, 20.0, 15.0, 5.0]
    assert R._ascent_ft(up_then_down) == pytest.approx(20.0 * M)


def test_ascent_ignores_descent():
    assert R._ascent_ft([100.0, 90.0, 80.0, 70.0]) == 0.0


def test_ascent_of_a_flat_series_is_zero():
    assert R._ascent_ft([42.0] * 50) == 0.0


def test_ascent_of_a_single_sample_is_unknown_not_zero():
    """One sample has no steps to sum. Reporting 0 would claim a flat run."""
    assert R._ascent_ft([100.0]) is None
    assert R._ascent_ft([]) is None


def test_ascent_of_a_flat_run_is_distinct_from_a_missing_one():
    """Zero climb is a real observation; None means we could not measure it."""
    assert R._ascent_ft([100.0, 100.0]) == 0.0
    assert R._ascent_ft([100.0]) is None


# ------------------------------------------------- diagnostics on a real row

@requires_real_fit
def test_a_real_row_carries_the_elevation_diagnostics():
    row = R.read_fit(REAL_FIT[0])
    assert row is not None
    assert row["_ascent_samples"] >= 2
    assert row["_elev_range_ft"] >= 0
    assert row["_ascent_smoothed_ft"] is not None
    assert row["_ascent_raw_ft"] is not None


@requires_real_fit
def test_the_published_figure_is_still_the_device_value():
    """The CSV contract must not silently switch to a number we invented."""
    row = R.read_fit(REAL_FIT[0])
    assert row["Source"] == "Garmin FIT"
    assert isinstance(row["Total Ascent"], int)


@requires_real_fit
def test_raw_sum_is_never_below_the_smoothed_sum_for_the_real_corpus():
    """Smoothing can only remove noise, never invent climb. If this ever fails
    the smoothing window is wrong."""
    for path in REAL_FIT[:12]:
        row = R.read_fit(path)
        if not row or row["_ascent_raw_ft"] == "":
            continue
        assert row["_ascent_raw_ft"] >= row["_ascent_smoothed_ft"]


@requires_real_fit
def test_every_real_activity_has_a_sane_ratio_of_ascent_to_range():
    """The signal that caught the 16-mile run: 1765 ft of climb inside an 84 ft
    range. That is not proof of error, so this asserts only that the diagnostics
    exist to make such a case reviewable, and that the reader did not divide by
    zero or produce nonsense.
    """
    for path in REAL_FIT:
        row = R.read_fit(path)
        if not row or not row["_elev_range_ft"]:
            continue
        assert row["Total Ascent"] >= 0
        assert row["_ascent_smoothed_ft"] >= 0


# ------------------------------------------- one series per record, not two

def test_a_record_carrying_both_altitude_series_yields_one_sample(monkeypatch):
    """Regression: the reader used to append enhanced_altitude AND altitude from
    the same record, interleaving two series into one list. They are identical on
    current firmware so min/max were unaffected, but on firmware where they
    diverge it would take a minimum from one series and a maximum from the other.
    """
    rec = FakeMessage([("timestamp", 1000),
                       ("altitude", 100.0),
                       ("enhanced_altitude", 200.0)])
    fit = FakeFitFile(records=[rec], sessions=[session()])
    monkeypatch.setattr(R.fitparse, "FitFile", lambda p: fit)
    row = R.read_fit("ignored.fit")
    assert row["_ascent_samples"] == 1
    assert row["Max Elevation"] == round(200.0 * M)  # enhanced preferred
    assert row["Min Elevation"] == round(200.0 * M)  # not a blend of 100 and 200


def test_altitude_is_used_when_enhanced_is_absent(monkeypatch):
    rec = FakeMessage([("timestamp", 1000), ("altitude", 150.0)])
    fit = FakeFitFile(records=[rec], sessions=[session()])
    monkeypatch.setattr(R.fitparse, "FitFile", lambda p: fit)
    row = R.read_fit("ignored.fit")
    assert row["_ascent_samples"] == 1
    assert row["Max Elevation"] == round(150.0 * M)


def test_a_file_with_no_altitude_yields_empty_diagnostics(monkeypatch):
    rec = FakeMessage([("timestamp", 1000), ("enhanced_speed", 3.0)])
    fit = FakeFitFile(records=[rec], sessions=[session()])
    monkeypatch.setattr(R.fitparse, "FitFile", lambda p: fit)
    row = R.read_fit("ignored.fit")
    assert row["_ascent_samples"] == 0
    assert row["_ascent_smoothed_ft"] == ""
    assert row["_ascent_raw_ft"] == ""
    assert row["Min Elevation"] == ""
    assert row["Max Elevation"] == ""


def test_the_diagnostic_keys_do_not_trip_the_gps_guard(monkeypatch):
    """assert_no_gps scans key names for lat/lon/position/gps. The new keys must
    not accidentally match, and must not weaken the guard."""
    rec = FakeMessage([("timestamp", 1000), ("altitude", 10.0)])
    fit = FakeFitFile(records=[rec], sessions=[session()])
    monkeypatch.setattr(R.fitparse, "FitFile", lambda p: fit)
    row = R.read_fit("ignored.fit")
    for k in ("_elev_range_ft", "_ascent_smoothed_ft", "_ascent_raw_ft",
              "_ascent_samples"):
        assert k in row
        assert not any(b in k.lower() for b in ("lat", "lon", "position", "gps"))


def test_gps_guard_still_rejects_a_real_position_key():
    with pytest.raises(AssertionError):
        R.assert_no_gps({"Distance": 1.0, "start_position_lat": 12.3})


def test_reader_version_moved_for_the_new_derived_fields():
    """fit_audit records the reader version so a result names the code that
    produced it. The elevation diagnostics change what the reader means."""
    assert R.__version__ != "1.0.0"
    assert R.ELEV_SMOOTH_SAMPLES == 5
