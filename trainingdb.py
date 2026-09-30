"""SQLite data layer: connection handling and versioned schema migrations.

This is the repository's only data layer. It is deliberately the smallest
thing that satisfies the requirement for a real schema with real migrations:

  * stdlib sqlite3, so no new dependency and no build step
  * one local file, gitignored, never published
  * migrations are numbered SQL files, applied in order, recorded by checksum

The CSV export remains the published artifact. Nothing in this module writes to
the repository, and the privacy guard in export_publish.py still runs on every
commit, so a mistake here cannot leak a row.

Migration safety: each file is applied inside a transaction together with its
schema_migrations row, and an already-applied file whose contents changed is a
hard error rather than a silent drift. Because a failure rolls the whole
migration back, re-running is always safe.
"""

import hashlib
import os
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "trainloop.db"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# Set in tests to keep databases out of the working tree.
DB_ENV = "TRAINLOOP_DB"


def db_path():
    return Path(os.environ.get(DB_ENV) or DEFAULT_DB)


def connect(path=None):
    path = Path(path) if path else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _checksum(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _applied(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version     INTEGER PRIMARY KEY,
               name        TEXT NOT NULL,
               checksum    TEXT NOT NULL,
               applied_utc TEXT NOT NULL)"""
    )
    return {r["version"]: r for r in conn.execute("SELECT * FROM schema_migrations")}


def pending(conn):
    """Return [(version, name, path)] for migrations not yet applied."""
    done = _applied(conn)
    out = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(path.name.split("_", 1)[0])
        if version not in done:
            out.append((version, path.stem, path))
    return out


def migrate(conn=None, verbose=True):
    """Apply every pending migration, refusing to run against drifted ones.

    Iterates the files on disk rather than the pending list, because the
    checksum check has to run against migrations that are already applied.
    Returns the list of versions applied by this call.
    """
    own = conn is None
    conn = conn or connect()
    done = _applied(conn)
    applied = []

    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(path.name.split("_", 1)[0])
        text = path.read_text(encoding="utf-8")
        digest = _checksum(text)
        if version in done:
            if done[version]["checksum"] != digest:
                raise RuntimeError(
                    "migration %03d (%s) changed after it was applied. "
                    "Add a new migration instead of editing an applied one."
                    % (version, path.stem)
                )
            continue
        # executescript() commits any open transaction first, so the guard row
        # is written inside the same script and committed together with it.
        conn.executescript(
            text + "\nINSERT INTO schema_migrations VALUES (%d, %s, %s, strftime('%%Y-%%m-%%dT%%H:%%M:%%SZ','now'));\n"
            % (version, _sqlstr(path.stem), _sqlstr(digest))
        )
        applied.append(version)
        if verbose:
            print("applied %03d %s" % (version, path.stem))

    if own:
        conn.close()
    return applied


def _sqlstr(value):
    return "'" + str(value).replace("'", "''") + "'"


def status(conn=None):
    own = conn is None
    conn = conn or connect()
    done = _applied(conn)
    todo = pending(conn)
    if own:
        conn.close()
    return {"applied": sorted(done), "pending": [v for v, _, _ in todo]}


def _main(argv):
    path = Path(argv[1]) if len(argv) > 1 else None
    verb = argv[0] if argv else "status"
    if verb == "migrate":
        conn = connect(path)
        applied = migrate(conn)
        conn.close()
        if not applied:
            print("already up to date")
        return 0
    info = status(connect(path) if path else None)
    print("applied: %s" % (info["applied"] or "none"))
    print("pending: %s" % (info["pending"] or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
