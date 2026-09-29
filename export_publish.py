#!/usr/bin/env python3
"""
export_publish.py - normalise Garmin Connect CSV exports into one canonical
file, then commit and push it to a GitHub repo and print the raw download URL.

Run it whenever you export from Garmin Connect, or wire it in after garmin_sync.py.

    python export_publish.py --check     # report state, change nothing
    python export_publish.py              # build, commit, push, print URL

Requires: git on PATH, and this folder inside a git repo with a remote.
Create the repo private. A raw.githubusercontent.com URL from a public repo
exposes your run history permanently, and these files carry health data.

Publishes garmin_export.csv (one row per run) plus garmin_export.meta.json.
Never publishes .fit files: those embed GPS position, which maps your home,
work and routes. Never publishes tokens.
"""
import argparse
import csv
import glob
import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

# A scheduled task that prompts for a password hangs forever. Auth is handled by
# the credential manager, so fail fast with an error instead of blocking.
os.environ["GIT_TERMINAL_PROMPT"] = "0"

sys.path.insert(0, HERE)
import paths  # noqa: E402


def resolve_repo():
    # Superseded by paths.repo_dir(), which also works when this script is run
    # from inside the repository rather than from Downloads.
    return paths.repo_dir()



REPO = paths.repo_dir()
CANON = "garmin_export.csv"
META = "garmin_export.meta.json"
STATE = os.path.join(REPO, "publish_state.json")
# Raw FIT and the Garmin CSV export stay in the local data directory. They must
# never be written into the repository, which is public.
SRC_DIR = paths.data_dir()
FIT_DIR = paths.fit_dir()


# Written into the repo so a token or credential can never be committed with it.
# The sleep and HR entries are belt-and-braces: paths.py keeps those files in the
# local data directory, but if GARMIN_DATA_DIR is ever pointed at the repo they
# must still not be committable.
IGNORE = """\
# credentials - never commit
.garmin_tokens/
*_tokens.json
*_token*.json
*.env
.env*

# athlete health data - never commit
garmin_sleep.csv
garmin_hr.csv
garmin_last_sync.json
.coach_dash_token

# local-only artefacts
garmin_sync.log
__pycache__/
*.pyc
.pytest_cache/

# raw activity files embed GPS position
garmin_fit/
*.fit

# the dashboard embeds an exact lat/lon per run - local only
dashboard/
"""


# Columns that are numbers in the Garmin export, stored with thousands commas.
NUMERIC = {"Distance", "Calories", "Avg HR", "Max HR", "Avg Run Cadence",
           "Max Run Cadence", "Total Ascent", "Total Descent", "Avg Stride Length",
           "Training Stress Score", "Steps", "Moving Time", "Elapsed Time",
           "Number of Laps", "Min Elevation", "Max Elevation"}


def die(msg, hint=None):
    print("  ! %s" % msg)
    if hint:
        print("    -> %s" % hint)
    sys.exit(1)


def code_paths():
    """Version-controlled pipeline code, as repo-relative paths.

    The scripts used to live in Downloads with no version control, which meant
    a cleared Downloads folder would destroy the pipeline. They are in the repo
    now, so the publisher stages and fingerprints them.
    """
    out = ["pyproject.toml"]
    for name in sorted(os.listdir(REPO)):
        if name.endswith(".py") and os.path.isfile(os.path.join(REPO, name)):
            out.append(name)
    for sub in ("tests", "dashboard"):
        d = os.path.join(REPO, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            rel = "%s/%s" % (sub, name)
            if rel in LOCAL_ONLY:
                continue
            if name.endswith((".py", ".html", ".toml")):
                out.append(rel)
    return out



GIT = None


def find_git():
    w = shutil.which("git")
    if w:
        return w
    cands = []
    hub = os.environ.get("LOCALAPPDATA", "")
    if hub:
        base = os.path.join(hub, "GitHubDesktop")
        if os.path.isdir(base):
            for name in sorted(os.listdir(base), reverse=True):
                if name.startswith("app-"):
                    cands.append(os.path.join(base, name, "resources", "app",
                                               "git", "cmd", "git.exe"))
    cands += [r"C:\Program Files\Git\cmd\git.exe",
              r"C:\Program Files\Git\bin\git.exe",
              r"C:\Program Files (x86)\Git\cmd\git.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe")]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def run(args, **kw):
    a = list(args)
    if a and a[0] == "git":
        a = a[1:]
    cwd = REPO if os.path.isdir(REPO) else HERE
    return subprocess.run([GIT] + a, capture_output=True, text=True, cwd=cwd, **kw)


def ensure_helper():
    h = os.path.normpath(os.path.join(os.path.dirname(GIT), "..", "mingw64",
                                      "bin", "git-credential-manager.exe"))
    if os.path.exists(h):
        run(["config", "--global", "credential.helper", h])
        return h
    run(["config", "--global", "credential.helper", "manager"])
    return "manager"


def need_git():
    global GIT
    GIT = find_git()
    if not GIT:
        die("git not found",
            "install Git for Windows, or install/open GitHub Desktop once")
    return run(["--version"]).stdout.strip()


def need_repo():
    if not os.path.isdir(REPO):
        os.makedirs(REPO, exist_ok=True)
        print("created      : %s" % REPO)
    if not os.path.isdir(os.path.join(REPO, ".git")):
        r = run(["init", "-q", "-b", "main"])
        if r.returncode != 0:
            run(["init", "-q"])
        print("initialised  : a new git repo at %s" % REPO)
    r = run(["remote", "get-url", "origin"])
    if r.returncode != 0 or not r.stdout.strip():
        die("no 'origin' remote is configured in %s" % REPO,
            "create a PRIVATE repo in GitHub Desktop at this path, or run:\n"
            "       git remote add origin https://github.com/benpioske-del/garmin-export.git")
    return r.stdout.strip()


def newest_fit_date():
    dates = []
    for p in glob.glob(os.path.join(FIT_DIR, "*.fit")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", os.path.basename(p))
        if m:
            dates.append(m.group(1))
    return max(dates) if dates else None


def clean(v):
    if v is None:
        return ""
    v = v.strip()
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", v):
        v = v.replace(",", "")
    return v


def norm(c):
    # Garmin appends a registered-trademark symbol to some headers, e.g.
    # "Training Stress Score\u00ae". Any lookup of the clean name silently
    # misses, so strip marks and collapse odd whitespace at read time.
    if c is None:
        return ""
    for ch in ("\u00ae", "\u2122", "\u00a9", "\u00a0"):
        c = c.replace(ch, " " if ch == "\u00a0" else "")
    return re.sub(r"\s+", " ", c).strip()


def build_csv():
    csv_sources = sorted(glob.glob(os.path.join(SRC_DIR, "Activities*.csv")))
    fit_glob = os.path.join(FIT_DIR, "*.fit")

    # FIT files are the source of truth: they carry elevation, laps and splits
    # that the CSV export omits, and they arrive automatically. The CSV is kept
    # as a fallback for any run the FIT set is missing.
    fit_rows, fit_skipped = [], []
    if os.path.isdir(FIT_DIR) and glob.glob(fit_glob):
        try:
            import garmin_fit_reader
            fit_rows, fit_skipped = garmin_fit_reader.read_dir(fit_glob)
        except ImportError:
            print("  ! fitparse/reader unavailable - falling back to CSV exports only")
        except Exception as exc:
            print("  ! could not read FIT files (%s)" % exc)
    for name, err in fit_skipped[:3]:
        print("  - skipped FIT %s (%s)" % (name, err))
    if fit_skipped:
        print("  - %d FIT file(s) skipped" % len(fit_skipped))

    if not fit_rows and not csv_sources:
        die("no activity data found",
            "expected .fit files in %s or Activities*.csv in %s" % (FIT_DIR, SRC_DIR))

    header, rows, seen = None, [], set()

    def add(row, key_date, key_dist):
        key = (key_date, key_dist)
        if key in seen:
            return False
        seen.add(key)
        rows.append(row)
        return True

    # FIT rows first, so they win any collision.
    for r in fit_rows:
        add(r, r.get("Date", "")[:10], round(float(r.get("Distance") or 0), 1))

    for path in csv_sources:
        base = os.path.basename(path)
        try:
            with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
                rdr = csv.DictReader(fh)
                if not rdr.fieldnames or "Date" not in rdr.fieldnames:
                    print("  - skipping %s (no Date column)" % base)
                    continue
                if header is None:
                    header = [norm(c) for c in rdr.fieldnames]
                for row in rdr:
                    date = clean(row.get("Date"))
                    if not date:
                        continue
                    out = {norm(c): clean(row.get(c)) for c in rdr.fieldnames}
                    # Garmin titles can name a city or route. Drop it: this is a
                    # public repo and a place name is a location identifier.
                    out["Title"] = ""
                    out["Source"] = "Garmin CSV export"
                    out["Timezone Status"] = "unknown; athlete-supplied date"
                    out.setdefault("Date (UTC)", "")
                    out["_source_file"] = base
                    try:
                        dist = round(float(out.get("Distance") or 0), 1)
                    except ValueError:
                        dist = out.get("Distance")
                    if not add(out, date[:10], dist):
                        continue
        except Exception as exc:
            print("  - could not read %s (%s)" % (base, exc))

    if not rows:
        die("no usable rows found in the activity sources")

    # Union of every column seen, FIT columns first then any CSV-only columns.
    cols = []
    for r in rows:
        for c in r:
            if c not in cols:
                cols.append(c)
    # Provenance columns last, in a fixed order, so the export's shape is stable.
    if "_source_file" in cols:
        cols.remove("_source_file")
    for c in ("Date (UTC)", "Timezone Status", "Source", "_source_file"):
        if c in cols:
            cols.remove(c)
        cols.append(c)

    def sk(r):
        d = r.get("Date", "")
        return (d[5:10], d[:10]) if len(d) >= 10 else ("", d)

    rows.sort(key=sk)
    # _source_file is the internal key; publish it as a real provenance column.
    header = {"_source_file": "Source File"}
    with open(os.path.join(REPO, CANON), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore",
                           restval="", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({header.get(k, k): v for k, v in r.items() if k in cols})

    dates = sorted(r.get("Date", "")[:10] for r in rows if r.get("Date"))
    meta = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_count": len(rows),
        "earliest_run": dates[0] if dates else None,
        "latest_run": dates[-1] if dates else None,
        "runs_from_fit": len(fit_rows),
        "runs_from_csv": len(rows) - len(fit_rows),
        "sources": ([os.path.basename(s) for s in csv_sources]
                    + ["garmin_fit/*.fit (%d files)" % len(fit_rows)] if fit_rows
                    else [os.path.basename(s) for s in csv_sources]),
        "newest_fit_file": newest_fit_date(),
        "note": "Built from Garmin .FIT files, with CSV exports as fallback. "
                "Times are local wall clock; distances miles; pace min/mi. "
                "No GPS, no coordinates, no credentials. Title is withheld.",
    }
    with open(os.path.join(REPO, META), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")
    return meta, cols


def guard_secrets():
    r = run(["git", "status", "--porcelain"])
    for line in r.stdout.splitlines():
        name = line[3:].strip().strip('"')
        low = name.lower()
        if "token" in low or low.endswith(".env") or "/.env" in low or low.endswith(".fit"):
            die("refusing to commit %s" % name,
                "it looks like a credential or a GPS-bearing file")
    for bad in (".garmin_tokens", "garmin_fit", ".env"):
        if os.path.exists(os.path.join(REPO, bad)) and bad != ".env":
            ig = os.path.join(REPO, ".gitignore")
            have = open(ig, encoding="utf-8").read() if os.path.exists(ig) else ""
            if bad.rstrip("/") not in have:
                print("  ! %s is not in .gitignore - refusing to continue" % bad)
                sys.exit(1)
    guard_gps_content()


# Files we refuse to publish at all. The dashboard embeds an exact latitude and
# longitude for individual runs, so it is a local-only artefact. It was committed
# by accident once; that is what this list is here to prevent a second time.
LOCAL_ONLY = ("dashboard/index.html",)

# Files that necessarily contain the detection patterns themselves. The scanner
# has to spell out the strings it looks for, so it would otherwise flag its own
# source and its own tests. This list is deliberately explicit rather than
# pattern-based, so an exemption can never be granted by accident.
GUARD_IMPL = ("export_publish.py", "capture_supervisor_brief.py",
              "tests/test_gps_guard.py", "tests/test_capture_supervisor.py")


def guard_gps_content():
    """Refuse to stage any text file that embeds per-activity coordinates.

    The earlier guard only inspected file NAMES, so a file named index.html with
    a dozen hardcoded lat/lon pairs sailed straight into a public repository.
    Checking content is what actually protects the athlete.

    A labelled coordinate is the signal. A bare decimal pair is not: training
    data is full of them (pace splits, lap times), and a false positive would
    block legitimate work.
    """
    # Key/value forms, applied to code, data and markup.
    patterns = [
        (r'"lat"\s*:\s*-?\d{1,3}\.\d{3,}', "JSON \"lat\" coordinate"),
        (r'"lon[g]?"\s*:\s*-?\d{1,3}\.\d{3,}', "JSON \"lon\" coordinate"),
        (r'"latitude"\s*:\s*-?\d{1,3}\.\d{3,}', "JSON \"latitude\" coordinate"),
        (r'"longitude"\s*:\s*-?\d{1,3}\.\d{3,}', "JSON \"longitude\" coordinate"),
        # Raw FIT stores semicircles as large integers, not degrees. A field
        # name on its own is harmless (the reader must name them to reject
        # them), but a name paired with a value is an exact position.
        (r'["\']position_lat["\']\s*:\s*-?\d{5,}', "raw FIT semicircle latitude"),
        (r'["\']position_l[o]?ng["\']\s*:\s*-?\d{5,}', "raw FIT semicircle longitude"),
    ]
    # Header-column form. Restricted to .csv because the same shape appears in
    # ordinary Python, e.g. "lat, lon = raw_lat * SCALE, raw_lon * SCALE".
    csv_patterns = [
        (r'(?im)(?:^|,)\s*lat\b\s*(?:,|$)', "CSV \"lat\" column"),
        (r'(?im)(?:^|,)\s*lon[g]?\b\s*(?:,|$)', "CSV \"lon\" column"),
        (r'(?im)(?:^|,)\s*latitude\b\s*(?:,|$)', "CSV \"latitude\" column"),
    ]
    skip_dirs = (".git", "__pycache__", ".pytest_cache", "dashboard")
    for dirpath, dirnames, filenames in os.walk(REPO):
        dirnames[:] = [d for d in dirnames
                       if d not in skip_dirs and not d.startswith(".")]
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), REPO).replace("\\", "/")
            if not fn.endswith((".py", ".html", ".js", ".json", ".md", ".csv", ".txt")):
                continue
            if rel in LOCAL_ONLY or rel in GUARD_IMPL:
                continue
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) > 8_000_000:
                    continue
                with open(p, "rb") as fh:
                    body = fh.read().decode("utf-8", "replace")
            except OSError:
                continue
            # A bare field NAME is not a leak. garmin_fit_reader.py has to name
            # position_lat to reject it, and CREW_BRIEF.md documents that GPS is
            # deliberately excluded. Only a numeric value paired with a location
            # key is a leak, so that is what is matched below.
            for pat, kind in patterns:
                if re.search(pat, body):
                    die("refusing to commit %s" % rel,
                        "it contains a %s. This repository is public.\n"
                        "Add it to LOCAL_ONLY and keep it local." % kind)
            if fn.endswith(".csv"):
                for pat, kind in csv_patterns:
                    if re.search(pat, body):
                        die("refusing to commit %s" % rel,
                            "it has a %s. This repository is public.\n"
                            "Add it to LOCAL_ONLY and keep it local." % kind)



def sync_with_remote(branch):
    """Fold any commits made on GitHub by others (e.g. a CrewAI crew) under ours.

    Without this, a local commit on top of a stale clone makes 'git push' fail as
    a non-fast-forward, and every later scheduled run fails the same way -- the
    local repo is permanently wedged. Everything we generate is reproducible from
    the .FIT files, so on a rebase conflict it is safe to reset onto the remote
    and redo the export. Hand-edited files are backed up first so a conflict
    cannot eat the owner's edits to profile.json.
    """
    keep = {}
    for name in ("profile.json", "CREW_BRIEF.md"):
        p = os.path.join(REPO, name)
        if os.path.exists(p):
            keep[name] = open(p, "rb").read()

    r = run(["git", "fetch", "origin", branch])
    if r.returncode != 0:
        print("  ! could not fetch origin/%s (%s)" % (branch, r.stderr.strip()[:70]))
        return

    behind = run(["git", "rev-list", "--count", "HEAD..origin/" + branch]).stdout.strip()
    ahead = run(["git", "rev-list", "--count", "origin/%s..HEAD" % branch]).stdout.strip()
    if behind in ("0", ""):
        return

    print("remote moved: %s new commit(s) on origin/%s - folding them in" % (behind, branch))

    if ahead in ("0", ""):
        # Nothing local to replay, so a plain fast-forward is enough. Without
        # this, 'git rebase' is a silent no-op and files a crew added to the
        # repo (e.g. tasks) would never show up in the working tree.
        r = run(["git", "merge", "--ff-only", "origin/" + branch])
        if r.returncode == 0:
            print("  fast-forwarded to origin/%s" % branch)
        else:
            run(["git", "reset", "--hard", "origin/" + branch])
            print("  fast-forward refused - reset to origin/%s" % branch)
            restore_hand_edited(keep, branch)
        return

    r = run(["git", "rebase", "origin/" + branch])
    if r.returncode == 0:
        print("  rebased cleanly (kept %s local commit(s))" % ahead)
        return

    # Conflict. Our generated files can always be rebuilt, so start from remote
    # and restore anything the owner edited by hand.
    run(["git", "rebase", "--abort"])
    run(["git", "reset", "--hard", "origin/" + branch])
    print("  rebase conflicted - reset to origin/%s, will rebuild" % branch)
    restore_hand_edited(keep, branch)


def restore_hand_edited(keep, branch):
    """Put back owner-edited files that differ from the remote version."""
    for name, blob in keep.items():
        p = os.path.join(REPO, name)
        remote = run(["git", "show", "origin/%s:%s" % (branch, name)]).stdout
        if remote is not None and remote != blob.decode("utf-8", "replace"):
            with open(p, "wb") as fh:
                fh.write(blob)
            print("  restored hand-edited %s" % name)


def report_tasks():
    """Summarise the task queue so the log shows when a crew has left work."""
    tdir = os.path.join(REPO, "tasks")
    if not os.path.isdir(tdir):
        return
    pending = []
    for name in sorted(os.listdir(tdir)):
        if not name.lower().endswith(".md"):
            continue
        try:
            head = open(os.path.join(tdir, name), encoding="utf-8").read(4000)
        except OSError:
            continue
        status = "pending"
        for line in head.splitlines():
            s = line.strip().lower()
            if s.startswith("status:"):
                status = s.split(":", 1)[1].strip()
                break
        if status in ("pending", "in_progress"):
            pending.append((name, status))
    if pending:
        print("tasks       : %d awaiting the coach" % len(pending))
        for name, status in pending:
            print("              - tasks/%s (%s)" % (name, status))
        print("              ask the coach: \"check for new tasks\"")
    else:
        print("tasks       : none pending")


def raw_url(remote, branch):
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote)
    if not m:
        return None
    return "https://raw.githubusercontent.com/%s/%s/%s/%s" % (
        m.group(1), m.group(2), branch, CANON)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, change nothing")
    a = ap.parse_args()

    ver = need_git()
    print("git         : %s" % ver)
    print("            (%s)" % GIT)
    print("auth        : %s" % ensure_helper())
    print("repo        : %s" % REPO)
    print("export file : %s" % CANON)

    remote = need_repo()
    print("origin      : %s" % remote)

    ig = os.path.join(REPO, ".gitignore")
    if not os.path.exists(ig):
        with open(ig, "w", encoding="utf-8") as fh:
            fh.write(IGNORE)
        print("gitignore   : created")
    else:
        have = open(ig, encoding="utf-8").read().splitlines()
        added = 0
        for line in IGNORE.splitlines():
            if line.strip() and not line.startswith("#") and line not in have:
                with open(ig, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                added += 1
        print("gitignore   : %s" % ("ensured" if not added else "+%d rule(s)" % added))

    if a.check:
        nf = newest_fit_date()
        print("newest .fit : %s" % (nf or "none"))
        st = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
        print("last url    : %s" % st.get("raw_url", "never published"))
        return 0

    guard_secrets()
    meta, cols = build_csv()
    print("runs        : %d  (%s -> %s)" % (meta["run_count"],
                                           meta["earliest_run"], meta["latest_run"]))
    if meta["newest_fit_file"] and meta["latest_run"] and \
            meta["newest_fit_file"] > meta["latest_run"]:
        print("  ! STALE: newest .fit is %s but the export stops at %s."
              % (meta["newest_fit_file"], meta["latest_run"]))
        print("    Export a fresh Activities.csv from Garmin Connect, or the crew"
              " will think you stopped training.")

    # Resolve the branch and write the state file BEFORE staging, so it can be
    # committed in the same pass. The URL is deterministic from remote+branch.
    # The metadata carries a generated_utc timestamp, so the working tree always
    # looks dirty. Hash the data plus every hand-editable file we publish, so an
    # unchanged export does not produce an empty commit while a real edit to the
    # brief or the profile does publish. META is deliberately excluded: it holds a
    # fresh timestamp on every run and would commit every time.
    # SUPERVISOR_BRIEF.md and TASKS.md are the two allowed names for a captured
    # crew brief (see capture_supervisor_brief.py). Both are fingerprinted so a
    # new brief commits even when the FIT export has not changed.
    h = hashlib.sha256()
    for part in (CANON, "CREW_BRIEF.md", "profile.json", "CREW_TASKS.md",
                 "SUPERVISOR_BRIEF.md", "TASKS.md"):
        p = os.path.join(REPO, part)
        h.update(part.encode("utf-8"))
        if os.path.exists(p):
            h.update(open(p, "rb").read())
    ddir = os.path.join(REPO, "docs")
    if os.path.isdir(ddir):
        for n in sorted(os.listdir(ddir)):
            if n.lower().endswith(".md"):
                h.update(("docs/" + n).encode("utf-8"))
                h.update(open(os.path.join(ddir, n), "rb").read())
    tdir = os.path.join(REPO, "tasks")
    if os.path.isdir(tdir):
        for n in sorted(os.listdir(tdir)):
            if n.lower().endswith(".md"):
                h.update(n.encode("utf-8"))
                h.update(open(os.path.join(tdir, n), "rb").read())
    data_sha = h.hexdigest()

    # Hash the pipeline code separately. It used to live in Downloads and was
    # not version controlled at all; now that it is in the repository, a code
    # change has to be able to trigger a commit on its own, otherwise a fix to
    # the importer would sit uncommitted while the publisher reported that
    # nothing changed. Kept out of data_sha so that message still means the
    # athlete's activity data is untouched.
    hc = hashlib.sha256()
    code_files = code_paths()
    for rel in code_files:
        p = os.path.join(REPO, rel)
        hc.update(rel.encode("utf-8"))
        if os.path.exists(p):
            with open(p, "rb") as fh:
                hc.update(fh.read())
    code_sha = hc.hexdigest()

    prev = {}
    if os.path.exists(STATE):
        try:
            prev = json.load(open(STATE, encoding="utf-8"))
        except Exception:
            prev = {}

    branch = run(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip() or "main"
    if branch == "HEAD":
        branch = "main"
    url = raw_url(remote, branch)

    # Fold in anything a CrewAI crew committed to GitHub before we build on top
    # of it, otherwise the push is rejected and the local clone stays wedged.
    sync_with_remote(branch)

    if prev.get("data_sha") == data_sha and prev.get("code_sha") == code_sha:
        run(["git", "checkout", "--", META, "publish_state.json"])
        print("data unchanged since last publish - no commit needed.")
        report_tasks()
        print("raw url     : %s" % url)
        return 0

    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump({"raw_url": url, "branch": branch, "at": meta["generated_utc"],
                   "run_count": meta["run_count"], "latest_run": meta["latest_run"],
                   "data_sha": data_sha, "code_sha": code_sha,
                   "repo_visibility": "public - readable without a token"},
                  fh, indent=2)
        fh.write("\n")

    tracked = [CANON, META, ".gitignore", "publish_state.json"]
    for extra in ("CREW_BRIEF.md", "profile.json", "CREW_TASKS.md",
                  "SUPERVISOR_BRIEF.md", "TASKS.md"):
        if os.path.exists(os.path.join(REPO, extra)):
            tracked.append(extra)
    ddir = os.path.join(REPO, "docs")
    if os.path.isdir(ddir):
        for n in sorted(os.listdir(ddir)):
            if n.lower().endswith(".md"):
                tracked.append("docs/" + n)
    # Task files are written and updated by hand, so keep them in the commit.
    tdir = os.path.join(REPO, "tasks")
    if os.path.isdir(tdir):
        for n in sorted(os.listdir(tdir)):
            if n.lower().endswith(".md"):
                tracked.append("tasks/" + n)
    tracked.extend(code_paths())
    r = run(["git", "add"] + tracked)
    if r.returncode != 0:
        die("git add failed", r.stderr.strip())

    r = run(["status", "--porcelain"])
    if not r.stdout.strip():
        print("\nnothing changed - the file already matches the last commit.")
        print("raw url     : %s" % url)
        return 0

    msg = "garmin export: %d runs, latest %s" % (meta["run_count"], meta["latest_run"])
    r = run(["git", "commit", "-m", msg])
    if r.returncode != 0:
        die("git commit failed", r.stderr.strip())
    print("committed   : %s" % msg)

    r = run(["git", "push", "origin", branch])
    if r.returncode != 0:
        die("git push failed - nothing was published",
            r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")
    print("pushed      : origin/%s" % branch)

    print("\nraw download url")
    print(url)
    print("\nThis repo is PUBLIC, so that URL is readable with no token.")
    print("CrewAI can poll it directly. If you ever make the repo private")
    print("again, that same URL will start returning 404.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


