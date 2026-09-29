"""Tests for the GPS content guard.

The guard exists because a file named index.html carrying exact per-run
coordinates was committed to a public repository. Checking file names was not
enough; the content has to be inspected.
"""

import os

import pytest

import export_publish


COORDS = '{"seq": 50, "lat": 41.6001, "lon": -30.5001, "tempF": 92.3}'


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """Point the guard at a throwaway directory."""
    monkeypatch.setattr(export_publish, "REPO", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write(repo, rel, body):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_bare_json_coordinates_are_refused(fake_repo, capsys):
    write(fake_repo, "leak.js", COORDS)
    with pytest.raises(SystemExit):
        export_publish.guard_gps_content()
    # die() prints the reason and exits, so the explanation is on stdout.
    out = capsys.readouterr().out
    assert "lat" in out and "public" in out


def test_latitude_longitude_keys_are_refused(fake_repo):
    write(fake_repo, "leak.json", '{"latitude": 41.6001, "longitude": -30.5001}')
    with pytest.raises(SystemExit):
        export_publish.guard_gps_content()


def test_fit_position_field_names_are_refused(fake_repo):
    """Naming the field is only a problem when a value accompanies it."""
    write(fake_repo, "leak.py",
          "FIELDS = ['position_lat', 'position_long']\n"
          "SAMPLE = {'position_lat': 838498115, 'position_long': -1677263123}\n")
    with pytest.raises(SystemExit):
        export_publish.guard_gps_content()


def test_mentioning_the_field_name_in_prose_is_fine(fake_repo):
    """The brief documents that GPS is excluded. Naming the field is safe."""
    write(fake_repo, "CREW_BRIEF.md",
          "**No GPS coordinates.** The source `.FIT` files contain "
          "`position_lat/long` and `nec_lat/long` fields; they are deliberately "
          "not published.\n")
    write(fake_repo, "garmin_fit_reader.py",
          "FORBIDDEN = {'position_lat', 'position_long', 'nec_lat'}\n")
    export_publish.guard_gps_content()  # must not raise


def test_local_only_dashboard_is_skipped(fake_repo):
    write(fake_repo, "dashboard/index.html", COORDS)
    export_publish.guard_gps_content()  # must not raise


def test_ordinary_pipeline_code_passes(fake_repo):
    write(fake_repo, "export_publish.py", "distance = 4.9588\npace = 9.6123\n")
    write(fake_repo, "README.md", "Pace splits of 5.0712 and 5.0844 are normal.")
    export_publish.guard_gps_content()  # must not raise


def test_pace_splits_do_not_trip_the_guard(fake_repo):
    """Training data is full of decimals. Only labelled keys count."""
    write(fake_repo, "notes.md",
          "Splits 4.52, 4.48, 4.61 per mile; laps 5.0712, 5.0844, 5.1123.")
    export_publish.guard_gps_content()  # must not raise


def test_published_csv_with_coordinates_would_be_refused(fake_repo):
    write(fake_repo, "garmin_export.csv", "Date,lat,lon\n2026-09-01,44.75,-93.62\n")
    with pytest.raises(SystemExit):
        export_publish.guard_gps_content()
