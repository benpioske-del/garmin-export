"""Tests for the manual run sidecar behind the dashboard quick-log form.

The quick log used to write only to localStorage: the entry vanished on reload
and a Garmin sync never saw it. These tests pin the replacement contract:

  * a typed run is validated rather than stored as a guess,
  * one entry per date, so re-saving replaces instead of stacking,
  * it is merged into /api/activities as a clearly manual row,
  * a device activity on the same day hides the typed copy,
  * it never becomes a canonical activity (loadcalc reads the table only).
"""

import json

import pytest

import manual_runs


def _payload(**over):
    row = {
        "date": "2026-11-16",
        "distance": 5.0,
        "time": "45:00",
        "hr": 150,
        "rpe": 6,
    }
    row.update(over)
    return row


# --------------------------------------------------------------- duration

@pytest.mark.parametrize("text,seconds", [
    ("45:00", 2700),
    ("1:02:03", 3723),
    ("2700", 2700),
    ("0:30", 30),
    (2700, 2700),
    (45.4, 45),
])
def test_parse_duration_accepts_the_shapes_a_runner_types(text, seconds):
    assert manual_runs.parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", None, "abc", "1:2:3:4", "0:00", "-5:00"])
def test_parse_duration_rejects_what_it_cannot_read(text):
    assert manual_runs.parse_duration(text) is None


# --------------------------------------------------------------- validation

def test_normalize_builds_one_row_per_date():
    row = manual_runs.normalize(_payload())
    assert row["activity_id"] == "manual:2026-11-16"
    assert row["date"] == "2026-11-16"
    assert row["distance_mi"] == 5.0
    assert row["moving_time_s"] == 2700
    assert row["avg_pace_s_per_mi"] == 540
    assert row["avg_hr"] == 150
    assert row["rpe"] == 6
    assert row["logged_utc"].endswith("Z")


def test_normalize_treats_missing_hr_and_rpe_as_absent_not_zero():
    row = manual_runs.normalize(
        {"date": "2026-11-16", "distance_mi": 3, "seconds": 1800})
    assert row["avg_hr"] is None
    assert row["rpe"] is None


@pytest.mark.parametrize("bad", [
    {"date": "16/11/2026", "distance": 5, "time": "45:00"},
    {"date": "2026-02-30", "distance": 5, "time": "45:00"},
    {"date": "2026-11-16", "distance": 0, "time": "45:00"},
    {"date": "2026-11-16", "distance": 5, "time": "soon"},
    {"date": "2026-11-16", "distance": 5, "time": "45:00", "hr": 400},
    {"date": "2026-11-16", "distance": 5, "time": "45:00", "rpe": 11},
    {"date": "2026-11-16", "distance": 5, "time": "25:00:00"},
])
def test_normalize_refuses_impossible_entries(bad):
    with pytest.raises(manual_runs.ManualRunError):
        manual_runs.normalize(bad)


def test_normalize_refuses_a_non_object():
    with pytest.raises(manual_runs.ManualRunError):
        manual_runs.normalize(["not", "a", "run"])


# -------------------------------------------------------------------- store

def test_missing_and_corrupt_stores_read_as_empty(tmp_path):
    missing = tmp_path / "nope.json"
    assert manual_runs.load(str(missing)) == []
    corrupt = tmp_path / "bad.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert manual_runs.load(str(corrupt)) == []


def test_upsert_writes_atomically_and_sorts(tmp_path):
    path = str(tmp_path / "manual_runs.json")
    manual_runs.upsert(_payload(date="2026-11-16"), path)
    manual_runs.upsert(_payload(date="2026-11-10"), path)
    rows = manual_runs.load(path)
    assert [r["date"] for r in rows] == ["2026-11-10", "2026-11-16"]
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["version"] == 1
    assert not [n for n in tmp_path.iterdir() if n.name.startswith(".manual-")]


def test_upsert_same_date_replaces_instead_of_stacking(tmp_path):
    path = str(tmp_path / "manual_runs.json")
    manual_runs.upsert(_payload(distance=5), path)
    manual_runs.upsert(_payload(distance=7, time="1:05:00"), path)
    rows = manual_runs.load(path)
    assert len(rows) == 1
    assert rows[0]["distance_mi"] == 7
    assert rows[0]["moving_time_s"] == 3900


# ------------------------------------------------------------ merge into API

def _api_payload():
    return {
        "activities": [{
            "activity_id": "garmin:1",
            "source_system": "garmin",
            "start_utc": "2026-11-15T12:00:00Z",
            "start_local": "2026-11-15",
            "sport": "Running",
            "distance_mi": 4.0,
            "splits": [540, 550],
        }],
        "count": 1,
    }


def test_manual_rows_are_merged_and_labelled(tmp_path):
    path = str(tmp_path / "manual_runs.json")
    manual_runs.upsert(_payload(date="2026-11-16"), path)
    payload = manual_runs.merge(_api_payload(), path)
    assert payload["count"] == 2
    assert payload["manual_count"] == 1
    manual = [a for a in payload["activities"] if a["source_system"] == "manual"]
    assert len(manual) == 1
    assert manual[0]["manual"] is True
    assert manual[0]["start_local"] == "2026-11-16"
    assert manual[0]["splits"] is None
    assert manual[0]["avg_hr"] == 150
    # Newest first, same order the canonical route already uses.
    assert payload["activities"][0]["start_local"] == "2026-11-16"


def test_a_device_activity_on_the_same_day_hides_the_manual_copy(tmp_path):
    path = str(tmp_path / "manual_runs.json")
    manual_runs.upsert(_payload(date="2026-11-15"), path)
    payload = manual_runs.merge(_api_payload(), path)
    assert payload["count"] == 1
    assert payload["manual_count"] == 0
    assert all(a["source_system"] != "manual" for a in payload["activities"])


def test_merge_is_idempotent(tmp_path):
    path = str(tmp_path / "manual_runs.json")
    manual_runs.upsert(_payload(date="2026-11-16"), path)
    payload = manual_runs.merge(_api_payload(), path)
    again = manual_runs.merge(payload, path)
    assert again["count"] == 2
    assert again["manual_count"] == 1


def test_merge_without_a_store_leaves_the_payload_alone(tmp_path):
    payload = _api_payload()
    out = manual_runs.merge(payload, str(tmp_path / "missing.json"))
    assert out["count"] == 1
    assert out["manual_count"] == 0


def test_manual_rows_never_claim_device_provenance(tmp_path):
    path = str(tmp_path / "manual_runs.json")
    manual_runs.upsert(_payload(), path)
    row = manual_runs.activity_rows(set(), path)[0]
    assert row["value_state"] == "athlete_reported"
    assert row["source_file"] == "manual entry"
    assert row["timezone_source"] == "manual"
    assert row["review_state"] == "manual"
    assert row["has_open_review"] is False
