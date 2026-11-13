"""Offline backup of the local-only athlete data.

The code lives on GitHub, so a dead laptop does not lose the pipeline. What it
does lose is everything the publisher deliberately keeps out of the tree: the
FIT corpus, ``trainloop.db``, the gitignored classic dashboard, the nutrition log
and its Health Connect sidecar.

``backup_data.py`` copies exactly those files into one timestamped zip and
prunes older copies. Credentials are excluded by default. The dashboard token,
the password hash, the nutrition hook token and the Garmin session tokens can
all be recreated after a restore, and a zip that ends up in cloud storage should
not carry them.

Nothing here touches the network. Point ``--dest`` at a synced folder and the
provider does the rest.

Usage::

    python backup_data.py                      # default destination, keep 14
    python backup_data.py --dest D:\\Backups     # explicit destination
    python backup_data.py --dry-run            # report what would be bundled
    python backup_data.py --include-secrets    # only for an encrypted archive
"""

import argparse
import datetime
import os
import zipfile

import paths

BACKUP_PREFIX = "coach-data-"
MANIFEST_NAME = "MANIFEST.txt"
DEFAULT_KEEP = 14

# Athlete data that is not in git and cannot be rebuilt from Garmin Connect.
DATA_FILES = (
    "garmin_sleep.csv",
    "garmin_hr.csv",
    "garmin_last_sync.json",
    "nutrition_log.csv",
    "nutrition_log.records.json",
)

# Repository files that are not in git. ``trainloop.db`` is rebuilt by
# ``trainloop.py bootstrap``; ``dashboard/index.html`` holds hand-entered
# athlete data and is not rebuilt from anything, so losing it is permanent.
REPO_FILES = ("trainloop.db", "dashboard/index.html")

# Credentials. Never bundled unless the caller asks for them. The sync log is
# not listed: it is regenerated on the next run and is not a credential.
SECRET_FILES = (
    ".coach_dash_token",
    ".coach_dash_auth",
    "nutrition_log.hook-token",
    "garmin_tokens.json",
)
SECRET_DIRS = (".garmin_tokens",)


def default_dest():
    """Prefer the OneDrive folder that is already syncing this machine.

    Falling back to Documents keeps the tool usable on a machine without
    OneDrive instead of failing outright.
    """
    candidates = [
        os.environ.get("OneDrive"),
        os.path.join(os.path.expanduser("~"), "OneDrive"),
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            return os.path.join(candidate, "CoachDashboardBackups")
    return os.path.join(os.path.expanduser("~"), "Documents",
                        "CoachDashboardBackups")


def fit_files(fit_dir):
    """Flat list of ``*.fit`` files, sorted, ignoring subdirectories."""
    if not os.path.isdir(fit_dir):
        return []
    found = []
    for name in sorted(os.listdir(fit_dir)):
        full = os.path.join(fit_dir, name)
        if name.lower().endswith(".fit") and os.path.isfile(full):
            found.append(full)
    return found


def collect(data_dir=None, repo_dir=None, include_secrets=False):
    """Return ``(included, excluded)`` as lists of ``(abs_path, arcname)``.

    ``excluded`` names the credentials that were deliberately left out, so the
    manifest and the console both say what the archive does not contain.
    """
    data_dir = data_dir or paths.data_dir()
    repo_dir = repo_dir or paths.repo_dir()

    included = []
    excluded = []

    for full in fit_files(os.path.join(data_dir, "garmin_fit")):
        included.append((full, "garmin_fit/" + os.path.basename(full)))

    for name in DATA_FILES:
        full = os.path.join(data_dir, name)
        if os.path.isfile(full):
            included.append((full, name))

    for name in REPO_FILES:
        full = os.path.join(repo_dir, name)
        if os.path.isfile(full):
            included.append((full, name))

    if include_secrets:
        for name in SECRET_FILES:
            full = os.path.join(data_dir, name)
            if os.path.isfile(full):
                included.append((full, name))
        for name in SECRET_DIRS:
            base = os.path.join(data_dir, name)
            if not os.path.isdir(base):
                continue
            for child in sorted(os.listdir(base)):
                full = os.path.join(base, child)
                if os.path.isfile(full):
                    included.append((full, name + "/" + child))
    else:
        for name in SECRET_FILES:
            if os.path.isfile(os.path.join(data_dir, name)):
                excluded.append(name)
        for name in SECRET_DIRS:
            if os.path.isdir(os.path.join(data_dir, name)):
                excluded.append(name + "/")

    return included, excluded


def head_commit(repo_dir):
    """Best-effort short hash, read without shelling out to git."""
    git_dir = os.path.join(repo_dir, ".git")
    try:
        with open(os.path.join(git_dir, "HEAD"), encoding="utf-8") as fh:
            ref = fh.read().strip()
        if ref.startswith("ref: "):
            target = os.path.join(git_dir, *ref[5:].split("/"))
            with open(target, encoding="utf-8") as fh:
                return fh.read().strip()[:12]
        return ref[:12]
    except OSError:
        return "unknown"


def build_manifest(included, excluded, when, commit):
    lines = [
        "Coach dashboard data backup",
        "created: %s" % when.strftime("%Y-%m-%d %H:%M:%S"),
        "code commit: %s" % commit,
        "files: %d" % len(included),
        "",
        "included:",
    ]
    for full, arcname in included:
        try:
            size = os.path.getsize(full)
        except OSError:
            size = -1
        lines.append("  %-40s %10d" % (arcname, size))
    lines.append("")
    if excluded:
        lines.append("excluded credentials (recreate after a restore):")
        for name in excluded:
            lines.append("  " + name)
    else:
        lines.append("excluded credentials: none found")
    lines.append("")
    lines.append("Restore with docs/RESTORE.md.")
    return "\n".join(lines) + "\n"


def prune(dest, keep=DEFAULT_KEEP):
    """Delete the oldest backups beyond ``keep``. Returns the removed names."""
    if keep < 1 or not os.path.isdir(dest):
        return []
    names = sorted(
        name for name in os.listdir(dest)
        if name.startswith(BACKUP_PREFIX) and name.endswith(".zip")
    )
    if len(names) <= keep:
        return []
    removed = []
    for name in names[:len(names) - keep]:
        try:
            os.remove(os.path.join(dest, name))
            removed.append(name)
        except OSError:
            pass
    return removed


def create_backup(dest=None, keep=DEFAULT_KEEP, include_secrets=False,
                  data_dir=None, repo_dir=None, now=None):
    """Write one zip and prune old ones.

    Returns a dict instead of raising so a scheduled run can log a useful
    failure (an empty data directory on a fresh machine is not a crash).
    """
    now = now or datetime.datetime.now()
    repo_dir = repo_dir or paths.repo_dir()
    dest = os.path.abspath(dest or default_dest())

    included, excluded = collect(data_dir=data_dir, repo_dir=repo_dir,
                                 include_secrets=include_secrets)
    if not included:
        return {"ok": False, "error": "nothing to back up", "dest": dest}

    os.makedirs(dest, exist_ok=True)
    name = BACKUP_PREFIX + now.strftime("%Y-%m-%d_%H%M%S") + ".zip"
    out = os.path.join(dest, name)
    manifest = build_manifest(included, excluded, now, head_commit(repo_dir))

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_NAME, manifest)
        for full, arcname in included:
            zf.write(full, arcname)

    return {
        "ok": True,
        "path": out,
        "bytes": os.path.getsize(out),
        "files": len(included),
        "excluded": excluded,
        "pruned": prune(dest, keep),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Back up local-only athlete data.")
    ap.add_argument("--dest", help="destination folder (default: OneDrive)")
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                    help="copies to keep, oldest pruned (default: %d)" % DEFAULT_KEEP)
    ap.add_argument("--include-secrets", action="store_true",
                    help="include tokens and the password hash (encrypt the result)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be bundled, write nothing")
    args = ap.parse_args(argv)

    if args.dry_run:
        included, excluded = collect(include_secrets=args.include_secrets)
        dest = os.path.abspath(args.dest or default_dest())
        print("destination: %s" % dest)
        print("files      : %d" % len(included))
        for full, arcname in included:
            print("  %-40s %10d" % (arcname, os.path.getsize(full)))
        print("excluded   : %s" % (", ".join(excluded) or "none"))
        return 0

    result = create_backup(dest=args.dest, keep=args.keep,
                           include_secrets=args.include_secrets)
    if not result["ok"]:
        print("backup failed: %s" % result["error"])
        return 1
    print("backup   : %s" % result["path"])
    print("files    : %d" % result["files"])
    print("size     : %.1f MB" % (result["bytes"] / (1024.0 * 1024.0)))
    print("excluded : %s" % (", ".join(result["excluded"]) or "none"))
    if result["pruned"]:
        print("pruned   : %s" % ", ".join(result["pruned"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
