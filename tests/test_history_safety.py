"""The publisher must never silently discard a rewritten local history.

Regression guard. sync_with_remote() used to recover from any rebase conflict
by resetting --hard onto origin/<branch>. When the remote history had been
rewritten on purpose to purge leaked coordinates, that reset threw the purge
away and the next push republished the removed commits.

The check is a merge-base test: rewritten histories share no common ancestor.
"""

import os
import subprocess

import pytest

import export_publish

GIT = None


def sh(repo, *args):
    """Run git in `repo`. Mirrors export_publish.run(), which prepends GIT."""
    return subprocess.run([GIT, "-C", str(repo)] + list(args),
                          capture_output=True)


@pytest.fixture(autouse=True)
def git_binary():
    """GIT is resolved by need_git() at publish time, not at import."""
    global GIT
    export_publish.need_git()
    GIT = export_publish.GIT
    assert GIT, "git not found on this machine"
    return GIT


@pytest.fixture
def divergent_repos(tmp_path):
    """A bare 'remote' and a local clone, then a force-push that rewrites it.

    Returns (local, bare_remote_path). Afterwards the two histories share no
    common ancestor, which is exactly the state a privacy purge produces.
    """
    bare = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    sh(tmp_path, "init", "-q", "-b", "main", str(seed))
    sh(seed, "config", "user.email", "t@t")
    sh(seed, "config", "user.name", "t")
    (seed / "f.txt").write_text("one\n", encoding="utf-8")
    sh(seed, "add", "f.txt")
    sh(seed, "commit", "-q", "-m", "first")
    sh(seed, "init", "-q", "--bare", "-b", "main", str(bare))
    sh(seed, "remote", "add", "origin", str(bare))
    sh(seed, "push", "-q", "origin", "main")

    local = tmp_path / "local"
    sh(tmp_path, "clone", "-q", str(bare), str(local))
    sh(local, "config", "user.email", "t@t")
    sh(local, "config", "user.name", "t")

    # Rewrite the remote. A second commit on top of the same history and a
    # force-push is still a fast-forward relationship, so the histories keep a
    # common ancestor. A real rewrite drops the old commits entirely, which is
    # what an orphan commit models. A fresh directory is used rather than
    # deleting `seed`, because git object files are read-only on Windows.
    fresh = tmp_path / "fresh"
    sh(tmp_path, "init", "-q", "-b", "main", str(fresh))
    sh(fresh, "config", "user.email", "t@t")
    sh(fresh, "config", "user.name", "t")
    (fresh / "f.txt").write_text("two\n", encoding="utf-8")
    sh(fresh, "add", "f.txt")
    sh(fresh, "commit", "-q", "-m", "rewritten root")
    sh(fresh, "remote", "add", "origin", str(bare))
    sh(fresh, "push", "-q", "--force", "origin", "main")

    sh(local, "fetch", "-q", "origin", "main")
    return local, bare


def test_rewritten_remote_is_detected_as_divergent(divergent_repos):
    local, _ = divergent_repos
    # Local still has the pre-rewrite history; origin has the new one.
    assert sh(local, "fetch", "origin").returncode == 0
    r = sh(local, "merge-base", "HEAD", "origin/main")
    assert r.returncode != 0, "expected no common ancestor"


@pytest.fixture
def isolated_publish(monkeypatch, divergent_repos):
    """Point every path the publisher uses at a throwaway clone.

    sync_with_remote() can run 'git reset --hard' and 'git rebase' against
    whatever REPO points at. monkeypatch.setattr on the module global is not
    enough on its own: run() reads the module-level REPO, and if any code path
    re-reads it from disk the real repository gets reset by a test. The
    guard below fails loudly rather than letting a test touch real history.
    """
    local, bare = divergent_repos
    real = os.path.realpath(export_publish.REPO)
    fake = os.path.realpath(str(local))
    assert real != fake, "test must not operate on the real repository"

    monkeypatch.setattr(export_publish, "REPO", str(local))
    export_publish.need_git()
    return local


def test_sync_refuses_instead_of_resetting(isolated_publish):
    """The publisher must abort, not reset --hard onto the rewritten remote."""
    local = isolated_publish

    before = sh(local, "rev-parse", "HEAD").stdout.decode().strip()

    with pytest.raises(SystemExit):
        export_publish.sync_with_remote("main")

    after = sh(local, "rev-parse", "HEAD").stdout.decode().strip()
    assert before == after, "sync moved HEAD; the purge would be undone"

    # And the pre-rewrite commit must still be reachable locally.
    assert sh(local, "cat-file", "-e", "HEAD:f.txt").returncode == 0
