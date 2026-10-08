"""Measured 5 km crossing and lap splits.

Task 002 asked for a verifiable 5K mark. A projection from whole-run average
pace is not one; the crossing time of the distance curve is. These tests pin
that `_best_5k_seconds` reads the curve (distance + timestamps), that it never
touches position fields, and that a run which never reaches 5 km reports no
crossing instead of inventing one.
"""

from datetime import datetime, timedelta, timezone

import garmin_fit_reader as r
from conftest import FakeFitFile, FakeMessage

START = datetime(2026, 6, 16, 19, 26, 37, tzinfo=timezone.utc)


def _records(distances, seconds_step):
    return [
        FakeMessage([("timestamp", START + timedelta(seconds=i * seconds_step)),
                     ("distance", float(d))])
        for i, d in enumerate(distances)
    ]


def test_crossing_time_comes_from_the_distance_curve():
    """Second record past 5000 m is the crossing; earlier records are ignored."""
    recs = _records([0.0, 2500.0, 5000.0, 5200.0], seconds_step=600)
    assert r._best_5k_seconds(FakeFitFile(records=recs), START) == 1200


def test_run_shorter_than_5k_has_no_crossing():
    recs = _records([0.0, 2000.0, 4000.0], seconds_step=100)
    assert r._best_5k_seconds(FakeFitFile(records=recs), START) is None


def test_no_start_means_no_crossing():
    recs = _records([0.0, 5000.0], seconds_step=50)
    assert r._best_5k_seconds(FakeFitFile(records=recs), None) is None


def test_crossing_never_reads_position_fields():
    """The distance curve must not become a covert coordinate channel."""
    recs = [
        FakeMessage([("timestamp", START), ("distance", 0.0),
                     ("position_lat", 100000000), ("position_long", -50000000)]),
        FakeMessage([("timestamp", START + timedelta(seconds=60)),
                     ("distance", 5000.0),
                     ("position_lat", 100000001), ("position_long", -50000001)]),
    ]
    assert r._best_5k_seconds(FakeFitFile(records=recs), START) == 60


def test_non_monotonic_distance_uses_first_crossing():
    """A spurious later record cannot rewrite the crossing backwards."""
    recs = [
        FakeMessage([("timestamp", START), ("distance", 0.0)]),
        FakeMessage([("timestamp", START + timedelta(seconds=61)),
                     ("distance", 5000.0)]),
        FakeMessage([("timestamp", START + timedelta(seconds=10)),
                     ("distance", 10.0)]),
    ]
    assert r._best_5k_seconds(FakeFitFile(records=recs), START) == 61


# --- per-mile splits from the distance curve ---------------------------------

def test_mile_splits_come_from_the_distance_curve():
    recs = _records([0.0, 1609.344, 3218.688, 4828.032], seconds_step=360)
    assert r._mile_splits(FakeFitFile(records=recs), START) == \
        ["6:00", "6:00", "6:00"]


def test_mile_splits_are_segments_not_cumulative_times():
    recs = _records([0.0, 1609.344, 3218.688, 4828.032], seconds_step=300)
    assert r._mile_splits(FakeFitFile(records=recs), START) == \
        ["5:00", "5:00", "5:00"]


def test_mile_splits_need_a_start_and_a_full_mile():
    recs = _records([0.0, 1000.0], seconds_step=300)
    assert r._mile_splits(FakeFitFile(records=recs), None) == []
    assert r._mile_splits(FakeFitFile(records=[]), START) == []
    assert r._mile_splits(FakeFitFile(records=recs), START) == []


def test_mile_splits_skip_non_datetime_timestamps_without_crashing():
    recs = [
        FakeMessage([("timestamp", START), ("distance", 0.0)]),
        FakeMessage([("timestamp", "not a time"), ("distance", 1609.344)]),
        FakeMessage([("timestamp", START + timedelta(seconds=90)),
                     ("distance", 1609.344)]),
    ]
    assert r._mile_splits(FakeFitFile(records=recs), START) == ["1:30"]


def test_mile_splits_do_not_repeat_after_a_backward_distance_read():
    recs = [
        FakeMessage([("timestamp", START), ("distance", 0.0)]),
        FakeMessage([("timestamp", START + timedelta(seconds=300)),
                     ("distance", 1609.344)]),
        FakeMessage([("timestamp", START + timedelta(seconds=400)),
                     ("distance", 20.0)]),
        FakeMessage([("timestamp", START + timedelta(seconds=700)),
                     ("distance", 3218.688)]),
    ]
    assert r._mile_splits(FakeFitFile(records=recs), START) == \
        ["5:00", "6:40"]