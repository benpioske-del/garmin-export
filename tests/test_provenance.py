"""Task 2: timestamp, provenance and timezone-status behaviour."""

import csv
import datetime
import os

import pytest

import garmin_fit_reader as r
from conftest import REAL_FIT, requires_real_fit

UTC = datetime.timezone.utc

CANON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "garmin_export.csv")


@pytest.fixture(scope="module")
def real_rows():
    """Rows of the actually-published export, when it has been built.

    Asserting on the real artifact catches wiring mistakes that a unit test on a
    hand-made dict cannot.
    """
    if not os.path.exists(CANON):
        pytest.skip("no published export yet; run export_publish.py")
    with open(CANON, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_naive_fit_start_is_treated_as_utc():
    """fitparse hands back a naive datetime; UTC must be attached explicitly."""
    naive = datetime.datetime(2026, 4, 14, 19, 1, 36)
    local, utc = r.split_start(naive, "2026-04-14_22528049459.fit")
    assert utc.tzinfo is UTC
    assert utc.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-04-14T19:01:36Z"


def test_local_date_comes_from_filename_not_utc():
    """The known-bad run: 01:10 UTC on the 27th is an evening run on the 26th."""
    naive = datetime.datetime(2026, 7, 27, 1, 10, 15)
    local, utc = r.split_start(naive, "2026-07-26_23745136848.fit")
    assert local.strftime("%Y-%m-%d %H:%M:%S") == "2026-07-26 01:10:15"
    assert utc.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-07-27T01:10:15Z"
    assert local.strftime("%Y-%m-%d") != utc.strftime("%Y-%m-%d")


def test_midday_run_keeps_its_date():
    naive = datetime.datetime(2026, 5, 8, 20, 7, 0)
    local, _ = r.split_start(naive, "2026-05-08_22813434784.fit")
    assert local.strftime("%Y-%m-%d") == "2026-05-08"


@pytest.mark.parametrize("name", [
    "not-a-fit-name.fit",
    "2026-13-45_123.fit",      # unparseable date
    "20260414_123.fit",        # no underscore separator
])
def test_bad_filename_falls_back_to_utc_date(name):
    """A renamed file must not crash or silently invent a local date."""
    naive = datetime.datetime(2026, 4, 14, 19, 1, 36)
    local, utc = r.split_start(naive, name)
    assert local.strftime("%Y-%m-%d") == utc.strftime("%Y-%m-%d")
    assert utc.tzinfo is UTC


def test_aware_start_is_respected_not_reinterpreted():
    """A tz-aware value must keep its own offset, not be overwritten."""
    aware = datetime.datetime(2026, 7, 27, 1, 10, 15, tzinfo=UTC)
    _, utc = r.split_start(aware, "2026-07-26_23745136848.fit")
    assert utc.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-07-27T01:10:15Z"


def test_timezone_status_is_never_silently_known():
    """The label must admit the assumption rather than claim certainty."""
    assert "assumed" in r.TZ_ASSUMED_UTC
    assert "utc" in r.TZ_ASSUMED_UTC.lower()


@requires_real_fit
def test_read_fit_emits_provenance_columns():
    row = r.read_fit(REAL_FIT[0])
    assert row is not None
    for col in ("Date", "Date (UTC)", "Timezone Status", "Source", "_source_file"):
        assert col in row, "missing provenance column %r" % col
    assert row["Source"] == "Garmin FIT"
    assert row["Date (UTC)"].endswith("Z")
    # Internal key and published name must stay distinguishable.
    assert row["_source_file"] == os.path.basename(REAL_FIT[0])


@requires_real_fit
def test_no_published_column_does_not_look_like_a_coordinate():
    """Provenance must not become a covert location channel."""
    row = r.read_fit(REAL_FIT[0])
    for k in row:
        assert not any(b in k.lower() for b in ("lat", "lon", "gps", "position"))


def test_provenance_survives_the_public_csv_header():
    """Renaming _source_file must happen at write time, not lose the value.

    Regression guard for a real bug: fieldnames and row keys must be renamed
    together, and the row filter must test the *published* name. Filtering on
    the internal key drops every value and emits a blank column.
    """
    row = {"Date": "2026-07-26 01:10:15", "Date (UTC)": "2026-07-27T01:10:15Z",
           "Timezone Status": "assumed_utc", "Source": "Garmin FIT",
           "_source_file": "2026-07-26_23745136848.fit"}
    internal = list(row)
    header = {"_source_file": "Source File"}
    cols = [header.get(c, c) for c in internal]

    assert "Source File" in cols and "_source_file" not in cols

    out = {header.get(k, k): v for k, v in row.items()
           if header.get(k, k) in cols}
    assert out["Source File"] == "2026-07-26_23745136848.fit"


def test_every_provenance_column_carries_a_value(real_rows):
    """Blank provenance is worse than none: it looks like a device gave no data."""
    for r in real_rows:
        for col in ("Date (UTC)", "Timezone Status", "Source", "Source File"):
            assert r.get(col, "").strip(), \
                "%s blank for %s" % (col, r.get("Source File"))


def test_published_header_uses_the_public_column_name(real_rows):
    """The internal _source_file key must never reach the published header."""
    assert "Source File" in real_rows[0]
    assert "_source_file" not in real_rows[0]


def test_no_two_rows_are_the_same_activity(real_rows):
    """The corrected date must not have collapsed two genuinely different runs.

    Dedupe keys on date + rounded distance, so two real activities sharing a
    date and distance would silently lose one. The count is asserted because
    dropping a phantom duplicate (57 -> 56) was a fix, but a real loss would
    look identical in the log.

    The expected count comes from the FIT files on disk rather than a literal,
    because the athlete adds runs. A hardcoded number turns every new activity
    into a test failure, which trains you to ignore this check; deriving it keeps
    the property that actually matters, which is that nothing was lost between
    the FIT files and the published CSV.
    """
    keys = [(r["Date"][:10], round(float(r["Distance"]), 1)) for r in real_rows]
    assert len(keys) == len(set(keys)), "duplicate date+distance in the export"

    expected = len(REAL_FIT)
    assert len(real_rows) == expected, (
        "published %d rows but %d FIT files on disk: %s"
        % (len(real_rows), expected,
           "an activity was lost or duplicated in the export"
           if len(real_rows) < expected else
           "the export has rows with no FIT file behind them"))


def test_corrected_run_is_dated_to_its_local_day(real_rows):
    """The FIT 2026-07-27 01:10Z run is an evening run on 2026-07-26."""
    hit = [r for r in real_rows
           if r["Source File"] == "2026-07-26_23745136848.fit"]
    assert len(hit) == 1, "expected exactly one row for the corrected run"
    row = hit[0]
    assert row["Date"].startswith("2026-07-26")
    assert row["Date (UTC)"].startswith("2026-07-27T01:10:15")
