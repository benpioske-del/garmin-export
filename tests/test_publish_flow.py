"""Tests for publish visibility, the publish lock, and the private fetch path.

Two scheduled tasks (`Garmin Export Publish`, `Garmin Export Publish PM`) run the
publisher unattended and push to GitHub with no human present. That makes two
things matter:

* `repo_visibility` used to be hardcoded to "public - readable without a token",
  so the moment the repo was made private the published meta file started lying
  and the raw URL started 404ing for the supervisor flow.
* A scheduled run would happily commit and push whatever was in the working tree,
  which is how half-finished work reached the public repo.
"""

import json
import os
import re
import time

import pytest

import export_publish


REMOTE = "https://github.com/benpioske-del/garmin-export.git"


@pytest.fixture
def fake_data_dir(tmp_path, monkeypatch):
    """Point the lock at a throwaway data directory."""
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setenv("GARMIN_DATA_DIR", str(d))
    monkeypatch.setattr(export_publish.paths, "data_dir", lambda: str(d))
    return d


def resp(status):
    class R:
        def __init__(self):
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    return R()


def http_error(code):
    return export_publish.urllib.error.HTTPError("u", code, "m", {}, None)


# --- visibility ---------------------------------------------------------------

def test_public_repo_probes_as_public(monkeypatch):
    seen = {}

    def fake(req, timeout=None):
        seen["method"] = req.get_method()
        seen["url"] = req.full_url
        return resp(200)

    monkeypatch.setattr(export_publish.urllib.request, "urlopen", fake)
    assert export_publish.probe_visibility(REMOTE, "main") == "public"
    assert seen["method"] == "HEAD"
    assert seen["url"].endswith("/main/garmin_export.csv")


@pytest.mark.parametrize("code", [401, 403, 404])
def test_refused_probe_means_private(monkeypatch, code):
    def fake(req, timeout=None):
        raise http_error(code)

    monkeypatch.setattr(export_publish.urllib.request, "urlopen", fake)
    assert export_publish.probe_visibility(REMOTE, "main") == "private"


def test_other_http_errors_are_unknown(monkeypatch):
    def fake(req, timeout=None):
        raise http_error(500)

    monkeypatch.setattr(export_publish.urllib.request, "urlopen", fake)
    assert export_publish.probe_visibility(REMOTE, "main") == "unknown"


def test_network_failure_is_unknown_not_public(monkeypatch):
    def fake(req, timeout=None):
        raise OSError("offline")

    monkeypatch.setattr(export_publish.urllib.request, "urlopen", fake)
    assert export_publish.probe_visibility(REMOTE, "main") == "unknown"


def test_non_github_remote_cannot_be_probed():
    assert export_publish.probe_visibility("https://example.com/x.git", "main") == "unknown"


def test_visibility_is_not_hardcoded_anywhere():
    """The old bug: meta claimed public regardless of the truth."""
    src = open(export_publish.__file__, encoding="utf-8").read()
    assert '"public - readable without a token"' not in src
    assert '"repo_visibility": "public"' not in src


# --- fetch instructions -------------------------------------------------------

def test_public_fetch_is_the_plain_raw_url():
    lines = export_publish.fetch_instructions(REMOTE, "main", "public")
    assert lines == ["curl -fsSL https://raw.githubusercontent.com/"
                     "benpioske-del/garmin-export/main/garmin_export.csv"]


def test_private_fetch_uses_the_api_and_names_the_env_var():
    lines = "\n".join(export_publish.fetch_instructions(REMOTE, "main", "private"))
    assert "api.github.com" in lines or "gh api" in lines
    assert "GITHUB_TOKEN" in lines
    # the raw url must not be offered as if it works
    assert "curl -fsSL https://raw.githubusercontent.com" not in lines


def test_private_instructions_embed_no_token_value():
    """A literal token in the instructions would end up in the meta file."""
    lines = "\n".join(export_publish.fetch_instructions(REMOTE, "main", "private"))
    assert "ghp_" not in lines
    assert "github_pat_" not in lines
    assert "$GITHUB_TOKEN" in lines


def test_unknown_visibility_is_treated_conservatively():
    lines = "\n".join(export_publish.fetch_instructions(REMOTE, "main", "unknown"))
    assert "could not be probed" in lines
    assert "GITHUB_TOKEN" in lines


def test_non_github_remote_says_so():
    lines = export_publish.fetch_instructions("https://example.com/x.git", "main", "public")
    assert "not a GitHub URL" in lines[0]


# --- the publish lock ---------------------------------------------------------

def test_lock_lives_outside_the_repository(fake_data_dir):
    p = export_publish.lock_path()
    assert str(fake_data_dir) in p
    assert os.path.dirname(p) != export_publish.REPO


def test_no_lock_means_not_locked(fake_data_dir):
    assert export_publish.lock_age_minutes() is None
    assert export_publish.is_locked() is False


def test_taking_the_lock_is_observable(fake_data_dir):
    export_publish.hold_lock()
    assert export_publish.is_locked() is True
    assert export_publish.lock_holder() == os.environ.get("USERNAME", "unknown")


def test_releasing_the_lock_clears_it(fake_data_dir):
    export_publish.hold_lock()
    assert export_publish.release_lock() is True
    assert export_publish.is_locked() is False


def test_releasing_an_unheld_lock_is_not_an_error(fake_data_dir):
    assert export_publish.release_lock() is False


def test_a_stale_lock_does_not_block_publishing_forever(fake_data_dir):
    """A crashed run must not silently stop the daily publish for good."""
    export_publish.hold_lock()
    stale = time.time() - (60 * 60 * 3)
    os.utime(export_publish.lock_path(), (stale, stale))
    assert export_publish.lock_age_minutes() > 45
    assert export_publish.is_locked() is False
    assert export_publish.is_locked(stale_minutes=240) is True


def test_a_corrupt_lock_file_does_not_crash_the_publisher(fake_data_dir):
    with open(export_publish.lock_path(), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert export_publish.lock_holder() == "unknown"
    assert export_publish.is_locked() is True


def test_lock_file_is_json_with_a_holder(fake_data_dir):
    export_publish.hold_lock()
    with open(export_publish.lock_path(), encoding="utf-8") as fh:
        data = json.load(fh)
    assert "at" in data and "pid" in data


# --- the stand-down path ------------------------------------------------------

def test_locked_publisher_stands_down_without_committing(fake_data_dir, monkeypatch, capsys):
    """The whole point: no commit, no push, and a clear reason."""
    git_calls = []
    monkeypatch.setattr(export_publish, "need_git", lambda: "git ok")
    monkeypatch.setattr(export_publish, "ensure_helper", lambda: "helper ok")
    monkeypatch.setattr(export_publish, "need_repo", lambda: REMOTE)
    monkeypatch.setattr(export_publish, "current_branch", lambda: "main")
    monkeypatch.setattr(export_publish, "probe_visibility", lambda r, b: "public")
    monkeypatch.setattr(export_publish, "run", lambda a, **k: git_calls.append(a))
    monkeypatch.setattr("sys.argv", ["export_publish.py"])
    export_publish.hold_lock()
    assert export_publish.main() == 0
    out = capsys.readouterr().out
    assert "standing down" in out
    assert not any("commit" in a for a in git_calls)
    assert not any("push" in a for a in git_calls)


def test_lock_flag_needs_no_git(monkeypatch, fake_data_dir, capsys):
    monkeypatch.setattr("sys.argv", ["export_publish.py", "--lock"])
    assert export_publish.main() == 0
    assert export_publish.is_locked() is True
    assert "held at" in capsys.readouterr().out


def test_unlock_flag_is_idempotent(monkeypatch, fake_data_dir, capsys):
    monkeypatch.setattr("sys.argv", ["export_publish.py", "--unlock"])
    assert export_publish.main() == 0
    assert "was not held" in capsys.readouterr().out


def test_lock_short_circuits_before_git_is_even_needed(monkeypatch, fake_data_dir):
    """--lock must work on a machine with no git on PATH."""
    def boom():
        raise AssertionError("should not have needed git")

    monkeypatch.setattr(export_publish, "need_git", boom)
    monkeypatch.setattr("sys.argv", ["export_publish.py", "--lock"])
    assert export_publish.main() == 0


# --- the content-level secret guard -------------------------------------------

REAL_TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"


def test_scan_catches_a_github_token():
    assert export_publish.scan_secrets("see token: %s" % REAL_TOKEN)


def test_scan_catches_an_authorization_header():
    assert export_publish.scan_secrets(
        'curl -H "Authorization: Bearer %s"' % REAL_TOKEN)


def test_scan_catches_a_real_looking_email():
    assert export_publish.scan_secrets("write to runner@protonmail.com")


def test_scan_allows_reserved_example_domains():
    """RFC 2606 domains cannot belong to a person, so docs are not a leak."""
    assert export_publish.scan_secrets("mail runner@example.com") == []
    assert export_publish.scan_secrets("mail runner@example.org") == []
    assert export_publish.scan_secrets("host localhost") == []


def test_scan_allows_the_env_var_reference_we_ship():
    """CREW_BRIEF.md documents the token *variable*, which must stay publishable."""
    recipe = ('curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \\\n'
              '  https://api.github.com/repos/o/r/contents/garmin_export.csv')
    assert export_publish.scan_secrets(recipe) == []


def test_scan_redacts_long_samples():
    found = export_publish.scan_secrets(REAL_TOKEN)
    assert found and "..." in found[0][1]


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(export_publish, "REPO", str(tmp_path))
    return tmp_path


def test_guard_refuses_a_file_containing_a_token(fake_repo):
    (fake_repo / "notes.md").write_text("token: %s\n" % REAL_TOKEN, encoding="utf-8")
    with pytest.raises(SystemExit):
        export_publish.guard_token_content(["notes.md"])


def test_guard_passes_a_clean_file(fake_repo):
    (fake_repo / "notes.md").write_text("just prose about running\n", encoding="utf-8")
    export_publish.guard_token_content(["notes.md"])


def test_guard_skips_declared_exempt_files(fake_repo):
    (fake_repo / "tests").mkdir()
    for rel in export_publish.GUARD_IMPL + export_publish.SYNTHETIC_CREDENTIAL_FILES:
        if "/" in rel:
            (fake_repo / rel).write_text("token: %s\n" % REAL_TOKEN, encoding="utf-8")
    export_publish.guard_token_content(
        list(export_publish.GUARD_IMPL) + list(export_publish.SYNTHETIC_CREDENTIAL_FILES))


def test_every_exemption_exists_on_disk():
    """An exemption for a file that no longer exists is a silent hole."""
    for rel in export_publish.GUARD_IMPL + export_publish.SYNTHETIC_CREDENTIAL_FILES:
        assert os.path.isfile(os.path.join(export_publish.REPO, rel)), rel


def test_exemptions_are_not_the_whole_test_suite():
    """Guard the guard: the exemption list must stay small and explicit."""
    assert len(export_publish.GUARD_IMPL) + len(export_publish.SYNTHETIC_CREDENTIAL_FILES) <= 10


def test_publishable_paths_cover_the_brief_and_the_export():
    paths = export_publish.publishable_text_paths()
    assert "CREW_BRIEF.md" in paths
    assert "CREW_TASKS.md" in paths
    assert "garmin_export.csv" in paths


def test_publishable_paths_exclude_the_private_dashboard():
    assert "dashboard/index.html" not in export_publish.publishable_text_paths()


def test_publishable_paths_have_no_duplicates():
    paths = export_publish.publishable_text_paths()
    assert len(paths) == len(set(paths))


def test_real_repository_passes_the_secret_guard():
    """The guard must pass the real tree, or publishing is permanently wedged."""
    export_publish.guard_token_content(export_publish.publishable_text_paths())


# --- where repo_visibility actually lands -------------------------------------

def test_publish_state_records_the_probed_visibility():
    """Pinned because it was documented as living in the wrong file.

    `garmin_export.meta.json` is built by build_csv(), which knows nothing about
    visibility; the probed value is written to publish_state.json in main().
    """
    state = json.load(open(os.path.join(export_publish.REPO, "publish_state.json"),
                           encoding="utf-8"))
    vis = state.get("repo_visibility")
    assert vis, "publish_state.json has no repo_visibility"
    assert vis.split()[0] in ("public", "private", "unknown")


def test_visibility_is_absent_from_the_csv_meta():
    """It must live in exactly one file, so it cannot disagree with itself."""
    meta = json.load(open(os.path.join(export_publish.REPO, "garmin_export.meta.json"),
                          encoding="utf-8"))
    assert "repo_visibility" not in meta


@pytest.mark.parametrize("doc", ["CREW_BRIEF.md", "CREW_TASKS.md",
                                 "docs/IMPLEMENTATION_INVENTORY.md"])
def test_docs_naming_repo_visibility_name_the_right_file(doc):
    """Every paragraph that mentions repo_visibility must say where it lives.

    The docs claimed `garmin_export.meta.json`, which never had the field. Pointing
    a reader at the wrong file is worse than not documenting it at all.
    """
    path = os.path.join(export_publish.REPO, doc)
    if not os.path.isfile(path):
        pytest.skip("%s not present" % doc)
    text = open(path, encoding="utf-8").read()
    for para in re.split(r"\n\s*\n", text):
        if "repo_visibility" not in para:
            continue
        assert "publish_state.json" in para, (
            "%s mentions repo_visibility in a paragraph that does not name "
            "publish_state.json" % doc)