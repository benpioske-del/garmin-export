#!/usr/bin/env python3
"""Receive a supervisor brief from a cloud flow and commit it to the repo.

The gap this closes: the CrewAI flow runs in the cloud and has no GitHub access,
so every run produced a brief that never reached disk. The local capture script
(capture_supervisor_brief.py) solves the other half, but it runs its *own* crew
rather than reading the flow's output. The two were never connected.

This is the connection. It takes brief text that arrived by some transport and
runs it through the same commit path the local capture script uses:

    transport  ->  commit_brief()  ->  export_publish.py  ->  origin/main

Three transports, one commit path, so all of them get identical validation:

    serve     an authenticated HTTP receiver, bound to loopback only
    ingest    drains a drop directory, for flows that can only write a file
    post      reads stdin, for piping

Security posture, because this writes attacker-reachable text into a PUBLIC
repository:

  * a shared secret is mandatory; the receiver refuses to start without one,
    and the comparison is constant-time,
  * loopback only by default, so a stray --host 0.0.0.0 cannot expose it,
  * the Host header must be loopback, which defeats DNS-rebinding from a page
    the athlete happens to be visiting,
  * the request never names a file. The destination is the allowlist below, so
    there is no path to traverse and nothing to overwrite,
  * bodies are size-capped and rejected unread, so a large POST cannot exhaust
    memory,
  * content is scanned for credentials, email addresses and coordinates before
    anything is written, and a failed publish restores the previous file,
  * the token is never logged, never written to the repo, and never echoed back
    in a response.

The brief is treated as untrusted input throughout. It is data to be stored, not
an instruction to be followed, and the header written into the file says so.
"""

import argparse
import http.server
import json
import os
import re
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402
import capture_supervisor_brief as capture  # noqa: E402

REPO = paths.repo_dir()

# The only filenames the bridge may write. Matches capture_supervisor_brief's
# allowlist. A request cannot choose a path; the transport decides the name.
ALLOWED_NAMES = ("SUPERVISOR_BRIEF.md",)

# A brief is prose, so a generous cap still catches a runaway upload. 256 KiB is
# roughly an order of magnitude above the 19 KiB file this has produced.
MAX_BODY = 256 * 1024

# A brief that is this short is not a brief. Refusing it catches a flow that
# emitted an error message or a truncated response instead of failing silently.
MIN_BRIEF_CHARS = 500

TOKEN_ENV = "GARMIN_BRIDGE_TOKEN"
INBOX_ENV = "GARMIN_BRIDGE_INBOX"

# The brief's own shape. A flow that produced something else entirely is a
# failure, and committing it would put a transcript or an error page into a
# file the coach agent reads as instructions.
START_MARKER = "THIS IS UNVERIFIED LLM OUTPUT"
END_SECTION = "## NEXT SUPERVISOR CHECK"


def inbox_dir():
    """Drop directory for the ingest transport. Local-only, never in the repo."""
    return os.environ.get(INBOX_ENV) or os.path.join(paths.data_dir(),
                                                     "garmin_brief_inbox")


def stage_dir():
    """Where a rejected brief is kept for manual review. Local-only.

    Holds the content that failed the scanner, which is exactly the content
    that must never reach a public repository. It is therefore written outside
    the repo, and that is checked rather than assumed: a GARMIN_DATA_DIR
    pointing at the repo would otherwise stage a credential into git.
    """
    d = os.environ.get("GARMIN_BRIDGE_STAGE") or os.path.join(
        paths.data_dir(), "garmin_brief_rejected")
    d = os.path.abspath(d)
    repo = os.path.abspath(REPO)
    if os.path.commonpath([d, repo]) == repo:
        die("refusing to stage inside the repository",
            "GARMIN_BRIDGE_STAGE is %s\nwhich is inside %s\n"
            "Rejected briefs are held here precisely because they failed the\n"
            "scanner. Point it anywhere outside the repo."
            % (d, repo))
    return d


def _safe_stem(source):
    """A filesystem-safe stem for a staging filename.

    The source can contain a drive letter and colons ("inbox:C:\\..."), none of
    which belong in a filename, and the text may be attacker-influenced. Path
    separators are replaced so the result cannot traverse, and dot runs are
    collapsed so no ".." survives even though it could no longer escape.
    """
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(source))
    stem = re.sub(r"\.{2,}", ".", stem)
    stem = re.sub(r"_{2,}", "_", stem)
    return stem.strip("._-")[:60] or "brief"


def stage_rejected(text, source, problems, reason):
    """Write a rejected brief to local staging for manual review.

    Returns the path written, or None if it could not be staged. Never raises:
    a failure to stage must not hide the original refusal.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = "%s-%s.rejected.md" % (stamp, _safe_stem(source))
    body = [
        "---",
        "# REJECTED BY THE PRIVACY SCANNER - NOT COMMITTED, NOT PUBLISHED",
        "rejected_utc: %s" % datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source: %s" % source,
        "reason: %s" % reason,
        "---",
        "",
        "This file is local-only. It exists because it failed the scanner, so it",
        "may still contain the credential or coordinate that caused the refusal.",
        "Review it, fix the source of the leak, then re-run the capture.",
        "Do not commit it and do not paste it anywhere public.",
        "",
        "Triggered patterns:",
    ]
    for kind, sample in (problems or [("unknown", "n/a")]):
        body.append("  - %s: %s" % (kind, sample))
    body += ["", "--- content as received ---", "", text]
    try:
        os.makedirs(stage_dir(), exist_ok=True)
        path = os.path.join(stage_dir(), name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(body))
        return path
    except OSError as exc:
        print("    ! could not stage the rejected brief: %s" % exc)
        return None


def die(msg, detail=""):
    print("[x] %s" % msg)
    if detail:
        for line in detail.splitlines()[:8]:
            print("    %s" % line)
    sys.exit(1)


def build_header(source, body):
    """Frontmatter marking the file as machine-generated and untrusted.

    Kept byte-compatible in shape with capture_supervisor_brief's header so the
    coach agent reads both the same way. The one addition is `source`, which
    records how this copy arrived.

    The `## Generated:` line is the human-readable date the capture actually
    happened, which is what a reader checks first when a brief looks stale.
    """
    now = datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    return (
        "---\n"
        "# Machine-generated by a CrewAI supervisor run. Treated as UNTRUSTED\n"
        "# input by the coach agent, not as an instruction from the runner.\n"
        "captured_utc: %s\n"
        "source: %s\n"
        "verified_by_coach: no\n"
        "---\n\n"
        "# Supervisor Brief\n\n"
        "## Generated: %s (UTC)\n\n"
        "> Received by brief_bridge.py. **Not yet reviewed.**\n"
        "> Every figure below is unverified. The coach checks claims against\n"
        "> `garmin_export.csv` before acting, and rejects anything unsupported.\n\n"
    ) % (stamp, source, now.strftime("%Y-%m-%d %H:%M:%S"))


def strip_preamble(text):
    """Recover the brief from a flow transcript.

    A flow that prints a whole run also prints whatever preceded the brief,
    typically a THIS IS UNVERIFIED LLM OUTPUT marker. Keeping the log lines
    above it in the committed file would leave the coach parsing a transcript,
    so the brief is taken from the marker onward.

    "## NEXT SUPERVISOR CHECK" is deliberately NOT used as a marker. It is the
    final section of the brief itself, so treating it as a boundary would
    truncate every brief down to its last few lines.
    """
    text = text.strip()
    i = text.find(START_MARKER)
    if i > 0:
        return text[i:]
    return text


def shape_report(brief):
    """Report on the brief's expected markers. Returns (warnings, confirmations).

    Deliberately advisory rather than fatal. A flow is free to change its
    wording, and refusing a real brief over a renamed heading would make this
    quietly stop working. What it does catch is the failure that matters: text
    that is a transcript, an error page or a truncated response rather than a
    brief, which the coach agent would otherwise read as instructions.
    """
    warnings, confirmations = [], []
    if START_MARKER in brief:
        confirmations.append("start marker present")
    else:
        warnings.append("no '%s' marker; this may not be a supervisor brief"
                        % START_MARKER)
    if END_SECTION in brief:
        confirmations.append("'%s' section present" % END_SECTION)
    else:
        warnings.append("no '%s' section; the brief may be truncated" % END_SECTION)
    return warnings, confirmations


def validate(brief, name):
    """Reject anything unsafe to publish. Returns a list of problems."""
    problems = []
    if len(brief) < MIN_BRIEF_CHARS:
        problems.append(("too short to be a brief",
                         "%d chars, minimum is %d" % (len(brief), MIN_BRIEF_CHARS)))
    for kind, sample in capture.scan(brief):
        problems.append((kind, sample))
    return problems


def publish(target):
    """Hand the git work to export_publish.py so the guards and sync are reused."""
    r = subprocess.run([sys.executable, os.path.join(HERE, "export_publish.py")],
                       cwd=REPO, capture_output=True, text=True)
    for line in (r.stdout or "").splitlines():
        if any(k in line for k in ("committed", "pushed", "unchanged", "raw url",
                                   "!", "aborting")):
            print("  " + line.strip())
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def commit_brief(text, source="stdin", name=None, dry_run=False):
    """Validate, write and publish a brief. Returns a process exit code.

    Restores the previous file if publishing fails, so a rejected brief never
    leaves a bad file sitting in the worktree for the next run to inherit.
    """
    if name is None:
        name = ALLOWED_NAMES[0]
    if name not in ALLOWED_NAMES:
        die("refusing to write %s" % name,
            "allowed: %s" % ", ".join(ALLOWED_NAMES))

    brief = strip_preamble(text)
    problems = validate(brief, name)
    if problems:
        print("[!] refusing to commit: %d unsafe or invalid item(s)" % len(problems))
        for kind, sample in problems:
            print("    - %-24s %s" % (kind, sample))
        staged = stage_rejected(text, source, problems,
                                "failed the privacy scanner before writing")
        if staged:
            print("\nStaged for manual review, outside the repository:\n  %s" % staged)
        print("\nThis repo is PUBLIC. Nothing was written and nothing was pushed.")
        return 1

    warnings, confirmations = shape_report(brief)
    for c in confirmations:
        print("    ok: %s" % c)
    for w in warnings:
        print("    ! %s" % w)

    body = build_header(source, brief) + brief + "\n"
    dest = os.path.join(REPO, name)

    # Idempotency: an identical brief is a no-op rather than a second commit.
    try:
        with open(dest, "r", encoding="utf-8") as fh:
            if fh.read() == body:
                print("%s is already current; nothing to publish" % name)
                return 0
    except OSError:
        pass

    nums = re.findall(r"(?m)^\s*(\d{1,2})[.)]\s+\S", brief)
    print("brief: %d chars, appears to contain %d numbered item(s)"
          % (len(brief), len(nums)))

    if dry_run:
        print("\n--- would write %s (%d chars) ---" % (name, len(body)))
        print(body[:1200])
        return 0

    previous = None
    had_previous = os.path.exists(dest)
    if had_previous:
        with open(dest, "r", encoding="utf-8") as fh:
            previous = fh.read()

    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    print("wrote %s (%d bytes)" % (name, len(body.encode("utf-8"))))

    code, out = publish(name)
    if code != 0:
        # export_publish.py's worktree guard is the second line of defence and
        # catches patterns capture.scan() does not know about. Its refusal
        # arrives as text, so the reason is recovered from that output rather
        # than assumed, and the content is staged for review the same way.
        reason = "blocked by export_publish.py"
        m = re.search(r"it contains a ([^\n.]+)", out or "")
        if m:
            reason = "blocked by export_publish.py: %s" % m.group(1).strip()
        print("\n[!] %s" % reason)
        staged = stage_rejected(text, source, [(reason, "see the message above")],
                                reason)
        if staged:
            print("    staged for manual review, outside the repository:\n      %s" % staged)
        # Put the old file back so the worktree is not left holding a brief
        # that was rejected. A brief that cannot be published is not a brief.
        if had_previous:
            with open(dest, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(previous)
            print("    publish failed; restored the previous %s" % name)
        else:
            os.remove(dest)
            print("    publish failed; removed the new %s" % name)
        return 1
    return 0


def ingest(dry_run=False):
    """Drain the drop directory. One file per commit, oldest first."""
    d = inbox_dir()
    if not os.path.isdir(d):
        print("no inbox at %s; nothing to ingest" % d)
        print("create it, or point %s elsewhere" % INBOX_ENV)
        return 0
    try:
        names = sorted(n for n in os.listdir(d) if n.endswith(".md"))
    except OSError as exc:
        die("cannot read the inbox", str(exc))
    if not names:
        print("inbox %s is empty" % d)
        return 0
    rc = 0
    for n in names:
        src = os.path.join(d, n)
        # A subdirectory or a symlink is not a drop. isfile() follows symlinks,
        # so check islink() first and refuse rather than reading a link target.
        if os.path.islink(src) or not os.path.isfile(src):
            print("skipping %s: not a regular file" % n)
            rc = 1
            continue
        try:
            if os.path.getsize(src) > MAX_BODY:
                print("skipping %s: larger than %d bytes" % (n, MAX_BODY))
                rc = 1
                continue
            with open(src, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print("skipping %s: %s" % (n, exc))
            rc = 1
            continue
        print("\n=== %s ===" % n)
        code = commit_brief(text, source="inbox:%s" % n, dry_run=dry_run)
        if code != 0:
            # Left in place on purpose. A brief the guards rejected is the one
            # worth reading: it is how a credential or a coordinate gets found.
            # Deleting it would destroy the only evidence.
            print("  %s was rejected and has been left in the inbox" % n)
            rc = code
            continue
        if not dry_run:
            # Consumed, so a rerun is a no-op rather than a second commit.
            try:
                os.remove(src)
            except OSError as exc:
                print("could not remove %s: %s" % (n, exc))
                rc = 1
    return rc


FLOW_CMD_ENV = "CREWAI_FLOW_CMD"


def capture_flow(dry_run=False, timeout=900, command=None):
    """Run a configured flow command and commit whatever brief it prints.

    This is the transport for a flow whose runner can be invoked locally, which
    includes a `crewai` CLI, a Studio CLI, or any wrapper the athlete writes.
    The command is supplied by the athlete rather than guessed at here: the
    CrewAI Studio HTTP API's request and response shapes are not something this
    file can verify, and a speculative client that looks functional is worse
    than an explicit seam. Set CREWAI_FLOW_CMD to a full command line and it is
    run with the repo as the working directory; its stdout is treated exactly
    like a brief that arrived by any other transport.

    Not configured is a normal state, not an error: the inbox and webhook
    transports cover flows that cannot be run from here.
    """
    cmd = command or os.environ.get(FLOW_CMD_ENV)
    if not cmd:
        print("no flow command configured; nothing to capture")
        print("set %s to the command that produces the brief, e.g." % FLOW_CMD_ENV)
        print('  set "%s=crewai run write_tasks_brief"')
        print("or drop the brief in the inbox and run:  brief_bridge.py ingest")
        return 0
    import shlex
    argv = shlex.split(cmd, posix=False) if os.name != "nt" else cmd.split()
    print("running flow command: %s" % cmd)
    try:
        p = subprocess.run(argv, cwd=REPO, capture_output=True, text=True,
                           timeout=timeout)
    except FileNotFoundError:
        die("flow command not found", "  %s\ncheck the path in %s"
            % (argv[0], FLOW_CMD_ENV))
    except subprocess.TimeoutExpired:
        die("flow command timed out after %ss" % timeout)
    text = (p.stdout or "").strip()
    if not text:
        # A flow that fails often writes the reason to stderr only. Surface it,
        # because "no output" on its own is not debuggable.
        die("the flow command produced no stdout",
            (p.stderr or "").strip()[:800] or "exit code %d" % p.returncode)
    if p.returncode != 0:
        print("    ! flow exited %d; capturing its output anyway" % p.returncode)
    print("captured %d chars of stdout" % len(text))
    return commit_brief(text, source="flow-cmd", dry_run=dry_run)


class Handler(BaseHTTPRequestHandler):
    """Accept one authenticated POST and hand the body to commit_brief()."""

    server_version = "garmin-bridge/1"
    token = None
    dry_run = False

    def log_message(self, fmt, *args):
        # Never let a request path or header reach the log, and never the token:
        # it is compared in the header and is not part of the request line.
        print("  bridge: " + (fmt % args))

    def _reply(self, code, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        # No CORS headers at all, so a hostile page cannot read a response.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def host_is_loopback(self):
        host = (self.headers.get("Host") or "").strip()
        if host.startswith("["):  # bracketed IPv6
            return host.split("]")[0].lstrip("[").strip() in ("::1", "127.0.0.1")
        h, _, _p = host.rpartition(":")
        h = h or host
        return h in ("127.0.0.1", "localhost", "::1")

    def authorised(self):
        got = self.headers.get("X-Bridge-Token") or ""
        return bool(self.token) and secrets.compare_digest(got, self.token)

    def _drain(self, length):
        """Read and discard the request body.

        Without this the server replies to an error while the client is still
        sending, and the client sees a connection abort instead of the response
        it is waiting for. Bounded by MAX_BODY so a lying Content-Length cannot
        make us read forever.
        """
        if length <= 0:
            return
        remaining = min(length, MAX_BODY)
        try:
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            pass

    def _fail(self, code, payload, length=0):
        """Send an error response, having first consumed the request body."""
        self._drain(length)
        self._reply(code, payload)

    def do_GET(self):
        # Health check only. It confirms the receiver is up and nothing else;
        # it deliberately does not report the inbox state or the token state.
        if not self.host_is_loopback():
            self._reply(403, {"error": "host not allowed"})
            return
        self._reply(200, {"status": "ok", "accepts": "POST /brief"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._reply(400, {"error": "bad content-length"})
            return
        if not self.host_is_loopback():
            self._fail(403, {"error": "host not allowed"}, length)
            return
        if self.path.split("?")[0] != "/brief":
            self._fail(404, {"error": "unknown path"}, length)
            return
        if not self.authorised():
            # Same response for a missing and a wrong token, so the endpoint
            # does not confirm which tokens exist.
            self._fail(401, {"error": "unauthorised"}, length)
            return
        if length <= 0:
            self._reply(400, {"error": "empty body"})
            return
        if length > MAX_BODY:
            # Refuse without reading the body, so a large POST cannot exhaust
            # memory. The connection is closed because the unread remainder
            # would otherwise desynchronise a keep-alive client.
            self.send_response(413)
            raw = json.dumps({"error": "body too large",
                              "limit": MAX_BODY}).encode("utf-8")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)
            self.close_connection = True
            return
        raw = self.rfile.read(length)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            self._reply(400, {"error": "body is not utf-8"})
            return
        if len(text) < MIN_BRIEF_CHARS:
            self._reply(400, {"error": "too short to be a brief"})
            return

        print("accepted %d bytes over http; validating..." % len(raw))
        code = commit_brief(text, source="webhook", dry_run=self.dry_run)
        if code != 0:
            self._reply(422, {"error": "refused; nothing was written or pushed"})
            return
        self._reply(200, {"status": "published"})


def serve(port, token, host, idle_minutes, dry_run=False):
    if not token:
        die("no token configured",
            "set %s to a long random string, or pass --token.\n"
            "The receiver will not start unauthenticated, because it writes\n"
            "untrusted text into a public repository." % TOKEN_ENV)
    if host not in ("127.0.0.1", "localhost", "::1"):
        die("refusing to bind %s" % host,
            "This receiver writes to a public repository. It binds loopback\n"
            "only. If a cloud flow must reach it, put an authenticated tunnel in\n"
            "front of it rather than exposing the socket directly.")
    Handler.token = token
    Handler.dry_run = dry_run
    httpd = ThreadingHTTPServer((host, port), Handler)
    print("brief bridge listening on http://%s:%d/brief" % (host, port))
    print("  token: from %s (not shown)" % TOKEN_ENV)
    print("  idle shutdown after %d minutes; Ctrl-C to stop now" % idle_minutes)
    print("  a wrong or missing token is rejected before the body is read\n")
    import time
    deadline = time.time() + idle_minutes * 60
    try:
        httpd.timeout = 30
        while time.time() < deadline:
            httpd.handle_request()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        httpd.server_close()
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Commit a supervisor brief that arrived from a cloud flow.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="authenticated HTTP receiver")
    s.add_argument("--port", type=int, default=8790)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--token", default=os.environ.get(TOKEN_ENV))
    s.add_argument("--idle-minutes", type=int, default=20)
    s.add_argument("--dry-run", action="store_true")

    i = sub.add_parser("ingest", help="drain the drop directory")
    i.add_argument("--dry-run", action="store_true")

    c = sub.add_parser("capture", help="run a configured flow command and commit its brief")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--timeout", type=int, default=900)
    c.add_argument("--command", help="override %s for this run" % FLOW_CMD_ENV)

    p = sub.add_parser("post", help="read a brief from stdin")
    p.add_argument("--source", default="stdin")
    p.add_argument("--dry-run", action="store_true")

    a = ap.parse_args()
    if a.cmd == "serve":
        return serve(a.port, a.token, a.host, a.idle_minutes, a.dry_run)
    if a.cmd == "ingest":
        return ingest(a.dry_run)
    if a.cmd == "capture":
        return capture_flow(a.dry_run, a.timeout, a.command)
    if sys.stdin.isatty():
        die("no brief on stdin",
            "pipe one in, e.g.  type file.md | python brief_bridge.py post")
    data = sys.stdin.read()
    if len(data.encode("utf-8")) > MAX_BODY:
        die("stdin is larger than %d bytes" % MAX_BODY)
    return commit_brief(data, source=a.source, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
