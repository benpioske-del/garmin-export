"""In-run fuel: validation, storage, fade, attach and journal recovery.

Every test passes an explicit store path or monkeypatches ``STORE_FILE`` so the
athlete's real ``run_fuel.json`` is never read or written.
"""

import json
import os

import pytest

import run_fuel


# --------------------------------------------------------------- parse_position

@pytest.mark.parametrize("value,expected", [
    (5, (5.0, None)),
    ("5", (5.0, None)),
    ("Mile 5", (5.0, None)),
    ("between 8 and 9", (8.0, None)),
    ("start", (0.0, "start")),
    ("pre-run", (0.0, "start")),
    ("finish", (None, "finish")),
    ("mid-run", (None, "mid")),
    ("None", (None, None)),
    ("", (None, None)),
    (None, (None, None)),
])
def test_parse_position_accepts_what_the_journal_wrote(value, expected):
    assert run_fuel.parse_position(value) == expected


def test_parse_position_rejects_an_impossible_mile():
    with pytest.raises(run_fuel.FuelError):
        run_fuel.parse_position(300)


def test_parse_position_rejects_a_boolean():
    with pytest.raises(run_fuel.FuelError):
        run_fuel.parse_position(True)


# --------------------------------------------------------------- normalize_event

def test_normalize_event_requires_a_kind():
    with pytest.raises(run_fuel.FuelError):
        run_fuel.normalize_event({"mile": 5})


def test_normalize_event_rejects_an_unknown_kind():
    with pytest.raises(run_fuel.FuelError):
        run_fuel.normalize_event({"kind": "pizza"})


def test_normalize_event_accepts_the_journal_mi_key():
    event = run_fuel.normalize_event({"mi": "Mile 5", "kind": "fuel"})
    assert event["mile"] == 5.0
    assert event["at"] is None


def test_normalize_event_accepts_type_as_a_kind_alias():
    event = run_fuel.normalize_event({"type": "water"})
    assert event["kind"] == "water"


def test_normalize_event_promotes_zero_ounces_from_text():
    event = run_fuel.normalize_event({"kind": "water", "what": "0 oz"})
    assert event["oz"] == 0.0


def test_normalize_event_leaves_an_unmeasured_amount_as_none():
    event = run_fuel.normalize_event({"kind": "fuel", "what": "a gel"})
    assert event["kcal"] is None
    assert event["carbs_g"] is None
    assert event["oz"] is None


def test_normalize_event_rejects_nan():
    with pytest.raises(run_fuel.FuelError):
        run_fuel.normalize_event({"kind": "water", "oz": float("nan")})


def test_normalize_event_rejects_an_out_of_range_amount():
    with pytest.raises(run_fuel.FuelError):
        run_fuel.normalize_event({"kind": "water", "oz": 999})


def test_normalize_event_rejects_overlong_text():
    with pytest.raises(run_fuel.FuelError):
        run_fuel.normalize_event({"kind": "fuel", "what": "x" * 500})


# --------------------------------------------------------------- normalize_entry

def test_normalize_entry_requires_an_iso_date():
    with pytest.raises(run_fuel.FuelError):
        run_fuel.normalize_entry({"date": "09/09/2026"})


def test_normalize_entry_rejects_a_day_that_does_not_exist():
    with pytest.raises(run_fuel.FuelError):
        run_fuel.normalize_entry({"date": "2026-02-30"})


def test_normalize_entry_requires_events_to_be_a_list():
    with pytest.raises(run_fuel.FuelError):
        run_fuel.normalize_entry({"date": "2026-09-09", "events": "gel"})


def test_normalize_entry_caps_the_number_of_events():
    events = [{"kind": "fuel"}] * (run_fuel.MAX_EVENTS + 1)
    with pytest.raises(run_fuel.FuelError):
        run_fuel.normalize_entry({"date": "2026-09-09", "events": events})


def test_normalize_entry_coerces_an_unknown_source_to_manual():
    entry = run_fuel.normalize_entry({"date": "2026-09-09", "source": "guess"})
    assert entry["source"] == "manual"


def test_normalize_entry_requires_activity_id_to_be_a_string():
    with pytest.raises(run_fuel.FuelError):
        run_fuel.normalize_entry({"date": "2026-09-09", "activity_id": 123})


def test_normalize_entry_keeps_needs_review():
    entry = run_fuel.normalize_entry(
        {"date": "2026-09-09", "needs_review": True})
    assert entry["needs_review"] is True


# ------------------------------------------------------------------ the store

def _entry(date="2026-09-09", **kw):
    payload = {"date": date, "events": [{"kind": "fuel", "mile": 5}]}
    payload.update(kw)
    return payload


def test_a_missing_store_reads_as_empty(tmp_path):
    assert run_fuel.load(str(tmp_path / "absent.json")) == []


def test_a_corrupt_store_reads_as_empty(tmp_path):
    path = tmp_path / "run_fuel.json"
    path.write_text("{not json", encoding="utf-8")
    assert run_fuel.load(str(path)) == []


def test_save_and_load_round_trip(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert(_entry(), path)
    rows = run_fuel.load(path)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-09-09"
    assert rows[0]["events"][0]["kind"] == "fuel"


def test_save_is_atomic_and_leaves_no_temporary_files(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert(_entry(), path)
    names = os.listdir(str(tmp_path))
    assert names == ["run_fuel.json"]


def test_upsert_replaces_the_same_run(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert(_entry(), path)
    run_fuel.upsert(_entry(events=[{"kind": "water", "oz": 20}]), path)
    rows = run_fuel.load(path)
    assert len(rows) == 1
    assert rows[0]["events"][0]["kind"] == "water"


def test_upsert_keeps_a_known_activity_id_when_the_new_body_omits_it(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert(_entry(activity_id="garmin:1"), path)
    run_fuel.upsert(_entry(), path)
    assert run_fuel.load(path)[0]["activity_id"] == "garmin:1"


def test_upsert_matches_by_activity_id_before_date(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert(_entry(activity_id="garmin:1"), path)
    run_fuel.upsert(_entry(activity_id="garmin:1",
                           events=[{"kind": "electrolyte"}]), path)
    rows = run_fuel.load(path)
    assert len(rows) == 1
    assert rows[0]["events"][0]["kind"] == "electrolyte"


def test_delete_by_date(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert(_entry(), path)
    assert run_fuel.delete("2026-09-09", path=path) == 1
    assert run_fuel.load(path) == []


def test_delete_with_an_activity_id_keeps_a_different_one(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert(_entry(activity_id="garmin:1"), path)
    assert run_fuel.delete("2026-09-09", "garmin:2", path) == 0
    assert len(run_fuel.load(path)) == 1


def test_delete_of_an_absent_run_returns_zero(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    assert run_fuel.delete("2026-01-01", path=path) == 0


# ---------------------------------------------------------------------- fade

def test_fade_needs_at_least_four_splits():
    assert run_fuel.fade([600, 610, 620]) is None


def test_fade_is_positive_when_the_second_half_is_slower():
    result = run_fuel.fade([600, 610, 700, 720])
    assert result["first_half_s_per_mi"] == 605
    assert result["second_half_s_per_mi"] == 710
    assert result["fade_s_per_mi"] == 105
    assert result["fade_pct"] == 17.4


def test_fade_is_negative_for_a_negative_split():
    result = run_fuel.fade([700, 720, 600, 610])
    assert result["fade_s_per_mi"] < 0


def test_fade_ignores_blank_and_non_numeric_splits():
    result = run_fuel.fade([600, None, "bad", 650, 700, 720])
    assert result["splits_used"] == 4


# ------------------------------------------------------------------- summary

def test_summary_totals_ignore_unmeasured_events(tmp_path):
    entry = run_fuel.normalize_entry({
        "date": "2026-09-09",
        "events": [
            {"kind": "water", "oz": 20},
            {"kind": "water", "oz": 10},
            {"kind": "fuel", "what": "gel"},
        ],
    })
    result = run_fuel.summary(entry, {"moving_time_s": 7200})
    assert result["totals"]["oz"] == 30.0
    assert result["totals"]["kcal"] is None
    assert result["rates"]["oz_per_h"] == 15.0


def test_summary_has_no_rate_without_a_duration():
    entry = run_fuel.normalize_entry({
        "date": "2026-09-09",
        "events": [{"kind": "water", "oz": 20}],
    })
    result = run_fuel.summary(entry, {})
    assert result["rates"]["oz_per_h"] is None
    assert result["duration_h"] is None


def test_summary_carries_the_events_for_the_editor():
    entry = run_fuel.normalize_entry({
        "date": "2026-09-09",
        "events": [{"kind": "water", "oz": 20}],
    })
    result = run_fuel.summary(entry, {})
    assert result["items"][0]["oz"] == 20.0


def test_summary_uses_the_supplied_splits_for_fade():
    entry = run_fuel.normalize_entry({"date": "2026-09-09", "events": []})
    result = run_fuel.summary(entry, {"splits": [600, 610, 700, 720]})
    assert result["fade"]["fade_s_per_mi"] == 105


# -------------------------------------------------------------------- attach

def _payload(date="2026-09-09", activity_id="garmin:1", splits=None):
    return {
        "activities": [{
            "activity_id": activity_id,
            "start_local": date + "T07:00:00",
            "moving_time_s": 3600,
            "splits": splits or [600, 610, 700, 720],
        }]
    }


def test_attach_matches_by_local_date(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert(_entry(), path)
    payload = run_fuel.attach(_payload(), path)
    assert payload["activities"][0]["fuel"]["totals"] is not None
    assert payload["fuel_count"] == 1


def test_attach_matches_by_activity_id(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert(_entry(activity_id="garmin:1"), path)
    payload = run_fuel.attach(_payload(activity_id="garmin:1"), path)
    assert payload["fuel_count"] == 1


def test_attach_is_idempotent(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert(_entry(), path)
    payload = run_fuel.attach(_payload(), path)
    run_fuel.attach(payload, path)
    assert payload["fuel_count"] == 1
    assert isinstance(payload["activities"][0]["fuel"], dict)


def test_attach_counts_runs_that_have_a_fade(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert(_entry(), path)
    payload = run_fuel.attach(_payload(splits=[600, 610, 700, 720]), path)
    assert payload["fuel_with_fade"] == 1


def test_attach_leaves_other_runs_untouched(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert(_entry("2026-09-09"), path)
    payload = run_fuel.attach(_payload("2026-09-10"), path)
    assert "fuel" not in payload["activities"][0]
    assert payload["fuel_count"] == 0


def test_attach_tolerates_a_non_dict_payload():
    assert run_fuel.attach([], "unused") == []


# ---------------------------------------------------------------- suggestions

def test_suggest_finds_fuel_and_electrolytes_at_mid_run():
    events = run_fuel.suggest_events("88F heat; gel + LMNT mid-run.")
    kinds = sorted(event["kind"] for event in events)
    assert kinds == ["electrolyte", "fuel"]
    assert all(event["at"] == "mid" for event in events)


def test_suggest_turns_no_water_into_an_explicit_zero():
    events = run_fuel.suggest_events("Deliberately under-hydrated (no water, vest only).")
    water = [event for event in events if event["kind"] == "water"]
    assert water and water[0]["oz"] == 0.0


def test_suggest_turns_no_gel_into_an_explicit_zero():
    events = run_fuel.suggest_events("LMNT only, no gel.")
    fuel = [event for event in events if event["kind"] == "fuel"]
    assert fuel and fuel[0]["kcal"] == 0.0


def test_suggest_keeps_a_mile_marker():
    events = run_fuel.suggest_events("water ran out at mile 14")
    assert events[0]["mile"] == 14.0


def test_suggest_returns_nothing_for_a_blank_note():
    assert run_fuel.suggest_events("") == []


def test_suggest_returns_nothing_for_a_note_about_other_things():
    assert run_fuel.suggest_events("Legs felt heavy, hamstrings tight.") == []


# ------------------------------------------------------------- journal import

def _journal_html(runs):
    payload = json.dumps(runs)
    return "<script>const baseRuns = %s; const baseWeights=[];</script>" % payload


def test_import_journal_seeds_structured_events(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    html = _journal_html([{
        "seq": 1, "date": "2026-09-09", "dist": 10,
        "fnotes": [{"mi": "Mile 5", "kind": "fuel", "what": ""}],
    }])
    result = run_fuel.import_journal(html, path)
    assert result["with_events"] == 1
    rows = run_fuel.load(path)
    assert rows[0]["source"] == "journal"
    assert rows[0]["needs_review"] is False


def test_import_journal_keeps_a_note_only_entry_for_review(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    html = _journal_html([{
        "seq": 1, "date": "2026-05-15", "dist": 15,
        "note": "88F heat; gel + LMNT mid-run.",
    }])
    result = run_fuel.import_journal(html, path)
    assert result["notes_only"] == 1
    row = run_fuel.load(path)[0]
    assert row["source"] == "journal-note"
    assert row["needs_review"] is True
    assert row["events"] == []


def test_import_journal_skips_a_run_with_no_intake_words(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    html = _journal_html([{
        "seq": 1, "date": "2026-05-15", "dist": 15,
        "note": "Easy recovery run, legs felt fine.",
    }])
    result = run_fuel.import_journal(html, path)
    assert result["seeded"] == 0


def test_import_journal_does_not_overwrite_saved_events(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert({
        "date": "2026-09-09",
        "events": [{"kind": "water", "oz": 20}],
        "source": "manual",
    }, path)
    html = _journal_html([{
        "seq": 1, "date": "2026-09-09", "dist": 10,
        "fnotes": [{"mi": "Mile 5", "kind": "fuel", "what": ""}],
    }])
    result = run_fuel.import_journal(html, path)
    assert result["skipped"] == 1
    assert run_fuel.load(path)[0]["events"][0]["kind"] == "water"


def test_import_journal_overwrite_replaces_saved_events(tmp_path):
    path = str(tmp_path / "run_fuel.json")
    run_fuel.upsert({
        "date": "2026-09-09",
        "events": [{"kind": "water", "oz": 20}],
        "source": "manual",
    }, path)
    html = _journal_html([{
        "seq": 1, "date": "2026-09-09", "dist": 10,
        "fnotes": [{"mi": "Mile 5", "kind": "fuel", "what": ""}],
    }])
    run_fuel.import_journal(html, path, overwrite=True)
    assert run_fuel.load(path)[0]["events"][0]["kind"] == "fuel"


def test_import_journal_rejects_html_without_base_runs(tmp_path):
    with pytest.raises(run_fuel.FuelError):
        run_fuel.import_journal("<html>nothing</html>", str(tmp_path / "x.json"))


# --------------------------------------------------------------------- payload

def test_payload_offers_suggestions_only_for_note_only_entries(tmp_path, monkeypatch):
    path = str(tmp_path / "run_fuel.json")
    monkeypatch.setattr(run_fuel, "STORE_FILE", path)
    run_fuel.upsert({
        "date": "2026-05-15",
        "note": "gel + LMNT mid-run.",
        "source": "journal-note",
        "needs_review": True,
    }, path)
    run_fuel.upsert({
        "date": "2026-09-09",
        "events": [{"kind": "water", "oz": 20}],
        "note": "gel + LMNT mid-run.",
        "source": "journal",
    }, path)
    payload = run_fuel.payload()
    by_date = {row["date"]: row for row in payload["runs"]}
    assert by_date["2026-05-15"]["suggested"]
    assert by_date["2026-09-09"]["suggested"] == []


def test_cli_import_and_show(tmp_path, capsys):
    html = tmp_path / "index.html"
    html.write_text(_journal_html([{
        "seq": 1, "date": "2026-09-09", "dist": 10,
        "fnotes": [{"mi": "Mile 5", "kind": "fuel", "what": ""}],
    }]), encoding="utf-8")
    store = str(tmp_path / "run_fuel.json")
    assert run_fuel.main(["--file", store, "import-journal", str(html)]) == 0
    out = capsys.readouterr().out
    assert "entries seeded  : 1" in out
    assert run_fuel.main(["--file", store, "show"]) == 0
    assert "2026-09-09" in capsys.readouterr().out
