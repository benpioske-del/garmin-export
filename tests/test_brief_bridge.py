"""Tests for the supervisor brief bridge.

The bridge takes untrusted text from a transport and writes it into a PUBLIC
repository, so most of these tests are about what it refuses: an unauthorised
caller, a request that tries to choose its own filename, an oversized body, a
brief carrying a credential or a coordinate, and a publish that fails. The
failure cases matter more than the happy path, because a mistake here publishes
someone's location.
"""

import io
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import brief_bridge
from brief_bridge import Handler

TOKEN = "test-token-not-a-real-secret-value-0123456789"

BRIEF = """# Supervisor Brief

## Task 1
Inspect the repository and document the existing architecture in
docs/IMPLEMENTATION_INVENTORY.md, naming exact file paths for the importer,
the schema layer and the test commands. This is a long enough body that it
clears the minimum-length check, which is deliberately small but non-zero.

## Task 2
Implement canonical activity records with provenance, keeping the raw source
value beside the derived one so a reader can tell which is which at a glance.

## Task 3
Add an explicit data-completeness state per activity, and never let a missing
day be recorded as a rest day without an explicit confirmation from the athlete.

## NEXT SUPERVISOR CHECK
Confirm the inventory names the real schema and that no task is marked done
without command output behind it.
"""


@pytest.fixture(autouse=True)
def isolated_staging(tmp_path, monkeypatch):
    """Keep every rejection out of the athlete's real data directory.

    Rejected briefs are staged under paths.data_dir(), which is ~/Downloads on
    a normal machine. Without this the test suite quietly accumulates files in
    the real inbox and staging folders, and a rejected brief can be left behind
    for a run that never happened.

    The directories are siblings of tmp_path, not children, because fake_repo
    points REPO at tmp_path and staging refuses to sit inside the repository.
    """
    base = tmp_path.parent / (tmp_path.name + "_isolated")
    monkeypatch.setenv("GARMIN_BRIDGE_STAGE", str(base / "staging"))
    monkeypatch.setenv("GARMIN_BRIDGE_INBOX", str(base / "inbox"))


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """Point the bridge at a throwaway repo and never publish for real."""
    monkeypatch.setattr(brief_bridge, "REPO", str(tmp_path))
    monkeypatch.setattr(brief_bridge, "publish", lambda target: (0, "ok"))
    return tmp_path


def serve_once(handler_cls=Handler):
    """Start the receiver on an ephemeral port and return (server, url)."""
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


def post(url, body, token=TOKEN, path="/brief", headers=None, ctype="text/plain"):
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url + path, data=data, method="POST")
    req.add_header("Content-Type", ctype)
    if token is not None:
        req.add_header("X-Bridge-Token", token)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


# ---------------------------------------------------------------- validation

def test_valid_brief_is_written(fake_repo):
    assert brief_bridge.commit_brief(BRIEF, source="test") == 0
    out = (fake_repo / "SUPERVISOR_BRIEF.md").read_text(encoding="utf-8")
    assert "Task 1" in out
    assert "source: test" in out
    assert "UNTRUSTED" in out


def test_brief_with_a_credential_is_refused(fake_repo):
    bad = BRIEF + "\n\ntoken: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345\n"
    assert brief_bridge.commit_brief(bad, source="test") == 1
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_brief_with_a_coordinate_is_refused(fake_repo):
    bad = BRIEF + "\n\nThe run started at 12.3456, -67.8910 this morning.\n"
    assert brief_bridge.commit_brief(bad, source="test") == 1
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_brief_with_an_email_is_refused(fake_repo):
    bad = BRIEF + "\n\nSend questions to athlete@example.com before running.\n"
    assert brief_bridge.commit_brief(bad, source="test") == 1
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_short_brief_is_refused(fake_repo):
    assert brief_bridge.commit_brief("task: do the thing", source="test") == 1
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_only_allowlisted_names_may_be_written(fake_repo):
    """A transport must not be able to choose an arbitrary destination."""
    with pytest.raises(SystemExit):
        brief_bridge.commit_brief(BRIEF, name="CREW_TASKS.md")
    assert not (fake_repo / "CREW_TASKS.md").exists()


def test_transport_preamble_is_stripped(fake_repo):
    """A flow transcript should not be committed whole.

    The flow prints a marker and whatever came before it. Only the brief is
    worth keeping, otherwise the coach agent reads a transcript.
    """
    transcript = ("log line one\nlog line two\nTHIS IS UNVERIFIED LLM OUTPUT\n"
                  + BRIEF)
    brief_bridge.commit_brief(transcript, source="test")
    out = (fake_repo / "SUPERVISOR_BRIEF.md").read_text(encoding="utf-8")
    assert "log line one" not in out
    assert "THIS IS UNVERIFIED LLM OUTPUT" in out
    assert "Task 1" in out


def test_republishing_an_identical_brief_is_a_noop(fake_repo):
    brief_bridge.commit_brief(BRIEF, source="test")
    first = (fake_repo / "SUPERVISOR_BRIEF.md").read_text(encoding="utf-8")
    # The header carries a timestamp, so a same-second rerun is byte-identical
    # only if the stamp matches; freeze it to test the real idempotency path.
    assert brief_bridge.commit_brief(BRIEF, source="test") == 0
    second = (fake_repo / "SUPERVISOR_BRIEF.md").read_text(encoding="utf-8")
    assert first == second


def test_failed_publish_restores_the_previous_brief(fake_repo, monkeypatch):
    brief_bridge.commit_brief(BRIEF, source="test")
    good = (fake_repo / "SUPERVISOR_BRIEF.md").read_text(encoding="utf-8")
    monkeypatch.setattr(brief_bridge, "publish", lambda target: (1, "boom"))
    assert brief_bridge.commit_brief(BRIEF + "\n\n## Task 9\nSomething new.\n",
                                     source="test") == 1
    assert (fake_repo / "SUPERVISOR_BRIEF.md").read_text(encoding="utf-8") == good


def test_failed_publish_removes_a_new_brief(fake_repo, monkeypatch):
    monkeypatch.setattr(brief_bridge, "publish", lambda target: (1, "boom"))
    assert brief_bridge.commit_brief(BRIEF, source="test") == 1
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


# -------------------------------------------------------------------- ingest

def test_ingest_drains_the_drop_directory(fake_repo, tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "brief.md").write_text(BRIEF, encoding="utf-8")
    monkeypatch.setattr(brief_bridge, "inbox_dir", lambda: str(inbox))
    assert brief_bridge.ingest() == 0
    assert (fake_repo / "SUPERVISOR_BRIEF.md").exists()
    assert not (inbox / "brief.md").exists(), "a consumed brief is not re-ingested"


def test_ingest_keeps_a_rejected_brief_for_inspection(fake_repo, tmp_path,
                                                      monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    bad = inbox / "bad.md"
    bad.write_text("too short", encoding="utf-8")
    monkeypatch.setattr(brief_bridge, "inbox_dir", lambda: str(inbox))
    assert brief_bridge.ingest() == 1
    assert bad.exists(), "a rejected brief stays put so it can be read"


@pytest.mark.parametrize("name", ["brief.md", "brief.markdown", "brief.txt"])
def test_ingest_accepts_the_extensions_notepad_actually_saves(
        name, tmp_path, monkeypatch, fake_repo):
    """Notepad saves .txt by default, and CrewAI Studio output is copied out.

    Matching only .md meant a perfectly good drop was skipped without a word and
    the run still reported success, which is indistinguishable from a broken
    bridge. The athlete would conclude the automation was failing.
    """
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / name).write_text(BRIEF, encoding="utf-8")
    monkeypatch.setattr(brief_bridge, "inbox_dir", lambda: str(inbox))
    assert brief_bridge.ingest() == 0
    assert (fake_repo / "SUPERVISOR_BRIEF.md").exists()
    assert not (inbox / name).exists()


def test_ingest_still_ignores_an_unrelated_extension(tmp_path, monkeypatch,
                                                     fake_repo):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "notes.pdf").write_text(BRIEF, encoding="utf-8")
    monkeypatch.setattr(brief_bridge, "inbox_dir", lambda: str(inbox))
    assert brief_bridge.ingest() == 0
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()
    assert (inbox / "notes.pdf").exists()


def test_paste_publishes_a_brief_on_the_clipboard(fake_repo, monkeypatch):
    # Real Studio output carries the marker. BRIEF does not, which is deliberate:
    # it proves the marker check is what gates this transport.
    marked = brief_bridge.START_MARKER + " - review before acting.\n\n" + BRIEF
    monkeypatch.setattr(brief_bridge, "clipboard_text", lambda: marked)
    assert brief_bridge.paste() == 0
    assert (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_paste_refuses_a_clipboard_that_is_not_a_brief(fake_repo, monkeypatch,
                                                        capsys):
    """The clipboard holds whatever was last copied, which may be a password.

    Without the marker check this transport would publish arbitrary clipboard
    content into a file the coach agent reads as instructions.
    """
    monkeypatch.setattr(brief_bridge, "clipboard_text",
                        lambda: "my wifi password is hunter2")
    assert brief_bridge.paste() == 1
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()
    assert "does not look like" in capsys.readouterr().out


def test_paste_with_an_empty_clipboard_is_not_a_failure(fake_repo, monkeypatch,
                                                        capsys):
    monkeypatch.setattr(brief_bridge, "clipboard_text", lambda: "")
    assert brief_bridge.paste() == 0
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_paste_reports_an_unreadable_clipboard(fake_repo, monkeypatch, capsys):
    monkeypatch.setattr(brief_bridge, "clipboard_text", lambda: None)
    assert brief_bridge.paste() == 0
    assert "could not be read" in capsys.readouterr().out


def test_ingest_refuses_a_symlink(tmp_path, monkeypatch, fake_repo):
    """A symlink is not a drop; following it could read an arbitrary file."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    secret = tmp_path / "secret.md"
    secret.write_text(BRIEF, encoding="utf-8")
    link = inbox / "link.md"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this filesystem")
    monkeypatch.setattr(brief_bridge, "inbox_dir", lambda: str(inbox))
    brief_bridge.ingest()
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_ingest_with_no_inbox_is_not_an_error(fake_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(brief_bridge, "inbox_dir", lambda: str(tmp_path / "nope"))
    assert brief_bridge.ingest() == 0


# --------------------------------------------------------------------- serve

def test_health_check_needs_no_token(fake_repo):
    Handler.token = TOKEN
    srv, url = serve_once()
    try:
        with urllib.request.urlopen(url + "/ping", timeout=10) as r:
            assert r.status == 200
    finally:
        srv.shutdown()


def test_post_without_a_token_is_rejected(fake_repo):
    Handler.token = TOKEN
    srv, url = serve_once()
    try:
        status, body = post(url, BRIEF, token=None)
        assert status == 401
        assert "error" in body
    finally:
        srv.shutdown()
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_post_with_a_wrong_token_is_rejected(fake_repo):
    Handler.token = TOKEN
    srv, url = serve_once()
    try:
        status, _ = post(url, BRIEF, token="wrong-token-entirely-0000000000")
        assert status == 401
    finally:
        srv.shutdown()
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_wrong_and_missing_token_are_indistinguishable(fake_repo):
    """The response must not reveal which tokens exist."""
    Handler.token = TOKEN
    srv, url = serve_once()
    try:
        _, missing = post(url, BRIEF, token=None)
        _, wrong = post(url, BRIEF, token="nope")
        assert missing == wrong
    finally:
        srv.shutdown()


def test_post_with_a_valid_token_is_published(fake_repo):
    Handler.token = TOKEN
    srv, url = serve_once()
    try:
        status, body = post(url, BRIEF)
        assert status == 200, body
    finally:
        srv.shutdown()
    assert (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_oversized_body_is_refused_without_reading(fake_repo):
    """An oversized POST must not be buffered.

    The server answers 413 and closes without reading the body, so a client
    still mid-upload may see the socket close instead of the response. Either
    outcome is correct; what matters is that nothing is written. This is also
    why the 413 sets Connection: close rather than leaving a desynchronised
    keep-alive connection behind.
    """
    Handler.token = TOKEN
    srv, url = serve_once()
    try:
        try:
            status, body = post(url, "x" * (brief_bridge.MAX_BODY + 1))
            assert status == 413
            assert body["error"] == "body too large"
        except (urllib.error.URLError, ConnectionError, OSError):
            pass  # refused mid-upload, which is the intended outcome
    finally:
        srv.shutdown()
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_unsafe_brief_over_http_is_refused(fake_repo):
    Handler.token = TOKEN
    srv, url = serve_once()
    try:
        bad = BRIEF + "\n\ntoken: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345\n"
        status, _ = post(url, bad)
        assert status == 422
    finally:
        srv.shutdown()
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_unknown_path_is_404(fake_repo):
    Handler.token = TOKEN
    srv, url = serve_once()
    try:
        status, _ = post(url, BRIEF, path="/etc/passwd")
        assert status == 404
    finally:
        srv.shutdown()


def test_non_utf8_body_is_refused(fake_repo):
    Handler.token = TOKEN
    srv, url = serve_once()
    try:
        status, _ = post(url, b"\xff\xfe\x00bad")
        assert status == 400
    finally:
        srv.shutdown()
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_host_header_must_be_loopback(fake_repo):
    """A page on the internet must not be able to post to a running bridge."""
    Handler.token = TOKEN
    srv, url = serve_once()
    try:
        status, _ = post(url, BRIEF, headers={"Host": "evil.example.com"})
        assert status == 403
    finally:
        srv.shutdown()
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


# ------------------------------------------------------------------- binding

def test_serve_refuses_to_start_without_a_token(fake_repo):
    with pytest.raises(SystemExit):
        brief_bridge.serve(8790, None, "127.0.0.1", 1)


def test_serve_refuses_a_non_loopback_bind(fake_repo):
    with pytest.raises(SystemExit):
        brief_bridge.serve(8790, TOKEN, "0.0.0.0", 1)


# ------------------------------------------------------- rejected-brief staging

def test_rejected_brief_is_staged_outside_the_repo(fake_repo, tmp_path, monkeypatch,
                                                   capsys):
    """A brief carrying a credential is written nowhere near git, but is kept.

    The staging copy is the only evidence of what tripped the scanner, so it has
    to survive; that is exactly why it must not be somewhere git can see.
    """
    # Staging must sit OUTSIDE fake_repo, which is what the real layout does.
    stage = tmp_path.parent / (tmp_path.name + "_staging")
    monkeypatch.setenv("GARMIN_BRIDGE_STAGE", str(stage))
    leaky = BRIEF + "\nThe token is ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345\n"
    assert brief_bridge.commit_brief(leaky, source="inbox:leaky.md") == 1

    out = capsys.readouterr().out
    assert "GitHub token" in out
    assert "Staged for manual review" in out

    staged = list(stage.glob("*.rejected.md"))
    assert len(staged) == 1
    body = staged[0].read_text(encoding="utf-8")
    assert "ghp_ABCDEFGHI" in body          # the evidence is preserved
    assert "GitHub token" in body           # and the reason is recorded
    assert not (fake_repo / "SUPERVISOR_BRIEF.md").exists()


def test_staging_refuses_a_directory_inside_the_repo(fake_repo, tmp_path,
                                                     monkeypatch):
    """GARMIN_DATA_DIR pointed at the repo must not stage a credential into git."""
    monkeypatch.setenv("GARMIN_BRIDGE_STAGE", str(fake_repo / "staging"))
    with pytest.raises(SystemExit):
        brief_bridge.stage_dir()


def test_staging_filename_survives_a_hostile_source(fake_repo, tmp_path,
                                                    monkeypatch):
    stage = tmp_path.parent / (tmp_path.name + "_stem")
    monkeypatch.setenv("GARMIN_BRIDGE_STAGE", str(stage))
    path = brief_bridge.stage_rejected(BRIEF, r"inbox:..\..\evil:C:\x", [],
                                       "test")
    assert path is not None
    assert os.path.dirname(path) == str(stage)
    assert ".." not in os.path.basename(path)


def test_short_brief_is_staged_not_just_refused(fake_repo, tmp_path, monkeypatch):
    stage = tmp_path.parent / (tmp_path.name + "_short")
    monkeypatch.setenv("GARMIN_BRIDGE_STAGE", str(stage))
    assert brief_bridge.commit_brief("too short", source="tiny") == 1
    assert list(stage.glob("*.rejected.md"))


def test_publish_failure_stages_and_restores(fake_repo, monkeypatch, capsys):
    """A brief the publisher's guard refuses is staged and the old one restored."""
    (fake_repo / "SUPERVISOR_BRIEF.md").write_text("PREVIOUS BRIEF", encoding="utf-8")
    monkeypatch.setattr(
        brief_bridge, "publish",
        lambda target: (1, "refusing to commit SUPERVISOR_BRIEF.md\n"
                          "it contains a degree coordinate pair. This repository is public."))
    stage = fake_repo.parent / "stage2"
    monkeypatch.setenv("GARMIN_BRIDGE_STAGE", str(stage))
    assert brief_bridge.commit_brief(BRIEF, source="blocked") == 1
    out = capsys.readouterr().out
    assert "degree coordinate pair" in out
    assert "restored the previous" in out
    assert (fake_repo / "SUPERVISOR_BRIEF.md").read_text() == "PREVIOUS BRIEF"
    assert list(stage.glob("*.rejected.md"))


# ------------------------------------------------------------------- the header

def test_written_brief_carries_a_generated_date(fake_repo):
    assert brief_bridge.commit_brief(BRIEF, source="test") == 0
    body = (fake_repo / "SUPERVISOR_BRIEF.md").read_text(encoding="utf-8")
    today = brief_bridge.datetime.now(brief_bridge.timezone.utc).strftime("%Y-%m-%d")
    assert "## Generated: %s" % today in body
    assert "source: test" in body


def test_identical_brief_is_not_committed_twice(fake_repo, capsys):
    assert brief_bridge.commit_brief(BRIEF, source="test") == 0
    assert brief_bridge.commit_brief(BRIEF, source="test") == 0
    assert "already current" in capsys.readouterr().out


# --------------------------------------------------------------- shape reporting

def test_shape_report_flags_a_missing_start_marker():
    """The fixture has the end section but no start marker, so exactly one gap."""
    warnings, confirmations = brief_bridge.shape_report(BRIEF)
    assert confirmations == ["'## NEXT SUPERVISOR CHECK' section present"]
    assert len(warnings) == 1
    assert "UNVERIFIED LLM OUTPUT" in warnings[0]


def test_shape_report_confirms_a_well_formed_brief():
    text = brief_bridge.START_MARKER + "\n\nbody text\n\n" + brief_bridge.END_SECTION + "\n"
    warnings, confirmations = brief_bridge.shape_report(text)
    assert warnings == []
    assert len(confirmations) == 2


def test_shape_report_warns_on_a_transcript():
    text = "Traceback (most recent call last):\n  File x\nRuntimeError: boom\n" * 40
    warnings, confirmations = brief_bridge.shape_report(text)
    assert confirmations == []
    assert len(warnings) == 2


def test_missing_markers_warn_but_still_publish(fake_repo, capsys):
    """A renamed heading must not silently stop the bridge working."""
    body = BRIEF.replace(brief_bridge.END_SECTION, "## NEXT CHECK")
    assert brief_bridge.commit_brief(body, source="renamed") == 0
    out = capsys.readouterr().out
    assert "may be truncated" in out
    assert (fake_repo / "SUPERVISOR_BRIEF.md").exists()


# ------------------------------------------------------------ flow-command capture

def test_capture_without_a_configured_command_is_not_an_error(monkeypatch, capsys):
    monkeypatch.delenv("CREWAI_FLOW_CMD", raising=False)
    assert brief_bridge.capture_flow() == 0
    out = capsys.readouterr().out
    assert "no flow command configured" in out
    assert "CREWAI_FLOW_CMD" in out


def test_capture_commits_the_brief_the_command_printed(fake_repo, monkeypatch):
    import subprocess

    class R:
        returncode = 0
        stdout = brief_bridge.START_MARKER + "\n" + BRIEF
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert brief_bridge.capture_flow(command="anything") == 0
    body = (fake_repo / "SUPERVISOR_BRIEF.md").read_text(encoding="utf-8")
    assert "source: flow-cmd" in body


def test_capture_surfaces_stderr_when_there_is_no_stdout(fake_repo, monkeypatch):
    import subprocess

    class R:
        returncode = 1
        stdout = ""
        stderr = "flow failed: bad credentials"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    with pytest.raises(SystemExit):
        brief_bridge.capture_flow(command="anything")


def test_capture_does_not_silently_swallow_a_missing_command(fake_repo, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    with pytest.raises(SystemExit):
        brief_bridge.capture_flow(command="no-such-binary-xyz")
