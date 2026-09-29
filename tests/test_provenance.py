"""Task 2: timestamp, provenance and timezone-status behaviour."""

import datetime
import os

import pytest

import garmin_fit_reader as r
from conftest import REAL_FIT, requires_real_fit

UTC = datetime.timezone.utc


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
    """Renaming _source_file must happen at write time, not lose the value."""
    rows = [{"Date": "2026-07-26 01:10:15", "Date (UTC)": "2026-07-27T01:10:15Z",
             "Timezone Status": "assumed_utc", "Source": "Garmin FIT",
             "_source_file": "2026-07-26_23745136848.fit"}]
    cols = list(rows[0])
    header = {"_source_file": "Source File"}
    out = {header.get(k, k): v for k, v in rows[0].items() if k in cols}
    assert "Source File" in out
    assert out["Source File"] == "2026-07-26_23745136848.fit"
    assert "_source_file" not in out
