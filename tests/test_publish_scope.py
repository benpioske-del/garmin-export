"""Tests for what the unattended publisher is allowed to publish.

`Garmin Export Publish` and `Garmin Export Publish PM` are scheduled tasks that
stage, commit and push with no human present. `code_paths()` used to stage every
root-level `*.py`, so a throwaway scratch script was swept into a commit titled
"garmin export: N runs" and pushed to the public repo. The scope is now an
explicit allowlist, and these tests pin that behaviour.
"""

import os

import pytest

import export_publish


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(export_publish, "REPO", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write(repo, rel, body="x = 1\n"):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_scratch_scripts_are_recognised_as_scratch():
    assert export_publish.is_scratch_script("_cleanup.py")
    assert export_publish.is_scratch_script("_probe.py")
    assert export_publish.is_scratch_script("scratch.tmp")
    assert export_publish.is_scratch_script("notes.bak")
    assert export_publish.is_scratch_script("merge.orig")


def test_ordinary_modules_are_not_treated_as_scratch():
    assert not export_publish.is_scratch_script("recommend.py")
    assert not export_publish.is_scratch_script("trainingdb.py")
    assert not export_publish.is_scratch_script("export_publish.py")


def test_scratch_script_is_not_staged(fake_repo):
    write(fake_repo, "_cleanup.py", "import sqlite3\n")
    assert "_cleanup.py" not in export_publish.code_paths()


def test_unknown_module_is_not_staged(fake_repo):
    write(fake_repo, "brand_new_module.py")
    assert "brand_new_module.py" not in export_publish.code_paths()


def test_published_module_is_staged_when_present(fake_repo):
    write(fake_repo, "recommend.py")
    assert "recommend.py" in export_publish.code_paths()


def test_unpublished_scripts_reports_unknown_module(fake_repo):
    write(fake_repo, "brand_new_module.py")
    assert export_publish.unpublished_scripts() == ["brand_new_module.py"]


def test_unpublished_scripts_stays_quiet_for_scratch_and_known(fake_repo):
    write(fake_repo, "_cleanup.py")
    write(fake_repo, "recommend.py")
    assert export_publish.unpublished_scripts() == []


def test_missing_modules_are_simply_absent(fake_repo):
    # code_paths() must not invent paths that are not on disk.
    assert "recommend.py" not in export_publish.code_paths()


def test_nested_fixture_json_is_staged(fake_repo):
    write(fake_repo, "tests/fixtures/recommend/build-band.json", "{}")
    paths = export_publish.code_paths()
    assert "tests/fixtures/recommend/build-band.json" in paths


def test_non_json_fixture_is_not_staged(fake_repo):
    write(fake_repo, "tests/fixtures/notes.txt", "hi")
    assert "tests/fixtures/notes.txt" not in export_publish.code_paths()


def test_local_only_dashboard_is_still_skipped(fake_repo):
    write(fake_repo, "dashboard/index.html", "<html></html>")
    assert "dashboard/index.html" not in export_publish.code_paths()


def test_every_root_module_is_published_or_scratch():
    """No third category: an unlisted module would be silently unpublished."""
    repo = export_publish.REPO
    for name in sorted(os.listdir(repo)):
        if not name.endswith(".py") or not os.path.isfile(os.path.join(repo, name)):
            continue
        assert (name in export_publish.PUBLISHED_MODULES
                or export_publish.is_scratch_script(name)), (
            "%s is neither published nor scratch; decide which, on purpose" % name)


def test_published_modules_all_exist():
    for name in sorted(export_publish.PUBLISHED_MODULES):
        assert os.path.isfile(os.path.join(export_publish.REPO, name)), (
            "%s is listed for publishing but is not in the repo" % name)


def test_real_repository_has_no_stray_scripts():
    assert export_publish.unpublished_scripts() == []


def test_recommend_goldens_are_published():
    paths = export_publish.code_paths()
    assert "tests/fixtures/recommend/build-band.json" in paths
    assert "tests/fixtures/recommend/confirmation-required.json" in paths


def test_commit_message_stays_bare_for_a_data_only_refresh():
    msg = export_publish.build_commit_message(
        58, "2026-10-01", ["garmin_runs.csv", "garmin_export.meta.json"],
        {"garmin_runs.csv", "garmin_export.meta.json", "publish_state.json"})
    assert msg == "garmin export: 58 runs, latest 2026-10-01"


def test_commit_message_names_pipeline_files_it_also_ships():
    msg = export_publish.build_commit_message(
        58, "2026-10-01",
        ["garmin_runs.csv", "recommend.py", "docs/COACHING_POLICY_AUDIT.md"],
        {"garmin_runs.csv", "garmin_export.meta.json", "publish_state.json"})
    assert msg.startswith("garmin export: 58 runs, latest 2026-10-01")
    assert "2 pipeline file(s)" in msg
    assert "docs/COACHING_POLICY_AUDIT.md" in msg
    assert "recommend.py" in msg
    # the data file must not be listed as a pipeline change
    assert "garmin_runs.csv" not in msg.split("pipeline file(s):")[1]