"""Tests for the dashboard JSON API in garmin_server.

Supervisor brief `connect-dashboard-to-data-layer`. The point of these routes is
that the dashboard stops being its own source of truth, so the tests are mostly
about what the API must NOT do:

  * recompute anything loadcalc/recommend already compute,
  * turn null, unavailable or refused into zero or into advice,
  * suppress an unresolved review,
  * answer with a hardcoded count that has since gone stale.

The builders are pure functions of a connection, so no socket is bound here.
test_dashboard_api_http.py covers the wire behaviour.
"""

import datetime
import json

import pytest

import garmin_server as G
import loadcalc
import recommend
import trainingdb

UTC = datetime.timezone.utc


@pytest.fixture
def conn(tmp_path, monkeypatch):
    """A migrated, empty database. Tests seed only what they need."""
    db = tmp_path / "t.db"
    monkeypatch.setenv(trainingdb.DB_ENV, str(db))
    c = trainingdb.connect(db)
    trainingdb.migrate(c, verbose=False)
    yield c
    c.close()


def _seed_run(conn, aid, start_utc, distance=5.0, hr=140, review_state="open"):
    conn.execute(
        "INSERT INTO activities (activity_id, source_system, source_activity_id,"
        " sport, start_utc, start_local, timezone_source, distance_mi,"
        " moving_time_s, avg_hr, value_state, confidence, confirmation,"
        " review_state, first_seen_utc, last_updated_utc)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (aid, "garmin", aid.split(":")[-1], "Running", start_utc,
         start_utc.replace("T", " ").replace("Z", ""), "filename_date",
         distance, 3000, hr, "device_derived", "unverified",
         "confirmation_required", review_state, start_utc, start_utc),
    )
    return aid


def _open_review(conn, aid, reason, detail=None):
    conn.execute(
        "INSERT INTO review_items (activity_id, reason, state, detail, opened_utc)"
        " VALUES (?,?,?,?,?)",
        (aid, reason, "open", detail, "2026-10-01T00:00:00Z"),
    )


def _iso(days_ago=1):
    return (datetime.datetime.now(UTC)
            - datetime.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------ route registry

def test_exactly_the_three_brief_routes_exist():
    assert sorted(G.API_ROUTES) == [
        "/api/activities", "/api/coaching", "/api/load"]


def test_routes_are_under_the_api_prefix():
    for path in G.API_ROUTES:
        assert path.startswith(G.API_PREFIX)


# ------------------------------------------------------------ /api/activities

def test_activities_route_returns_a_stable_envelope(conn):
    body = G.api_activities(conn)
    assert set(body) >= {"activities", "count", "review_summary", "data_version"}
    assert body["activities"] == []
    assert body["count"] == 0


def test_activity_identity_is_stable_and_not_positional(conn):
    _seed_run(conn, "garmin:111", _iso(2))
    _seed_run(conn, "garmin:222", _iso(1))
    body = G.api_activities(conn)
    ids = [a["activity_id"] for a in body["activities"]]
    assert ids == ["garmin:222", "garmin:111"], "must order newest first"
    assert "garmin:222" in ids, "identity must survive reordering"


def test_activity_exposes_the_fields_the_brief_requires(conn):
    _seed_run(conn, "garmin:111", _iso(1))
    a = G.api_activities(conn)["activities"][0]
    for field in ("activity_id", "start_utc", "start_local", "sport",
                  "moving_time_s", "distance_mi", "value_state",
                  "review_state", "reviews", "source_file"):
        assert field in a, "missing %s" % field


def test_activity_exposes_device_summary_fields(conn):
    """Calories, cadence and pace are in the database; the API must not drop
    them, because the run detail and the pace charts read them."""
    _seed_run(conn, "garmin:111", _iso(1))
    conn.execute(
        "UPDATE activities SET calories=520, avg_cadence=170, max_cadence=182,"
        " avg_pace_s_per_mi=530, best_pace_s_per_mi=480,"
        " training_stress_score=88 WHERE activity_id=?",
        ("garmin:111",),
    )
    a = G.api_activities(conn)["activities"][0]
    assert a["calories"] == 520
    assert a["avg_cadence"] == 170
    assert a["max_cadence"] == 182
    assert a["avg_pace_s_per_mi"] == 530
    assert a["best_pace_s_per_mi"] == 480
    assert a["training_stress_score"] == 88


def test_lap_splits_are_read_from_the_published_csv(conn, tmp_path, monkeypatch):
    """The database has no splits table, so the API joins the published CSV by
    source file. Without this the run detail has a canvas and no data."""
    _seed_run(conn, "garmin:111", _iso(1))
    conn.execute(
        "INSERT INTO activity_raw_refs (activity_id, source_file, sha256,"
        " byte_size, parser, parser_version, imported_utc)"
        " VALUES (?,?,?,?,?,?,?)",
        ("garmin:111", "2026-10-01_111.fit", "a" * 64, 100,
         "garmin_fit_reader", "1.1.0", "2026-10-01T00:00:00Z"),
    )
    csv_path = tmp_path / "garmin_export.csv"
    csv_path.write_text(
        "Source File,Lap Splits,Best 5K Time,Number of Laps\n"
        '2026-10-01_111.fit,"8:35, 8:51, 9:02",27:12,3\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(G, "EXPORT_CSV", str(csv_path))
    a = G.api_activities(conn)["activities"][0]
    assert a["splits"] == [515, 531, 542]
    assert a["best_5k_s"] == 1632
    assert a["laps"] == 3


def test_splits_are_null_when_the_csv_is_absent(conn, tmp_path, monkeypatch):
    """No CSV is not an error and must never become an invented split."""
    _seed_run(conn, "garmin:111", _iso(1))
    conn.execute(
        "INSERT INTO activity_raw_refs (activity_id, source_file, sha256,"
        " byte_size, parser, parser_version, imported_utc)"
        " VALUES (?,?,?,?,?,?,?)",
        ("garmin:111", "2026-10-01_111.fit", "a" * 64, 100,
         "garmin_fit_reader", "1.1.0", "2026-10-01T00:00:00Z"),
    )
    monkeypatch.setattr(G, "EXPORT_CSV", str(tmp_path / "missing.csv"))
    a = G.api_activities(conn)["activities"][0]
    assert a["splits"] is None
    assert a["best_5k_s"] is None
    assert a["laps"] is None


def test_split_and_pace_parsers_reject_malformed_cells():
    assert G._pace_seconds("27:12") == 1632
    assert G._pace_seconds("") is None
    assert G._pace_seconds("nope") is None
    assert G._split_seconds("8:35, 8:51") == [515, 531]
    assert G._split_seconds("") is None
    assert G._split_seconds("8:35, nope") is None


def test_source_file_resolves_through_raw_refs_not_a_second_convention(conn):
    _seed_run(conn, "garmin:111", _iso(1))
    conn.execute(
        "INSERT INTO activity_raw_refs (activity_id, source_file, sha256,"
        " byte_size, parser, parser_version, imported_utc)"
        " VALUES (?,?,?,?,?,?,?)",
        ("garmin:111", "2026-10-01_111.fit", "a" * 64, 100,
         "garmin_fit_reader", "1.1.0", "2026-10-01T00:00:00Z"),
    )
    a = G.api_activities(conn)["activities"][0]
    assert a["source_file"] == "2026-10-01_111.fit"


def test_missing_raw_ref_yields_null_source_file_not_a_guess(conn):
    """A FIT filename must never be reconstructed from the activity id. If the
    ref row is absent the honest answer is null."""
    _seed_run(conn, "garmin:111", _iso(1))
    a = G.api_activities(conn)["activities"][0]
    assert a["source_file"] is None


def test_unresolved_reviews_are_preserved_not_suppressed(conn):
    _seed_run(conn, "garmin:111", _iso(1))
    _open_review(conn, "garmin:111", "timezone_uncertain", "offset unknown")
    a = G.api_activities(conn)["activities"][0]
    assert a["review_state"] == "open"
    assert a["has_open_review"] is True
    assert [r["reason"] for r in a["reviews"]] == ["timezone_uncertain"]
    assert a["reviews"][0]["detail"] == "offset unknown"


def test_review_summary_counts_every_open_reason(conn):
    _seed_run(conn, "garmin:111", _iso(1))
    _seed_run(conn, "garmin:222", _iso(2))
    _open_review(conn, "garmin:111", "timezone_uncertain")
    _open_review(conn, "garmin:222", "timezone_uncertain")
    # activity_gap rows have a null activity_id: no activity exists for a gap.
    conn.execute(
        "INSERT INTO review_items (activity_id, reason, state, detail, opened_utc)"
        " VALUES (NULL,'activity_gap','open','no activity 2026-06-26..2026-07-05',?)",
        ("2026-10-01T00:00:00Z",),
    )
    s = G.api_activities(conn)["review_summary"]
    assert s["open_reviews"] == 3
    assert s["timezone_uncertain"] == 2
    assert s["activity_gap"] == 1


def test_resolved_reviews_are_not_counted_as_open(conn):
    _seed_run(conn, "garmin:111", _iso(1))
    _open_review(conn, "garmin:111", "timezone_uncertain")
    conn.execute("UPDATE review_items SET state='resolved'")
    s = G.api_activities(conn)["review_summary"]
    assert s["open_reviews"] == 0
    assert G.api_activities(conn)["activities"][0]["reviews"] == []


def test_no_synthetic_row_is_invented_for_a_gap(conn):
    """The brief forbids fabricating a row for the documented gap. A gap review
    must not become an activity."""
    conn.execute(
        "INSERT INTO review_items (activity_id, reason, state, detail, opened_utc)"
        " VALUES (NULL,'activity_gap','open','no activity',?)",
        ("2026-10-01T00:00:00Z",),
    )
    body = G.api_activities(conn)
    assert body["count"] == 0
    assert body["review_summary"]["activity_gap"] == 1


def test_counts_are_queried_not_hardcoded(conn):
    """Two activities must report two. A constant would pass the empty case and
    fail here, which is the whole point."""
    _seed_run(conn, "garmin:111", _iso(1))
    assert G.api_activities(conn)["count"] == 1
    _seed_run(conn, "garmin:222", _iso(2))
    _seed_run(conn, "garmin:333", _iso(3))
    assert G.api_activities(conn)["count"] == 3


def test_data_version_tracks_the_newest_import(conn):
    _seed_run(conn, "garmin:111", "2026-09-01T10:00:00Z")
    v1 = G.api_activities(conn)["data_version"]["last_activity_update_utc"]
    _seed_run(conn, "garmin:222", "2026-10-01T10:00:00Z")
    v2 = G.api_activities(conn)["data_version"]["last_activity_update_utc"]
    assert v2 > v1


def test_activities_body_is_json_serialisable(conn):
    _seed_run(conn, "garmin:111", _iso(1))
    _open_review(conn, "garmin:111", "timezone_uncertain")
    # default=str in the handler, but the payload itself should need no help.
    json.dumps(G.api_activities(conn))


def test_no_coordinate_field_ever_appears(conn):
    _seed_run(conn, "garmin:111", _iso(1))
    blob = json.dumps(G.api_activities(conn)).lower()
    for bad in ("lat", "lon", "latitude", "longitude", "position"):
        assert bad not in blob, "%s leaked into the activities payload" % bad


# ------------------------------------------------------------------ /api/load

def test_load_route_reports_the_real_algorithm(conn):
    body = G.api_load(conn, 198.0)
    assert body["algorithm"] == loadcalc.LOAD_VERSION


def test_load_route_exposes_all_three_windows_with_bounds(conn):
    body = G.api_load(conn, 198.0)
    assert sorted(body["windows"]) == ["14d", "28d", "7d"]
    for key, w in body["windows"].items():
        assert w["start"] and w["end"], "%s has no window bounds" % key
        assert w["days"] == int(key[:-1])


def test_load_numbers_come_from_loadcalc_not_recomputed(conn):
    _seed_run(conn, "garmin:111", _iso(1), hr=150)
    conn2 = trainingdb.connect(trainingdb.db_path())
    try:
        direct = loadcalc.compute(conn2, hr_max=198.0)
        via_api = G.api_load(conn2, 198.0)
        for key in ("7", "14", "28"):
            assert (via_api["windows"]["%sd" % key]["value"]
                    == direct["windows"][key]["run_load"])
    finally:
        conn2.close()


def test_strength_load_is_null_when_no_sessions_exist(conn):
    """null means "no confirmed strength data". It must not become 0, which
    would read as "trained and did nothing"."""
    body = G.api_load(conn, 198.0)
    assert body["strength_load"] is None
    assert body["strength_state"] == "unverified"


def test_an_empty_database_reports_null_not_zero_everywhere(conn):
    """The whole point of the null/zero distinction, on the emptiest possible
    input: every window is unknown, and unknown is not zero."""
    body = G.api_load(conn, 198.0)
    for key in ("7d", "14d", "28d"):
        w = body["windows"][key]
        assert w["value"] is None, "%s invented a value on an empty db" % key
        assert w["combined_load"] is None
        assert w["runs_included"] == 0
    assert body["strength_load"] is None


def test_a_real_run_makes_the_window_numeric_and_leaves_strength_null(conn):
    """The asymmetry that matters: run load becomes a number, strength stays
    null, in the same payload."""
    _seed_run(conn, "garmin:111", _iso(1), hr=150)
    body = G.api_load(conn, 198.0)
    assert body["windows"]["7d"]["value"] is not None
    assert body["strength_load"] is None


def test_strength_load_is_not_zero_even_when_run_load_is_zero(conn):
    body = G.api_load(conn, 198.0)
    assert body["windows"]["7d"]["value"] is None or \
        body["windows"]["7d"]["value"] == 0
    assert body["strength_load"] is None
    assert body["strength_load"] != 0


def test_load_records_that_hr_max_was_supplied(conn):
    assert G.api_load(conn, 198.0)["hr_max_supplied"] == 198.0
    assert G.api_load(conn, 198.0)["hr_max_note"] is None


def test_load_says_so_when_hr_max_is_missing(conn):
    """Never invent a max. Flag the fallback rather than hiding it."""
    body = G.api_load(conn, None)
    assert body["hr_max_supplied"] is None
    assert body["hr_max_note"], "a missing hr_max must be visible to the UI"


def test_load_preserves_loadcalcs_unavailable_reasons_verbatim(conn):
    body = G.api_load(conn, None)
    for key in ("7d", "14d", "28d"):
        assert "run" in body["windows"][key]["unavailable"]


def test_load_honours_as_of(conn):
    _seed_run(conn, "garmin:111", "2026-09-01T10:00:00Z", hr=150)
    early = G.api_load(conn, 198.0, as_of="2026-09-05T00:00:00Z")
    late = G.api_load(conn, 198.0, as_of="2026-10-04T00:00:00Z")
    assert early["windows"]["7d"]["runs_included"] == 1
    assert late["windows"]["7d"]["runs_included"] == 0


def test_load_window_start_precedes_end(conn):
    for w in G.api_load(conn, 198.0)["windows"].values():
        assert w["start"] < w["end"]


def test_load_body_is_json_serialisable(conn):
    json.dumps(G.api_load(conn, 198.0))


# -------------------------------------------------------------- /api/coaching

def test_coaching_route_envelope(conn):
    body = G.api_coaching(conn, 198.0)
    for field in ("state", "refused", "blocking_conditions", "rationale",
                  "evidence", "version", "available_states"):
        assert field in body, "missing %s" % field


def test_coaching_never_invents_a_state(conn):
    body = G.api_coaching(conn, 198.0)
    assert body["state"] in body["available_states"]


def test_coaching_agrees_with_recommend(conn):
    direct = recommend.recommend(conn, hr_max=198.0)
    via_api = G.api_coaching(conn, 198.0)
    assert via_api["state"] == direct["state"]
    assert via_api["refused"] == (not direct["advisory"])


def test_open_reviews_force_a_refusal(conn):
    _seed_run(conn, "garmin:111", _iso(1))
    _open_review(conn, "garmin:111", "timezone_uncertain")
    body = G.api_coaching(conn, 198.0)
    assert body["refused"] is True
    assert body["advisory"] is False
    assert body["blocking_conditions"], "a refusal must state what blocks it"


def test_a_refusal_carries_its_disclaimers(conn):
    _seed_run(conn, "garmin:111", _iso(1))
    _open_review(conn, "garmin:111", "timezone_uncertain")
    assert G.api_coaching(conn, 198.0)["disclaimers"]


def test_coaching_surfaces_the_review_summary(conn):
    """The coaching panel is where an athlete looks, so the unresolved count
    has to be reachable from it too."""
    _seed_run(conn, "garmin:111", _iso(1))
    _open_review(conn, "garmin:111", "timezone_uncertain")
    assert G.api_coaching(conn, 198.0)["review_summary"]["open_reviews"] == 1


def test_coaching_keeps_strength_null_in_its_evidence(conn):
    body = G.api_coaching(conn, 198.0)
    assert body["evidence"]["strength_load_28d"] is None
    assert body["evidence"]["strength_load_28d"] != 0


def test_coaching_is_refused_not_advisory_on_an_empty_database(conn):
    body = G.api_coaching(conn, 198.0)
    assert body["refused"] is True
    assert body["state"] != recommend.terms.STATE_BUILD


def test_coaching_body_is_json_serialisable(conn):
    json.dumps(G.api_coaching(conn, 198.0))


def test_no_coordinate_field_appears_in_coaching(conn):
    blob = json.dumps(G.api_coaching(conn, 198.0)).lower()
    for bad in ("lat", "lon", "latitude", "longitude"):
        assert bad not in blob