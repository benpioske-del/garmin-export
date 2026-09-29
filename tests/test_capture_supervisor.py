"""Tests for the supervisor brief capture and its publication safety scan.

The brief is LLM-generated text. It is scanned before it is written, because
the repository is public and the brief is not trusted input.
"""

import pytest

from capture_supervisor_brief import scan


CLEAN = (
    "1. Add a resting heart rate trend.\n"
    "2. The 9/20 tempo run was 4.61 pace at 88F, slower than the 4.52\n"
    "   baseline.\n"
    "3. Splits were 4.52, 4.48, 4.61 over three miles.\n"
    "4. Add strength session logging for squat and deadlift.\n"
)


@pytest.mark.parametrize("text", [CLEAN])
def test_normal_brief_text_passes(text):
    assert scan(text) == []


@pytest.mark.parametrize("text,kind", [
    ("Use ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 to push", "GitHub token"),
    ("key sk-abcdefghijklmnopqrstuvwxyz12345", "OpenAI-style secret key"),
    ("AKIAIOSFODNN7EXAMPLE is the key", "AWS access key id"),
    ('api_key = "7f3b9c1e5a2d84bf6c0e1d7a4b3c2f19"', "assigned secret"),
    ("Authorization: Bearer abcdefghijklmnopqrstuvwx", "authorization header"),
    ("mail the report to runner@example.com", "email address"),
])
def test_secrets_are_caught(text, kind):
    hits = scan(text)
    assert kind in [k for k, _ in hits], "missed: %s" % text


@pytest.mark.parametrize("text,kind", [
    ("The run started at 41.6001, -30.5001 out at sea.", "lat/lon coordinate pair (west)"),
    ("Track was at -33.8688, 151.2093.", "lat/lon coordinate pair (south)"),
    ("Add position_lat to the export.", "FIT GPS field name"),
    ("latitude: 41.6001", "latitude value"),
    ("longitude = -30.5001", "longitude value"),
])
def test_gps_is_caught(text, kind):
    hits = scan(text)
    assert kind in [k for k, _ in hits], "missed: %s" % text


def test_labelled_positive_pair_is_still_caught():
    """The unlabelled rule needs a minus sign, so the labelled forms must
    cover the all-positive case."""
    assert scan("latitude: 41.6001, longitude: -30.5001")
    assert scan("lat = 41.6001")


def test_pace_splits_are_not_mistaken_for_coordinates():
    """Decimals are everywhere in training data and must not false-positive."""
    assert scan("Splits 4.52, 4.48, 4.61 over 4.11 miles") == []
    assert scan("Lap times 5.0712, 5.0844, 5.1123") == []
    assert scan("Pace 4.5612, 4.5844, 4.6123 per km") == []


def test_scanner_reports_sample_not_whole_secret():
    text = "token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 end"
    hits = scan(text)
    assert hits
    kind, sample = hits[0]
    assert "..." in sample
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in sample


def test_brief_filenames_are_restricted():
    """An arbitrary name could shadow CREW_TASKS.md or the tasks directory."""
    import capture_supervisor_brief as c
    assert set(c.ALLOWED_NAMES) == {"SUPERVISOR_BRIEF.md", "TASKS.md"}
    assert "CREW_TASKS.md" not in c.ALLOWED_NAMES
