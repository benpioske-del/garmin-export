"""Tests for path resolution and the publish safety guards.

These are the two places where a mistake leaks athlete data or credentials into
a public repository, so they are worth pinning down.
"""

import os

import pytest

import paths


# --- path resolution -------------------------------------------------------

def test_data_dir_defaults_outside_the_repo(monkeypatch):
    monkeypatch.delenv("GARMIN_DATA_DIR", raising=False)
    d = paths.data_dir()
    assert os.path.isabs(d)
    assert not os.path.isdir(os.path.join(d, ".git"))


def test_data_dir_honours_override(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path))
    assert paths.data_dir() == str(tmp_path)


def test_fit_dir_defaults_under_data_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("GARMIN_FIT_DIR", raising=False)
    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path))
    assert paths.fit_dir() == os.path.join(str(tmp_path), "garmin_fit")


def test_fit_dir_can_be_overridden_independently(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GARMIN_FIT_DIR", str(tmp_path / "elsewhere"))
    assert paths.fit_dir() == str(tmp_path / "elsewhere")


def test_repo_dir_prefers_its_own_directory(monkeypatch):
    """Now that the code lives in the repo, it must publish into itself."""
    monkeypatch.delenv("GARMIN_REPO", raising=False)
    here = os.path.dirname(os.path.abspath(paths.__file__))
    if os.path.isdir(os.path.join(here, ".git")):
        assert paths.repo_dir() == here


def test_repo_dir_honours_override(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_REPO", str(tmp_path))
    assert paths.repo_dir() == str(tmp_path)


def test_known_sensitive_names_are_declared():
    """Everything garmin_sync.py writes locally must be in the ignore list."""
    for name in ("garmin_sleep.csv", "garmin_hr.csv", "garmin_last_sync.json"):
        assert name in paths.DATA_FILES
    assert ".garmin_tokens" in paths.DATA_SUBDIRS


# --- the publish guard -----------------------------------------------------

def test_publisher_blocks_credentials_and_raw_fit():
    import export_publish
    body = export_publish.IGNORE
    assert ".garmin_tokens/" in body
    assert "*.fit" in body
    assert ".env" in body
    # These two are written next to garmin_sync.py's data dir and contain
    # health information. They were not in the ignore list until the pipeline
    # was moved into the repository.
    assert "garmin_sleep.csv" in body
    assert "garmin_hr.csv" in body


def test_published_csv_carries_no_gps_or_health_columns():
    """Assert against the real published header, not a copy of it."""
    import csv
    import export_publish
    canon = os.path.join(export_publish.REPO, export_publish.CANON)
    if not os.path.exists(canon):
        pytest.skip("no published CSV yet")
    with open(canon, newline="", encoding="utf-8-sig") as fh:
        header = next(csv.reader(fh))
    lowered = [c.lower() for c in header]
    for bad in ("position_lat", "position_long", "lat", "lon", "longitude",
                "latitude", "temperature", "humidity", "sleep", "hrv",
                "rhr", "weather", "wind"):
        assert bad not in lowered, "%s must never be published" % bad
