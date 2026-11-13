"""Tests for the server-side CalTrak nutrition parser and local log.

CalTrak exports one row per food entry, so the parser's job is aggregation:
several rows can share a date and the dashboard wants one daily total. These
tests pin the aggregation, the header aliases, the rejection rules, and the
fact that the log is read and written idempotently.

The committed ``nutrition_log.csv`` is headers only; ingested rows live in the
local data directory. Every test here points ``NUTRITION_FILE`` at a temp file,
so the athlete's real log is never read or written.
"""

import csv

import pytest

import nutrition


@pytest.fixture
def log_path(monkeypatch, tmp_path):
    path = tmp_path / "nutrition_log.csv"
    monkeypatch.setattr(nutrition, "NUTRITION_FILE", str(path))
    return path


# --------------------------------------------------------------- aggregation

def test_rows_sharing_a_date_are_summed():
    csv_text = (
        "date,calories,protein,carbs,fat\n"
        "2026-11-10,300,20,30,10\n"
        "2026-11-10,250,15,40,8\n"
        "2026-11-11,500,30,60,15\n"
    )
    days = nutrition.parse_caltrak_csv(csv_text)
    assert days == [
        {"date": "2026-11-10", "calories": 550, "protein": 35,
         "carbs": 70, "fat": 18},
        {"date": "2026-11-11", "calories": 500, "protein": 30,
         "carbs": 60, "fat": 15},
    ]


def test_days_come_back_sorted_by_date():
    csv_text = (
        "date,calories,protein,carbs,fat\n"
        "2026-11-12,100,1,1,1\n"
        "2026-11-10,100,1,1,1\n"
        "2026-11-11,100,1,1,1\n"
    )
    assert [d["date"] for d in nutrition.parse_caltrak_csv(csv_text)] == [
        "2026-11-10", "2026-11-11", "2026-11-12"]


def test_fractional_totals_are_kept():
    csv_text = (
        "date,calories,protein,carbs,fat\n"
        "2026-11-10,100.5,10.25,1,0\n"
        "2026-11-10,0.5,0.75,0,0\n"
    )
    day = nutrition.parse_caltrak_csv(csv_text)[0]
    assert day["calories"] == 101
    assert day["protein"] == 11
    assert day["carbs"] == 1
    assert day["fat"] == 0


def test_empty_numeric_cells_count_as_zero():
    csv_text = (
        "date,calories,protein,carbs,fat\n"
        "2026-11-10,,20,,5\n"
    )
    day = nutrition.parse_caltrak_csv(csv_text)[0]
    assert day == {"date": "2026-11-10", "calories": 0, "protein": 20,
                   "carbs": 0, "fat": 5}


def test_a_missing_numeric_column_is_simply_not_summed():
    csv_text = "date,calories,protein\n2026-11-10,400,25\n"
    day = nutrition.parse_caltrak_csv(csv_text)[0]
    assert day == {"date": "2026-11-10", "calories": 400, "protein": 25,
                   "carbs": 0, "fat": 0}


def test_blank_lines_are_skipped():
    csv_text = (
        "date,calories,protein,carbs,fat\n"
        "\n"
        "2026-11-10,300,20,30,10\n"
        "   \n"
    )
    assert len(nutrition.parse_caltrak_csv(csv_text)) == 1


# ------------------------------------------------------------------- aliases

def test_common_caltrak_header_aliases_are_accepted():
    csv_text = (
        "Day,kcal,Protein,Carbohydrates,Fat\n"
        "2026-11-10,300,20,30,10\n"
    )
    day = nutrition.parse_caltrak_csv(csv_text)[0]
    assert day == {"date": "2026-11-10", "calories": 300, "protein": 20,
                   "carbs": 30, "fat": 10}


def test_energy_and_carb_aliases_are_accepted():
    csv_text = "day,energy,protein,carb,fat\n2026-11-10,300,20,30,10\n"
    day = nutrition.parse_caltrak_csv(csv_text)[0]
    assert day["calories"] == 300
    assert day["carbs"] == 30


def test_headers_are_case_and_space_insensitive():
    csv_text = (
        "  Date , CALORIES , Protein , Carbs , Fat \n"
        "2026-11-10,300,20,30,10\n"
    )
    day = nutrition.parse_caltrak_csv(csv_text)[0]
    assert day["calories"] == 300


@pytest.mark.parametrize("text,expected", [
    ("2026-11-10", "2026-11-10"),
    ("2026/11/10", "2026-11-10"),
    ("11/10/2026", "2026-11-10"),
    ("11/10/26", "2026-11-10"),
])
def test_date_formats_are_normalized(text, expected):
    csv_text = "date,calories,protein,carbs,fat\n%s,300,20,30,10\n" % text
    assert nutrition.parse_caltrak_csv(csv_text)[0]["date"] == expected


# ------------------------------------------------------------------ rejection

def test_empty_csv_is_rejected():
    with pytest.raises(nutrition.NutritionError):
        nutrition.parse_caltrak_csv("")


def test_missing_date_column_is_rejected():
    with pytest.raises(nutrition.NutritionError):
        nutrition.parse_caltrak_csv("calories,protein\n300,20\n")


def test_invalid_date_is_rejected():
    with pytest.raises(nutrition.NutritionError):
        nutrition.parse_caltrak_csv(
            "date,calories,protein,carbs,fat\nnot-a-date,1,1,1,1\n")


def test_negative_value_is_rejected():
    with pytest.raises(nutrition.NutritionError):
        nutrition.parse_caltrak_csv(
            "date,calories,protein,carbs,fat\n2026-11-10,-1,1,1,1\n")


def test_non_numeric_value_is_rejected():
    with pytest.raises(nutrition.NutritionError):
        nutrition.parse_caltrak_csv(
            "date,calories,protein,carbs,fat\n2026-11-10,many,1,1,1\n")


def test_a_row_without_a_date_is_rejected():
    with pytest.raises(nutrition.NutritionError):
        nutrition.parse_caltrak_csv(
            "date,calories,protein,carbs,fat\n,300,20,30,10\n")


# ------------------------------------------------------------ days payloads

def test_normalize_days_merges_repeated_dates():
    days = nutrition.normalize_days([
        {"date": "2026-11-10", "calories": 300, "protein": 20,
         "carbs": 30, "fat": 10},
        {"date": "2026-11-10", "calories": 250, "protein": 15,
         "carbs": 40, "fat": 8},
    ])
    assert days == [{"date": "2026-11-10", "calories": 250, "protein": 15,
                     "carbs": 40, "fat": 8}]


def test_normalize_days_accepts_calorie_aliases():
    days = nutrition.normalize_days([{"date": "2026-11-10", "kcal": 300}])
    assert days[0]["calories"] == 300


def test_normalize_days_rejects_a_non_list():
    with pytest.raises(nutrition.NutritionError):
        nutrition.normalize_days({"date": "2026-11-10"})


def test_normalize_days_rejects_a_non_object_entry():
    with pytest.raises(nutrition.NutritionError):
        nutrition.normalize_days(["2026-11-10"])


def test_normalize_days_rejects_a_negative_value():
    with pytest.raises(nutrition.NutritionError):
        nutrition.normalize_days([{"date": "2026-11-10", "fat": -2}])


# ------------------------------------------------------------- local storage

def test_missing_log_reads_as_empty(log_path):
    assert not log_path.exists()
    assert nutrition.read_days() == []


def test_upsert_then_read_round_trips(log_path):
    result = nutrition.upsert_days([
        {"date": "2026-11-10", "calories": 500, "protein": 30,
         "carbs": 60, "fat": 15},
    ])
    assert result == {"accepted": 1, "upserted": 1, "total_days": 1}
    assert nutrition.read_days() == [
        {"date": "2026-11-10", "calories": 500, "protein": 30,
         "carbs": 60, "fat": 15}]


def test_upsert_is_idempotent(log_path):
    day = {"date": "2026-11-10", "calories": 500, "protein": 30,
           "carbs": 60, "fat": 15}
    first = nutrition.upsert_days([day])
    second = nutrition.upsert_days([day])
    assert first == second
    assert len(nutrition.read_days()) == 1


def test_upsert_repeated_date_updates_instead_of_appending(log_path):
    nutrition.upsert_days([
        {"date": "2026-11-10", "calories": 500, "protein": 30,
         "carbs": 60, "fat": 15},
    ])
    result = nutrition.upsert_days([
        {"date": "2026-11-10", "calories": 600, "protein": 40,
         "carbs": 70, "fat": 20},
    ])
    assert result["total_days"] == 1
    rows = nutrition.read_days()
    assert len(rows) == 1
    assert rows[0]["calories"] == 600


def test_upsert_keeps_unrelated_dates(log_path):
    nutrition.upsert_days([{"date": "2026-11-10", "calories": 500}])
    nutrition.upsert_days([{"date": "2026-11-11", "calories": 700}])
    assert [r["date"] for r in nutrition.read_days()] == [
        "2026-11-10", "2026-11-11"]


def test_written_log_has_the_committed_schema(log_path):
    nutrition.upsert_days([{"date": "2026-11-10", "calories": 500,
                            "protein": 30, "carbs": 60, "fat": 15}])
    with open(log_path, "r", encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh))
    assert header == list(nutrition.FIELDS)


def test_a_corrupt_log_header_is_an_error_not_an_empty_log(log_path):
    log_path.write_text("calories,protein\n500,30\n", encoding="utf-8")
    with pytest.raises(nutrition.NutritionError):
        nutrition.read_days()


def test_payload_envelope(log_path):
    nutrition.upsert_days([{"date": "2026-11-10", "calories": 500,
                            "protein": 30, "carbs": 60, "fat": 15}])
    body = nutrition.payload()
    assert body["count"] == 1
    assert body["days"] == [
        {"date": "2026-11-10", "calories": 500, "protein": 30,
         "carbs": 60, "fat": 15}]
    assert body["fields"] == list(nutrition.FIELDS)
    assert "local" in body["storage"]


def test_the_committed_template_is_still_the_schema():
    """The committed file must stay headers-only: real rows are local."""
    import os
    import paths
    committed = os.path.join(paths.repo_dir(), "nutrition_log.csv")
    with open(committed, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == list(nutrition.FIELDS)
    assert len(rows) == 1


# ------------------------------------------------- health connect webhook

def _hc_raw(record_id, date, calories, protein=0, carbs=0, fat=0):
    return {
        "start_time": date + "T08:00:00-08:00",
        "end_time": date + "T08:05:00-08:00",
        "calories": calories,
        "protein_grams": protein,
        "carbs_grams": carbs,
        "fat_grams": fat,
        "metadata": {"id": record_id},
    }


def test_health_connect_daily_record_is_upserted(log_path):
    result = nutrition.ingest_health_connect({
        "timezone": "America/Los_Angeles",
        "nutrition": [{
            "start_time": "2026-11-10T00:00:00-08:00",
            "end_time": "2026-11-11T00:00:00-08:00",
            "calories": 2100,
            "protein_grams": 140,
            "carbs_grams": 220,
            "fat_grams": 70,
        }],
    })
    assert result["accepted"] == 1
    assert result["upserted"] == 1
    assert nutrition.read_days() == [{
        "date": "2026-11-10", "calories": 2100, "protein": 140,
        "carbs": 220, "fat": 70}]


def test_health_connect_raw_records_sum_within_a_day(log_path):
    nutrition.ingest_health_connect({"nutrition": [
        _hc_raw("a", "2026-11-10", 300, 20, 30, 10),
        _hc_raw("b", "2026-11-10", 250, 15, 40, 8),
    ]})
    assert nutrition.read_days() == [{
        "date": "2026-11-10", "calories": 550, "protein": 35,
        "carbs": 70, "fat": 18}]


def test_health_connect_incremental_record_keeps_the_rest_of_the_day(log_path):
    nutrition.ingest_health_connect({"nutrition": [
        _hc_raw("a", "2026-11-10", 300, 20, 30, 10)]})
    nutrition.ingest_health_connect({"nutrition": [
        _hc_raw("b", "2026-11-10", 250, 15, 40, 8)]})
    assert nutrition.read_days()[0]["calories"] == 550


def test_health_connect_edit_replaces_the_same_id(log_path):
    nutrition.ingest_health_connect({"nutrition": [
        _hc_raw("a", "2026-11-10", 300)]})
    nutrition.ingest_health_connect({"nutrition": [
        _hc_raw("a", "2026-11-10", 350)]})
    assert nutrition.read_days()[0]["calories"] == 350


def test_health_connect_deleted_record_is_removed(log_path):
    nutrition.ingest_health_connect({"nutrition": [
        _hc_raw("a", "2026-11-10", 300),
        _hc_raw("b", "2026-11-10", 250),
    ]})
    nutrition.ingest_health_connect({
        "nutrition": [],
        "deleted": [{"type": "nutrition", "id": "a"}],
    })
    assert nutrition.read_days()[0]["calories"] == 250


def test_a_daily_record_supersedes_raw_records_for_that_day(log_path):
    nutrition.ingest_health_connect({"nutrition": [
        _hc_raw("a", "2026-11-10", 300)]})
    nutrition.ingest_health_connect({"nutrition": [{
        "start_time": "2026-11-10T00:00:00-08:00",
        "end_time": "2026-11-11T00:00:00-08:00",
        "calories": 2100,
    }]})
    assert nutrition.read_days()[0]["calories"] == 2100


def test_health_connect_does_not_erase_a_manual_day(log_path):
    nutrition.upsert_days([{"date": "2026-11-09", "calories": 100}])
    nutrition.ingest_health_connect({"nutrition": [
        _hc_raw("a", "2026-11-10", 300)]})
    assert [row["date"] for row in nutrition.read_days()] == [
        "2026-11-09", "2026-11-10"]


def test_health_connect_rejects_a_non_object_payload(log_path):
    with pytest.raises(nutrition.NutritionError):
        nutrition.ingest_health_connect([])


def test_health_connect_rejects_a_non_list_nutrition(log_path):
    with pytest.raises(nutrition.NutritionError):
        nutrition.ingest_health_connect({"nutrition": {}})


# ---------------------------------------------------- CalTrak JSON backups

def test_json_backup_days_shape_is_accepted():
    days = nutrition.parse_caltrak_json(
        '{"days": [{"date": "2026-11-10", "calories": 500}]}')
    assert days == [{"date": "2026-11-10", "calories": 500,
                     "protein": 0, "carbs": 0, "fat": 0}]


def test_json_backup_nested_food_log_is_aggregated():
    days = nutrition.parse_caltrak_json({
        "version": 1,
        "food_log": [
            {"logged_at": "2026-11-10T08:00:00Z",
             "food": {"name": "oats", "calories": 300, "protein": 20,
                      "carbs": 30, "fat": 10}},
            {"logged_at": "2026-11-10T12:00:00Z",
             "food": {"name": "rice", "calories": 400, "protein": 10,
                      "carbs": 80, "fat": 5}},
        ],
    })
    assert days == [{"date": "2026-11-10", "calories": 700,
                     "protein": 30, "carbs": 110, "fat": 15}]


def test_json_backup_without_nutrition_is_rejected():
    with pytest.raises(nutrition.NutritionError):
        nutrition.parse_caltrak_json({"version": 1, "notes": []})


def test_parse_export_detects_json_and_csv():
    json_day = nutrition.parse_export(
        '{"days": [{"date": "2026-11-10", "calories": 1}]}')[0]
    csv_day = nutrition.parse_export(
        "date,calories\n2026-11-10,1\n")[0]
    assert json_day["date"] == "2026-11-10"
    assert csv_day["date"] == "2026-11-10"


# ------------------------------------------------------- phone webhook token

def test_hook_token_is_stable_and_stored_next_to_the_log(log_path):
    first = nutrition.load_or_make_hook_token()
    second = nutrition.load_or_make_hook_token()
    assert first == second
    assert len(first) >= 20
    with open(nutrition.hook_token_path(), "r", encoding="utf-8") as fh:
        assert fh.read().strip() == first


def test_hook_info_reports_the_last_upload(log_path):
    nutrition.ingest_health_connect({"nutrition": [
        _hc_raw("a", "2026-11-10", 300)]})
    info = nutrition.hook_info()
    assert info["path"] == "/api/nutrition/hook"
    assert info["header"] == "X-Nutrition-Token"
    assert info["token"]
    assert info["last_received"]
    assert info["managed_days"] == 1
