"""Automatic timezone confirmation is explicit, DST-aware and audited.

FIT files carry no UTC offset. Newly synced runs used to keep an open review
forever, which made coaching refuse every signal. The athlete's confirmed US
Central zone now lets the import confirm those local dates, but only when the
policy is explicitly present in profile.json. No offset is guessed and no
confirmation is silent.
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import activities  # noqa: E402
import terms  # noqa: E402
import trainingdb  # noqa: E402


@pytest.fixture()
def db():
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.unlink(path)
    conn = trainingdb.connect(path)
    trainingdb.migrate(conn, verbose=False)
    yield conn
    conn.close()
    os.unlink(path)


def provisional_row(day, hour=18):
    return {
        "Activity Type": "Running",
        "Date": "%s %02d:00:00" % (day, hour),
        "Date (UTC)": "%sT%02d:00:00Z" % (day, hour),
        "Timezone Status": "assumed_utc; local date from filename",
        "Source": "Garmin FIT",
        "Distance": 6.0,
        "Moving Time": "0:40:00",
        "Elapsed Time": "0:45:00",
        "Avg HR": 150,
        "Max HR": 160,
        # The activity id comes from the filename's native id; keep it unique
        # so these two fixtures are two rows, not an update of one.
        "_source_file": "%s_%s.fit" % (day, day.replace("-", "")),
    }


def test_policy_requires_an_explicit_confirmation(monkeypatch, tmp_path):
    path = tmp_path / "profile.json"
    monkeypatch.setattr(activities.paths, "repo_dir", lambda: str(tmp_path))
    path.write_text(json.dumps({"timezone_policy": "America/Chicago"}),
                    encoding="utf-8")
    assert activities.timezone_policy() is None

    path.write_text(json.dumps({
        "timezone_policy": "America/Chicago",
        "timezone_policy_confirmed_utc": "2026-11-24",
    }), encoding="utf-8")
    assert activities.timezone_policy() == "America/Chicago"

    path.write_text("{not json", encoding="utf-8")
    assert activities.timezone_policy() is None


def test_offsets_follow_the_current_us_dst_rule():
    zone = "America/Chicago"
    assert activities.offset_for_policy(zone, "2026-01-15T18:00:00Z") == -6
    assert activities.offset_for_policy(zone, "2026-07-15T18:00:00Z") == -5
    # Transitions are UTC instants: 2:00 local on each changeover Sunday.
    assert activities.offset_for_policy(zone, "2026-03-08T07:59:00Z") == -6
    assert activities.offset_for_policy(zone, "2026-03-08T08:00:00Z") == -5
    assert activities.offset_for_policy(zone, "2026-11-01T06:59:00Z") == -5
    assert activities.offset_for_policy(zone, "2026-11-01T07:00:00Z") == -6
    # An unknown zone and an unparseable timestamp are not reasons to guess.
    assert activities.offset_for_policy("UTC", "2026-07-15T18:00:00Z") is None
    assert activities.offset_for_policy(zone, "not a date") is None


def test_auto_confirm_is_dst_aware_idempotent_and_audited(db):
    aid_winter, _ = activities.upsert_activity(db, provisional_row("2026-01-15"))
    aid_summer, _ = activities.upsert_activity(db, provisional_row("2026-07-15"))

    first = activities.auto_confirm_timezones(db, zone="America/Chicago")
    assert first == {"zone": "America/Chicago", "confirmed": 2}

    winter = db.execute("SELECT * FROM activities WHERE activity_id = ?",
                        (aid_winter,)).fetchone()
    summer = db.execute("SELECT * FROM activities WHERE activity_id = ?",
                        (aid_summer,)).fetchone()
    assert winter["timezone_source"] == terms.TZ_CONFIRMED_OFFSET
    assert winter["start_local"] == "2026-01-15T12:00:00"
    assert summer["start_local"] == "2026-07-15T13:00:00"
    for aid in (aid_winter, aid_summer):
        assert not db.execute(
            "SELECT 1 FROM review_items WHERE activity_id = ? AND state = ?",
            (aid, terms.OPEN)).fetchone()
        prov = db.execute(
            "SELECT * FROM activity_field_provenance WHERE activity_id = ? "
            "AND field_name = 'start_local'", (aid,)).fetchone()
        assert prov["value_state"] == terms.ATHLETE_REPORTED

    rows = db.execute(
        "SELECT * FROM activity_import_audit WHERE event = 'timezone_confirmed' "
        "ORDER BY audit_id").fetchall()
    assert len(rows) == 2
    assert all(r["actor"] == "autoconfirm" for r in rows)
    assert all("policy America/Chicago" in r["reason"] for r in rows)

    second = activities.auto_confirm_timezones(db, zone="America/Chicago")
    assert second["confirmed"] == 0
    assert db.execute(
        "SELECT COUNT(*) c FROM activity_import_audit "
        "WHERE event = 'timezone_confirmed'").fetchone()["c"] == 2


def test_no_policy_leaves_the_review_open(db, monkeypatch):
    aid, _ = activities.upsert_activity(db, provisional_row("2026-07-15"))
    monkeypatch.setattr(activities, "timezone_policy", lambda: None)
    result = activities.auto_confirm_timezones(db)
    assert result == {"zone": None, "confirmed": 0}
    rec = db.execute("SELECT * FROM activities WHERE activity_id = ?",
                     (aid,)).fetchone()
    assert rec["timezone_source"] == terms.TZ_FILENAME_DATE
    assert db.execute(
        "SELECT 1 FROM review_items WHERE activity_id = ? AND state = ?",
        (aid, terms.OPEN)).fetchone()


def test_import_dir_confirms_before_gap_detection(db, monkeypatch):
    """Every import path (CLI, /sync, nightly) goes through this choke point."""
    calls = []
    monkeypatch.setattr("glob.glob", lambda pattern: [])
    monkeypatch.setattr(activities, "auto_confirm_timezones",
                        lambda conn: calls.append(conn) or {"confirmed": 0})
    activities.import_dir("no-such-fit/*.fit", db)
    assert calls == [db]
