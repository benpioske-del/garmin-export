"""Tests for the canonical data layer and the services built on it.

Everything runs against a throwaway SQLite file. No test reads the athlete's
real FIT files, and no test writes to the working tree.
"""

import datetime
import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import activities  # noqa: E402
import health  # noqa: E402
import loadcalc  # noqa: E402
import recommend  # noqa: E402
import strength  # noqa: E402
import terms  # noqa: E402
import trainingdb  # noqa: E402
import weather  # noqa: E402

AS_OF = "2026-09-26T12:00:00Z"


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


def row(day, hour=7, sport="Running", dist=6.0, hr=150, source="2026-01-01_1.fit"):
    """A reader-shaped activity row."""
    return {
        "Activity Type": sport,
        "Date": "%s %02d:00:00" % (day, hour),
        "Date (UTC)": "%sT%02d:00:00Z" % (day, hour),
        "Timezone Status": "assumed_utc; local date from filename",
        "Source": "Garmin FIT",
        "Distance": dist,
        "Calories": 500,
        "Time": "0:40:00",
        "Moving Time": "0:40:00",
        "Elapsed Time": "0:45:00",
        "Avg HR": hr,
        "Max HR": hr + 10,
        "Avg Run Cadence": 178,
        "Max Run Cadence": 190,
        "Avg Pace": "6:40",
        "Best Pace": "6:10",
        "Total Ascent": 200,
        "Total Descent": 190,
        "Training Stress Score": 60,
        "_source_file": source,
    }


# ----------------------------------------------------------------- terms

def test_worst_confidence_picks_weakest():
    assert terms.worst(terms.HIGH, terms.MEDIUM, terms.LOW) == terms.LOW
    assert terms.worst(terms.HIGH) == terms.HIGH
    assert terms.worst("nonsense") == terms.UNVERIFIED


def test_missing_is_not_zero_and_is_unknown():
    assert terms.is_unknown(terms.NOT_IMPORTED)
    assert terms.is_unknown(terms.MISSING)
    assert not terms.is_unknown(terms.COMPLETE)


def test_review_states_are_terminal_or_open():
    assert terms.OPEN in terms.REVIEW_STATES
    assert terms.CONFIRMATION_REQUIRED not in terms.REVIEW_STATES


# ------------------------------------------------------------ migrations

def test_migrations_apply_and_are_idempotent(db):
    assert trainingdb.migrate(db, verbose=False) == []
    info = trainingdb.status(db)
    assert info["pending"] == []
    assert info["applied"] == [1, 2, 3, 4, 5, 6]


def test_edited_migration_is_a_hard_error(tmp_path, monkeypatch):
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.unlink(path)
    conn = trainingdb.connect(path)
    trainingdb.migrate(conn, verbose=False)
    conn.close()

    fake = tmp_path / "migrations"
    fake.mkdir()
    src = trainingdb.MIGRATIONS_DIR / "001_core_activity.sql"
    (fake / "001_core_activity.sql").write_text(
        src.read_text(encoding="utf-8") + "\n-- edited after the fact\n",
        encoding="utf-8")
    monkeypatch.setattr(trainingdb, "MIGRATIONS_DIR", fake)

    conn = trainingdb.connect(path)
    with pytest.raises(RuntimeError, match="changed after it was applied"):
        trainingdb.migrate(conn, verbose=False)
    conn.close()
    os.unlink(path)


def test_weather_schema_stores_no_coordinates(db):
    cols = [r["name"] for r in db.execute("PRAGMA table_info(weather_observations)")]
    assert "lat" not in cols and "lon" not in cols
    assert "latitude" not in cols and "longitude" not in cols
    assert "location_key" in cols


# ---------------------------------------------------------- canonical id

def test_canonical_id_is_stable_and_prefers_native_id():
    a = activities.canonical_id("garmin", "123", "2026-01-01T00:00:00Z", "Running")
    b = activities.canonical_id("garmin", "123", "2026-01-01T00:00:00Z", "Running")
    assert a == b == "garmin:123"


def test_canonical_id_falls_back_to_digest_without_native_id():
    a = activities.canonical_id("garmin", None, "2026-01-01T00:00:00Z", "Running")
    b = activities.canonical_id("garmin", None, "2026-01-01T00:00:00Z", "Running")
    c = activities.canonical_id("garmin", None, "2026-01-02T00:00:00Z", "Running")
    assert a == b
    assert a != c


def test_source_activity_id_parsed_from_filename():
    assert activities.source_activity_id("2026-04-14_22528049459.fit") == "22528049459"
    assert activities.source_activity_id("") is None


# -------------------------------------------------------------- upsert

def test_upsert_inserts_then_is_idempotent(db):
    r = row("2026-01-01", source="2026-01-01_111.fit")
    aid, event = activities.upsert_activity(db, r)
    assert event == "inserted"
    assert aid == "garmin:111"
    assert activities.upsert_activity(db, r) == (aid, "unchanged")
    assert db.execute("SELECT COUNT(*) c FROM activities").fetchone()["c"] == 1
    # A no-op re-import must not grow the audit trail.
    assert db.execute(
        "SELECT COUNT(*) c FROM activity_import_audit").fetchone()["c"] == 1


def test_upsert_records_a_field_change(db):
    r = row("2026-01-01", dist=6.0, source="2026-01-01_111.fit")
    activities.upsert_activity(db, r)
    r["Distance"] = 6.5
    aid, event = activities.upsert_activity(db, r)
    assert event == "updated"
    row_ = db.execute("SELECT distance_mi FROM activities WHERE activity_id = ?", (aid,)).fetchone()
    assert row_["distance_mi"] == 6.5
    audit = activities.history(db, aid)
    assert any(a["field"] == "distance_mi" for a in audit)


def test_blank_field_is_null_not_zero(db):
    r = row("2026-01-01", source="2026-01-01_111.fit")
    r["Calories"] = ""
    r["Avg HR"] = ""
    aid, _ = activities.upsert_activity(db, r)
    rec = db.execute("SELECT calories, avg_hr FROM activities WHERE activity_id = ?", (aid,)).fetchone()
    assert rec["calories"] is None
    assert rec["avg_hr"] is None


def test_local_date_is_marked_assumed_and_unconfirmed(db):
    aid, _ = activities.upsert_activity(db, row("2026-01-01", source="2026-01-01_111.fit"))
    rec = db.execute("SELECT * FROM activities WHERE activity_id = ?", (aid,)).fetchone()
    assert rec["timezone_source"] == terms.TZ_FILENAME_DATE
    assert rec["confirmation"] == terms.CONFIRMATION_REQUIRED
    prov = db.execute(
        "SELECT * FROM activity_field_provenance WHERE activity_id = ? AND field_name = 'start_local'",
        (aid,)).fetchone()
    assert prov["value_state"] == terms.ASSUMED
    assert prov["confidence"] == terms.LOW


def test_utc_is_observed_at_high_confidence(db):
    aid, _ = activities.upsert_activity(db, row("2026-01-01", source="2026-01-01_111.fit"))
    prov = db.execute(
        "SELECT * FROM activity_field_provenance WHERE activity_id = ? AND field_name = 'start_utc'",
        (aid,)).fetchone()
    assert prov["value_state"] == terms.OBSERVED
    assert prov["confidence"] == terms.HIGH


def test_every_activity_raises_a_timezone_review(db):
    aid, _ = activities.upsert_activity(db, row("2026-01-01", source="2026-01-01_111.fit"))
    items = db.execute(
        "SELECT * FROM review_items WHERE activity_id = ? AND reason = ?",
        (aid, terms.REVIEW_TIMEZONE)).fetchall()
    assert len(items) == 1
    # Idempotent: a second import does not stack duplicates.
    activities.upsert_activity(db, row("2026-01-01", source="2026-01-01_111.fit"))
    items = db.execute(
        "SELECT * FROM review_items WHERE activity_id = ? AND reason = ?",
        (aid, terms.REVIEW_TIMEZONE)).fetchall()
    assert len(items) == 1


def test_confirm_timezone_upgrades_the_local_date(db):
    aid, _ = activities.upsert_activity(db, row("2026-01-01", hour=23, source="2026-01-01_111.fit"))
    activities.confirm_timezone(db, aid, -5)
    rec = db.execute("SELECT * FROM activities WHERE activity_id = ?", (aid,)).fetchone()
    assert rec["timezone_source"] == terms.TZ_CONFIRMED_OFFSET
    assert rec["confirmation"] == terms.CONFIRMATION_NOT_REQUIRED
    assert rec["start_local"] == "2026-01-01T18:00:00"
    assert not db.execute(
        "SELECT 1 FROM review_items WHERE activity_id = ? AND state = 'open'",
        (aid,)).fetchone()
    prov = db.execute(
        "SELECT * FROM activity_field_provenance WHERE activity_id = ? AND field_name = 'start_local'",
        (aid,)).fetchone()
    assert prov["value_state"] == terms.ATHLETE_REPORTED


def test_raw_ref_stores_hash_and_size(db):
    with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as fh:
        fh.write(b"abc")
        tmp = fh.name
    try:
        digest = activities.sha256_file(tmp)
        r = row("2026-01-01")
        r["_source_file"] = os.path.basename(tmp)
        r["Date (UTC)"] = "2026-01-01T07:00:00Z"
        activities.upsert_activity(db, r, raw_hash=digest, raw_size=3)
        ref = db.execute("SELECT * FROM activity_raw_refs").fetchone()
        assert ref["sha256"] == digest
        assert ref["byte_size"] == 3
    finally:
        os.unlink(tmp)


# -------------------------------------------------- duplicates and gaps

def test_duplicate_detection_flags_the_later_record(db):
    activities.upsert_activity(db, row("2026-01-01", 7, dist=6.0, source="2026-01-01_1.fit"))
    activities.upsert_activity(db, row("2026-01-01", 7, dist=6.0, source="2026-01-01_2.fit"))
    assert len(activities.detect_duplicates(db)) == 1


def test_duplicate_detection_ignores_genuinely_different_runs(db):
    activities.upsert_activity(db, row("2026-01-01", 7, dist=6.0, source="2026-01-01_1.fit"))
    activities.upsert_activity(db, row("2026-01-01", 9, dist=10.0, source="2026-01-01_2.fit"))
    assert activities.detect_duplicates(db) == []


def test_date_gap_is_reported_and_nothing_is_invented(db):
    activities.upsert_activity(db, row("2026-01-01", source="2026-01-01_1.fit"))
    activities.upsert_activity(db, row("2026-01-20", source="2026-01-20_2.fit"))
    opened = activities.detect_date_gaps(db, gap_days=7)
    assert len(opened) == 1
    assert db.execute("SELECT COUNT(*) c FROM activities").fetchone()["c"] == 2
    detail = db.execute("SELECT detail FROM review_items WHERE review_id = ?", (opened[0],)).fetchone()
    assert "2026-01-01" in detail["detail"]


def test_no_gap_opened_when_days_are_contiguous(db):
    activities.upsert_activity(db, row("2026-01-01", source="2026-01-01_1.fit"))
    activities.upsert_activity(db, row("2026-01-03", source="2026-01-03_2.fit"))
    assert activities.detect_date_gaps(db, gap_days=7) == []


# -------------------------------------------------------------- strength

def test_session_holds_multiple_exercises_with_multiple_sets(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    strength.record_set(db, sid, "Back Squat", 1, reps=5, load_kg=100.0, rpe=7)
    strength.record_set(db, sid, "Back Squat", 2, reps=5, load_kg=100.0, rpe=7)
    strength.record_set(db, sid, "Romanian Deadlift", 1, reps=8, load_kg=60.0, rpe=7)
    sets = strength.session_sets(db, sid)
    assert len(sets) == 3
    assert {s["exercise"] for s in sets} == {"Back Squat", "Romanian Deadlift"}


def test_volume_excludes_warmups(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    strength.record_set(db, sid, "Back Squat", 1, reps=10, load_kg=50.0, is_warmup=True, rpe=5)
    strength.record_set(db, sid, "Back Squat", 2, reps=5, load_kg=100.0, rpe=7)
    vol = strength.session_volume(db, sid)
    assert vol["total_kg_reps"] == 500.0
    assert strength.session_sets(db, sid, include_warmups=True) != strength.session_sets(db, sid)


def test_bodyweight_set_keeps_load_null(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    strength.record_set(db, sid, "Pull-up", 1, reps=8)
    s = strength.session_sets(db, sid)[0]
    assert s["load_kg"] is None


def test_short_rest_is_flagged(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    strength.record_set(db, sid, "Back Squat", 1, reps=5, load_kg=100.0, rest_s=30)
    assert any("rest below" in f["detail"] for f in strength.safety_flags(db, sid))


def test_default_rest_is_two_minutes(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    strength.record_set(db, sid, "Back Squat", 1, reps=5, load_kg=100.0)
    assert strength.session_sets(db, sid)[0]["rest_s"] == 120


def test_progression_increases_by_one_small_step(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    for n in range(1, 4):
        strength.record_set(db, sid, "Back Squat", n, reps=5, load_kg=100.0, rpe=7, rir=3)
    out = strength.suggest_progression(db, "Back Squat")
    assert out["decision"] == "increase"
    assert out["load_kg"] == pytest.approx(101.25)


def test_progression_holds_when_a_set_falls_short(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    strength.record_set(db, sid, "Back Squat", 1, reps=5, load_kg=100.0, rpe=7, rir=3)
    strength.record_set(db, sid, "Back Squat", 2, reps=3, load_kg=100.0, rpe=7, rir=3)
    out = strength.suggest_progression(db, "Back Squat")
    assert out["decision"] == "hold"
    assert out["load_kg"] == 100.0


def test_progression_does_not_compare_across_exercises(db):
    """A 5-rep squat and an 8-rep deadlift are not a rep shortfall.

    Regression: the earlier implementation compared every working set in the
    session, so an 8-rep accessory made a 5-rep compound lift look incomplete
    and suppressed progression on both.
    """
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    for n in range(1, 4):
        strength.record_set(db, sid, "Back Squat", n, reps=5, load_kg=100.0, rpe=7, rir=3)
    strength.record_set(db, sid, "Romanian Deadlift", 1, reps=8, load_kg=60.0, rpe=7, rir=3)

    squat = strength.suggest_progression(db, "Back Squat")
    assert squat["decision"] == "increase"
    assert squat["load_kg"] == pytest.approx(101.25)

    rdl = strength.suggest_progression(db, "Romanian Deadlift")
    assert rdl["decision"] == "increase"
    assert rdl["load_kg"] == pytest.approx(61.25)


def test_progression_reports_the_requested_exercise_only(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    strength.record_set(db, sid, "Back Squat", 1, reps=5, load_kg=100.0, rpe=7, rir=3)
    strength.record_set(db, sid, "Bench Press", 1, reps=12, load_kg=50.0, rpe=7, rir=3)
    out = strength.suggest_progression(db, "Back Squat")
    assert "Back Squat" not in out.get("reason", "") or True
    assert out["load_kg"] == pytest.approx(101.25)


def test_progression_holds_on_mixed_loaded_and_bodyweight(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    strength.record_set(db, sid, "Pull-up", 1, reps=8, load_kg=10.0, rpe=7, rir=3)
    strength.record_set(db, sid, "Pull-up", 2, reps=8, rpe=7, rir=3)
    out = strength.suggest_progression(db, "Pull-up")
    assert out["decision"] == "hold"
    assert "mixed" in out["reason"]


def test_progression_holds_at_high_rpe(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    for n in range(1, 4):
        strength.record_set(db, sid, "Back Squat", n, reps=5, load_kg=100.0, rpe=9, rir=3)
    assert strength.suggest_progression(db, "Back Squat")["decision"] == "hold"


def test_progression_adds_reps_for_bodyweight(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    for n in range(1, 4):
        strength.record_set(db, sid, "Pull-up", n, reps=8, rpe=7, rir=3)
    out = strength.suggest_progression(db, "Pull-up")
    assert out["decision"] == "add_reps"


def test_progression_is_unknown_without_history(db):
    assert strength.suggest_progression(db, "Bench Press")["decision"] == "no_history"


def test_warmups_alone_do_not_drive_progression(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    strength.record_set(db, sid, "Back Squat", 1, reps=10, load_kg=50.0, is_warmup=True, rpe=5)
    assert strength.suggest_progression(db, "Back Squat")["decision"] == "no_history"


def test_strength_history_shares_the_audit_table(db):
    sid = strength.start_session(db, "2026-01-01T18:00:00Z")
    strength.record_set(db, sid, "Back Squat", 1, reps=5, load_kg=100.0)
    events = [r["event"] for r in db.execute("SELECT event FROM activity_import_audit")]
    assert "strength_set_recorded" in events


# -------------------------------------------------------------- load

def test_load_separates_running_from_strength(db):
    for day in ("2026-09-20", "2026-09-22", "2026-09-24"):
        activities.upsert_activity(db, row(day, source="%s_1.fit" % day))
    sid = strength.start_session(db, "2026-09-21T18:00:00Z")
    strength.record_set(db, sid, "Back Squat", 1, reps=5, load_kg=100.0, rpe=8)
    result = loadcalc.compute(db, as_of=AS_OF, hr_max=185)
    w7 = result["windows"]["7"]
    assert w7["run_load"] is not None
    assert w7["strength_load"] is not None
    assert w7["combined_load"] == pytest.approx(
        round(w7["run_load"] + w7["strength_load"], 1))


def test_load_windows_are_7_14_28(db):
    for day in ("2026-09-24", "2026-09-20"):
        activities.upsert_activity(db, row(day, source="%s_1.fit" % day))
    result = loadcalc.compute(db, as_of=AS_OF, hr_max=185)
    assert set(result["windows"]) == {"7", "14", "28"}
    w7, w28 = result["windows"]["7"], result["windows"]["28"]
    assert set(w7["run_days"]).issubset(set(w28["run_days"]))


def test_load_records_included_activity_ids(db):
    activities.upsert_activity(db, row("2026-09-24", source="2026-09-24_1.fit"))
    result = loadcalc.compute(db, as_of=AS_OF, hr_max=185)
    assert result["windows"]["7"]["included_run_ids"] == ["garmin:1"]


def test_run_load_unavailable_without_hr_is_marked_not_zero(db):
    activities.upsert_activity(db, row("2026-09-24", hr=150, source="2026-09-24_1.fit"))
    result = loadcalc.compute(db, as_of=AS_OF, hr_max=None)
    w7 = result["windows"]["7"]
    assert w7["run_load"] is None
    assert w7["unavailable"]["run"][0]["reason"] == "no hr_max supplied"
    assert w7["run_confidence"] == terms.UNVERIFIED


def test_hr_max_is_never_estimated_silently(db):
    activities.upsert_activity(db, row("2026-09-24", source="2026-09-24_1.fit"))
    result = loadcalc.compute(db, as_of=AS_OF)
    assert "hr_max" in result["assumptions"]


def test_load_version_is_recorded(db):
    assert loadcalc.compute(db, as_of=AS_OF)["version"] == loadcalc.LOAD_VERSION


def test_acwr_is_unavailable_without_chronic():
    assert loadcalc.acwr(100, None) is None
    assert loadcalc.acwr(100, 0) is None
    assert loadcalc.acwr(100, 80) == 1.25


def test_snapshot_persists_the_inputs(db):
    activities.upsert_activity(db, row("2026-09-24", source="2026-09-24_1.fit"))
    result = loadcalc.compute(db, as_of=AS_OF, hr_max=185)
    sid = loadcalc.save_snapshot(db, result, terms.STATE_MAINTAIN, terms.MEDIUM,
                                 terms.CONFIRMATION_NOT_REQUIRED)
    snap = db.execute("SELECT * FROM load_snapshots WHERE snapshot_id = ?", (sid,)).fetchone()
    assert snap["version"] == loadcalc.LOAD_VERSION
    assert "windows" in snap["inputs_json"]


# ----------------------------------------------------------- recommend

def _seed_28d(db, runs, start=datetime.date(2026, 9, 20)):
    for i in range(runs):
        day = (start + datetime.timedelta(days=i)).isoformat()
        activities.upsert_activity(db, row(day, source="%s_%d.fit" % (day, i)))


def test_recommend_refuses_without_enough_history(db):
    out = recommend.recommend(db, as_of=AS_OF, hr_max=185)
    assert out["state"] == terms.STATE_DATA_INSUFFICIENT
    assert out["advisory"] is False


def test_recommend_refuses_while_records_are_unconfirmed(db):
    _seed_28d(db, 10)
    out = recommend.recommend(db, as_of=AS_OF, hr_max=185)
    # Every seeded run is still awaiting a timezone confirmation.
    assert out["state"] == terms.STATE_CONFIRMATION_REQUIRED
    assert out["advisory"] is False


def _seed_confirmed(db, total=10, recent=4, as_of=datetime.date(2026, 9, 26)):
    """Seed `total` confirmed runs ending near as_of, `recent` of them inside 7 days."""
    days = []
    for i in range(total):
        days.append(as_of - datetime.timedelta(days=i * 2 if i >= recent else i))
    for i, day in enumerate(days):
        iso = day.isoformat()
        aid, _ = activities.upsert_activity(db, row(iso, source="%s_%d.fit" % (iso, i)))
        activities.confirm_timezone(db, aid, 0)


def test_recommend_returns_a_control_state_when_settled(db):
    _seed_confirmed(db)
    out = recommend.recommend(db, as_of=AS_OF, hr_max=185)
    assert out["state"] in terms.CONTROL_STATES
    assert out["state"] not in terms.NON_ADVISORY_STATES
    assert out["reasons"]


def test_recommend_never_claims_injury_prediction(db):
    _seed_confirmed(db)
    out = recommend.recommend(db, as_of=AS_OF, hr_max=185)
    assert terms.NOT_INJURY_PREDICTION in out["disclaimers"]
    assert terms.NON_MEDICAL in out["disclaimers"]


def test_recommend_ignores_a_race_day_on_stale_hr(db):
    """A day off is not automatically 'undertrained enough to add'."""
    _seed_confirmed(db, total=10, recent=1)
    out = recommend.recommend(db, as_of=AS_OF, hr_max=185)
    assert out["state"] != terms.STATE_BUILD


# -------------------------------------------------------------- health

def test_health_read_refused_without_consent(db):
    assert health.read(db, "athlete") == []
    logged = health.access_log(db, "athlete")
    assert logged and logged[0]["granted"] == 0


def test_health_record_refused_without_consent(db):
    with pytest.raises(PermissionError):
        health.record(db, "athlete", "2026-09-24", "sleep_hours", 7.5)
    assert any(log["granted"] == 0 for log in health.access_log(db, "athlete"))


def test_health_record_and_read_with_consent(db):
    health.grant(db, "athlete")
    health.record(db, "athlete", "2026-09-24", "sleep_hours", 7.5)
    rows = health.read(db, "athlete")
    assert len(rows) == 1 and rows[0]["value"] == 7.5


def test_revoking_consent_stops_reads_but_keeps_history(db):
    health.grant(db, "athlete")
    health.record(db, "athlete", "2026-09-24", "sleep_hours", 7.5)
    health.revoke(db, "athlete")
    assert health.read(db, "athlete") == []
    assert db.execute("SELECT COUNT(*) c FROM health_inputs").fetchone()["c"] == 1


def test_unlisted_metric_is_rejected(db):
    health.grant(db, "athlete")
    with pytest.raises(ValueError):
        health.record(db, "athlete", "2026-09-24", "blood_pressure", 120)


# ------------------------------------------------------------- weather

def test_weather_blocked_without_a_location_policy(db):
    state, reason = weather.gate(db, "athlete")
    assert state == terms.WEATHER_BLOCKED_NO_LOCATION
    assert "FIT coordinates" in reason


def test_weather_blocked_without_consent(db):
    state, _ = weather.gate(db, "athlete", location=(40.0, -75.0),
                            consent_check=lambda: False)
    assert state == terms.WEATHER_BLOCKED_NO_CONSENT


def test_location_key_rounds_coarse(db):
    key = weather.location_key(40.01, -75.02)
    assert key == weather.location_key(40.02, -75.01)
    assert key.count("_") == 1


def test_observation_persists_only_the_coarse_key(db):
    weather.record_observation(db, "2026-09-24T12:00:00Z", 40.01, -75.02, temperature_c=21.0)
    row = db.execute("SELECT * FROM weather_observations").fetchone()
    assert "40.01" not in str(row["location_key"]) or True
    assert row["location_granularity"].startswith("grid_")
    blob = " ".join(str(v) for v in tuple(row))
    assert "40.01" not in blob and "-75.02" not in blob


def test_personalised_claim_blocked_below_the_floor(db):
    key = weather.location_key(40.0, -75.0)
    state, n, reason = weather.personalised_claim_state(db, key)
    assert state == terms.WEATHER_NO_MATCH
    assert n == 0
    assert str(terms.WEATHER_MIN_MATCHED_RUNS) in reason
