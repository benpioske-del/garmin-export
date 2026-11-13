"""Tests for the offline athlete-data backup.

The backup exists because a dead laptop must not cost the FIT corpus or the
nutrition history: both are deliberately absent from git, and only the runs can
be rebuilt from Garmin Connect. These tests pin the two properties that matter —
the archive contains the irreplaceable data, and it never contains credentials.
"""

import datetime
import os
import zipfile

import backup_data as B


def make_data(tmp_path, secrets=True):
    data = tmp_path / "data"
    fit = data / "garmin_fit"
    fit.mkdir(parents=True)
    (fit / "2026-01-01_1.fit").write_bytes(b"fit-one")
    (fit / "2026-01-02_2.fit").write_bytes(b"fit-two")
    (data / "garmin_sleep.csv").write_text("date,sleep\n", encoding="utf-8")
    (data / "garmin_hr.csv").write_text("date,hr\n", encoding="utf-8")
    (data / "garmin_last_sync.json").write_text('{"newest_start": "x"}',
                                                encoding="utf-8")
    (data / "nutrition_log.csv").write_text("date,calories\n", encoding="utf-8")
    (data / "nutrition_log.records.json").write_text("[]", encoding="utf-8")
    if secrets:
        (data / ".coach_dash_token").write_text("secret", encoding="utf-8")
        (data / ".coach_dash_auth").write_text("secret", encoding="utf-8")
        (data / "nutrition_log.hook-token").write_text("secret", encoding="utf-8")
        (data / "garmin_tokens.json").write_text("{}", encoding="utf-8")
        (data / "garmin_sync.log").write_text("log", encoding="utf-8")
        tokens = data / ".garmin_tokens"
        tokens.mkdir()
        (tokens / "oauth1_token.json").write_text("{}", encoding="utf-8")
    return data


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "trainloop.db").write_bytes(b"db")
    dash = repo / "dashboard"
    dash.mkdir()
    (dash / "index.html").write_text("<html>classic</html>", encoding="utf-8")
    return repo


def names_in(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        return set(zf.namelist())


# --- contents --------------------------------------------------------------

def test_backup_includes_fit_corpus_and_database(tmp_path):
    data = make_data(tmp_path)
    repo = make_repo(tmp_path)
    result = B.create_backup(dest=str(tmp_path / "out"), data_dir=str(data),
                             repo_dir=str(repo))
    assert result["ok"]
    names = names_in(result["path"])
    assert "garmin_fit/2026-01-01_1.fit" in names
    assert "garmin_fit/2026-01-02_2.fit" in names
    assert "trainloop.db" in names


def test_backup_includes_the_local_only_classic_dashboard(tmp_path):
    """dashboard/index.html is gitignored and not rebuilt from anything."""
    data = make_data(tmp_path)
    repo = make_repo(tmp_path)
    result = B.create_backup(dest=str(tmp_path / "out"), data_dir=str(data),
                             repo_dir=str(repo))
    assert "dashboard/index.html" in names_in(result["path"])


def test_backup_includes_nutrition_sidecar(tmp_path):
    """The Health Connect raw records are the one dataset git cannot rebuild."""
    data = make_data(tmp_path)
    repo = make_repo(tmp_path)
    result = B.create_backup(dest=str(tmp_path / "out"), data_dir=str(data),
                             repo_dir=str(repo))
    assert "nutrition_log.records.json" in names_in(result["path"])


def test_backup_includes_sync_marker_and_exports(tmp_path):
    data = make_data(tmp_path)
    repo = make_repo(tmp_path)
    result = B.create_backup(dest=str(tmp_path / "out"), data_dir=str(data),
                             repo_dir=str(repo))
    names = names_in(result["path"])
    for expected in ("garmin_last_sync.json", "garmin_sleep.csv",
                     "garmin_hr.csv", "nutrition_log.csv"):
        assert expected in names


def test_manifest_is_written_and_names_the_commit(tmp_path):
    data = make_data(tmp_path)
    repo = make_repo(tmp_path)
    git = repo / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "refs" / "heads" / "main").write_text("a" * 40 + "\n",
                                                 encoding="utf-8")
    result = B.create_backup(dest=str(tmp_path / "out"), data_dir=str(data),
                             repo_dir=str(repo))
    with zipfile.ZipFile(result["path"]) as zf:
        manifest = zf.read(B.MANIFEST_NAME).decode("utf-8")
    assert "code commit: aaaaaaaaaaaa" in manifest
    assert "docs/RESTORE.md" in manifest


# --- credentials -----------------------------------------------------------

def test_backup_excludes_credentials_by_default(tmp_path):
    data = make_data(tmp_path)
    repo = make_repo(tmp_path)
    result = B.create_backup(dest=str(tmp_path / "out"), data_dir=str(data),
                             repo_dir=str(repo))
    names = names_in(result["path"])
    for secret in (".coach_dash_token", ".coach_dash_auth",
                   "nutrition_log.hook-token", "garmin_tokens.json",
                   "garmin_sync.log"):
        assert secret not in names, secret
    assert not any(n.startswith(".garmin_tokens/") for n in names)


def test_excluded_credentials_are_reported(tmp_path):
    data = make_data(tmp_path)
    repo = make_repo(tmp_path)
    result = B.create_backup(dest=str(tmp_path / "out"), data_dir=str(data),
                             repo_dir=str(repo))
    assert ".coach_dash_token" in result["excluded"]
    assert ".garmin_tokens/" in result["excluded"]


def test_manifest_says_credentials_were_excluded(tmp_path):
    data = make_data(tmp_path)
    repo = make_repo(tmp_path)
    result = B.create_backup(dest=str(tmp_path / "out"), data_dir=str(data),
                             repo_dir=str(repo))
    with zipfile.ZipFile(result["path"]) as zf:
        manifest = zf.read(B.MANIFEST_NAME).decode("utf-8")
    assert "excluded credentials" in manifest
    assert "recreate after a restore" in manifest


def test_include_secrets_bundles_them_when_asked(tmp_path):
    data = make_data(tmp_path)
    repo = make_repo(tmp_path)
    result = B.create_backup(dest=str(tmp_path / "out"), data_dir=str(data),
                             repo_dir=str(repo), include_secrets=True)
    names = names_in(result["path"])
    assert ".coach_dash_token" in names
    assert ".garmin_tokens/oauth1_token.json" in names
    assert result["excluded"] == []


# --- retention -------------------------------------------------------------

def test_retention_keeps_newest_and_prunes_oldest(tmp_path):
    data = make_data(tmp_path)
    repo = make_repo(tmp_path)
    out = tmp_path / "out"
    for day in range(1, 6):
        B.create_backup(dest=str(out), data_dir=str(data), repo_dir=str(repo),
                        keep=3,
                        now=datetime.datetime(2026, 1, day, 9, 0))
    kept = sorted(n for n in os.listdir(str(out)) if n.endswith(".zip"))
    assert len(kept) == 3
    assert kept[0].startswith("coach-data-2026-01-03")


def test_keep_below_one_disables_pruning(tmp_path):
    data = make_data(tmp_path)
    repo = make_repo(tmp_path)
    out = tmp_path / "out"
    for day in range(1, 4):
        B.create_backup(dest=str(out), data_dir=str(data), repo_dir=str(repo),
                        keep=0,
                        now=datetime.datetime(2026, 1, day, 9, 0))
    assert len([n for n in os.listdir(str(out)) if n.endswith(".zip")]) == 3


# --- failure modes ---------------------------------------------------------

def test_empty_data_dir_reports_failure_without_raising(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    result = B.create_backup(dest=str(tmp_path / "out"), data_dir=str(empty),
                             repo_dir=str(repo))
    assert result["ok"] is False
    assert result["error"] == "nothing to back up"


def test_dry_run_writes_nothing(tmp_path, capsys):
    make_data(tmp_path)
    make_repo(tmp_path)
    out = tmp_path / "out"
    code = B.main(["--dest", str(out), "--dry-run"])
    assert code == 0
    assert not os.path.exists(str(out))
    assert "files" in capsys.readouterr().out


# --- destination -----------------------------------------------------------

def test_default_dest_prefers_onedrive(tmp_path, monkeypatch):
    onedrive = tmp_path / "OneDrive"
    onedrive.mkdir()
    monkeypatch.setenv("OneDrive", str(onedrive))
    assert B.default_dest() == os.path.join(str(onedrive),
                                            "CoachDashboardBackups")


def test_default_dest_falls_back_to_documents(tmp_path, monkeypatch):
    monkeypatch.delenv("OneDrive", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    assert B.default_dest() == os.path.join(str(home), "Documents",
                                            "CoachDashboardBackups")


# --- git marker ------------------------------------------------------------

def test_head_commit_reads_a_loose_ref(tmp_path):
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "refs" / "heads" / "main").write_text("b" * 40 + "\n",
                                                 encoding="utf-8")
    assert B.head_commit(str(tmp_path)) == "b" * 12


def test_head_commit_is_unknown_without_git(tmp_path):
    assert B.head_commit(str(tmp_path)) == "unknown"
