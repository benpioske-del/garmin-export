#!/usr/bin/env python3
"""Check the supervisor brief against things that can actually be measured.

The brief's task table is prose written by a process that cannot see most of this
repository: `dashboard/` is gitignored because it holds a running journal, body
weight and coordinates, and the FIT files are local-only. Three consecutive
briefs asserted a dashboard state the writer had no way to observe.

`CREW_TASKS.md` already says `tasks/` is the real queue. Nothing enforced it, so
the table grew entries with no backing file. This module makes that checkable:

    python brief_consistency.py          # report, exit 1 if anything is unbacked
    python brief_consistency.py --quiet  # report, always exit 0

An unbacked row is not automatically wrong. It is a claim with no evidence
attached, which is the thing worth surfacing.
"""
import argparse
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

REPO = paths.repo_dir()
BRIEF = os.path.join(REPO, "SUPERVISOR_BRIEF.md")
TASKS = os.path.join(REPO, "tasks")

# `slug | STATUS | prose`, as written by the brief process. No leading pipe.
ROW = re.compile(r"^\s*([a-z0-9][a-z0-9-]{6,})\s*\|\s*([A-Z][A-Z /-]*[A-Z])\s*\|\s*(.+)$")


def brief_rows():
    """(slug, status, text) for every row in the brief's task table."""
    if not os.path.isfile(BRIEF):
        return []
    rows = []
    for line in open(BRIEF, encoding="utf-8").read().splitlines():
        m = ROW.match(line)
        if m:
            rows.append((m.group(1), m.group(2).strip(), m.group(3).strip()))
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="report, always exit 0")
    a = ap.parse_args()

    rows = brief_rows()
    queued = queued_slugs()
    orphans = unbacked_rows()

    print("brief rows        : %d" % len(rows))
    print("task files queued : %d  (%s)" % (len(queued), ", ".join(sorted(queued))))
    print("unbacked rows     : %d" % len(orphans))
    for slug, status, text in orphans:
        print("  %-52s %s" % (slug, status))

    cov = lap_coverage()
    if cov:
        have, seen = cov
        print("\nFIT files with lap records: %d/%d" % (have, seen))
        if seen and have == seen:
            print("  per-mile splits ARE available; a brief claiming otherwise is wrong")

    if orphans:
        print("\nEach unbacked row is a claim with no task file behind it. That is not")
        print("automatically false, but it cannot be verified from tasks/ either.")
        print("A brief cannot observe gitignored files, so expect these to persist")
        print("until the observability gap is closed.")

    return 0 if (a.quiet or not orphans) else 1


if __name__ == "__main__":
    sys.exit(main())