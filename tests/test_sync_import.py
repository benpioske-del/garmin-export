"""The dashboard's "Sync Garmin now" action must import what it downloads.

Downloading and importing are separate steps. garmin_sync.py only writes .FIT
files; the dashboard, the audit and the briefs read trainloop.db. A sync that
stops after the download leaves a run invisible on the dashboard - the
2026-11-10 run arrived on disk and never showed up for exactly that reason.

These tests pin the order and the failure reporting without touching Garmin or
the real database.
"""

import subprocess
import sys

import garmin_server as G


class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _record(monkeypatch, results):
    """Replace subprocess.run with a scripted sequence and record each call."""
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return results[len(calls) - 1]

    monkeypatch.setattr(G.subprocess, "run", fake_run)
    return calls


def test_sync_downloads_then_imports(monkeypatch):
    calls = _record(monkeypatch, [
        _Result(stdout="Done\n"),
        _Result(stdout='{"inserted": 1, "unchanged": 72}\n'),
    ])

    res = G._run_sync()

    assert res["ok"] is True
    assert res["download_ok"] is True
    assert res["import_ok"] is True
    assert [c[0] for c in calls] == [
        [sys.executable, G.SYNC_SCRIPT],
        [sys.executable, G.IMPORT_SCRIPT, "bootstrap"],
    ]
    assert [c[1]["timeout"] for c in calls] == [300, 900]
    assert all(c[1]["cwd"] == G.ROOT for c in calls)
    assert "== Garmin sync ==" in res["output"]
    assert "== Database import ==" in res["output"]


def test_import_still_runs_when_the_download_fails(monkeypatch):
    calls = _record(monkeypatch, [
        _Result(returncode=1, stdout="login failed\n"),
        _Result(stdout="imported\n"),
    ])

    res = G._run_sync()

    assert res["ok"] is False
    assert res["download_ok"] is False
    assert res["import_ok"] is True
    assert len(calls) == 2
    assert "login failed" in res["output"]
    assert "[exit code 1]" in res["output"]


def test_a_failed_import_makes_the_sync_fail(monkeypatch):
    _record(monkeypatch, [
        _Result(stdout="Done\n"),
        _Result(returncode=2, stdout="bad database\n"),
    ])

    res = G._run_sync()

    assert res["ok"] is False
    assert res["download_ok"] is True
    assert res["import_ok"] is False
    assert res["exit"] == 2
    assert "[exit code 2]" in res["output"]


def test_a_timeout_names_the_step_that_timed_out(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))
        return _Result(stdout="ok\n")

    monkeypatch.setattr(G.subprocess, "run", fake_run)

    res = G._run_sync()

    assert res["ok"] is False
    assert res["download_ok"] is False
    assert res["import_ok"] is True
    assert "Garmin sync ran longer than 300s" in res["output"]


def test_a_missing_import_script_fails_before_downloading(monkeypatch, tmp_path):
    monkeypatch.setattr(G, "IMPORT_SCRIPT", str(tmp_path / "nope.py"))
    called = []
    monkeypatch.setattr(G.subprocess, "run",
                        lambda *a, **k: called.append(a) or _Result())

    res = G._run_sync()

    assert res["ok"] is False
    assert "trainloop.py not found" in res["output"]
    assert called == []
