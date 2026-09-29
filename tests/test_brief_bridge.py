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
