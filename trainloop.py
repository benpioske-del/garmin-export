"""Single entry point for everything this repository does.

Supervisor brief work landed across a dozen modules, each with its own
invocation. That is fine for tests and terrible for a person opening a command
prompt, who now has to know which of them to run and in what order. This module
is the one thing to remember:

    python trainloop.py status        # what exists, what is missing
    python trainloop.py bootstrap     # migrate + import, safe to re-run
    python trainloop.py audit         # reproducible FIT audit
    python trainloop.py load          # 7/14/28-day load
    python trainloop.py recommend     # training control state
    python trainloop.py test          # full suite
    python trainloop.py publish       # guarded export + push
    python trainloop.py doctor        # diagnose a broken setup

`trainloop.cmd` wraps this for double-click and plain cmd use.

Design rules:

  * Nothing here invents an input. If `hr_max` is unset, `load` and
    `recommend` say so and refuse rather than assuming a maximum.
  * `status` never reports a count that hides a gap. An empty database with 56
    FIT files on disk is reported as two facts, not as "0 activities".
  * Every mutating command is idempotent, so re-running is safe.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import activities  # noqa: E402
import fit_audit  # noqa: E402
import loadcalc  # noqa: E402
import paths  # noqa: E402
import recommend  # noqa: E402
import trainingdb  # noqa: E402

DEFAULT_FIT_GLOB = r"C:\Users\benpi\Downloads\garmin_fit\*.fit"


# --------------------------------------------------------------- helpers

def _hr_max(explicit=None):
    """Resolve a max heart rate, or None.

    Checked in order: the command line, then profile.json. Never derived from
    age, because 220-age is a population heuristic and it would silently move
    every load number in the system.
    """
    if explicit:
        return float(explicit)
    try:
        profile = json.loads((HERE / "profile.json").read_text(encoding="utf-8"))
        value = profile.get("hr_max")
        if value:
            return float(value)
    except (OSError, ValueError):
        pass
    return None


def _db_activities(conn):
    return conn.execute("SELECT COUNT(*) c FROM activities").fetchone()["c"]


def _fit_files(pattern):
    return sorted(glob.glob(pattern))


def _run(argv):
    """Run a subprocess in this directory and stream its output."""
    return subprocess.call([sys.executable] + argv, cwd=str(HERE))


# --------------------------------------------------------------- commands

def cmd_migrate(args):
    conn = trainingdb.connect()
    applied = trainingdb.migrate(conn, verbose=True)
    conn.close()
    if not applied:
        print("database already up to date")
    print("database: %s" % trainingdb.db_path())
    return 0


def cmd_import(args):
    conn = trainingdb.connect()
    trainingdb.migrate(conn, verbose=False)
    pattern = args.pattern
    found = _fit_files(pattern)
    if not found:
        print("no FIT files matched %s" % pattern)
        print("edit --pattern, or set the source directory in paths.py")
        conn.close()
        return 1
    print("importing %d files from %s" % (len(found), pattern))
    tally = activities.import_dir(pattern, conn)
    print(json.dumps(tally, indent=2))
    summary = activities.summary(conn)
    print("activities: %(activities)d, open reviews: %(open_reviews)d" % summary)
    conn.close()
    return 0


def cmd_bootstrap(args):
    """Everything needed for the database to be useful, in one safe step."""
    rc = cmd_migrate(args)
    if rc:
        return rc
    print()
    return cmd_import(args)


def cmd_audit(args):
    pattern = args.pattern
    files = _fit_files(pattern)
    results, failures = fit_audit.summarise(files)
    roll = fit_audit.rollup(results, failures)
    print(fit_audit.render(results, failures, roll))
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"versions": fit_audit.parser_versions(), "rollup": roll, "files": results},
            indent=2, sort_keys=True, default=str), encoding="utf-8")
        print("wrote %s" % args.json)
    return 1 if roll["parse_failures"] else 0


def cmd_load(args):
    conn = trainingdb.connect()
    trainingdb.migrate(conn, verbose=False)
    if _db_activities(conn) == 0:
        print("no activities in the database. Run: python trainloop.py bootstrap")
        conn.close()
        return 1
    hr_max = _hr_max(args.hr_max)
    if hr_max is None:
        print("hr_max is not set, so running load is UNAVAILABLE by design.")
        print("Supply it explicitly:  --hr-max 185")
        print("or add \"hr_max\": <value> to profile.json")
        print("(It is never estimated from age. See docs/TRAINING_LOAD_METHODOLOGY.md)")
    result = loadcalc.compute(conn, as_of=args.as_of, hr_max=hr_max)
    print("version: %s" % result["version"])
    print("as of  : %s" % result["as_of_utc"])
    print()
    header = "%-6s %10s %10s %10s  %-12s %-12s" % (
        "window", "run", "strength", "combined", "run_conf", "strength_conf")
    print(header)
    print("-" * len(header))
    for key in ("7", "14", "28"):
        w = result["windows"][key]
        def fmt(v):
            return "n/a" if v is None else "%.1f" % v
        print("%-6s %10s %10s %10s  %-12s %-12s" % (
            key + "d", fmt(w["run_load"]), fmt(w["strength_load"]),
            fmt(w["combined_load"]), w["run_confidence"], w["strength_confidence"]))
    print()
    for key in ("7", "14", "28"):
        w = result["windows"][key]
        if w["unavailable"]["run"] or w["unavailable"]["strength"]:
            print("%sd unavailable:" % key)
            for note in w["unavailable"]["run"][:5]:
                print("   run      %s -> %s" % (note["activity_id"], note["reason"]))
            for note in w["unavailable"]["strength"][:5]:
                print("   strength %s -> %s" % (note["session_id"], note["reason"]))
    print()
    print("components are always shown separately. See docs/TRAINING_LOAD_METHODOLOGY.md")
    conn.close()
    return 0


def cmd_recommend(args):
    conn = trainingdb.connect()
    trainingdb.migrate(conn, verbose=False)
    if _db_activities(conn) == 0:
        print("no activities in the database. Run: python trainloop.py bootstrap")
        conn.close()
        return 1
    hr_max = _hr_max(args.hr_max)
    out = recommend.recommend(conn, as_of=args.as_of, hr_max=hr_max)
    print("state: %s" % out["state"])
    print("advisory: %s" % ("yes" if out["advisory"] else "no"))
    print()
    print("reasons:")
    for reason in out["reasons"]:
        print("  - %s" % reason)
    print()
    print("limitation: %s" % out["limitation"])
    print()
    print("evidence:")
    for k, v in sorted(out["evidence"].items()):
        if k.endswith("unavailable"):
            continue
        print("  %-20s %s" % (k, v))
    print()
    for line in out["disclaimers"]:
        print("  " + line)
    conn.close()
    return 0


def cmd_strength(args):
    """Record a strength session from the command line.

    Usage:
      python trainloop.py strength --name "Back Squat" --sets 3 --reps 5 \
              --load-kg 100 --rpe 7
    Repeated --set "name,reps,kg,rpe" also works for multi-exercise sessions.
    """
    import strength
    conn = trainingdb.connect()
    trainingdb.migrate(conn, verbose=False)
    sid = strength.start_session(conn, args.at)
    if args.set:
        for spec in args.set:
            parts = [p.strip() for p in spec.split(",")]
            name = parts[0]
            reps = int(parts[1]) if len(parts) > 1 else None
            load = float(parts[2]) if len(parts) > 2 and parts[2] else None
            rpe = float(parts[3]) if len(parts) > 3 and parts[3] else None
            n = strength.session_sets(conn, sid)
            strength.record_set(conn, sid, name, len(n) + 1, reps,
                                load_kg=load, rpe=rpe)
    if args.name:
        for n in range(1, args.sets + 1):
            strength.record_set(conn, sid, args.name, n, args.reps,
                                load_kg=args.load_kg, rpe=args.rpe)
    conn.commit()
    volume = strength.session_volume(conn, sid)
    print("session: %s" % sid)
    print("volume : %s" % json.dumps(volume))
    for row in strength.session_sets(conn, sid, include_warmups=True):
        print("   %-22s set %d  reps=%-4s load=%-8s rpe=%-4s warmup=%s"
              % (row["exercise"], row["set_number"], row["reps"],
                 row["load_kg"], row["rpe"], bool(row["is_warmup"])))
    flags = strength.safety_flags(conn, sid)
    if flags:
        print("safety flags:")
        for f in flags:
            print("   - %s" % f["detail"])
    for name in sorted({r["exercise"] for r in strength.session_sets(conn, sid)}):
        print("next: %s" % json.dumps(strength.suggest_progression(conn, name)))
    conn.close()
    return 0


def cmd_status(args):
    conn = trainingdb.connect()
    trainingdb.migrate(conn, verbose=False)
    db_count = _db_activities(conn)
    strength_count = conn.execute(
        "SELECT COUNT(*) c FROM strength_sessions").fetchone()["c"]
    open_reviews = conn.execute(
        "SELECT COUNT(*) c FROM review_items WHERE state = 'open'").fetchone()["c"]
    info = trainingdb.status(conn)
    conn.close()

    fit_files = _fit_files(args.pattern)
    csv_path = HERE / "garmin_export.csv"
    csv_rows = 0
    if csv_path.exists():
        with csv_path.open(encoding="utf-8", errors="replace") as fh:
            csv_rows = max(0, sum(1 for _ in fh) - 1)
    hr_max = _hr_max(args.hr_max)

    print("repository : %s" % HERE)
    print("database   : %s" % trainingdb.db_path())
    print("migrations : applied %s, pending %s"
          % (info["applied"] or "none", info["pending"] or "none"))
    print()
    print("FIT files on disk    : %d" % len(fit_files))
    print("activities in database: %d" % db_count)
    print("strength sessions     : %d" % strength_count)
    print("published CSV rows    : %d" % csv_rows)
    print("open review items     : %d" % open_reviews)
    print("hr_max                : %s" % (hr_max if hr_max else "NOT SET"))
    print()

    def plural(n, word, plural_form=None):
        if n == 1:
            return "1 %s" % word
        return "%d %s" % (n, plural_form or word + "s")

    gaps = []
    if db_count == 0 and fit_files:
        gaps.append("database is empty but %s are on disk -> run: "
                    "python trainloop.py bootstrap" % plural(len(fit_files), "FIT file"))
    if db_count and db_count != len(fit_files):
        gaps.append("database has %s but %s are on disk"
                    % (plural(db_count, "activity", "activities"),
                       plural(len(fit_files), "FIT file")))
    if csv_rows and db_count and csv_rows != db_count:
        gaps.append("published CSV has %s, database has %s"
                    % (plural(csv_rows, "row"),
                       plural(db_count, "activity", "activities")))
    if hr_max is None:
        gaps.append("hr_max not set -> running load and recommendations are "
                    "unavailable by design (see docs/TRAINING_LOAD_METHODOLOGY.md)")
    if open_reviews:
        gaps.append("%s open, mostly timezone confirmations -> recommend() will "
                    "refuse until these are resolved" % plural(open_reviews, "review item"))

    if gaps:
        print("needs attention:")
        for g in gaps:
            print("  - %s" % g)
    else:
        print("nothing outstanding")
    return 0


def cmd_test(args):
    return _run(["-m", "pytest", "-q"] + (args.pytest_args or []))


def cmd_publish(args):
    return _run(["export_publish.py"])


def _find_git():
    """Locate git.exe, tolerating an installation that is not on PATH.

    On this machine git ships only inside GitHub Desktop, so assuming a bare
    "git" would make the gitignore check fail for the wrong reason.
    GIT_TRAINLOOP overrides the search.
    """
    override = os.environ.get("GIT_TRAINLOOP")
    if override:
        return override if os.path.exists(override) else None
    found = shutil.which("git")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        desktop = os.path.join(local, "GitHubDesktop")
        for base in sorted(os.listdir(desktop), reverse=True) if os.path.isdir(desktop) else []:
            for rel in (os.path.join("resources", "app", "git", "cmd", "git.exe"),
                        os.path.join("resources", "app", "git", "mingw64", "bin", "git.exe")):
                cand = os.path.join(desktop, base, rel)
                if os.path.exists(cand):
                    return cand
    for cand in (r"C:\Program Files\Git\cmd\git.exe",
                 r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if os.path.exists(cand):
            return cand
    return None


def cmd_doctor(args):
    """Diagnose the things that silently break this setup."""
    problems, notes = [], []

    try:
        conn = trainingdb.connect()
        trainingdb.migrate(conn, verbose=False)
        notes.append("database OK: %s" % trainingdb.db_path())
        conn.close()
    except Exception as exc:  # noqa: BLE001
        problems.append("database unusable: %s" % exc)

    try:
        import sqlite3
        notes.append("sqlite3 %s" % sqlite3.sqlite_version)
    except ImportError as exc:
        problems.append("sqlite3 missing: %s" % exc)

    try:
        import fitparse
        notes.append("fitparse %s" % getattr(fitparse, "__version__", "?"))
    except ImportError:
        problems.append("fitparse not installed. Run: pip install -r requirements.txt")

    fit_dir = paths.fit_dir()
    if os.path.isdir(fit_dir):
        count = len(_fit_files(os.path.join(fit_dir, "*.fit")))
        notes.append("FIT directory %s: %d files" % (fit_dir, count))
        if not count:
            problems.append("FIT directory %s is empty" % fit_dir)
    else:
        problems.append("FIT directory %s does not exist (paths.fit_dir)" % fit_dir)

    if not (HERE / "garmin_export.csv").exists():
        problems.append("garmin_export.csv missing; run publish")
    else:
        notes.append("garmin_export.csv present")

    if str(trainingdb.db_path()).startswith(str(HERE)):
        git = _find_git()
        if git is None:
            notes.append("git not found on PATH, skipping the "
                         "gitignore check (see GIT_TRAINLOOP to point at it)")
        else:
            ignored = subprocess.call(
                [git, "check-ignore", "-q",
                 str(trainingdb.db_path().relative_to(HERE))], cwd=str(HERE))
            if ignored != 0:
                problems.append("the database is NOT gitignored. Do not commit it.")
            else:
                notes.append("database is gitignored")

    print("notes:")
    for n in notes:
        print("  - %s" % n)
    print()
    if problems:
        print("problems:")
        for p in problems:
            print("  - %s" % p)
        return 1
    print("no problems found")
    return 0


# ------------------------------------------------------------------- main

def build_parser():
    p = argparse.ArgumentParser(
        prog="trainloop.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    # Set here rather than per subcommand so that commands which delegate to
    # each other (bootstrap -> import) always find these attributes present.
    p.set_defaults(pattern=DEFAULT_FIT_GLOB, hr_max=None, as_of=None)
    sub = p.add_subparsers(dest="command")

    def add(name, func, help_text):
        sp = sub.add_parser(name, help=help_text)
        sp.set_defaults(func=func)
        return sp

    add("status", cmd_status, "what exists and what is missing")
    add("doctor", cmd_doctor, "diagnose a broken setup")
    sp = add("bootstrap", cmd_bootstrap, "migrate + import, safe to re-run")
    sp.add_argument("--pattern", default=DEFAULT_FIT_GLOB)

    sp = add("migrate", cmd_migrate, "apply pending schema migrations")
    sp = add("import", cmd_import, "import FIT files into the database")
    sp.add_argument("--pattern", default=DEFAULT_FIT_GLOB)

    sp = add("audit", cmd_audit, "reproducible FIT data audit")
    sp.add_argument("--pattern", default=DEFAULT_FIT_GLOB)
    sp.add_argument("--json", default=None, help="write the manifest here")

    sp = add("load", cmd_load, "training load, 7/14/28-day windows")
    sp.add_argument("--hr-max", type=float, default=None)
    sp.add_argument("--as-of", default=None)

    sp = add("recommend", cmd_recommend, "training control state")
    sp.add_argument("--hr-max", type=float, default=None)
    sp.add_argument("--as-of", default=None)

    sp = add("strength", cmd_strength, "record a strength session")
    sp.add_argument("--name", default=None)
    sp.add_argument("--sets", type=int, default=3)
    sp.add_argument("--reps", type=int, default=5)
    sp.add_argument("--load-kg", type=float, default=None)
    sp.add_argument("--rpe", type=float, default=None)
    sp.add_argument("--at", required=True, help="session start, e.g. 2026-09-26T18:00:00Z")
    sp.add_argument("--set", action="append", dest="set",
                    help='"exercise,reps,load_kg,rpe" (repeatable)')

    sp = add("test", cmd_test, "run the full test suite")
    sp.add_argument("pytest_args", nargs="*")

    add("publish", cmd_publish, "guarded export and push")
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
