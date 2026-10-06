#!/usr/bin/env python3
"""Check the supervisor brief against things that can actually be measured.

The brief is written by a process that cannot see this repository. `dashboard/` is
gitignored, the FIT files are local-only, and since the repository went private
an anonymous fetch of every file 404s. Four consecutive briefs therefore asserted
numbers and states the writer had no way to observe: a dashboard that is already
wired, a corpus of 57 when there are 58, and a test count of 207 when there were
over 400.

Nothing about that is a carelessness problem, so link-checking alone does not fix
it. Two independent checks run here:

    backlinks   every task the brief names should have a file in tasks/, which
                CREW_TASKS.md already calls the real queue
    facts       every number the brief states should match what the local data,
                the dashboard and the verification record actually say

    python brief_consistency.py          # report, exit 1 on conflict or no rows
    python brief_consistency.py --quiet  # report, always exit 0

A brief with no recognisable task table is a failure, not a pass. Losing the
table is exactly the kind of silent regression this exists to catch, and an
earlier version of this module exited 0 in that case.

An unbacked row is not automatically wrong, and neither is a stale number. Both
are claims with no evidence attached, which is the thing worth surfacing.
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

REPO = paths.repo_dir()
BRIEF = os.path.join(REPO, "SUPERVISOR_BRIEF.md")
TASKS = os.path.join(REPO, "tasks")
VERIFICATION = os.path.join(REPO, "docs", "VERIFICATION_REPORT.md")
SERVER = os.path.join(REPO, "garmin_server.py")
DASHBOARD = os.path.join(REPO, "dashboard", "index.html")

# `slug | STATUS | prose`, as written by the brief process. No leading pipe.
ROW = re.compile(r"^\s*([a-z0-9][a-z0-9-]{6,})\s*\|\s*([A-Z][A-Z /-]*[A-Z])\s*\|\s*(.+)$")
# `rank: N | slug | prose`, the backlog shape.
RANKED = re.compile(r"^\s*rank:\s*\d+\s*\|\s*([a-z0-9][a-z0-9-]{6,})\s*\|\s*(.+)$")


def brief_rows():
    """(slug, status, text) for every row in the brief's task table.

    Ranked backlog entries are included with a synthetic status, because a brief
    that only ever has a backlog still has to be held to something.
    """
    if not os.path.isfile(BRIEF):
        return []
    rows = []
    for line in open(BRIEF, encoding="utf-8").read().splitlines():
        m = ROW.match(line)
        if m:
            rows.append((m.group(1), m.group(2).strip(), m.group(3).strip()))
            continue
        m = RANKED.match(line)
        if m:
            rows.append((m.group(1), "RANKED", m.group(2).strip()))
    return rows


def queued_slugs():
    """Slugs that have a real file in tasks/."""
    slugs = set()
    for path in sorted(glob.glob(os.path.join(TASKS, "*.md"))):
        slugs.add(os.path.splitext(os.path.basename(path))[0])
    return slugs


def unbacked_rows():
    """Brief rows with no corresponding task file."""
    queued = queued_slugs()
    return [r for r in brief_rows() if r[0] not in queued]


def lap_coverage(limit=None):
    """(files_with_laps, files_examined) over the local FIT files.

    The brief has claimed per-mile splits are unavailable. They are not: Garmin
    writes lap records, and this counts the files that actually contain them.
    """
    try:
        import fitparse
    except ImportError:
        return None
    pattern = os.path.join(paths.data_dir(), "garmin_fit", "*.fit")
    files = sorted(glob.glob(pattern))
    if limit:
        files = files[:limit]
    with_laps = 0
    for path in files:
        try:
            with open(path, "rb") as fh:
                fit = fitparse.FitFile(fh)
                fit.parse()
                if list(fit.get_messages("lap")):
                    with_laps += 1
        except Exception:
            continue
    return with_laps, len(files)


# --- facts -------------------------------------------------------------------
#
# Every one of these is measurable locally. The brief states each of them, and
# has stated all of them wrongly at least once.

def measured_facts():
    """Ground truth for the numbers a brief is expected to get right."""
    facts = {}
    facts["fit_files"] = len(glob.glob(os.path.join(paths.data_dir(),
                                                      "garmin_fit", "*.fit")))
    facts["activities"] = None
    facts["open_reviews"] = None
    facts["review_breakdown"] = {}
    try:
        import trainingdb
        conn = trainingdb.connect()
        facts["activities"] = conn.execute(
            "SELECT COUNT(*) FROM activities").fetchone()[0]
        facts["open_reviews"] = conn.execute(
            "SELECT COUNT(*) FROM review_items WHERE resolved_utc IS NULL"
        ).fetchone()[0]
        facts["review_breakdown"] = {
            r[0]: r[1] for r in conn.execute(
                "SELECT reason, COUNT(*) FROM review_items "
                "WHERE resolved_utc IS NULL GROUP BY reason")}
        conn.close()
    except Exception as exc:  # a missing database is not a crash
        facts["activities_error"] = str(exc)
    if os.path.isfile(VERIFICATION):
        m = re.search(r"(\d+) passed, (\d+) skipped",
                      open(VERIFICATION, encoding="utf-8").read())
        if m:
            facts["tests_passed"] = int(m.group(1))
            facts["tests_skipped"] = int(m.group(2))
    return facts


def _read(path):
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8", errors="replace").read()


def dashboard_wiring():
    """What the dashboard actually consumes. A brief cannot see this file."""
    server, dash = _read(SERVER), _read(DASHBOARD)
    if not server and not dash:
        return None
    return {
        "server_routes": [e for e in ("/api/activities", "/api/load",
                                      "/api/coaching")
                          if e in server],
        "dashboard_calls": [e for e in ("/api/activities", "/api/load",
                                        "/api/coaching")
                            if e in dash],
    }


# Claims phrased as prose rather than as a table row. Each is (regex, key, label)
# where key is a measured_facts() field.
CLAIM_PATTERNS = [
    (re.compile(r"(\d+)\s+(?:FIT\s+files?|fit\s+files?)", re.I),
     "fit_files", "FIT files"),
    (re.compile(r"(\d+)\s+activities", re.I), "activities", "activities"),
    (re.compile(r"(\d+)\s+open\s+reviews?", re.I), "open_reviews", "open reviews"),
    (re.compile(r"(\d+)\s+passed", re.I), "tests_passed", "tests passed"),
]


def claim_conflicts(facts=None):
    """(label, stated, actual, line) for every number in the brief that is wrong."""
    facts = facts or measured_facts()
    text = _read(BRIEF)
    out = []
    for pattern, key, label in CLAIM_PATTERNS:
        if key not in facts or facts[key] is None:
            continue
        actual = facts[key]
        for line in text.splitlines():
            m = pattern.search(line)
            if not m:
                continue
            try:
                stated = int(m.group(1))
            except (TypeError, ValueError):
                continue
            if stated != actual:
                out.append((label, stated, actual, line.strip()[:88]))
    return out


def reason_conflicts(facts=None):
    """Breakdown mismatches, e.g. '57 timezone_uncertain' when there are 58."""
    facts = facts or measured_facts()
    breakdown = facts.get("review_breakdown") or {}
    if not breakdown:
        return []
    out = []
    for line in _read(BRIEF).splitlines():
        for reason, actual in breakdown.items():
            m = re.search(r"(\d+)\s*`?%s`?" % re.escape(reason), line, re.I)
            if m and int(m.group(1)) != actual:
                out.append((reason, int(m.group(1)), actual,
                            line.strip()[:88]))
    return out


def dashboard_conflict():
    """The dashboard claim, in either direction.

    This is the claim four briefs in a row got wrong. It is checked as prose
    because it is always written as prose, never as a table row.
    """
    wiring = dashboard_wiring()
    if not wiring or not wiring["server_routes"] or not wiring["dashboard_calls"]:
        return None
    connected = len(wiring["dashboard_calls"]) == 3
    text = _read(BRIEF)
    claims_disconnected = re.search(
        r"dashboard[^\n.]{0,80}?(not\s+connected|disconnected|has\s+no\s+"
        r"references|not\s+been\s+connected|no\s+data-layer)", text, re.I)
    if connected and claims_disconnected:
        m = claims_disconnected
        return ("dashboard", "disconnected/not integrated",
                "consumes %s" % ", ".join(wiring["dashboard_calls"]),
                m.group(0)[:88])
    return None


def write_facts(path=None, commit=None, code_sha=None, visibility=None):
    """Write brief_facts.json: the numbers, machine-generated, for a brief to read.

    `CREW_BRIEF.md` states these figures in prose, which is fine for a reader and
    useless as a source: prose ages, and a writer that fetches nothing has no way
    to tell current from stale. This file is regenerated on every publish and
    carries the commit it describes, so a brief can quote it instead of
    remembering it, and a stale copy is recognisable as stale.

    `commit` is a git SHA and `code_sha` is the publisher's content digest. They
    are different things and are recorded separately: a reader who wants to check
    out the commit needs a real SHA, and conflating them makes the field a lie.

    Counts and states only. No activity identifiers, no timestamps of individual
    activities, nothing GPS-bearing: this file is published.
    """
    path = path or os.path.join(REPO, "brief_facts.json")
    if commit is None:
        commit = _head_sha()
    facts = measured_facts()
    doc = {
        "_comment": (
            "Generated by brief_consistency.py on every publish. Quote these "
            "figures instead of recalling them. If this file is missing or "
            "unreadable, say so; do not fill the gap from memory."),
        "generated_utc": _utcnow(),
        "commit": commit,
        "code_sha": code_sha,
        "repo_visibility": visibility,
        "corpus": {
            "fit_files": facts.get("fit_files"),
            "activities": facts.get("activities"),
        },
        "reviews": {
            "open": facts.get("open_reviews"),
            "by_reason": facts.get("review_breakdown") or {},
        },
        "tests": {
            "passed": facts.get("tests_passed"),
            "skipped": facts.get("tests_skipped"),
            "source": "docs/VERIFICATION_REPORT.md",
        },
        "dashboard": dashboard_wiring() or {},
        "queue": sorted(queued_slugs()),
    }
    cov = lap_coverage()
    doc["splits"] = {
        "files_with_laps": cov[0] if cov else None,
        "files_total": cov[1] if cov else None,
        "published": False,
    }
    doc["coaching"] = _coaching_facts()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=False)
        fh.write("\n")
    return doc


def _utcnow():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _head_sha():
    """The commit this snapshot describes. Null here means the file is not a
    usable source, because a reader cannot tell whether it is current.

    Reads .git/HEAD rather than shelling out to git: this box has git bundled
    inside GitHub Desktop and not on PATH, so a subprocess call fails for
    reasons that have nothing to do with the repository.
    """
    ref = None
    try:
        with open(os.path.join(REPO, ".git", "HEAD"), encoding="utf-8") as fh:
            head = fh.read().strip()
        if head.startswith("ref: "):
            ref = head[5:].strip()
            with open(os.path.join(REPO, ".git", ref), encoding="utf-8") as fh:
                return fh.read().strip()[:12]
        return head[:12] or None
    except Exception:
        return None


def _coaching_facts():
    """The current control state. A refusal is the honest answer and is recorded
    as one rather than being replaced by a stale recommendation."""
    try:
        import trainingdb
        import recommend
        conn = trainingdb.connect()
        try:
            r = recommend.recommend(conn)
        finally:
            conn.close()
        return {"state": r.get("state"), "advisory": r.get("advisory"),
                "reasons": r.get("reasons"),
                "acwr": (r.get("evidence") or {}).get("acwr")}
    except Exception as exc:
        return {"state": "unavailable", "error": str(exc)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="report, always exit 0")
    ap.add_argument("--write-facts", action="store_true",
                    help="regenerate brief_facts.json and exit")
    a = ap.parse_args()

    if a.write_facts:
        doc = write_facts()
        print("wrote brief_facts.json for commit %s" % (doc["commit"] or "unknown"))
        return 0

    rows = brief_rows()
    queued = queued_slugs()
    orphans = unbacked_rows()
    facts = measured_facts()

    print("brief rows        : %d" % len(rows))
    print("task files queued : %d  (%s)" % (len(queued), ", ".join(sorted(queued))))
    print("unbacked rows     : %d" % len(orphans))
    for slug, status, text in orphans:
        print("  %-52s %s" % (slug, status))

    print("\nmeasured facts")
    for key in ("fit_files", "activities", "open_reviews", "tests_passed",
                "tests_skipped"):
        if facts.get(key) is not None:
            print("  %-22s %s" % (key, facts[key]))
    for reason, n in sorted((facts.get("review_breakdown") or {}).items()):
        print("  %-22s %s" % (reason, n))
    wiring = dashboard_wiring()
    if wiring:
        print("  %-22s %s" % ("server routes", len(wiring["server_routes"])))
        print("  %-22s %s" % ("dashboard calls", len(wiring["dashboard_calls"])))

    conflicts = claim_conflicts(facts) + reason_conflicts(facts)
    dash = dashboard_conflict()
    if dash:
        conflicts.append(dash)
    print("\nconflicting claims : %d" % len(conflicts))
    for label, stated, actual, line in conflicts:
        print("  %-16s brief says %-22s actually %s" % (label, stated, actual))
        print("      %s" % line)

    cov = lap_coverage()
    if cov:
        have, seen = cov
        print("\nFIT files with lap records: %d/%d" % (have, seen))
        if seen and have == seen:
            print("  per-mile splits ARE available; a brief claiming otherwise is wrong")

    if orphans:
        print("\nEach unbacked row is a claim with no task file behind it. That is not")
        print("automatically false, but it cannot be verified from tasks/ either.")

    if conflicts:
        print("\nEvery conflict above is a number or state the writer could not read")
        print("from this repository. None of them are close calls.")

    # A brief with no recognisable rows is a regression, not a clean bill. An
    # earlier version returned 0 here, which meant losing the task table
    # silently passed.
    no_rows = not rows
    if no_rows:
        print("\nNO TASK ROWS PARSED. If the brief genuinely has no tasks, that")
        print("should be said in a form this module can read; otherwise the table")
        print("changed shape and this check is now blind to it.")

    failed = bool(orphans or conflicts or no_rows)
    return 0 if (a.quiet or not failed) else 1


if __name__ == "__main__":
    sys.exit(main())