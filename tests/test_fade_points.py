"""Fade points: canonical fade for every run, intersected with context.

Nothing in this file reads the athlete's real store or journal. Temperature
notes are synthetic and the runs are plain dictionaries in the shape
``/api/activities`` returns.
"""

import fade_points
import run_fuel


SPLITS = [600, 610, 700, 720]


def _row(date="2026-09-09", **kw):
    row = {
        "activity_id": "garmin:1",
        "start_local": date + "T07:00:00",
        "moving_time_s": 3600,
        "distance_mi": 5.0,
        "splits": list(SPLITS),
    }
    row.update(kw)
    return row


def _fuel(events=(), note="", totals=None, rates=None, needs_review=False):
    return {
        "items": list(events),
        "note": note,
        "totals": totals or {},
        "rates": rates or {},
        "needs_review": needs_review,
    }


# --------------------------------------------------------------- temperature

def test_temperature_reads_an_explicit_fahrenheit_value():
    result = fade_points.temperature("88F heat; gel mid-run")
    assert result["temp_f"] == 88.0
    assert result["band"] == "80s"
    assert result["source"] == "note_explicit"
    assert result["confidence"] == "high"
    assert result["raw"] == "88F"


def test_temperature_uses_the_midpoint_of_a_range():
    result = fade_points.temperature("85-86F, little shade")
    assert result["temp_f"] == 85.5
    assert result["source"] == "note_range"


def test_temperature_reads_a_low_decade_without_inventing_precision():
    result = fade_points.temperature("Dehydration bonk in low-70s breezy weather")
    assert result["temp_f"] == 72.0
    assert result["band"] == "70s"
    assert result["source"] == "note_decade"
    assert result["confidence"] == "low"


def test_temperature_reads_a_bare_decade():
    assert fade_points.temperature("rainy/cloudy 70s")["temp_f"] == 75.0
    assert fade_points.temperature("rainy, 60s")["band"] == "60s"


def test_feels_like_is_kept_out_of_the_air_temperature_column():
    result = fade_points.temperature("Feels-like 100F; run shortened")
    assert result["temp_f"] is None
    assert result["band"] is None
    assert result["feels_like_f"] == 100.0
    assert result["feels_like_band"] == "100s"
    assert result["feels_like_only"] is True


def test_feels_like_and_actual_temperature_can_coexist():
    result = fade_points.temperature("84F/feels-90 humid")
    assert result["temp_f"] == 84.0
    assert result["feels_like_f"] == 90.0
    assert result["band"] == "80s"
    assert result["feels_like_only"] is False


def test_feels_like_in_a_decade_note_does_not_become_the_air_temperature():
    result = fade_points.temperature("80s/feels-90 humid")
    assert result["temp_f"] == 85.0
    assert result["feels_like_f"] == 90.0


def test_heat_alone_is_not_a_temperature():
    assert fade_points.temperature("heat-driven bonk") is None
    assert fade_points.temperature("hot and miserable") is None


def test_a_split_time_is_not_a_temperature():
    assert fade_points.temperature("mile 14 blew up to 21:51") is None


def test_a_recorded_temp_f_wins_over_a_note():
    result = fade_points.temperature("85F, miserable", 92.3)
    assert result["temp_f"] == 92.3
    assert result["source"] == "recorded"


def test_implausible_temperatures_are_ignored():
    assert fade_points.temperature("5F outside") is None
    assert fade_points.temperature("200F outside") is None
    assert fade_points.temperature("", 300) is None


# ----------------------------------------------------------------------- point

def test_point_exists_without_any_fuel_entry():
    item = fade_points.point(_row())
    assert item is not None
    assert item["fade_s_per_mi"] == run_fuel.fade(SPLITS)["fade_s_per_mi"]
    assert item["fade_pct"] == run_fuel.fade(SPLITS)["fade_pct"]
    assert item["fade_onset"]["onset_mile"] == 3
    assert item["fade_onset"]["onset_time_s"] == 1210
    assert item["fade_onset"]["composite_score"] > 0
    assert item["fade_composite"] == item["fade_onset"]["composite_score"]
    assert "Descriptive" in item["fade_onset"]["caveat"]
    assert item["intake"]["water_oz"] is None
    assert item["intake"]["kcal"] is None
    assert item["hydration"] == "not recorded"
    assert item["fuel_status"] == "not recorded"
    assert item["electrolytes"] == "not recorded"


def test_point_requires_four_usable_splits():
    assert fade_points.point(_row(splits=[600, 610, 620])) is None
    assert fade_points.point(_row(splits=None)) is None


def test_a_run_that_got_faster_has_no_invented_onset():
    item = fade_points.point(_row(splits=[700, 720, 600, 610]))
    assert item is not None
    assert item["fade_onset"] is None
    assert item["fade_composite"] is None


def test_explicit_zeros_are_recorded_zeros_not_missing_values():
    events = [
        {"kind": "water", "oz": 0.0},
        {"kind": "electrolyte", "sodium_mg": 0.0},
    ]
    item = fade_points.point(_row(fuel=_fuel(
        events, totals={"oz": 0.0, "sodium_mg": 0.0})))
    assert item["intake"]["water_oz"] == 0.0
    assert item["intake"]["sodium_mg"] == 0.0
    assert item["hydration"] == "none"
    assert item["electrolytes"] == "none"


def test_unmeasured_events_are_not_reported_as_zeros():
    item = fade_points.point(_row(fuel=_fuel([
        {"kind": "water"}, {"kind": "fuel"}, {"kind": "electrolyte"}])))
    assert item["intake"]["water_oz"] is None
    assert item["hydration"] == "unmeasured"
    assert item["fuel_status"] == "unmeasured"
    assert item["electrolytes"] == "unmeasured"


def test_measured_intake_is_recorded():
    item = fade_points.point(_row(fuel=_fuel([
        {"kind": "water", "oz": 20},
        {"kind": "fuel", "kcal": 100, "carbs_g": 21},
        {"kind": "electrolyte", "sodium_mg": 500}])))
    assert item["hydration"] == "recorded"
    assert item["fuel_status"] == "recorded"
    assert item["electrolytes"] == "recorded"


def test_a_fuel_entry_note_supplies_temperature():
    item = fade_points.point(_row(fuel=_fuel(
        note="88F heat; gel + LMNT mid-run.")))
    assert item["temperature"]["temp_f"] == 88.0


def test_journal_notes_supply_temperature_when_fuel_says_nothing():
    notes = {"2026-09-09": {"note": "Feels-like 100F", "temp_f": None}}
    item = fade_points.point(_row(), notes)
    assert item["temperature"]["feels_like_f"] == 100.0
    assert item["temperature"]["band"] is None


def test_a_note_only_entry_stays_flagged_for_review():
    item = fade_points.point(_row(fuel=_fuel(
        note="heat-driven", needs_review=True)))
    assert item["needs_review"] is True
    assert item["temperature"] is None


# -------------------------------------------------------------- intersections

def _point(fade_pct, key="not recorded", temperature=None):
    item = {
        "date": "2026-09-09",
        "fade_pct": fade_pct,
        "hydration": key,
        "fuel_status": key,
        "electrolytes": key,
        "temperature": temperature,
    }
    return item


def test_groups_need_three_runs_before_they_are_shown():
    result = fade_points.intersections([
        _point(1, "recorded"), _point(3, "recorded"),
        _point(5, "not recorded"), _point(7, "not recorded"),
        _point(9, "not recorded"),
    ])
    hydration = result["dimensions"][0]
    assert hydration["groups"][0]["key"] == "not recorded"
    assert hydration["groups"][0]["n"] == 3
    assert hydration["suppressed"] == [{"key": "recorded", "n": 2}]


def test_group_median_and_mean_are_reported_with_a_caveat():
    result = fade_points.intersections([_point(1), _point(3), _point(8)])
    group = result["dimensions"][0]["groups"][0]
    assert group["n"] == 3
    assert group["median_fade_pct"] == 3.0
    assert group["mean_fade_pct"] == 4.0
    assert "Descriptive only" in result["caveat"]
    assert "logged zero" in result["caveat"]


def test_feels_like_only_runs_do_not_join_a_temperature_band():
    points = [
        _point(1, temperature={"band": "80s", "feels_like_only": False}),
        _point(2, temperature={"band": "80s", "feels_like_only": False}),
        _point(3, temperature={"band": "80s", "feels_like_only": False}),
        _point(4, temperature={"band": None, "feels_like_only": True}),
    ]
    temp = fade_points.intersections(points)["dimensions"][3]
    assert temp["groups"][0]["key"] == "80s"
    assert temp["groups"][0]["n"] == 3
    assert temp["suppressed"][0]["key"] == "not recorded"


def test_none_and_not_recorded_stay_separate_groups():
    points = [_point(1, "none"), _point(2, "none"), _point(3, "none"),
              _point(4, "not recorded"), _point(5, "not recorded"),
              _point(6, "not recorded")]
    groups = fade_points.intersections(points)["dimensions"][0]["groups"]
    assert {g["key"] for g in groups} == {"none", "not recorded"}


# ---------------------------------------------------------------------- attach

def test_attach_adds_both_the_list_and_the_analysis():
    payload = {"activities": [_row(), _row(splits=[600, 610])]}
    fade_points.attach(payload, {})
    assert len(payload["fade_points"]) == 1
    assert payload["fade_analysis"]["count"] == 1
    assert payload["activities"][0]["fadePoint"]["fade_pct"] == 17.4
    assert "fadePoint" not in payload["activities"][1]


def test_attach_is_idempotent():
    payload = {"activities": [_row()]}
    fade_points.attach(payload, {})
    first = dict(payload["activities"][0]["fadePoint"])
    fade_points.attach(payload, {})
    assert payload["activities"][0]["fadePoint"] == first
    assert len(payload["fade_points"]) == 1


def test_attach_tolerates_other_shapes():
    assert fade_points.attach([], {}) == []
    assert fade_points.attach({}, {}) == {}
