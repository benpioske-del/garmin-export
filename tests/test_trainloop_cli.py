"""Tests for the trainloop.py command line entry point.

This is the surface a person actually types into, so it gets tested like one:
argument wiring, honest reporting, and refusal to invent inputs.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import activities  # noqa: E402
import trainloop  # noqa: E402
import trainingdb  # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Point the default database at a throwaway file."""
    path = tmp_path / "cli.db"
    monkeypatch.setenv("TRAINLOOP_DB", str(path))
    monkeypatch.setattr(trainingdb, "DB_ENV", "TRAINLOOP_DB")
    yield path
    if path.exists():
        os.unlink(path)


def _args(**kw):
    import argparse
    return argparse.Namespace(pattern=kw.pop("pattern", r"C:\nonexistent\*.fit"),
                              hr_max=kw.pop("hr_max", None),
                              as_of=kw.pop("as_of", None), **kw)


def test_parser_exposes_every_command():
    parser = trainloop.build_parser()
    # Read the subparser table rather than parsing, because `strength`
    # requires --at and parsing it bare would exit.
    actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
    names = set(actions[0].choices)
    for name in ("status", "doctor", "bootstrap", "migrate", "import", "audit",
                 "load", "recommend", "strength", "test", "publish"):
        assert name in names


def test_shared_defaults_reach_every_subcommand():
    """Commands that delegate to each other must still find their arguments."""
    parser = trainloop.build_parser()
    for name in ("status", "bootstrap", "migrate", "load", "recommend", "audit"):
        args = parser.parse_args([name])
        assert hasattr(args, "pattern")
        assert hasattr(args, "hr_max")
        assert hasattr(args, "as_of")


def test_no_arguments_prints_help(capsys):
    assert trainloop.main([]) == 1
    assert "usage" in capsys.readouterr().out.lower()


def test_bootstrap_delegates_to_import(db, capsys):
    # An explicit empty pattern keeps this test hermetic. Without it the
    # default points at the athlete's real FIT directory and imports 56 files.
    assert trainloop.main(["bootstrap", "--pattern", r"C:\nonexistent\*.fit"]) == 1
    out = capsys.readouterr().out
    assert "no FIT files matched" in out
    assert "database:" in out


def test_status_reports_an_empty_database_honestly(db, capsys):
    trainloop.main(["status"])
    out = capsys.readouterr().out
    # An empty database must not be presented as "there are no activities"
    # without also saying the FIT files are sitting there unimported.
    assert "activities in database: 0" in out
    assert "FIT files on disk" in out


def test_status_flags_a_populated_database(db, capsys, monkeypatch):
    conn = trainingdb.connect()
    trainingdb.migrate(conn, verbose=False)
    conn.close()
    monkeypatch.setattr(trainloop, "_fit_files", lambda pattern: ["a.fit", "b.fit"])
    trainloop.main(["status"])
    out = capsys.readouterr().out
    assert "activities in database: 0" in out
    assert "run: python trainloop.py bootstrap" in out


def test_status_flags_a_database_that_disagrees_with_disk(db, capsys, monkeypatch):
    conn = trainingdb.connect()
    trainingdb.migrate(conn, verbose=False)
    conn.execute("""INSERT INTO activities
        (activity_id, source_system, sport, start_utc, timezone_source,
         value_state, confidence, confirmation, review_state,
         first_seen_utc, last_updated_utc)
        VALUES ('garmin:1','garmin','Running','2026-01-01T07:00:00Z','unknown',
                'observed','high','not_required','closed','x','x')""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(trainloop, "_fit_files", lambda pattern: ["a.fit", "b.fit"])
    trainloop.main(["status"])
    out = capsys.readouterr().out
    assert "database has 1 activity but 2 FIT files are on disk" in out


def _seed_one_activity():
    conn = trainingdb.connect()
    trainingdb.migrate(conn, verbose=False)
    conn.execute("""INSERT INTO activities
        (activity_id, source_system, sport, start_utc, timezone_source,
         avg_hr, moving_time_s, value_state, confidence, confirmation,
         review_state, first_seen_utc, last_updated_utc)
        VALUES ('garmin:1','garmin','Running','2026-01-01T07:00:00Z','unknown',
                150, 2400, 'observed','high','not_required','closed','x','x')""")
    conn.commit()
    conn.close()


def test_hr_max_never_invented_from_age(db, capsys, monkeypatch):
    _seed_one_activity()
    monkeypatch.setattr(trainloop, "_hr_max", lambda explicit=None: None)
    trainloop.main(["load"])
    out = capsys.readouterr().out
    assert "UNAVAILABLE by design" in out
    assert "never estimated from age" in out
    assert "n/a" in out


def test_hr_max_read_from_profile(db, monkeypatch, tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"hr_max": 190}), encoding="utf-8")
    monkeypatch.setattr(trainloop, "HERE", tmp_path)
    assert trainloop._hr_max() == 190.0


def test_hr_max_command_line_beats_profile(db, monkeypatch, tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"hr_max": 190}), encoding="utf-8")
    monkeypatch.setattr(trainloop, "HERE", tmp_path)
    assert trainloop._hr_max(175) == 175.0


def test_load_refuses_on_an_empty_database(db, capsys):
    assert trainloop.main(["load"]) == 1
    assert "python trainloop.py bootstrap" in capsys.readouterr().out


def test_recommend_refuses_on_an_empty_database(db, capsys):
    assert trainloop.main(["recommend"]) == 1
    assert "python trainloop.py bootstrap" in capsys.readouterr().out


def test_load_table_marks_missing_components_as_na(db, capsys):
    _seed_one_activity()
    trainloop.main(["load", "--hr-max", "185", "--as-of", "2026-01-05T00:00:00Z"])
    out = capsys.readouterr().out
    assert "n/a" in out           # strength has no sessions
    assert "components are always shown separately" in out


def test_strength_command_records_a_session(db, capsys):
    rc = trainloop.main(["strength", "--at", "2026-01-01T18:00:00Z",
                         "--set", "Back Squat,5,100,7",
                         "--set", "Back Squat,5,100,7"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Back Squat" in out
    assert "volume" in out
    conn = trainingdb.connect()
    assert conn.execute(
        "SELECT COUNT(*) c FROM strength_sets").fetchone()["c"] == 2
    conn.close()


def test_strength_command_reports_progression_per_exercise(db, capsys):
    trainloop.main(["strength", "--at", "2026-01-01T18:00:00Z",
                    "--set", "Back Squat,5,100,7", "--set", "Back Squat,5,100,7",
                    "--set", "Romanian Deadlift,8,60,7"])
    out = capsys.readouterr().out
    # Each exercise gets its own answer, not one blended session answer.
    assert out.count("next:") == 2
    assert "fell short" not in out


def test_audit_writes_a_manifest(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(trainloop, "_fit_files", lambda pattern: [])
    out_json = tmp_path / "manifest.json"
    assert trainloop.main(["audit", "--json", str(out_json)]) == 0
    assert "FIT data audit" in capsys.readouterr().out
    assert json.loads(out_json.read_text(encoding="utf-8"))["versions"]


def test_audit_returns_nonzero_on_parse_failures(tmp_path, capsys, monkeypatch):
    bad = tmp_path / "bad.fit"
    bad.write_bytes(b"not a fit file")
    monkeypatch.setattr(trainloop, "_fit_files", lambda pattern: [str(bad)])
    assert trainloop.main(["audit"]) == 1
    assert "parse failures" in capsys.readouterr().out


def test_find_git_prefers_the_environment_override(monkeypatch, tmp_path):
    fake = tmp_path / "git.exe"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_TRAINLOOP", str(fake))
    assert trainloop._find_git() == str(fake)


def test_find_git_rejects_a_bad_override(monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_TRAINLOOP", str(tmp_path / "nope" / "git.exe"))
    assert trainloop._find_git() is None


def test_find_git_uses_path(monkeypatch, tmp_path):
    monkeypatch.delenv("GIT_TRAINLOOP", raising=False)
    monkeypatch.setattr(trainloop.shutil, "which", lambda name: "C:/somewhere/git.exe")
    assert trainloop._find_git() == "C:/somewhere/git.exe"

def test_find_git_survives_missing_path(monkeypatch, tmp_path):
    """This machine has git only inside GitHub Desktop, never on PATH."""
    monkeypatch.delenv("GIT_TRAINLOOP", raising=False)
    monkeypatch.setattr(trainloop.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(trainloop.os.path, "exists", lambda p: False)
    assert trainloop._find_git() is None


def test_doctor_still_runs_without_git(db, capsys, monkeypatch, tmp_path):
    """A missing git must not make doctor claim the database is unignored."""
    # The gitignore check only runs when the database lives inside the repo,
    # so stand the repo root up alongside the temporary database.
    (tmp_path / "garmin_export.csv").write_text("a\n", encoding="utf-8")
    monkeypatch.setattr(trainloop, "HERE", tmp_path)
    monkeypatch.setattr(trainloop.paths, "fit_dir", lambda: str(tmp_path / "fits"))
    (tmp_path / "fits").mkdir()
    monkeypatch.setattr(trainloop, "_find_git", lambda: None)
    trainloop.main(["doctor"])
    out = capsys.readouterr().out
    assert "skipping the gitignore check" in out
    assert "NOT gitignored" not in out
