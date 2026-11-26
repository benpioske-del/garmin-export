"""Conversion of the athlete's typed classic journal into fuel entries.

The browser database itself is private and local-only, so these tests exercise
the allowlist, the value decoder and the conversion rules with synthetic rows.
No credential, token or browser file is read here.
"""

import json

import browser_journal
import run_fuel


def test_only_the_two_classic_keys_are_allowlisted():
    assert browser_journal.ALLOWED_KEYS == frozenset((
        "season-report-v1:custom-runs",
        "season-report-v1:run-overrides",
    ))


def test_missing_table_is_an_empty_journal(tmp_path):
    assert browser_journal.read(str(tmp_path / "missing.ldb")) == []


def test_cp1252_separator_and_generated_prefix_are_stripped():
    payload = {"note": "Imported from Garmin CSV \u00b7 10ft gain, 3ft loss "
                       "\u00b7 hydration 0 oz"}
    raw = b"\x01" + json.dumps(payload, ensure_ascii=False).encode("cp1252")
    assert browser_journal._decode_value(raw) == payload
    assert browser_journal._clean_note(payload["note"]) == "hydration 0 oz"


def test_typed_zero_oz_and_lower_case_none_are_deliberate_zeros():
    entry = browser_journal.to_entry({
        "date": "2026-10-10",
        "note": "hydration 0 oz \u00b7 electrolytes none",
        "events": [
            {"mi": "start", "kind": "water", "what": "0 oz"},
            {"mi": "start", "kind": "electrolyte", "what": "none"},
        ],
    })
    assert entry["source"] == "journal"
    assert entry["needs_review"] is False
    assert entry["events"][0]["oz"] == 0.0
    assert entry["events"][1]["sodium_mg"] == 0.0


def test_capital_none_is_not_recorded_and_stays_for_review():
    entry = browser_journal.to_entry({
        "date": "2026-09-29",
        "note": "Raining \u00b7 hydration None \u00b7 electrolytes None",
        "events": [
            {"mi": "start", "kind": "water", "what": "None"},
            {"mi": "start", "kind": "electrolyte", "what": "None"},
        ],
    })
    assert entry["needs_review"] is True
    for event in entry["events"]:
        for field in run_fuel.NUMERIC:
            assert event[field] is None
    assert [event["what"] for event in entry["events"]] == ["None", "None"]


def test_prose_amounts_are_never_silently_measured():
    entry = browser_journal.to_entry({
        "date": "2026-10-22",
        "note": "hydration 1500 ml \u00b7 electrolytes 1 LMNT at mile 7.5. "
                "2 gus 1 at 5 and one at 10,25",
        "events": [
            {"mi": "start", "kind": "water", "what": "1500 ml"},
            {"mi": "start", "kind": "electrolyte",
             "what": "1 LMNT at mile 7.5.   2 gus 1 at 5 and one at 10,25"},
        ],
    })
    assert entry["needs_review"] is True
    assert entry["events"][0]["what"] == "1500 ml"
    assert "2 gus" in entry["events"][1]["what"]
    for event in entry["events"]:
        for field in run_fuel.NUMERIC:
            assert event[field] is None


def test_note_only_entry_has_no_events_and_is_flagged():
    entry = browser_journal.to_entry({
        "date": "2026-10-29",
        "note": "Upper left leg/knee pain. Gu taken halfway.",
        "events": [],
    })
    assert entry["events"] == []
    assert entry["source"] == "journal-note"
    assert entry["needs_review"] is True
    assert "Gu taken halfway" in entry["note"]


def test_preview_redacts_sensitive_words_without_changing_the_entry():
    entry = browser_journal.to_entry({
        "date": "2026-10-01",
        "note": "cookie should never appear in a dry run",
        "events": [],
    })
    assert browser_journal.preview(entry)["note"] == "[suppressed]"
    assert entry["note"] == "cookie should never appear in a dry run"
